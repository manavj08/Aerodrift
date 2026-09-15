from dataclasses import dataclass, field
from typing import Any


@dataclass
class Resource:
    """A single AWS resource discovered during ingestion."""
    resource_id: str          # e.g. "sg-0123abc"
    resource_type: str        # e.g. "SecurityGroup", "EC2Instance"
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relationship:
    """A directed relationship between two resources."""
    source_id: str
    target_id: str
    relation_type: str        # e.g. "ATTACHED_TO", "ALLOWS_INGRESS"
    attributes: dict[str, Any] = field(default_factory=dict)