import asyncio

import pytest

from aerodrift.config import INTERNET_NODE
from aerodrift.ingestion.collector import AWSCollector, CollectionError
from aerodrift.ingestion.schema import REL_ALLOWS_INGRESS, REL_ATTACHED_TO, CloudState


def test_collect_returns_normalised_state(collector, cloud):
    state = collector.collect_sync()
    assert isinstance(state, CloudState)
    types = {r.resource_type for r in state.resources}
    assert {"internet", "vpc", "subnet", "security_group", "ec2", "rds"} <= types
    names = {r.attributes.get("name") for r in state.resources}
    assert {"prod-vpc", "web-01", "web-02", "app-01", "db-prod-01", "db-sg", "web-sg", "app-sg"} <= names


def test_collect_runs_every_api_concurrently_and_times_them(collector):
    state = collector.collect_sync()
    assert set(state.api_timings_ms) == {f"us-east-1:{op}" for op in (
        "describe_vpcs", "describe_subnets", "describe_security_groups", "describe_instances",
        "describe_db_instances")}
    # gather => wall time is less than the sum of the individual calls
    assert state.total_ms < sum(state.api_timings_ms.values())


def test_collect_is_awaitable(collector):
    state = asyncio.run(collector.collect())
    assert state.resources


def test_security_group_rules_become_relationships(collector, cloud):
    state = collector.collect_sync()
    ingress = {(r.source_id, r.target_id, r.attributes["rule"]) for r in state.relationships
               if r.relation_type == REL_ALLOWS_INGRESS}
    assert (INTERNET_NODE, cloud.ids["sg_web"], "0.0.0.0/0:443/tcp") in ingress
    assert (cloud.ids["sg_app"], cloud.ids["sg_db"], f"{cloud.ids['sg_app']}:5432/tcp") in ingress
    assert ("10.0.0.0/16", cloud.ids["sg_app"], "10.0.0.0/16:22/tcp") in ingress


def test_attachments_cover_ec2_and_rds(collector, cloud):
    state = collector.collect_sync()
    attached = {(r.source_id, r.target_id) for r in state.relationships if r.relation_type == REL_ATTACHED_TO}
    assert ("db-prod-01", cloud.ids["sg_db"]) in attached
    assert (cloud.ids["ec2_app_1"], cloud.ids["sg_app"]) in attached


def test_empty_default_vpc_is_pruned(collector):
    state = collector.collect_sync()
    vpcs = [r for r in state.resources if r.resource_type == "vpc"]
    assert [v.attributes["name"] for v in vpcs] == ["prod-vpc"]


def test_injected_drift_shows_up_in_next_collection(collector, cloud):
    cloud.inject_drift("open-db")
    state = collector.collect_sync()
    assert any(r.source_id == INTERNET_NODE and r.target_id == cloud.ids["sg_db"]
               for r in state.relationships if r.relation_type == REL_ALLOWS_INGRESS)


def test_multi_region_collection(cloud):
    col = AWSCollector(cloud.session, regions=["us-east-1", "eu-west-1"])
    state = col.collect_sync()
    assert state.regions == ["us-east-1", "eu-west-1"]
    assert any(k.startswith("eu-west-1:") for k in state.api_timings_ms)


def test_api_failure_raises_collection_error(cloud):
    col = AWSCollector(cloud.session)

    class Boom:
        def get_paginator(self, _):
            raise RuntimeError("throttled")

    col._clients[("ec2", "us-east-1")] = Boom()
    with pytest.raises(CollectionError, match="throttled"):
        col.collect_sync()
