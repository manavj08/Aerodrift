"""Ingestion output schema.

``Resource`` / ``Relationship`` are the normalised records every
ingestion source produces; ``CloudState`` bundles one full poll.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Relationship types
REL_CONTAINS = "CONTAINS"            # vpc -> subnet, subnet -> ec2/rds
REL_ATTACHED_TO = "ATTACHED_TO"      # ec2/rds -> security group protecting it
REL_ALLOWS_INGRESS = "ALLOWS_INGRESS"  # source (internet / cidr / sg) -> security group


@dataclass
class Resource:
    """A single AWS resource discovered during ingestion."""
    resource_id: str          # e.g. "sg-0123abc"
    resource_type: str        # e.g. "security_group", "ec2", "rds"
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relationship:
    """A directed relationship between two resources."""
    source_id: str
    target_id: str
    relation_type: str        # e.g. "ATTACHED_TO", "ALLOWS_INGRESS"
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class CloudState:
    """Everything one ingestion pass saw, plus how long each API call took."""
    resources: list[Resource]
    relationships: list[Relationship]
    collected_at: str
    regions: list[str] = field(default_factory=list)
    api_timings_ms: dict[str, float] = field(default_factory=dict)
    total_ms: float = 0.0
    source: str = "aws"

    def by_type(self, resource_type: str) -> list[Resource]:
        return [r for r in self.resources if r.resource_type == resource_type]
