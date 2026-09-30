import pytest

from aerodrift.ingestion.rules import (
    SOURCE_CIDR6,
    SOURCE_GROUP,
    IngressRule,
    RuleParseError,
    rules_from_ip_permissions,
)


@pytest.mark.parametrize("text", ["0.0.0.0/0:22/tcp", "0.0.0.0/0:0-65535/tcp", "0.0.0.0/0:all/all",
                                  "sg-0abc:8080/tcp", "10.0.0.0/16:53/udp", "::/0:443/tcp"])
def test_parse_and_format_round_trip(text):
    assert str(IngressRule.parse(text)) == text


def test_parse_defaults_protocol_to_tcp():
    assert IngressRule.parse("0.0.0.0/0:22") == IngressRule("0.0.0.0/0", "tcp", 22, 22)


def test_parse_detects_source_kinds():
    assert IngressRule.parse("sg-123:80/tcp").source_kind == SOURCE_GROUP
    assert IngressRule.parse("::/0:80/tcp").source_kind == SOURCE_CIDR6


@pytest.mark.parametrize("bad", ["", "nonsense", "0.0.0.0/0:abc/tcp", "0.0.0.0/0:22/xyz",
                                 "not-an-ip:22/tcp", "0.0.0.0/0:70000/tcp", ":22/tcp"])
def test_parse_rejects_bad_rules(bad):
    with pytest.raises(RuleParseError):
        IngressRule.parse(bad)


def test_public_and_port_helpers():
    ssh = IngressRule.parse("0.0.0.0/0:22/tcp")
    assert ssh.is_public and ssh.covers_port(22) and not ssh.covers_port(23) and not ssh.all_ports
    everything = IngressRule.parse("0.0.0.0/0:all/all")
    assert everything.all_ports and everything.covers_port(3389)
    assert IngressRule.parse("0.0.0.0/0:0-65535/tcp").all_ports
    assert not IngressRule.parse("10.0.0.0/8:22/tcp").is_public
    assert IngressRule.parse("::/0:22/tcp").is_public


def test_to_ip_permission_shapes():
    assert IngressRule.parse("0.0.0.0/0:5432/tcp").to_ip_permission() == {
        "IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}
    assert IngressRule.parse("0.0.0.0/0:all/all").to_ip_permission() == {
        "IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}
    assert IngressRule.parse("sg-9:80/tcp").to_ip_permission()["UserIdGroupPairs"] == [{"GroupId": "sg-9"}]
    assert IngressRule.parse("::/0:443/tcp").to_ip_permission()["Ipv6Ranges"] == [{"CidrIpv6": "::/0"}]


def test_flattens_merged_aws_permissions():
    perms = [{"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
              "IpRanges": [{"CidrIp": "0.0.0.0/0"}, {"CidrIp": "10.0.0.0/8"}],
              "Ipv6Ranges": [{"CidrIpv6": "::/0"}],
              "UserIdGroupPairs": [{"GroupId": "sg-app", "UserId": "1"}]},
             {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]
    rules = [str(r) for r in rules_from_ip_permissions(perms)]
    assert rules == ["0.0.0.0/0:5432/tcp", "10.0.0.0/8:5432/tcp", "::/0:5432/tcp", "sg-app:5432/tcp",
                     "0.0.0.0/0:all/all"]


def test_dict_round_trip():
    r = IngressRule.parse("sg-1:8080/tcp")
    assert IngressRule.from_dict(r.to_dict()) == r
    assert r.to_dict()["rule"] == "sg-1:8080/tcp"
