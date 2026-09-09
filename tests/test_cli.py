"""Tests for aerodrift.cli.main — Week 1 scaffolding."""

from aerodrift.cli.main import main


def test_cli_scan_runs(capsys):
    exit_code = main(["scan"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "scan" in captured.out


def test_cli_status_runs(capsys):
    exit_code = main(["status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "status" in captured.out


def test_cli_requires_command():
    import pytest
    with pytest.raises(SystemExit):
        main([])
