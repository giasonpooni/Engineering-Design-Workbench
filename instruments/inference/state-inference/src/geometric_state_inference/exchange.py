# SPDX-License-Identifier: MPL-2.0
"""Explicit, source-pinned instrument-exchange adapters.

The optional checker is the public State-Estimation-Evaluation-Testbed
``state_estimation_testbed/contracts.py`` at revision
``542e672be512bf43b61253f2b2a43cd967cb3062``. Only its approved source bytes
execute; no package initializer, artifact-supplied code, or download executes.
This is the same checker pinned by the CIW read-only exchange inspector.

Imports preserve the supplied artifact separately from the numerical view.
Exports are interpreted estimator results, not independently verified evidence
or claims of execution through an external runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import ModuleType
from typing import Mapping, Sequence
from uuid import uuid4

import numpy as np

from .contracts import Estimate, Observation
from .estimator import replay_estimate


ADAPTER_VERSION = "geometric-state-inference.exchange.v1"
CHECKER_REVISION = "542e672be512bf43b61253f2b2a43cd967cb3062"
CHECKER_SHA256 = "2385537daa6147ef2475d17bd75c026fe187077b90841515a9e9378e0246ae54"
CHECKER_PATH = "state_estimation_testbed/contracts.py"
RESULT_SCHEMA = "notation.instrument.result-artifact.v1"
OPERATION_REF = "geometric-state-inference.update.v1"
MAX_COMPONENTS = 64
MAX_ARTIFACT_BYTES = 1_048_576


def _canonical(value: object) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("exchange artifact must be finite JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise ValueError("exchange artifact exceeds the 1 MiB budget")
    return encoded


def _checker(validator_repo: str | Path) -> ModuleType:
    path = Path(validator_repo) / CHECKER_PATH
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("exchange checker must be a regular file")
        source = stream.read(131_073).replace(b"\r\n", b"\n")
    if len(source) > 131_072 or sha256(source).hexdigest() != CHECKER_SHA256:
        raise ValueError("exchange checker source differs from the approved source pin")
    # Unique module names avoid competing imports sharing dataclass resolution.
    name = "_gsie_exchange_checker_" + uuid4().hex
    module = ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    finally:
        del sys.modules[name]
    return module


def _instant(value: str, name: str) -> datetime:
    # The numerical view has microsecond UTC parsing precision. Refuse higher
    # precision instead of allowing datetime to silently truncate it.
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value
    ):
        raise ValueError(f"{name} must be a UTC instant with at most six fractional digits")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid UTC instant") from exc


def _names(values: Sequence[str], name: str, *, unique: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise ValueError(f"{name} must be an ordered list or tuple")
    result = tuple(values)
    if not 1 <= len(result) <= MAX_COMPONENTS or any(
        not isinstance(value, str) or not value.strip() for value in result
    ):
        raise ValueError(f"{name} must contain 1 to {MAX_COMPONENTS} nonempty strings")
    if unique and len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _references(values: Sequence[str], name: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError(f"{name} must be an ordered list or tuple of nonempty references")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(values)


@dataclass(frozen=True)
class ImportedObservation:
    """Numerical observation plus an immutable snapshot of its source claim.

    ``artifact`` returns a fresh object, so edits to that view cannot rewrite
    the retained snapshot. The digest binds supplied content, not its author.
    """

    observation: Observation
    source_json: str
    epoch: str

    def __post_init__(self) -> None:
        if not isinstance(self.observation, Observation):
            raise ValueError("imported observation requires a numerical Observation")
        if not isinstance(self.source_json, str):
            raise ValueError("source_json must be canonical JSON text")
        try:
            snapshot = json.loads(self.source_json)
        except (ValueError, RecursionError) as exc:
            raise ValueError("source_json must be canonical JSON text") from exc
        if not isinstance(snapshot, dict) or _canonical(snapshot) != self.source_json:
            raise ValueError("source_json must be a canonical JSON object")
        _instant(self.epoch, "epoch")

    @property
    def artifact(self) -> dict:
        return json.loads(self.source_json)

    @property
    def source_digest(self) -> str:
        return "sha256:" + sha256(self.source_json.encode("utf-8")).hexdigest()


def import_observation_batch(
    artifact: dict,
    *,
    epoch: str,
    variables: Sequence[str],
    units: Sequence[str],
    frame: Mapping[str, object],
    validator_repo: str | Path,
) -> ImportedObservation:
    """Map an exact declared observation layout into an estimator observation.

    Time is elapsed seconds from ``epoch``. Component ordering, units, and the
    complete frame declaration must match exactly. This function does not
    transform coordinates, select components, convert units, infer timing
    accuracy, or fabricate absent uncertainty. All original metadata remains
    in the retained snapshot, including observation/receipt time and references.
    """
    variables = _names(variables, "variables")
    units = _names(units, "units", unique=False)
    if not isinstance(artifact, dict) or not isinstance(artifact.get("components"), list):
        raise ValueError("exchange observation must be an object with ordered components")
    if not 1 <= len(artifact["components"]) <= MAX_COMPONENTS:
        raise ValueError("exchange observation must contain 1 to 64 components")
    snapshot = _canonical(artifact)
    retained = json.loads(snapshot)
    _checker(validator_repo).validate_observation_batch(retained)
    actual_variables = tuple(item["name"] for item in retained["components"])
    actual_units = tuple(item["unit"] for item in retained["components"])
    if actual_variables != variables:
        raise ValueError("observation component order differs from the declared variables")
    if actual_units != units:
        raise ValueError("observation units differ from the declared units")
    if not isinstance(frame, Mapping) or dict(frame) != retained["covariance"]["frame"]:
        raise ValueError("observation frame differs from the complete declared frame")
    if retained["covariance"]["matrix"] is None:
        raise ValueError("estimation requires explicit observation covariance; absent is not zero")
    seconds = (_instant(retained["observed_at"], "observed_at") - _instant(epoch, "epoch")).total_seconds()
    observation = Observation(
        time=seconds,
        values=[item["value"] for item in retained["components"]],
        covariance=retained["covariance"]["matrix"],
        frame_id=retained["covariance"]["frame"]["id"],
        units=units,
        observation_id=retained["batch_id"],
        evidence_refs=tuple(retained["source_artifact_refs"]),
    )
    return ImportedObservation(observation=observation, source_json=snapshot, epoch=epoch)


def export_result_artifact(
    estimate: Estimate,
    *,
    source: ImportedObservation,
    variables: Sequence[str],
    frame: Mapping[str, object],
    execution_ref: str,
    created_at: str,
    applicability: str,
    validator_repo: str | Path,
    calibration_refs: Sequence[str] = (),
) -> dict:
    """Export a result that the pinned SET/CIW exchange path can inspect.

    The observation snapshot, prior state reference, evidence and calibration
    references travel automatically. ``execution_ref`` names an externally
    assigned execution occurrence and must be distinct from inputs and operation.
    It is a declared reference, not a native Scientific Computation Runtime
    execution commitment. Names and output-frame semantics remain caller-declared
    interpretations. No verification artifact or authority is manufactured.
    """
    if not isinstance(estimate, Estimate) or not isinstance(source, ImportedObservation):
        raise ValueError("export requires an Estimate and its ImportedObservation source")
    variables = _names(variables, "variables")
    if len(variables) != estimate.mean.size:
        raise ValueError("result variable count must match the estimated state")
    if not isinstance(frame, Mapping) or frame.get("id") != estimate.frame_id:
        raise ValueError("result frame id must match the estimated state frame")
    retained = source.artifact
    # Revalidate both the snapshot and its numerical view so a forged/replaced
    # wrapper cannot silently attach another observation's metadata to a result.
    imported = import_observation_batch(
        retained, epoch=source.epoch,
        variables=tuple(item["name"] for item in retained["components"]),
        units=tuple(item["unit"] for item in retained["components"]),
        frame=retained["covariance"]["frame"], validator_repo=validator_repo,
    )
    observed, restored = source.observation, imported.observation
    if not isinstance(observed, Observation) or any((
        observed.time != restored.time,
        observed.frame_id != restored.frame_id,
        observed.units != restored.units,
        observed.observation_id != restored.observation_id,
        observed.evidence_refs != restored.evidence_refs,
        not np.array_equal(observed.values, restored.values),
        not np.array_equal(observed.covariance, restored.covariance),
    )):
        raise ValueError("numerical observation differs from the retained source snapshot")
    if (estimate.observation_id != observed.observation_id
            or estimate.evidence_refs != observed.evidence_refs
            or estimate.time != observed.time
            or estimate.innovation.size != observed.values.size):
        raise ValueError("estimate references do not match its imported observation")
    if estimate.prior_state_id in (observed.observation_id, *observed.evidence_refs):
        raise ValueError("prior state identity must differ from observation and evidence")
    if estimate.replay_snapshot is None:
        raise ValueError("result export requires the retained estimator replay configuration")
    replayed = replay_estimate(estimate.replay_snapshot)
    if any(getattr(replayed, name) != getattr(estimate, name) for name in (
        "numerical_result_id", "state_id", "prior_state_id", "observation_id",
        "evidence_refs", "observation_model_id", "dynamics_model_id",
        "observability_assessment_id",
    )):
        raise ValueError("estimate differs from its bound replay configuration")
    replay_observation = estimate.replay_snapshot["observation"]
    if (replay_observation["values"] != observed.values.tolist()
            or replay_observation["covariance"] != observed.covariance.tolist()
            or replay_observation["frame_id"] != observed.frame_id
            or replay_observation["units"] != list(observed.units)):
        raise ValueError("replay observation differs from the retained source snapshot")
    calibration_refs = _references(calibration_refs, "calibration_refs")
    calibration = list(dict.fromkeys([
        *retained["calibration_refs"], *retained["covariance"]["calibration_refs"],
        *calibration_refs,
    ]))
    inputs = list(dict.fromkeys([
        estimate.prior_state_id, observed.observation_id, *observed.evidence_refs,
        *(() if estimate.observability_assessment_id is None else
          (estimate.observability_assessment_id,)),
    ]))
    model_refs = [estimate.observation_model_id]
    if estimate.dynamics_model_id is not None:
        model_refs.append(estimate.dynamics_model_id)
    if (not isinstance(execution_ref, str) or not execution_ref.strip()
            or execution_ref in (*inputs, *model_refs, *calibration, OPERATION_REF,
                                  estimate.state_id, estimate.numerical_result_id)):
        raise ValueError("execution_ref must be nonempty and distinct from other declared identities")
    artifact = {
        "schema": RESULT_SCHEMA,
        "execution_ref": execution_ref,
        "operation_ref": OPERATION_REF,
        "state_id": estimate.state_id,
        "predecessor_state_id": estimate.prior_state_id,
        "numerical_result_id": estimate.numerical_result_id,
        "input_refs": inputs,
        "model_refs": list(dict.fromkeys(model_refs)),
        "calibration_refs": calibration,
        "components": [
            {"name": name, "value": float(value), "unit": unit}
            for name, value, unit in zip(variables, estimate.mean, estimate.units)
        ],
        "covariance": {
            "status": "estimated",
            "variables": list(variables),
            "units": list(estimate.units),
            "matrix": estimate.covariance.tolist(),
            "frame": dict(frame),
            "method": "Joseph posterior covariance from the declared local linear update",
            "source_refs": inputs,
            "calibration_refs": calibration,
            "numerical_status": "eligible_under_pinned_exchange_checker",
        },
        "applicability": applicability,
        "created_at": created_at,
        "adapter_version": ADAPTER_VERSION,
        "observation_binding": {
            "batch_ref": observed.observation_id,
            "canonical_json_digest": source.source_digest,
            "time_origin_utc": source.epoch,
            "elapsed_seconds": estimate.time,
            "source_snapshot": retained,
            "status": "supplied_content_bound_not_authenticated",
        },
        "replay_binding": {
            "status": "local_replay_matched",
            "snapshot": estimate.replay_snapshot,
            "canonical_json_digest": "sha256:" + sha256(
                estimate.replay_json.encode("utf-8")).hexdigest(),
            "verification_independence": "not_established",
        },
        "diagnostics": {
            "measurement_variables": [item["name"] for item in retained["components"]],
            "measurement_units": list(observed.units),
            "measurement_frame": retained["covariance"]["frame"],
            "innovation": estimate.innovation.tolist(),
            "innovation_covariance": estimate.innovation_covariance.tolist(),
            "posterior_residual": estimate.residual.tolist(),
            "normalized_innovation_squared": estimate.nis,
            "calibration_validity": "not_established",
            "observability": (
                "not_evaluated" if estimate.observability_assessment_id is None else {
                    "status": "observable",
                    "assessment_id": estimate.observability_assessment_id,
                    "gate": "required_before_update",
                }
            ),
            "physical_validity": "not_established",
        },
        "execution_binding": {
            "reference_status": "caller_declared",
            "behavior_status": "unverified",
            "components_status": "caller_declared_interpretation",
        },
        "authority": {
            "may_authorize": False,
            "source_admission": "not_assessed",
            "independent_verification": "not_performed",
        },
    }
    canonical = _canonical(artifact)
    artifact["result_id"] = "sha256:" + sha256(
        RESULT_SCHEMA.encode("utf-8") + b"\x00" + canonical.encode("utf-8")
    ).hexdigest()
    _checker(validator_repo).validate_result_artifact(artifact)
    # Return JSON-native detached data; caller-owned frame lists cannot mutate
    # this content after result_id has been calculated.
    return json.loads(_canonical(artifact))
