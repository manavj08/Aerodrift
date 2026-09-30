import pytest

from aerodrift.graph.topology import build_mock_graph, detect_drift
from aerodrift.persistence.store import SnapshotNotFound, SnapshotStore
from aerodrift.remediation.engine import RemediationRecord


@pytest.fixture
def store(tmp_path):
    s = SnapshotStore(tmp_path / "h.db")
    yield s
    s.close()


def _seed(store):
    healthy, drifted = build_mock_graph(False), build_mock_graph(True)
    a = store.save_snapshot(healthy, [], label="base", baseline=True, taken_at="2026-09-30T10:00:00Z")
    b = store.save_snapshot(drifted, detect_drift(drifted), taken_at="2026-09-30T10:05:00Z")
    c = store.save_snapshot(healthy, [], taken_at="2026-09-30T10:06:00Z")
    return a, b, c


def test_save_and_list(store):
    a, b, c = _seed(store)
    snaps = store.list_snapshots()
    assert [s.id for s in snaps] == [c, b, a]
    assert snaps[1].drift_count == 2 and snaps[2].is_baseline


def test_resolve_references(store):
    a, b, c = _seed(store)
    assert store.resolve(a) == a and store.resolve(str(b)) == b
    assert store.resolve("latest") == c and store.resolve("baseline") == a
    assert store.resolve("2026-09-30T10:05:30Z") == b          # latest at-or-before
    assert store.resolve("2026-09-30T12:05:30+02:00") == b      # timezone-aware
    assert store.resolve("2026-09-30T10:05:00") == b            # naive => UTC
    with pytest.raises(SnapshotNotFound):
        store.resolve("2026-09-30T09:00:00Z")
    with pytest.raises(SnapshotNotFound):
        store.resolve(999)
    with pytest.raises(ValueError):
        store.resolve("yesterday-ish")


def test_loaded_snapshot_round_trips_graph_and_drift(store):
    _, b, _ = _seed(store)
    snap = store.get_snapshot(b)
    assert detect_drift(snap.graph)[0]["drift_id"] == snap.drifts[0]["drift_id"]


def test_diff_between_timestamps(store):
    _seed(store)
    a, b, diff = store.diff("2026-09-30T10:01:00Z", "2026-09-30T10:05:00Z")
    assert diff.newly_exposed == ["db-prod-01"] and len(diff.added_rules) == 2
    _, _, healed = store.diff("baseline", "latest")
    assert healed.is_empty


def test_baseline_management(store):
    a, b, c = _seed(store)
    store.set_baseline(c)
    assert store.get_baseline().id == c
    store.clear_baseline()
    assert store.get_baseline() is None


def test_incidents(store):
    _, b, c = _seed(store)
    d = detect_drift(build_mock_graph())[0]
    rec = RemediationRecord(d, "def remediate_x(ec2): ...", {"status": "success"})
    iid = store.record_incident(rec, snapshot_before=b)
    rec.verified = True
    store.update_incident(iid, verified=True, snapshot_after=c, record=rec)
    (row,) = store.list_incidents()
    assert row["incident_id"] == iid and row["verified"] is True
    assert row["snapshot_before"] == b and row["snapshot_after"] == c
    assert row["drift"]["drift_id"] == d["drift_id"] and row["status"] == "success"


def test_persists_across_connections(tmp_path):
    path = tmp_path / "p.db"
    with SnapshotStore(path) as s:
        sid = s.save_snapshot(build_mock_graph(), label="x")
    with SnapshotStore(path) as s:
        assert s.get_snapshot("latest").id == sid
