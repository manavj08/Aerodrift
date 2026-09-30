"""PDF incident reports: content, edge cases, escaping."""
from pypdf import PdfReader

from aerodrift.graph.topology import build_mock_graph, detect_drift, diff_topologies
from aerodrift.remediation.engine import remediate
from aerodrift.reports.pdf_report import _wrap_code, generate_incident_report


def _text(path):
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)


def _records(dry_run=True):
    drifts = detect_drift(build_mock_graph())
    return [remediate(d, None, dry_run=dry_run) for d in drifts]


def test_report_basic(tmp_path):
    out = tmp_path / "r.pdf"
    ret = generate_incident_report(str(out), _records())
    assert out.exists() and str(ret) == str(out)
    assert out.read_bytes()[:4] == b"%PDF"
    text = _text(out)
    assert "AeroDrift Incident Report" in text
    assert "sg-db" in text or "db-sg" in text
    assert "revoke_security_group_ingress" in text


def test_report_multiple_records_and_metrics(tmp_path):
    out = tmp_path / "m.pdf"
    recs = _records()
    generate_incident_report(str(out), recs, metrics={"detection_latency_s": 0.84, "time_to_heal_s": 0.06,
                                                      "collect_ms": 38})
    text = _text(out)
    assert len(recs) >= 2
    for r in recs:
        assert r.drift["affected_node"] in text or r.drift.get("affected_name", "") in text


def test_report_accepts_dict_records(tmp_path):
    out = tmp_path / "d.pdf"
    generate_incident_report(str(out), [r.to_dict() for r in _records()])
    assert "revoke_security_group_ingress" in _text(out)


def test_report_empty_records(tmp_path):
    out = tmp_path / "e.pdf"
    generate_incident_report(str(out), [])
    assert out.exists() and _text(out).strip()


def test_report_with_diffs(tmp_path):
    out = tmp_path / "diff.pdf"
    diff = diff_topologies(build_mock_graph(drifted=False), build_mock_graph())
    generate_incident_report(str(out), _records(), diffs=[("Baseline -> drifted", diff)])
    text = _text(out)
    assert "Baseline" in text and "0.0.0.0/0" in text


def test_report_escapes_markup(tmp_path):
    out = tmp_path / "x.pdf"
    recs = [r.to_dict() for r in _records()]
    recs[0]["drift"]["description"] = "<b>bad & <script>ugly</script>"
    generate_incident_report(str(out), recs, environment="env <&>", title="T & <T>")
    assert "T & <T>" in _text(out)


def test_report_creates_parent_dirs(tmp_path):
    out = tmp_path / "a" / "b" / "c.pdf"
    generate_incident_report(str(out), _records())
    assert out.exists()


def test_wrap_code_limits_width():
    long = "return ec2.revoke(" + ", ".join(f"Key{i}='value{i}'" for i in range(30)) + ")"
    wrapped = _wrap_code(long, width=60)
    assert all(len(line) <= 60 for line in wrapped.splitlines())
    assert wrapped.replace("\n", "").replace(" ", "") == long.replace(" ", "")
