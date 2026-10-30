"""Shared proposal contract for the CLI and optional SDK adapter."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Proposal:
    action: str
    confidence: float
    rationale: str
