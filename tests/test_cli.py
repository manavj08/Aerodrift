"""End-to-end CLI tests (simulated cloud / offline data only)."""
import json

import pytest
from pypdf import PdfReader

from aerodrift import __version__
from aerodrift.cli.main import build_parser, main


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_parser_requires_command():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_demo_drifted_and_healthy(capsys):
    code, out, _ = run(capsys, "demo")
    assert code == 0 and "DRIFT DETECTED" in out and "db-prod-01" in out
    code, out, _ = run(capsys, "demo", "--healthy")
    assert code == 0 and "no drift detected" in out


def test_scan_offline(capsys):
    code, out, _ = run(capsys, "scan", "--offline")
    assert code == 0 and "public_db_exposure" in out


def test_scan_simulated_clean(capsys):
    code, out, _ = run(capsys, "scan")
    assert code == 0 and "no drift detected" in out and "ingest" in out


def test_scan_simulated_with_scenario(capsys):
    code, out, _ = run(capsys, "scan", "--scenario", "open-db")
    assert code == 0 and "DRIFT DETECTED" in out and "5432" in out


def test_scan_live_rejects_inject(capsys):
    code, _, err = run(capsys, "scan", "--live", "--inject", "open-db")
    assert code == 2 and "--inject" in err


def test_scan_watch_heal_short(capsys):
    code, out, _ = run(capsys, "scan", "--watch", "--heal", "--interval", "0.3", "--duration", "2.5",
                       "--inject", "open-ssh", "--inject-after", "0.5")
    assert code == 0


def test_status_json_offline(capsys):
    code, out, _ = run(capsys, "status", "--offline", "--json")
    data = json.loads(out)
    assert code == 0 and {d["type"] for d in data} >= {"public_db_exposure"}
    assert all(d["affected_node"].startswith("sg-") for d in data)


def test_status_text_scenario(capsys):
    code, out, _ = run(capsys, "status", "--scenario", "open-ssh")
    assert code == 0 and "22" in out


def test_remediate_default_scenarios(capsys):
    code, out, _ = run(capsys, "remediate")
    assert code == 0
    assert "revoke_security_group_ingress" in out and "drift(s) gone" in out


def test_remediate_dry_run(capsys):
    code, out, _ = run(capsys, "remediate", "--dry-run", "--scenario", "open-all-app")
    assert code == 0 and "dry run" in out and "validated" in out


def test_remediate_unknown_drift_id(capsys):
    code, _, err = run(capsys, "remediate", "--drift-id", "nope")
    assert code == 1 and "nope" in err


def test_remediate_no_drift(capsys):
    code, out, _ = run(capsys, "remediate", "--scenario", "shadow-sg")
    assert code == 0


def test_remediate_manual_requires_both(capsys):
    code, _, err = run(capsys, "remediate", "--sg-id", "sg-123")
    assert code == 2 and "--rule" in err


def test_remediate_manual_bad_rule(capsys):
    code, _, err = run(capsys, "remediate", "--sg-id", "sg-123", "--rule", "garbage")
    assert code == 2


def test_remediate_manual_dry_run(capsys):
    code, out, _ = run(capsys, "remediate", "--sg-id", "sg-123", "--rule", "0.0.0.0/0:22/tcp")
    assert code == 0 and "GroupId='sg-123'" in out and "not executed" in out


def test_remediate_live_requires_yes(capsys):
    code, _, err = run(capsys, "remediate", "--live")
    assert code == 2 and "--yes" in err
    code, _, err = run(capsys, "remediate", "--live", "--sg-id", "sg-1", "--rule", "0.0.0.0/0:22/tcp")
    assert code == 2 and "--yes" in err


def test_report_live_requires_yes(capsys, tmp_path):
    code, _, err = run(capsys, "report", "--live", "--output", str(tmp_path / "x.pdf"))
    assert code == 2 and "--yes" in err


def test_report_simulated(capsys, tmp_path):
    out_pdf = tmp_path / "r.pdf"
    code, out, _ = run(capsys, "report", "--output", str(out_pdf))
    assert code == 0 and out_pdf.exists()
    text = "".join(p.extract_text() for p in PdfReader(str(out_pdf)).pages)
    assert "revoke_security_group_ingress" in text


def test_report_no_execute(capsys, tmp_path):
    out_pdf = tmp_path / "n.pdf"
    code, _, _ = run(capsys, "report", "--no-execute", "--output", str(out_pdf))
    assert code == 0 and out_pdf.exists()


def test_daemon_history_diff_and_report_from_db(capsys, tmp_path):
    db = str(tmp_path / "h.db")
    pdf = tmp_path / "d.pdf"
    code, out, _ = run(capsys, "daemon", "--db", db, "--interval", "0.3", "--duration", "3",
                       "--inject", "open-db", "--inject-after", "0.6", "--report", str(pdf))
    assert code == 0 and pdf.exists()

    code, out, _ = run(capsys, "history", "--db", db)
    assert code == 0 and "baseline" in out and "public_db_exposure" in out

    code, out, _ = run(capsys, "diff", "baseline", "latest", "--db", db, "--json")
    assert code == 0
    payload = json.loads(out)
    assert payload["diff"]["newly_exposed"] == []  # healed: no net exposure vs baseline

    code, out, _ = run(capsys, "diff", "baseline", "--db", db)
    assert code == 0

    pdf2 = tmp_path / "from_db.pdf"
    code, out, _ = run(capsys, "report", "--from-db", db, "--output", str(pdf2))
    assert code == 0 and pdf2.exists()


def test_daemon_no_heal_leaves_drift(capsys, tmp_path):
    db = str(tmp_path / "n.db")
    code, out, _ = run(capsys, "daemon", "--db", db, "--no-heal", "--cycles", "2", "--interval", "0.1",
                       "--scenario", "open-ssh")
    assert code == 0


def test_history_empty_db(capsys, tmp_path):
    code, out, _ = run(capsys, "history", "--db", str(tmp_path / "empty.db"))
    assert code == 0 and "No snapshots yet" in out


def test_diff_missing_snapshot(capsys, tmp_path):
    code, _, err = run(capsys, "diff", "baseline", "--db", str(tmp_path / "empty.db"))
    assert code == 1 and err


def test_report_from_empty_db(capsys, tmp_path):
    code, out, _ = run(capsys, "report", "--from-db", str(tmp_path / "e.db"), "--output", str(tmp_path / "e.pdf"))
    assert code == 0 and "No incidents" in out


def test_mid_review_demo(capsys):
    code, out, _ = run(capsys, "mid-review-demo")
    assert code == 0 and "PASS" in out.upper()


def test_self_heal_demo(capsys):
    code, out, _ = run(capsys, "self-heal-demo", "--scenario", "open-db")
    assert code == 0 and "revoke_security_group_ingress" in out


def test_final_demo(capsys, tmp_path):
    pdf = tmp_path / "final.pdf"
    code, out, _ = run(capsys, "final-demo", "--output", str(pdf), "--db", str(tmp_path / "f.db"))
    assert code == 0 and pdf.exists()
