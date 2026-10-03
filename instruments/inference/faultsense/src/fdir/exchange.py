"""Explicit export into SET's existing result-artifact.v1 contract.

The optional, source-pinned SET package owns conformance validation. Export
does not execute a calculation, verify provenance, or admit evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence

SET_REVISION = "bd261a765281a95312f7c91a3857233476294c5b"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def _refs(values: Sequence[str], name: str, *, required: bool = False) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{name} must be an ordered list or tuple")
    result = [_text(v, name) for v in values]
    if len(set(result)) != len(result) or (required and not result):
        raise ValueError(f"{name} must be unique and satisfy required cardinality")
    return result


def _json_snapshot(value: object) -> object:
    # Strict finite JSON also detaches caller-owned mutable objects. No NumPy
    # or dataclass conversion is implicit: scientific mapping is caller-owned.
    def normalize(item: object) -> object:
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON object keys must be strings")
            return {key: normalize(child) for key, child in item.items()}
        elif isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError("export requires explicitly mapped JSON values")
        return item
    return json.loads(json.dumps(normalize(value), allow_nan=False, sort_keys=True))


def _digest(value: object) -> str:
    encoded = json.dumps(value, allow_nan=False, sort_keys=True,
                         separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def export_result(*, operation_id: str, execution_ref: str, source_revision: str,
                  created_at: str, input_refs: Sequence[str],
                  input_payload: Mapping[str, object], numerical_result: Mapping[str, object],
                  components: Sequence[Mapping[str, object]], covariance: Mapping[str, object],
                  applicability: str, model_refs: Sequence[str] = (),
                  calibration_refs: Sequence[str] = ()) -> dict[str, object]:
    """Bind an explicit numerical mapping to existing SET exchange semantics.

    ``source_revision`` is a caller-supplied Git commit, not an attestation.
    Result identity includes execution identity; input digest is content-only.
    ``created_at`` is supplied by the caller; there is no wall-clock read.
    """
    from state_estimation_testbed.contracts import validate_result_artifact

    operation = _text(operation_id, "operation_id")
    execution = _text(execution_ref, "execution_ref")
    if not isinstance(source_revision, str) or re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
        raise ValueError("source_revision must be a full lowercase Git commit SHA")
    inputs = _refs(input_refs, "input_refs", required=True)
    models = _refs(model_refs, "model_refs")
    calibrations = _refs(calibration_refs, "calibration_refs")
    if not isinstance(covariance, Mapping):
        raise ValueError("covariance must be an object")
    covariance_sources = _refs(covariance.get("source_refs", ()), "covariance.source_refs")
    all_refs = inputs + models + calibrations + covariance_sources
    if operation == execution or execution in all_refs or operation in all_refs:
        raise ValueError("operation, execution and referenced artifacts must remain distinct")
    if not isinstance(input_payload, Mapping) or not isinstance(numerical_result, Mapping):
        raise ValueError("input_payload and numerical_result must be objects")
    snapshot = _json_snapshot(input_payload)
    artifact = {
        "schema": "notation.instrument.result-artifact.v1",
        "operation_id": operation,
        "execution_ref": execution,
        "created_at": created_at,
        "input_refs": inputs,
        "model_refs": models,
        "calibration_refs": calibrations,
        "components": _json_snapshot(components),
        "covariance": _json_snapshot(covariance),
        "applicability": _text(applicability, "applicability"),
        "computation": {
            "source_revision": source_revision,
            "source_revision_status": "caller_supplied_unattested",
            "input_digest": "sha256:" + _digest(snapshot),
            "inputs": snapshot,
            "numerical_result": _json_snapshot(numerical_result),
        },
        "verification_refs": [],
    }
    artifact["result_id"] = "result:sha256:" + _digest(artifact)
    if artifact["result_id"] in all_refs + [operation, execution]:
        raise ValueError("result identity must differ from input and operation identities")
    validate_result_artifact(artifact)
    return artifact
