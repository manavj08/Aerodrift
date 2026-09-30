from aerodrift.remediation.engine import RemediationRecord, remediate, remediate_all


class FakeEC2:
    def __init__(self):
        self.calls = []

    def revoke_security_group_ingress(self, **kw):
        self.calls.append(kw)
        return {"Return": True}


def _drift(**o):
    d = {"drift_id": "d1", "type": "open_ingress", "affected_node": "sg-1",
         "offending_edge": {"rule": "0.0.0.0/0:22/tcp"}}
    d.update(o)
    return d


def test_remediate_success_record():
    rec = remediate(_drift(), FakeEC2())
    assert rec.status == "success" and rec.succeeded and rec.code.startswith("def remediate_d1(ec2):")
    assert rec.executed_at is not None and rec.verified is None


def test_unsupported_is_captured_not_raised():
    rec = remediate(_drift(type="weird"), FakeEC2())
    assert rec.status == "unsupported" and rec.code is None and not rec.succeeded


def test_dry_run_does_not_call():
    ec2 = FakeEC2()
    rec = remediate(_drift(), ec2, dry_run=True)
    assert rec.status == "validated" and ec2.calls == [] and rec.executed_at is None


def test_record_round_trip():
    rec = remediate(_drift(), FakeEC2())
    rec.verified = True
    again = RemediationRecord.from_dict(rec.to_dict())
    assert again.to_dict() == rec.to_dict()


def test_remediate_all():
    ec2 = FakeEC2()
    recs = remediate_all([_drift(), _drift(drift_id="d2", affected_node="sg-2")], ec2)
    assert [c["GroupId"] for c in ec2.calls] == ["sg-1", "sg-2"] and all(r.succeeded for r in recs)
