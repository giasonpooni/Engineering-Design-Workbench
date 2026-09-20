"""Measurement-chain contract for retrofitted computational instruments."""

from .calibration import apply_calibration
from .digest import (
    CLAIM_SCOPE,
    SCHEMA as EVIDENCE_SCHEMA,
    canonical_digest,
    evidence_commitment,
    observation_digest,
    verify_evidence_commitment,
)
from .manifest import SCHEMA, Assembly, load_assembly
from .observation import Observation, Quality, acquire_or_unavailable
from .receiver import receive, replay
from .transport import Delivery, deliver
from .uncertainty_budget import (
    SCHEMA as BUDGET_SCHEMA,
    Budget,
    Dist,
    TypeA,
    TypeB,
    coverage_factor,
    from_record,
)

__all__ = [
    "BUDGET_SCHEMA",
    "CLAIM_SCOPE",
    "EVIDENCE_SCHEMA",
    "SCHEMA",
    "Assembly",
    "Budget",
    "Delivery",
    "Dist",
    "Observation",
    "Quality",
    "TypeA",
    "TypeB",
    "acquire_or_unavailable",
    "apply_calibration",
    "canonical_digest",
    "coverage_factor",
    "deliver",
    "evidence_commitment",
    "from_record",
    "load_assembly",
    "observation_digest",
    "receive",
    "replay",
    "verify_evidence_commitment",
]

__version__ = "0.2.0"
