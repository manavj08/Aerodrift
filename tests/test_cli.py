"""Tests for aerodrift.cli.main — Week 1 Day 2 CLI expansion."""

import pytest

from aerodrift.cli.main import main


def test_cli_scan_runs(capsys):
    exit_code = main(["scan"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "scan" in captured.out


def test_cli_scan_watch_flag(capsys):
    exit_code = main(["scan", "--watch"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "watch mode" in captured.out


def test_cli_status_runs(capsys):
    exit_code = main(["status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "status" in captured.out


def test_cli_status_json_flag(capsys):
    exit_code = main(["status", "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "JSON" in captured.out


def test_cli_remediate_requires_sg_and_rule(capsys):
    exit_code = main(["remediate"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "required" in captured.err


def test_cli_remediate_with_args(capsys):
    exit_code = main(["remediate", "--sg-id", "sg-123", "--rule", "0.0.0.0/0:22"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "sg-123" in captured.out
    assert "execute" in captured.out


def test_cli_remediate_dry_run(capsys):
    exit_code = main(
        ["remediate", "--sg-id", "sg-123", "--rule", "0.0.0.0/0:22", "--dry-run"]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "dry-run" in captured.out


def test_cli_report_default_output(capsys):
    exit_code = main(["report"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "incident_report.pdf" in captured.out


def test_cli_report_custom_output(capsys):
    exit_code = main(["report", "--output", "custom.pdf"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "custom.pdf" in captured.out


def test_cli_verbose_flag(capsys):
    exit_code = main(["--verbose", "scan"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[verbose]" in captured.out


def test_cli_version_flag():
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_cli_requires_command():
    with pytest.raises(SystemExit):
        main([])


def test_cli_demo_runs_with_drift(capsys):
    exit_code = main(["demo"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "AeroDrift" in captured.out
    assert "db-prod-01" in captured.out


def test_cli_demo_healthy_runs(capsys):
    exit_code = main(["demo", "--healthy"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "AeroDrift" in captured.out
    assert "healthy" in captured.out
