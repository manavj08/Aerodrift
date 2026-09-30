import pytest

from aerodrift.ingestion.simulated_cloud import SimulatedCloud


def test_seeds_expected_estate(cloud):
    assert {"vpc", "sg_web", "sg_app", "sg_db", "ec2_web_1", "ec2_web_2", "ec2_app_1", "rds_db"} <= cloud.ids.keys()
    assert sorted(cloud.ingress_rules(cloud.ids["sg_web"])) == ["0.0.0.0/0:443/tcp", "0.0.0.0/0:80/tcp"]


@pytest.mark.parametrize("scenario", SimulatedCloud.SCENARIOS)
def test_each_scenario_applies_its_rule(cloud, scenario):
    inj = cloud.inject_drift(scenario)
    assert inj.rule in cloud.ingress_rules(inj.group_id)
    assert cloud.injections == [inj]


def test_unknown_scenario(cloud):
    with pytest.raises(ValueError):
        cloud.inject_drift("delete-everything")


def test_each_cloud_is_isolated():
    with SimulatedCloud() as a:
        a.inject_drift("open-db")
        first = a.ids["sg_db"]
    with SimulatedCloud() as b:
        assert b.ids["sg_db"] != first
        assert "0.0.0.0/0:5432/tcp" not in b.ingress_rules(b.ids["sg_db"])
