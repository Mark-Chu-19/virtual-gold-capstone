"""Trusted tenant identity established from the authenticated API key."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    tenant_id: str
