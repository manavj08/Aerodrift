"""Tests for aerodrift.cli.dashboard — Week 1 Day 3-4 polish."""

from rich.layout import Layout

from aerodrift.cli.dashboard import (
    build_layout,
    _build_header,
    _build_topology_panel,
    _build_drift_list_panel,
    _build_footer,
    STATUS_HEALTHY,
    STATUS_DRIFTED,
)


def test_build_layout_returns_layout():
    layout = build_layout()
    assert isinstance(layout, Layout)


def test_layout_has_expected_regions():
    layout = build_layout()
    assert layout["header"] is not None
    assert layout["topology"] is not None
    assert layout["drift_list"] is not None
    assert layout["footer"] is not None


def test_build_layout_no_drifts_is_healthy():
    layout = build_layout(drifts=[])
    # Should not raise, and should build the healthy footer path.
    assert layout is not None


def test_build_layout_with_drifts():
    drifts = [
        {"drift_id": "drift-001", "type": "open_ingress", "severity": "critical"}
    ]
    layout = build_layout(drifts=drifts)
    assert layout is not None


def test_header_builds():
    assert _build_header() is not None


def test_topology_panel_no_drift():
    assert _build_topology_panel(drift_count=0) is not None


def test_topology_panel_with_drift():
    assert _build_topology_panel(drift_count=3) is not None


def test_drift_list_panel_empty():
    assert _build_drift_list_panel([]) is not None


def test_drift_list_panel_with_data():
    drifts = [{"type": "open_ingress", "severity": "critical"}]
    assert _build_drift_list_panel(drifts) is not None


def test_footer_healthy():
    assert _build_footer(STATUS_HEALTHY) is not None


def test_footer_drifted():
    assert _build_footer(STATUS_DRIFTED) is not None
