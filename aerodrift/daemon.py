"""The AeroDrift daemon: continuous detect -> heal -> verify loop.

Each cycle:
  1. asynchronously collect cloud state (``AWSCollector``),
  2. rebuild the NetworkX topology,
  3. detect drift against policy + the recorded baseline,
  4. for new drift (when ``auto_heal``), generate AST remediation code,
     run it in the sandbox, then immediately re-collect to *verify* the
     drift is gone,
  5. persist a snapshot whenever the topology changed, and every
     remediation as an incident (when a ``SnapshotStore`` is attached).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import networkx as nx

from aerodrift.graph.topology import TopologyDiff, build_topology, detect_drift, diff_topologies
from aerodrift.ingestion.collector import AWSCollector
from aerodrift.persistence.store import SnapshotStore
from aerodrift.remediation.engine import RemediationRecord, remediate


@dataclass
class CycleResult:
    cycle: int
    started_at: str
    graph: nx.DiGraph
    drifts: list[dict]
    new_drifts: list[dict] = field(default_factory=list)
    resolved_drift_ids: list[str] = field(default_factory=list)
    diff: TopologyDiff | None = None
    records: list[RemediationRecord] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    snapshot_id: int | None = None
    detected_monotonic: float | None = None
    healed_graph: nx.DiGraph | None = None
    healed_drifts: list[dict] | None = None

    @property
    def final_graph(self) -> nx.DiGraph:
        return self.healed_graph if self.healed_graph is not None else self.graph

    @property
    def final_drifts(self) -> list[dict]:
        return self.healed_drifts if self.healed_drifts is not None else self.drifts


class AeroDriftDaemon:
    def __init__(self, collector: AWSCollector, *, store: SnapshotStore | None = None,
                 interval: float = 2.0, auto_heal: bool = True, dry_run: bool = False,
                 remediation_client=None, on_cycle: Callable[[CycleResult], None] | None = None,
                 max_attempts: int = 2):
        self.collector = collector
        self.store = store
        self.interval = interval
        self.auto_heal = auto_heal
        self.dry_run = dry_run
        self.remediation_client = remediation_client or collector.client("ec2")
        self.on_cycle = on_cycle
        self.max_attempts = max_attempts

        self.baseline: nx.DiGraph | None = None
        self.baseline_snapshot_id: int | None = None
        self.previous: nx.DiGraph | None = None
        self.cycle = 0
        self.active: dict[str, dict] = {}
        self.first_seen: dict[str, float] = {}
        self.attempts: dict[str, int] = {}
        self.records: list[RemediationRecord] = []
        self.history: list[CycleResult] = []

    # ---------------------------------------------------------------- setup
    async def _snapshot(self) -> tuple[nx.DiGraph, dict]:
        t0 = time.perf_counter()
        state = await self.collector.collect()
        t1 = time.perf_counter()
        graph = build_topology(state)
        t2 = time.perf_counter()
        return graph, {"collect_ms": round((t1 - t0) * 1000, 2), "build_ms": round((t2 - t1) * 1000, 2)}

    async def establish_baseline(self, graph: nx.DiGraph | None = None) -> nx.DiGraph:
        """Adopt the current (or given) topology as the secure baseline.

        If the store already has a baseline it is reused, so drift is
        judged against the same reference across daemon restarts.
        """
        if graph is None and self.store is not None:
            snap = self.store.get_baseline()
            if snap is not None:
                self.baseline, self.baseline_snapshot_id = snap.graph, snap.id
                return self.baseline
        if graph is None:
            graph, _ = await self._snapshot()
        self.baseline = graph
        if self.store is not None:
            self.baseline_snapshot_id = self.store.save_snapshot(
                graph, detect_drift(graph), label="baseline", baseline=True)
        return graph

    # ---------------------------------------------------------------- cycle
    async def run_cycle(self) -> CycleResult:
        self.cycle += 1
        started = datetime.now(timezone.utc).isoformat()
        c0 = time.perf_counter()
        graph, timings = await self._snapshot()
        d0 = time.perf_counter()
        drifts = detect_drift(graph, baseline=self.baseline)
        timings["detect_ms"] = round((time.perf_counter() - d0) * 1000, 3)
        detected_at = time.monotonic()

        current = {d["drift_id"]: d for d in drifts}
        new = [d for i, d in current.items() if i not in self.active]
        resolved = [i for i in self.active if i not in current]
        for d in new:
            self.first_seen.setdefault(d["drift_id"], detected_at)
        self.active = current

        diff = diff_topologies(self.previous, graph) if self.previous is not None else None
        result = CycleResult(self.cycle, started, graph, drifts, new, resolved, diff,
                             timings_ms=timings, detected_monotonic=detected_at)

        if self.store is not None and (diff is None or not diff.is_empty):
            result.snapshot_id = self.store.save_snapshot(graph, drifts, label=f"cycle-{self.cycle}")

        to_heal = [d for d in drifts if self.attempts.get(d["drift_id"], 0) < self.max_attempts]
        if self.auto_heal and to_heal:
            h0 = time.perf_counter()
            for drift in to_heal:
                self.attempts[drift["drift_id"]] = self.attempts.get(drift["drift_id"], 0) + 1
                record = await asyncio.to_thread(remediate, drift, self.remediation_client, dry_run=self.dry_run)
                result.records.append(record)
            timings["heal_ms"] = round((time.perf_counter() - h0) * 1000, 2)

            if not self.dry_run:
                v0 = time.perf_counter()
                healed_graph, _ = await self._snapshot()
                healed_drifts = detect_drift(healed_graph, baseline=self.baseline)
                timings["verify_ms"] = round((time.perf_counter() - v0) * 1000, 2)
                still = {d["drift_id"] for d in healed_drifts}
                done = time.monotonic()
                for record in result.records:
                    did = record.drift["drift_id"]
                    record.verified = did not in still and record.succeeded
                    if record.verified:
                        record.time_to_heal_s = round(done - self.first_seen.get(did, detected_at), 3)
                        self.active.pop(did, None)
                result.healed_graph, result.healed_drifts = healed_graph, healed_drifts
                graph = healed_graph

            if self.store is not None:
                after_id = None
                if result.healed_graph is not None:
                    after_id = self.store.save_snapshot(result.healed_graph, result.healed_drifts,
                                                        label=f"cycle-{self.cycle}-healed")
                for record in result.records:
                    self.store.record_incident(record, snapshot_before=result.snapshot_id,
                                               snapshot_after=after_id)

        self.records.extend(result.records)
        timings["cycle_ms"] = round((time.perf_counter() - c0) * 1000, 2)
        self.previous = graph
        self.history.append(result)
        if self.on_cycle is not None:
            self.on_cycle(result)
        return result

    # ------------------------------------------------------------------ loop
    async def run(self, *, max_cycles: int | None = None, duration: float | None = None,
                  stop_event: asyncio.Event | None = None) -> list[CycleResult]:
        if self.baseline is None:
            await self.establish_baseline()
        deadline = time.monotonic() + duration if duration else None
        while True:
            start = time.monotonic()
            await self.run_cycle()
            if max_cycles is not None and self.cycle >= max_cycles:
                break
            if deadline is not None and time.monotonic() >= deadline:
                break
            if stop_event is not None and stop_event.is_set():
                break
            delay = max(0.0, self.interval - (time.monotonic() - start))
            if stop_event is not None:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                    break
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(delay)
        return self.history
