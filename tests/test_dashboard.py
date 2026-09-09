"""Tests for aerodrift.cli.dashboard — Week 1 layout shell."""

from rich.layout import Layout

from aerodrift.cli.dashboard import build_layout


def test_build_layout_returns_layout():
    layout = build_layout()
    assert isinstance(layout, Layout)


def test_layout_has_expected_regions():
    layout = build_layout()
    # Accessing these should not raise if the regions exist.
    assert layout["header"] is not None
    assert layout["topology"] is not None
    assert layout["drift_list"] is not None
    assert layout["footer"] is not None
