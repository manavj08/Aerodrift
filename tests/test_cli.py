"""Tests for aerodrift.cli.main — Week 2 Day 2 CLI expansion."""

import json

import pytest

from aerodrift.cli.main import main


def test_cli_scan_runs(capsys):
    exit_code = main(["scan"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "AeroDrift" in captured.out


def test_cli_scan_watch_flag_notes_not_implemented(capsys):
    exit_code = main(["scan", "--watch"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "not implemented" in captured.out


def test_cli_scan_demo_data_shows_drift(capsys):
    exit_code = main(["scan", "--demo-data"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DRIFTED" in captured.out


def test_cli_scan_real_detection_finds_mock_graph_drift(capsys):
    # Real detect_drift() now finds the mock graph's internet->DB edge.
    exit_code = main(["scan"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DRIFTED" in captured.out


def test_cli_status_runs(capsys):
    exit_code = main(["status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "db-prod-01" in captured.out
    assert "critical" in captured.out


def test_cli_status_demo_data(capsys):
    exit_code = main(["status", "--demo-data"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "critical" in captured.out
    assert "sg-0a1b2c3" in captured.out


def test_cli_status_json_flag(capsys):
    exit_code = main(["status", "--json", "--demo-data"])
    captured = capsys.readouterr()
    assert exit_code == 0
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert data[0]["drift_id"] == "drift-001"


def test_cli_status_json_real_detection(capsys):
    exit_code = main(["status", "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    data = json.loads(captured.out)
    assert len(data) == 1
    assert data[0]["affected_node"] == "db-prod-01"


def test_cli_status_json_empty_with_no_path_graph(monkeypatch, capsys):
    # Force an empty graph to verify the JSON-empty path still works.
    import networkx as nx
    from aerodrift.cli import main as main_module

    monkeypatch.setattr(main_module, "build_mock_graph", lambda: nx.DiGraph())
    exit_code = main(["status", "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == []


def test_cli_remediate_requires_sg_and_rule(capsys):
    exit_code = main(["remediate"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "required" in captured.err


def test_cli_remediate_with_args_executes_in_sandbox(capsys):
    exit_code = main(["remediate", "--sg-id", "sg-123", "--rule", "0.0.0.0/0:22"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "revoke_security_group_ingress" in captured.out
    assert "sg-123" in captured.out
    assert "0.0.0.0/0:22" in captured.out
    assert "Executed in sandbox" in captured.out
    assert "success" in captured.out


def test_cli_remediate_dry_run_does_not_execute(capsys):
    exit_code = main(
        ["remediate", "--sg-id", "sg-123", "--rule", "0.0.0.0/0:22", "--dry-run"]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "dry-run" in captured.out
    assert "revoke_security_group_ingress" in captured.out
    assert "Executed in sandbox" not in captured.out


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


def test_cli_mid_review_demo_runs(capsys):
    exit_code = main(["mid-review-demo"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Step 1/3" in captured.out
    assert "Step 2/3" in captured.out
    assert "Step 3/3" in captured.out
    assert "Detection completed in" in captured.out
    assert "sg-drift-demo" in captured.out


def test_cli_mid_review_demo_shows_new_drift(capsys):
    exit_code = main(["mid-review-demo"])
    captured = capsys.readouterr()
    assert exit_code == 0
    # After the simulated drift, sg-drift-demo should appear as DRIFTED
    # in the final rendered dashboard (it fronts the DB).
    assert "sg-drift-demo" in captured.out
    assert "DRIFTED" in captured.out


def test_cli_self_heal_demo_runs(capsys):
    exit_code = main(["self-heal-demo"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Step 1/4" in captured.out
    assert "Step 2/4" in captured.out
    assert "Step 3/4" in captured.out
    assert "Step 4/4" in captured.out
    assert "Detection completed in" in captured.out


def test_cli_self_heal_demo_generates_and_executes_remediation(capsys):
    exit_code = main(["self-heal-demo"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "revoke_security_group_ingress" in captured.out
    assert "sandbox result: success" in captured.out
    assert "db-prod-01" in captured.out


def test_cli_self_heal_demo_flags_sg_id_mismatch_honestly(capsys):
    # The demo must not silently pretend the DB node is a real SG — it
    # should state the mismatch explicitly.
    exit_code = main(["self-heal-demo"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "not necessarily an actual security group" in captured.out


def test_cli_self_heal_demo_calls_mock_remediation_for_real(capsys):
    from aerodrift.remediation.mock_methods import get_revoked_log, clear_revoked_log

    clear_revoked_log()
    main(["self-heal-demo"])
    log = get_revoked_log()
    assert len(log) == 1
    assert log[0]["sg_id"] == "db-prod-01"
    clear_revoked_log()
