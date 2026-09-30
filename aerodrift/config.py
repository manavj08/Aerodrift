"""Shared constants and policy knobs for AeroDrift.

Everything that encodes a *policy decision* (what counts as sensitive,
which ports are administrative, how severe each drift type is) lives here
so it is decided in exactly one place.
"""

# The synthetic node every internet-originating path starts from.
INTERNET_NODE = "0.0.0.0/0"

# CIDRs that mean "the whole internet".
PUBLIC_CIDRS = frozenset({"0.0.0.0/0", "::/0"})

# Canonical resource types used by the topology engine.
TYPE_INTERNET = "internet"
TYPE_VPC = "vpc"
TYPE_SUBNET = "subnet"
TYPE_SECURITY_GROUP = "security_group"
TYPE_EC2 = "ec2"
TYPE_RDS = "rds"

# Aliases seen from different producers, normalised to the canonical names.
TYPE_ALIASES = {
    "internet": TYPE_INTERNET,
    "vpc": TYPE_VPC,
    "subnet": TYPE_SUBNET,
    "security_group": TYPE_SECURITY_GROUP,
    "securitygroup": TYPE_SECURITY_GROUP,
    "sg": TYPE_SECURITY_GROUP,
    "ec2": TYPE_EC2,
    "ec2instance": TYPE_EC2,
    "instance": TYPE_EC2,
    "rds": TYPE_RDS,
    "database": TYPE_RDS,
    "dbinstance": TYPE_RDS,
}

# Resource types that must never be reachable straight from the internet.
SENSITIVE_RESOURCE_TYPES = frozenset({TYPE_RDS})

# Tags that mark any resource as sensitive (e.g. an EC2 running a datastore).
SENSITIVE_TAG_KEY = "aerodrift:sensitive"
SENSITIVE_TIER_VALUES = frozenset({"data", "database", "private"})

# Ports that should never be open to the whole internet.
ADMIN_PORTS = frozenset({22, 3389, 5985, 5986})

# Drift types.
DRIFT_PUBLIC_DB = "public_db_exposure"
DRIFT_OPEN_INGRESS = "open_ingress"
DRIFT_INDIRECT = "indirect_exposure"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def normalize_type(resource_type: str | None) -> str:
    """Map any known spelling of a resource type to its canonical name."""
    if not resource_type:
        return "unknown"
    key = str(resource_type).replace("-", "").replace(" ", "").lower()
    return TYPE_ALIASES.get(key, TYPE_ALIASES.get(key.replace("_", ""), str(resource_type).lower()))
