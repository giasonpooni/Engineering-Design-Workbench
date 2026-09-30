"""Small data-only NET boundaries. No provider loading, unit conversion or state owner.

Use CIW's existing content encoder/seals and covariance artifact. These records
are declarations and numerical checks, not verification occurrences or admission.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import math
from pathlib import Path
import re
from typing import Any

from .core.identities import content_identity
from .operations.runner import seal, check_seal

MAX_BYTES = 8 * 1024 * 1024
MAX_SAMPLES = 65536
SCHEMAS = {f"ciw.{name}.v1" for name in (
    "state", "observation", "artifact", "experiment", "comparison", "verification",
    "checkpoint", "parameter-space", "graph-run", "observation-stream",
    "annotation", "annotation-stream", "investigation-efficiency",
    "investigation-comparison", "container-spec", "container-composition",
    "container-telemetry", "needle-plan", "needle-run", "needle-delta",
    "system-board", "board-compilation", "parameter-program", "parameter-sweep", "representation-spec",
    "scientific-morphism", "morphism-registry", "morphism-witness",
    "intervention-gate", "board-morphism-binding", "board-morphism-compilation",
    "finite-preservation", "representation-expansion",
    "representation-expansion-verification", "representation-expansion-promotion",
    "board-view", "board-edit-preview", "board-visual-run")}


def text(value: Any) -> str:
    if type(value) is not str or not value.strip() or len(value) > 512:
        raise ValueError("Require bounded nonempty text")
    return value


def number(value: Any) -> float:
    if type(value) not in (int, float) or abs(value) > 1e150 or not math.isfinite(value):
        raise ValueError("Require a finite bounded number, not a boolean")
    return float(value)


def keys(value: Any, expected: set[str]) -> None:
    if type(value) is not dict or set(value) != expected:
        raise ValueError("Unexpected or missing contract fields")


def json_tree(value: Any, depth: int = 0) -> None:
    if depth > 24:
        raise ValueError("JSON nesting exceeds bound")
    if value is None or type(value) is bool:
        return
    if type(value) is str:
        if len(value) > 65536:
            raise ValueError("JSON text exceeds bound")
    elif type(value) in (int, float):
        number(value)
    elif type(value) is list and len(value) <= MAX_SAMPLES:
        for item in value:
            json_tree(item, depth + 1)
    elif type(value) is dict and len(value) <= 1024:
        for key, item in value.items():
            text(key)
            json_tree(item, depth + 1)
    else:
        raise ValueError("Require bounded JSON data")


def detached(value: Any) -> Any:
    json_tree(value)
    return deepcopy(value)


def content_ref(value: Any) -> str:
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ValueError("Require a canonical SHA256 reference")
    return value


def bytes_ref(value: bytes) -> str:
    if type(value) is not bytes:
        raise ValueError("Require exact bytes")
    return "sha256:" + sha256(value).hexdigest()


def record(schema_name: str, **fields: Any) -> dict:
    value = detached({"schema": f"ciw.{schema_name}.v1", **fields})
    if value["schema"] not in SCHEMAS:
        raise ValueError("Unknown control contract")
    return seal(value)


def _base(value: dict, kind: str, fields: set[str]) -> None:
    json_tree(value)
    keys(value, fields | {"schema", "record_digest"})
    if value["schema"] != f"ciw.{kind}.v1":
        raise ValueError("Wrong record schema")
    check_seal(value)


def _identity(value: dict) -> None:
    keys(value, {"model_id", "entity_id", "execution_id"})
    text(value["model_id"])
    text(value["entity_id"])
    # Null means a retained source without a known execution occurrence.
    if value["execution_id"] is not None:
        text(value["execution_id"])


def _clock(value: dict) -> None:
    keys(value, {"id", "time_s"})
    text(value["id"])
    number(value["time_s"])


def _provenance(value: dict) -> None:
    keys(value, {"provider", "sources", "semantics"})
    text(value["provider"])
    if value["semantics"] not in {"observed", "estimated", "simulated", "reference"}:
        raise ValueError("Declare observation semantics")
    if type(value["sources"]) is not list or not value["sources"]:
        raise ValueError("Require source content references")
    for ref in value["sources"]:
        content_ref(ref)
    if len(set(value["sources"])) != len(value["sources"]):
        raise ValueError("Duplicate source reference")


def _vector(value: Any) -> list:
    if value is None:
        return [None]
    if type(value) is list:
        if not 1 <= len(value) <= 64:
            raise ValueError("Require a nonempty bounded scalar/vector value")
        for item in value:
            if item is not None:
                number(item)
        return value
    number(value)
    return [value]


def _uncertainty(covariance: Any, variables: dict, frame: str) -> None:
    if covariance is None:
        return
    if type(covariance) is not dict:
        raise ValueError("Covariance must be a complete covariance artifact")
    from .core.covariance import validate_covariance_artifact
    quantities, units, values = [], [], []
    # Covariance axis order follows the retained explicit quantity_ids, not dict order.
    axes = {}
    for name, variable in variables.items():
        entries = _vector(variable["value"])
        for index, value in enumerate(entries):
            axis = f"{name}[{index}]" if type(variable["value"]) is list else name
            if axis in axes:
                raise ValueError("Ambiguous scalar/vector covariance axis name")
            axes[axis] = (variable["unit"], value)
    for axis in covariance.get("quantity_ids", []):
        if axis not in axes or axes[axis][1] is None:
            raise ValueError("Covariance axis has no retained reference value")
        quantities.append(axis)
        units.append(axes[axis][0])
        values.append(axes[axis][1])
    if set(quantities) != set(axes):
        raise ValueError("Partial covariance is not a full state covariance")
    validate_covariance_artifact(covariance, expected_quantity_ids=quantities,
                                expected_units=units, expected_frame=frame)
    if covariance["reference_values"] != values:
        raise ValueError("Covariance reference values differ from the retained state")


def state(*, identity: dict, clock: dict, frame: str, variables: dict,
          provenance: dict, uncertainty: dict | None = None) -> dict:
    value = record("state", identity=identity, clock=clock, frame=frame,
                   variables=variables, uncertainty=uncertainty, provenance=provenance)
    validate_state(value)
    return value


def validate_state(value: dict) -> None:
    _base(value, "state", {"identity", "clock", "frame", "variables", "uncertainty", "provenance"})
    _identity(value["identity"])
    _clock(value["clock"])
    text(value["frame"])
    _provenance(value["provenance"])
    if type(value["variables"]) is not dict or not 1 <= len(value["variables"]) <= 64:
        raise ValueError("Require 1..64 declared state variables")
    for name, variable in value["variables"].items():
        text(name)
        keys(variable, {"value", "unit"})
        _vector(variable["value"])
        text(variable["unit"])
    _uncertainty(value["uncertainty"], value["variables"], value["frame"])


def observation(*, identity: dict, clock: dict, frame: str, quantity: str,
                value: Any, unit: str, provenance: dict,
                uncertainty: dict | None = None) -> dict:
    result = record("observation", identity=identity, clock=clock, frame=frame,
                    quantity=quantity, value=value, unit=unit,
                    provenance=provenance, uncertainty=uncertainty)
    validate_observation(result)
    return result


def validate_observation(value: dict) -> None:
    _base(value, "observation", {"identity", "clock", "frame", "quantity", "value",
                                "unit", "uncertainty", "provenance"})
    _identity(value["identity"])
    _clock(value["clock"])
    text(value["frame"])
    text(value["quantity"])
    text(value["unit"])
    _vector(value["value"])
    _provenance(value["provenance"])
    _uncertainty(value["uncertainty"], {value["quantity"]: {
        "value": value["value"], "unit": value["unit"]}}, value["frame"])


def artifact(payload: bytes, *, media_type: str, producer: str, experiment_id: str,
             metadata: dict | None = None) -> dict:
    result = record("artifact", sha256=bytes_ref(payload), size_bytes=len(payload),
                    media_type=media_type, producer=producer, experiment_id=experiment_id,
                    created_at=datetime.now(timezone.utc).isoformat(), metadata={} if metadata is None else metadata)
    validate_artifact(result)
    return result


def validate_artifact(value: dict, payload: bytes | None = None) -> None:
    _base(value, "artifact", {"sha256", "size_bytes", "media_type", "producer",
                              "experiment_id", "created_at", "metadata"})
    content_ref(value["sha256"])
    if type(value["size_bytes"]) is not int or value["size_bytes"] < 0:
        raise ValueError("Invalid artifact size")
    for key in ("media_type", "producer", "experiment_id"):
        text(value[key])
    timestamp = datetime.fromisoformat(text(value["created_at"]))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Artifact creation time must have a timezone")
    if type(value["metadata"]) is not dict:
        raise ValueError("Artifact metadata must be an object")
    if payload is not None and (bytes_ref(payload) != value["sha256"] or len(payload) != value["size_bytes"]):
        raise ValueError("Artifact payload mismatch")


def specification_id(*, model: str, artifacts: list[str], parameters: dict,
                     initial_state: dict, runtime: dict, seed: int | None = None) -> str:
    """A reproducibility-specification hash, never an execution occurrence ID."""
    text(model)
    for ref in artifacts:
        content_ref(ref)
    validate_state(initial_state)
    if initial_state["identity"]["model_id"] != model:
        raise ValueError("Initial state/model mismatch")
    if not isinstance(runtime, dict) or not runtime:
        raise ValueError("Runtime identity is required")
    if seed is not None and type(seed) is not int:
        raise ValueError("Seed must be an integer or null")
    return content_identity(detached(dict(model=model, artifacts=artifacts, parameters=parameters,
                                         initial_state=initial_state, runtime=runtime, seed=seed)))


def load(path: Path, *, expected_sha256: str | None = None) -> Any:
    from .session import loads_json
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Control document exceeds byte budget or is empty")
    if expected_sha256 is not None:
        content_ref(expected_sha256)
        if bytes_ref(raw) != expected_sha256:
            raise ValueError("Selected source bytes differ from the expected SHA256")
    value = loads_json(raw.decode("utf-8"))
    json_tree(value)
    return value


def save_new(path: Path, value: Any) -> None:
    """Atomic create-only publication. Never overwrite an existing file/symlink."""
    import json
    import os
    import tempfile
    json_tree(value)
    raw = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("Control document exceeds byte budget")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".net-", dir=path.parent) as directory:
        staged = Path(directory) / "record.json"
        with staged.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, path)
