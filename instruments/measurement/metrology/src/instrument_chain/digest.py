"""Canonical SHA-256 of an observation payload.

Same encoding GAT uses for evidence digests: sorted keys, compact JSON,
UTF-8, no NaN. Delivery metadata is excluded. This is record integrity,
not a zk proof and not a claim that the physical quantity is true.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping

from .observation import Observation

SCHEMA = "rci-evidence-commitment-v1"
CLAIM_SCOPE = "record-integrity-only"


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def observation_payload(observation: Observation) -> dict[str, object]:
    return observation.as_dict()


def observation_digest(observation: Observation) -> str:
    return canonical_digest(observation_payload(observation))


def evidence_commitment(observation: Observation) -> dict[str, object]:
    payload = observation_payload(observation)
    return {
        "schema": SCHEMA,
        "kind": "instrument-observation",
        "claim_scope": CLAIM_SCOPE,
        "observation_id": observation.observation_id,
        "payload": payload,
        "digest": canonical_digest(payload),
    }


def verify_evidence_commitment(document: Mapping[str, object]) -> str:
    if document.get("schema") != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA!r}")
    if document.get("claim_scope") != CLAIM_SCOPE:
        raise ValueError(f"claim_scope must be {CLAIM_SCOPE!r}")
    payload = document.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be an object")
    expected = canonical_digest(payload)
    declared = document.get("digest")
    if declared != expected:
        raise ValueError("digest does not match payload")
    if document.get("observation_id") != payload.get("observation_id"):
        raise ValueError("observation_id does not match payload")
    return expected
