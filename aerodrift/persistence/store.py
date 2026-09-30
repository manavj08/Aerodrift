"""SQLite persistence for topology history and remediation incidents.

Every snapshot stores the full serialised graph plus the drift found in
it, so any two points in time can be diffed later::

    store = SnapshotStore("aerodrift.db")
    store.diff("2026-09-30T10:00:00", "latest")

Snapshot references accepted everywhere: an integer id, ``"latest"``,
``"baseline"``, or an ISO-8601 timestamp (resolved to the most recent
snapshot taken at or before that moment).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from aerodrift.graph.topology import TopologyDiff, diff_topologies, graph_from_dict, graph_to_dict

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    taken_at     TEXT    NOT NULL,
    label        TEXT,
    is_baseline  INTEGER NOT NULL DEFAULT 0,
    node_count   INTEGER NOT NULL,
    edge_count   INTEGER NOT NULL,
    drift_count  INTEGER NOT NULL,
    graph_json   TEXT    NOT NULL,
    drifts_json  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_snapshots_taken_at ON snapshots(taken_at);
CREATE TABLE IF NOT EXISTS incidents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    drift_id        TEXT NOT NULL,
    drift_type      TEXT NOT NULL,
    severity        TEXT,
    affected_node   TEXT,
    target_resource TEXT,
    detected_at     TEXT,
    executed_at     TEXT,
    status          TEXT NOT NULL,
    verified        INTEGER,
    code            TEXT,
    record_json     TEXT NOT NULL,
    snapshot_before INTEGER REFERENCES snapshots(id),
    snapshot_after  INTEGER REFERENCES snapshots(id)
);
"""


class SnapshotNotFound(LookupError):
    pass


@dataclass
class Snapshot:
    id: int
    taken_at: str
    label: str | None
    is_baseline: bool
    node_count: int
    edge_count: int
    drift_count: int
    graph: nx.DiGraph | None = None
    drifts: list | None = None


def _utc_iso(value: str | datetime | None = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            value = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"not an ISO-8601 timestamp: {value!r}") from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


class SnapshotStore:
    def __init__(self, path: str | Path = "aerodrift.db"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------------------------------------------------------- snapshots
    def save_snapshot(self, graph: nx.DiGraph, drifts: list | None = None, *, label: str | None = None,
                      baseline: bool = False, taken_at: str | datetime | None = None) -> int:
        drifts = drifts or []
        with self._lock, self._conn:
            if baseline:
                self._conn.execute("UPDATE snapshots SET is_baseline = 0")
            cur = self._conn.execute(
                "INSERT INTO snapshots (taken_at, label, is_baseline, node_count, edge_count, "
                "drift_count, graph_json, drifts_json) VALUES (?,?,?,?,?,?,?,?)",
                (_utc_iso(taken_at), label, int(baseline), graph.number_of_nodes(),
                 graph.number_of_edges(), len(drifts),
                 json.dumps(graph_to_dict(graph), default=str), json.dumps(drifts, default=str)))
            return cur.lastrowid

    def set_baseline(self, ref) -> int:
        snap_id = self.resolve(ref)
        with self._lock, self._conn:
            self._conn.execute("UPDATE snapshots SET is_baseline = 0")
            self._conn.execute("UPDATE snapshots SET is_baseline = 1 WHERE id = ?", (snap_id,))
        return snap_id

    def clear_baseline(self) -> None:
        """Forget the baseline flag (snapshots are kept)."""
        with self._lock, self._conn:
            self._conn.execute("UPDATE snapshots SET is_baseline = 0")

    def _row_to_snapshot(self, row, load: bool) -> Snapshot:
        snap = Snapshot(row["id"], row["taken_at"], row["label"], bool(row["is_baseline"]),
                        row["node_count"], row["edge_count"], row["drift_count"])
        if load:
            snap.graph = graph_from_dict(json.loads(row["graph_json"]))
            snap.drifts = json.loads(row["drifts_json"])
        return snap

    def resolve(self, ref) -> int:
        """Resolve id / 'latest' / 'baseline' / ISO timestamp to a snapshot id."""
        with self._lock, closing(self._conn.cursor()) as cur:
            if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
                row = cur.execute("SELECT id FROM snapshots WHERE id = ?", (int(ref),)).fetchone()
            elif ref in (None, "latest"):
                row = cur.execute("SELECT id FROM snapshots ORDER BY taken_at DESC, id DESC LIMIT 1").fetchone()
            elif ref == "baseline":
                row = cur.execute("SELECT id FROM snapshots WHERE is_baseline = 1 LIMIT 1").fetchone()
            else:
                ts = _utc_iso(ref)
                row = cur.execute("SELECT id FROM snapshots WHERE taken_at <= ? "
                                  "ORDER BY taken_at DESC, id DESC LIMIT 1", (ts,)).fetchone()
        if row is None:
            raise SnapshotNotFound(f"no snapshot matches {ref!r}")
        return row["id"]

    def get_snapshot(self, ref, load: bool = True) -> Snapshot:
        snap_id = self.resolve(ref)
        with self._lock:
            row = self._conn.execute("SELECT * FROM snapshots WHERE id = ?", (snap_id,)).fetchone()
        return self._row_to_snapshot(row, load)

    def get_baseline(self) -> Snapshot | None:
        try:
            return self.get_snapshot("baseline")
        except SnapshotNotFound:
            return None

    def list_snapshots(self, limit: int = 50) -> list[Snapshot]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, taken_at, label, is_baseline, node_count, edge_count, drift_count "
                "FROM snapshots ORDER BY taken_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_snapshot(r, load=False) for r in rows]

    def diff(self, ref_a, ref_b) -> tuple[Snapshot, Snapshot, TopologyDiff]:
        a, b = self.get_snapshot(ref_a), self.get_snapshot(ref_b)
        return a, b, diff_topologies(a.graph, b.graph)

    # ---------------------------------------------------------- incidents
    def record_incident(self, record, snapshot_before: int | None = None,
                        snapshot_after: int | None = None) -> int:
        data = record.to_dict() if hasattr(record, "to_dict") else dict(record)
        drift = data.get("drift", {})
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO incidents (drift_id, drift_type, severity, affected_node, target_resource, "
                "detected_at, executed_at, status, verified, code, record_json, snapshot_before, "
                "snapshot_after) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (drift.get("drift_id", "?"), drift.get("type", "?"), drift.get("severity"),
                 drift.get("affected_node"), drift.get("target_resource"), drift.get("detected_at"),
                 data.get("executed_at"), data.get("status") or data.get("result", {}).get("status", "unknown"),
                 None if data.get("verified") is None else int(bool(data.get("verified"))),
                 data.get("code"), json.dumps(data, default=str), snapshot_before, snapshot_after))
            return cur.lastrowid

    def update_incident(self, incident_id: int, *, verified: bool | None = None,
                        snapshot_after: int | None = None, record=None) -> None:
        sets, args = [], []
        if verified is not None:
            sets.append("verified = ?"); args.append(int(verified))
        if snapshot_after is not None:
            sets.append("snapshot_after = ?"); args.append(snapshot_after)
        if record is not None:
            sets.append("record_json = ?"); args.append(json.dumps(record.to_dict(), default=str))
        if not sets:
            return
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE incidents SET {', '.join(sets)} WHERE id = ?", (*args, incident_id))

    def list_incidents(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            rec = json.loads(r["record_json"])
            rec["incident_id"] = r["id"]
            rec["verified"] = None if r["verified"] is None else bool(r["verified"])
            rec["snapshot_before"] = r["snapshot_before"]
            rec["snapshot_after"] = r["snapshot_after"]
            out.append(rec)
        return out
