"""Security-group ingress rules: one canonical representation.

AWS returns ingress as ``IpPermissions`` blocks that can mix several
sources (CIDRs, IPv6 CIDRs, other security groups) under a single
protocol/port range. AeroDrift flattens those into one ``IngressRule``
per source, and gives every rule a stable string form used in drift
objects, e.g. ``"0.0.0.0/0:5432/tcp"`` or ``"sg-0abc:8080/tcp"``.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, asdict

from aerodrift.config import PUBLIC_CIDRS

SOURCE_CIDR = "cidr"
SOURCE_CIDR6 = "cidr6"
SOURCE_GROUP = "group"


class RuleParseError(ValueError):
    """Raised when a rule string cannot be parsed."""


@dataclass(frozen=True)
class IngressRule:
    source: str            # CIDR ("0.0.0.0/0") or security group id ("sg-...")
    protocol: str          # "tcp" | "udp" | "icmp" | "-1" (all)
    from_port: int | None  # None when protocol is "-1"
    to_port: int | None
    source_kind: str = SOURCE_CIDR

    # ------------------------------------------------------------------ props
    @property
    def is_public(self) -> bool:
        return self.source_kind in (SOURCE_CIDR, SOURCE_CIDR6) and self.source in PUBLIC_CIDRS

    @property
    def all_ports(self) -> bool:
        if self.protocol == "-1" or self.from_port is None:
            return True
        return self.from_port <= 0 and (self.to_port or 0) >= 65535

    def covers_port(self, port: int) -> bool:
        if self.all_ports:
            return True
        return self.from_port <= port <= self.to_port

    @property
    def port_label(self) -> str:
        if self.protocol == "-1" or self.from_port is None:
            return "all"
        if self.from_port == self.to_port:
            return str(self.from_port)
        return f"{self.from_port}-{self.to_port}"

    @property
    def protocol_label(self) -> str:
        return "all" if self.protocol == "-1" else self.protocol

    def __str__(self) -> str:
        return f"{self.source}:{self.port_label}/{self.protocol_label}"

    # ------------------------------------------------------------ conversions
    def to_ip_permission(self) -> dict:
        """The exact ``IpPermissions`` entry that matches (and revokes) this rule."""
        perm: dict = {"IpProtocol": self.protocol}
        if self.protocol != "-1" and self.from_port is not None:
            perm["FromPort"] = self.from_port
            perm["ToPort"] = self.to_port
        if self.source_kind == SOURCE_CIDR:
            perm["IpRanges"] = [{"CidrIp": self.source}]
        elif self.source_kind == SOURCE_CIDR6:
            perm["Ipv6Ranges"] = [{"CidrIpv6": self.source}]
        else:
            perm["UserIdGroupPairs"] = [{"GroupId": self.source}]
        return perm

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rule"] = str(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "IngressRule":
        return cls(
            source=data["source"],
            protocol=data["protocol"],
            from_port=data.get("from_port"),
            to_port=data.get("to_port"),
            source_kind=data.get("source_kind", SOURCE_CIDR),
        )

    @classmethod
    def parse(cls, text: str) -> "IngressRule":
        """Parse ``"<source>:<ports>/<proto>"`` (proto optional, default tcp).

        Examples: ``0.0.0.0/0:22/tcp``, ``0.0.0.0/0:0-65535/tcp``,
        ``0.0.0.0/0:all/all``, ``sg-0abc:8080``, ``::/0:443/tcp``.
        """
        if not text or not isinstance(text, str):
            raise RuleParseError(f"empty rule: {text!r}")
        head, sep, ports_proto = text.rpartition(":")
        if not sep or not head:
            raise RuleParseError(f"rule must look like '<source>:<port>/<proto>': {text!r}")
        ports, _, proto = ports_proto.partition("/")
        proto = (proto or "tcp").lower()
        if proto in ("all", "-1"):
            proto = "-1"
        elif proto not in ("tcp", "udp", "icmp"):
            raise RuleParseError(f"unknown protocol {proto!r} in {text!r}")

        if proto == "-1" or ports in ("all", "*", ""):
            from_port = to_port = None
            if proto != "-1" and ports in ("all", "*", ""):
                from_port, to_port = 0, 65535
        else:
            try:
                if "-" in ports:
                    a, b = ports.split("-", 1)
                    from_port, to_port = int(a), int(b)
                else:
                    from_port = to_port = int(ports)
            except ValueError as exc:
                raise RuleParseError(f"bad port spec {ports!r} in {text!r}") from exc
            if not (0 <= from_port <= to_port <= 65535) and proto != "icmp":
                raise RuleParseError(f"port range out of bounds in {text!r}")

        if head.startswith("sg-"):
            kind = SOURCE_GROUP
        else:
            try:
                net = ipaddress.ip_network(head, strict=False)
            except ValueError as exc:
                raise RuleParseError(f"bad source {head!r} in {text!r}") from exc
            kind = SOURCE_CIDR6 if net.version == 6 else SOURCE_CIDR
        return cls(head, proto, from_port, to_port, kind)


def rules_from_ip_permissions(permissions: list[dict]) -> list[IngressRule]:
    """Flatten AWS ``IpPermissions`` into one ``IngressRule`` per source."""
    rules: list[IngressRule] = []
    for perm in permissions or []:
        proto = str(perm.get("IpProtocol", "-1")).lower()
        if proto == "all":
            proto = "-1"
        from_port = perm.get("FromPort")
        to_port = perm.get("ToPort")
        if proto == "-1":
            from_port = to_port = None
        for rng in perm.get("IpRanges", []) or []:
            rules.append(IngressRule(rng["CidrIp"], proto, from_port, to_port, SOURCE_CIDR))
        for rng in perm.get("Ipv6Ranges", []) or []:
            rules.append(IngressRule(rng["CidrIpv6"], proto, from_port, to_port, SOURCE_CIDR6))
        for pair in perm.get("UserIdGroupPairs", []) or []:
            if pair.get("GroupId"):
                rules.append(IngressRule(pair["GroupId"], proto, from_port, to_port, SOURCE_GROUP))
    return rules
