"""Environment setup and the scripted drift -> detect -> heal scenario.

Shared by the CLI commands and tests so the orchestration logic lives in
one place and is independent of argparse/Rich.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import boto3

from aerodrift.daemon import AeroDriftDaemon, CycleResult
from aerodrift.graph.topology import diff_topologies
from aerodrift.ingestion.collector import AWSCollector
from aerodrift.ingestion.simulated_cloud import DriftInjection, SimulatedCloud
from aerodrift.persistence.store import SnapshotStore

DEFAULT_REGION = "us-east-1"


@dataclass
class Environment:
    collector: AWSCollector
    live: bool
    cloud: SimulatedCloud | None = None
    injections: list[DriftInjection] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.live:
            return f"live AWS ({', '.join(self.collector.regions)})"
        return "simulated AWS (moto)"

    @property
    def ec2(self):
        return self.collector.client("ec2")


@contextmanager
def open_environment(*, live: bool = False, region: str | None = None, regions: list[str] | None = None,
                     scenarios: list[str] | None = None, profile: str | None = None):
    """Yield an ``Environment``: real AWS (``live``) or a seeded moto sandbox."""
    if live:
        session = boto3.session.Session(profile_name=profile, region_name=region)
        yield Environment(AWSCollector(session, regions=regions or [region or session.region_name or DEFAULT_REGION]),
                          live=True)
        return
    with SimulatedCloud(region=region or DEFAULT_REGION) as cloud:
        env = Environment(AWSCollector(cloud.session, regions=[cloud.region]), live=False, cloud=cloud)
        for scenario in scenarios or []:
            env.injections.append(cloud.inject_drift(scenario))
        yield env


@dataclass
class ScenarioOutcome:
    baseline: object
    drifted: CycleResult | None
    injections: list[DriftInjection]
    detection_latency_s: float | None
    daemon: AeroDriftDaemon
    healed_graph: object = None
    healed_drifts: list | None = None

    @property
    def records(self):
        return self.drifted.records if self.drifted else []

    @property
    def diffs(self):
        out = []
        if self.drifted is not None:
            out.append(("Baseline -> drifted", diff_topologies(self.baseline, self.drifted.graph)))
            if self.healed_graph is not None:
                out.append(("Drifted -> healed", diff_topologies(self.drifted.graph, self.healed_graph)))
        return out

    def metrics(self) -> dict:
        m = {"detection_latency_s": self.detection_latency_s}
        if self.drifted is not None:
            m.update(collect_ms=self.drifted.timings_ms.get("collect_ms"),
                     detect_ms=self.drifted.timings_ms.get("detect_ms"),
                     nodes=self.drifted.graph.number_of_nodes(), edges=self.drifted.graph.number_of_edges())
            heals = [r.time_to_heal_s for r in self.drifted.records if r.time_to_heal_s is not None]
            if heals:
                m["time_to_heal_s"] = max(heals)
        return m


def run_drift_scenario(scenarios: list[str], *, heal: bool = True, interval: float = 1.0,
                       inject_after: float = 1.0, timeout: float = 15.0, store: SnapshotStore | None = None,
                       on_cycle=None, on_inject=None, region: str | None = None) -> ScenarioOutcome:
    """Run the daemon against a fresh simulated cloud, inject drift while it
    is polling, and measure how long detection (and healing) takes.

    Detection latency is wall-clock time from the moment the drift API call
    returned to the moment the daemon's graph query flagged it — i.e. it
    includes waiting for the next poll, exactly like production.
    """
    with open_environment(region=region) as env:
        daemon = AeroDriftDaemon(env.collector, store=store, interval=interval, auto_heal=heal, on_cycle=on_cycle)

        async def main():
            baseline = await daemon.establish_baseline()
            stop = asyncio.Event()
            found: dict = {}

            def watch(result: CycleResult):
                if on_cycle:
                    on_cycle(result)
                if env.injections and result.new_drifts and "cycle" not in found:
                    found["cycle"] = result
                    stop.set()

            daemon.on_cycle = watch

            async def chaos():
                await asyncio.sleep(inject_after)
                for sc in scenarios:
                    inj = await asyncio.to_thread(env.cloud.inject_drift, sc)
                    env.injections.append(inj)
                    if on_inject:
                        on_inject(inj)

            chaos_task = asyncio.create_task(chaos())
            try:
                await asyncio.wait_for(daemon.run(stop_event=stop), timeout=timeout)
            except asyncio.TimeoutError:
                pass
            await chaos_task
            return baseline, found.get("cycle")

        baseline, cycle = asyncio.run(main())
        latency = None
        if cycle is not None and env.injections:
            latency = round(cycle.detected_monotonic - min(i.injected_at for i in env.injections), 3)
        return ScenarioOutcome(baseline, cycle, list(env.injections), latency, daemon,
                               healed_graph=cycle.healed_graph if cycle else None,
                               healed_drifts=cycle.healed_drifts if cycle else None)


def one_shot_scan(env: Environment, baseline=None):
    """Collect once and return (state, graph, drifts)."""
    from aerodrift.graph.topology import build_topology, detect_drift
    state = env.collector.collect_sync()
    graph = build_topology(state)
    return state, graph, detect_drift(graph, baseline=baseline)


def elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
