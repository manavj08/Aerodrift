import json
import sqlite3
from datetime import datetime, timezone

import networkx as nx

DB_PATH = "snapshots.db"


def _connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            taken_at TEXT NOT NULL,
            graph_json TEXT NOT NULL
        )
        """
    )
    return conn


def save_snapshot(graph: nx.DiGraph, db_path: str = DB_PATH) -> int:
    """Stores the graph as JSON with a UTC timestamp. Returns the snapshot id."""
    data = nx.node_link_data(graph, edges="edges")
    taken_at = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO snapshots (taken_at, graph_json) VALUES (?, ?)",
            (taken_at, json.dumps(data)),
        )
        return cur.lastrowid


def load_snapshot(snapshot_id: int, db_path: str = DB_PATH) -> nx.DiGraph:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT graph_json FROM snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"No snapshot with id {snapshot_id}")
    return nx.node_link_graph(json.loads(row[0]), edges="edges")


def list_snapshots(db_path: str = DB_PATH) -> list[tuple[int, str]]:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT id, taken_at FROM snapshots ORDER BY id"
        ).fetchall()


def diff_snapshots(old_id: int, new_id: int, db_path: str = DB_PATH) -> dict:
    """Compares two snapshots and reports added, removed and changed resources."""
    old = load_snapshot(old_id, db_path)
    new = load_snapshot(new_id, db_path)

    old_nodes = dict(old.nodes(data=True))
    new_nodes = dict(new.nodes(data=True))

    added = [n for n in new_nodes if n not in old_nodes]
    removed = [n for n in old_nodes if n not in new_nodes]
    changed = {
        n: {"old": old_nodes[n], "new": new_nodes[n]}
        for n in old_nodes
        if n in new_nodes and old_nodes[n] != new_nodes[n]
    }
    return {"added": added, "removed": removed, "changed": changed}