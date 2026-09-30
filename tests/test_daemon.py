import asyncio

from aerodrift.daemon import AeroDriftDaemon
from aerodrift.persistence.store import SnapshotStore
from aerodrift.runtime import run_drift_scenario


def test_healthy_cycle_has_no_drift(collector):
    d = AeroDriftDaemon(collector, auto_heal=True)
    asyncio.run(d.establish_baseline())
    r = asyncio.run(d.run_cycle())
    assert r.drifts == [] and r.records == [] and {"collect_ms", "build_ms", "detect_ms"} <= r.timings_ms.keys()


def test_detects_heals_and_verifies(collector, cloud):
    d = AeroDriftDaemon(collector, auto_heal=True)

    async def go():
        await d.establish_baseline()
        await d.run_cycle()
        cloud.inject_drift("open-db")
        cloud.inject_drift("open-all-app")
        return await d.run_cycle(), await d.run_cycle()

    drifted, after = asyncio.run(go())
    assert {x["type"] for x in drifted.new_drifts} == {"public_db_exposure", "indirect_exposure"}
    assert all(r.status == "success" and r.verified for r in drifted.records)
    assert drifted.healed_drifts == [] and after.drifts == []
    assert "0.0.0.0/0:5432/tcp" not in cloud.ingress_rules(cloud.ids["sg_db"])
    assert "0.0.0.0/0:all/all" not in cloud.ingress_rules(cloud.ids["sg_app"])
    assert after.diff is not None and after.diff.is_empty


def test_detect_only_mode_changes_nothing(collector, cloud):
    d = AeroDriftDaemon(collector, auto_heal=False)

    async def go():
        await d.establish_baseline()
        cloud.inject_drift("open-db")
        return await d.run_cycle(), await d.run_cycle()

    first, second = asyncio.run(go())
    assert len(first.new_drifts) == 1 and first.records == []
    assert second.new_drifts == [] and len(second.drifts) == 1  # still active, not re-announced
    assert "0.0.0.0/0:5432/tcp" in cloud.ingress_rules(cloud.ids["sg_db"])


def test_persists_snapshots_and_incidents(collector, cloud, tmp_path):
    with SnapshotStore(tmp_path / "d.db") as store:
        d = AeroDriftDaemon(collector, store=store)

        async def go():
            await d.establish_baseline()
            await d.run_cycle()          # first cycle: stored
            await d.run_cycle()          # unchanged: not stored
            cloud.inject_drift("open-ssh")
            await d.run_cycle()          # drifted + healed: stored twice

        asyncio.run(go())
        labels = [s.label for s in store.list_snapshots()]
        assert labels == ["cycle-3-healed", "cycle-3", "cycle-1", "baseline"]
        (inc,) = store.list_incidents()
        assert inc["drift"]["type"] == "indirect_exposure" and inc["verified"] is True
        assert store.diff("baseline", "latest")[2].is_empty


def test_restart_reuses_stored_baseline(collector, cloud, tmp_path):
    with SnapshotStore(tmp_path / "b.db") as store:
        first = AeroDriftDaemon(collector, store=store)
        asyncio.run(first.establish_baseline())
        cloud.inject_drift("open-all-app")
        second = AeroDriftDaemon(collector, store=store, auto_heal=False)
        asyncio.run(second.establish_baseline())
        assert second.baseline_snapshot_id == first.baseline_snapshot_id
        r = asyncio.run(second.run_cycle())
        assert [x["type"] for x in r.drifts] == ["indirect_exposure"]


def test_gives_up_after_max_attempts(collector, cloud):
    class Broken:
        def revoke_security_group_ingress(self, **kw):
            raise RuntimeError("API down")

    d = AeroDriftDaemon(collector, remediation_client=Broken(), max_attempts=2)

    async def go():
        await d.establish_baseline()
        cloud.inject_drift("open-db")
        return [await d.run_cycle() for _ in range(3)]

    results = asyncio.run(go())
    assert [len(r.records) for r in results] == [1, 1, 0]
    assert all(rec.status == "failed" and rec.verified is False for r in results for rec in r.records)


def test_run_loop_respects_max_cycles(collector):
    d = AeroDriftDaemon(collector, interval=0.01)
    history = asyncio.run(d.run(max_cycles=3))
    assert len(history) == 3 and d.baseline is not None


def test_scenario_detects_well_under_five_seconds():
    outcome = run_drift_scenario(["open-db"], heal=True, interval=0.5, inject_after=0.3)
    assert outcome.drifted is not None
    assert outcome.detection_latency_s < 5.0
    assert all(r.verified for r in outcome.records)
    assert outcome.healed_drifts == []
    titles = [t for t, _ in outcome.diffs]
    assert titles == ["Baseline -> drifted", "Drifted -> healed"]
    assert outcome.metrics()["time_to_heal_s"] is not None
