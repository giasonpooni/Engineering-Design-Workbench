"""Ordered covariance records for the additive CIW v2 snapshot operation.

This is an FSRT-owned wire boundary, not a coordinate-propagation engine. The
existing v1 estimator and balance gate still compute every posterior and action.
The innovation covariance here is the same single-snapshot P_prior + R used by
that estimator, restricted to the observed principal submatrix.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re

import numpy as np

OPERATION_ID = "fsrt.tank-reconstruct.v2"
SCHEMA = "covariance-artifact.v1"
STATE_ORDER = ["tank-1.mass", "tank-2.mass"]
FRAME = "reservoir2.mass"
_CONTENT_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_INDEPENDENCE = (
    "prior_independent_of_observations",
    "declared_total_independent_of_observations",
    "prior_independent_of_declared_total",
)
_FIELDS = {
    "schema", "covariance_id", "quantity_ids", "units", "frame", "reference_values",
    "matrix", "method", "basis", "provenance", "assumptions",
}


class CovarianceRefusal(ValueError):
    def __init__(self, message, code="invalid_covariance_contract"):
        super().__init__(message)
        self.code = code


def _require(condition, message, code="invalid_covariance_contract"):
    if not condition:
        raise CovarianceRefusal(message, code)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _texts(value, *, nonempty=False, unique=False):
    return (isinstance(value, list) and (bool(value) or not nonempty)
            and all(_text(item) for item in value)
            and (not unique or len(value) == len(set(value))))


def _finite(value):
    return (type(value) in (int, float) and math.isfinite(value))


def _canonical(value):
    def is_json(item):
        if item is None or isinstance(item, (str, bool)):
            return True
        if type(item) in (int, float):
            return math.isfinite(item)
        if isinstance(item, list):
            return all(is_json(child) for child in item)
        if isinstance(item, dict):
            return all(isinstance(key, str) and is_json(child) for key, child in item.items())
        return False

    _require(is_json(value), "Covariance metadata must be finite JSON")
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CovarianceRefusal("Covariance metadata must be finite JSON") from error


def covariance_id(artifact):
    return "sha256:" + hashlib.sha256(_canonical(
        {key: value for key, value in artifact.items() if key != "covariance_id"}
    )).hexdigest()


def validate_artifact(artifact):
    """Validate content identity and ordered PSD covariance without repairing it."""
    _require(isinstance(artifact, dict) and set(artifact) == _FIELDS,
             "Covariance artifact must have exactly the covariance-artifact.v1 fields")
    _require(artifact["schema"] == SCHEMA, "Unsupported covariance schema")
    _require(artifact["covariance_id"] == covariance_id(artifact), "Covariance content identity mismatch")
    ids, units, reference = (artifact[key] for key in ("quantity_ids", "units", "reference_values"))
    _require(_texts(ids, nonempty=True, unique=True), "quantity_ids must be distinct ordered names")
    n = len(ids)
    _require(_texts(units) and len(units) == n, "units must match the quantity order")
    _require(_text(artifact["frame"]) and _text(artifact["method"]), "frame and method must be nonempty")
    _require(isinstance(reference, list) and len(reference) == n and all(_finite(x) for x in reference),
             "reference_values must be finite and match the quantity order")
    rows = artifact["matrix"]
    _require(isinstance(rows, list) and len(rows) == n
             and all(isinstance(row, list) and len(row) == n and all(_finite(x) for x in row) for row in rows),
             "matrix must be finite, square and match the quantity order")
    matrix = np.array(rows, dtype=float)
    diagonal = np.diag(matrix)
    _require(np.all(diagonal >= 0), "Covariance variances must be nonnegative", "numerical_refusal")
    for i in np.flatnonzero(diagonal == 0):
        _require(np.all(matrix[i] == 0) and np.all(matrix[:, i] == 0),
                 "Zero variance requires an exactly zero covariance row and column", "numerical_refusal")
    active = diagonal > 0
    if np.any(active):
        submatrix = matrix[np.ix_(active, active)]
        scales = np.sqrt(diagonal[active])
        correlation = (submatrix / scales[:, None]) / scales[None, :]
        _require(np.isfinite(correlation).all()
                 and np.allclose(correlation, correlation.T, rtol=0, atol=1e-12),
                 "Covariance is not symmetric in normalized coordinates", "numerical_refusal")
        _require(min(np.linalg.eigvalsh(correlation, UPLO="L").min(),
                     np.linalg.eigvalsh(correlation, UPLO="U").min()) >= -1e-10,
                 "Covariance is not positive semidefinite", "numerical_refusal")
    basis = artifact["basis"]
    _require(isinstance(basis, dict) and set(basis) == {"kind", "id"}
             and basis["kind"] in ("observation", "calibrated_observation", "estimated_state",
                                  "parameter", "coordinate", "residual") and _text(basis["id"]),
             "Covariance basis must declare its kind and identity")
    provenance = artifact["provenance"]
    _require(isinstance(provenance, dict)
             and {"provider", "source_evidence_ids", "source_covariance_ids"} <= set(provenance)
             and not set(provenance) - {"provider", "source_evidence_ids", "source_covariance_ids", "metadata"}
             and _text(provenance["provider"]), "Covariance provenance fields are invalid")
    for key in ("source_evidence_ids", "source_covariance_ids"):
        _require(_texts(provenance[key], unique=True)
                 and all(_CONTENT_ID.fullmatch(value) for value in provenance[key]),
                 f"{key} must contain distinct sha256 content identities")
    if "metadata" in provenance:
        _require(isinstance(provenance["metadata"], dict), "Covariance metadata must be an object")
    _require(_texts(artifact["assumptions"]), "Covariance assumptions must be explicit strings")
    return artifact


def _artifact(key, matrix, reference, quantities, basis_kind, source_covariances,
              source_evidence, metadata, assumptions, method):
    artifact = {
        "schema": SCHEMA, "quantity_ids": list(quantities), "units": ["kg"] * len(quantities),
        "frame": FRAME, "reference_values": list(reference), "matrix": np.asarray(matrix).tolist(),
        "method": method, "basis": {"kind": basis_kind, "id": OPERATION_ID + ":" + key},
        "provenance": {"provider": OPERATION_ID, "source_evidence_ids": list(source_evidence),
                       "source_covariance_ids": list(source_covariances),
                       "metadata": {**deepcopy(metadata), "stage": key}},
        "assumptions": list(assumptions),
    }
    artifact["covariance_id"] = covariance_id(artifact)
    return validate_artifact(artifact)


def evaluate_inputs(inputs, compute_v1):
    """Decorate the unchanged v1 science with checked covariance provenance."""
    _require(isinstance(inputs, dict) and set(inputs) == {
        "model", "observations", "state_order", "observation_covariance",
    }, "v2 requires model, observations, state_order and observation_covariance")
    _require(inputs["state_order"] == STATE_ORDER, "Unsupported or reordered reservoir state_order")
    artifact = validate_artifact(inputs["observation_covariance"])
    observations = inputs["observations"]
    _require(isinstance(observations, list) and len(observations) == 1,
             "v2 requires exactly one simultaneous snapshot", "unsupported_temporal_covariance")
    row = observations[0]
    _require(isinstance(row, dict) and isinstance(row.get("mask"), list) and len(row["mask"]) == 2
             and all(type(value) is bool for value in row["mask"])
             and isinstance(row.get("values"), list) and len(row["values"]) == 2,
             "Observation requires two values and two explicit Boolean mask entries")
    _require(artifact["quantity_ids"] == row.get("source_ids") and len(artifact["quantity_ids"]) == 2,
             "Covariance quantity order must equal two observation source_ids")
    _require(artifact["units"] == ["kg", "kg"] and artifact["frame"] == FRAME,
             "Observation covariance requires kg units and reservoir2.mass frame")
    _require(artifact["basis"]["kind"] == "calibrated_observation", "Observation covariance basis must be calibrated_observation")
    _require(artifact["matrix"] == row.get("covariance"), "Observation covariance matrix does not match the estimator input")
    _require(artifact["provenance"]["source_evidence_ids"] == row.get("evidence_ids"),
             "Covariance evidence order must equal observation evidence_ids")
    _require(all(not present or reference == value
                 for present, reference, value in zip(row["mask"], artifact["reference_values"], row["values"])),
             "Present observation references must equal the calibrated values")
    metadata = artifact["provenance"].get("metadata", {})
    _require(_texts(metadata.get("shared_dependencies"), unique=True),
             "shared_dependencies must explicitly list declared shared sources (possibly empty)")
    for key in _INDEPENDENCE:
        _require(metadata.get(key) is True, f"{key}=true must be explicitly declared; dependence is unsupported",
                 "unsupported_covariance_dependence")
    # All declared provenance/dependence is checked before executing the unchanged
    # estimator and its v1 refusal/balance gates.
    data = compute_v1({"model": inputs["model"], "observations": observations})
    observed = [i for i, present in enumerate(row["mask"]) if present]
    common_metadata = {
        **{key: True for key in _INDEPENDENCE},
        "shared_dependencies": deepcopy(metadata["shared_dependencies"]),
        "state_order": list(STATE_ORDER), "source_order": list(row["source_ids"]),
        "observed_mask": list(row["mask"]),
        "upstream_covariance_metadata": deepcopy(metadata),
        "reference_role": "artifact_quantity_values; absent input coordinates are declared references, not observations",
    }
    assumptions = [
        *artifact["assumptions"],
        "Prior, observation errors and declared total are mutually independent except correlations inside the observation matrix.",
        "The prior is isotropic Gaussian with the declared prior_std; the total has its declared independent variance.",
        "One simultaneous snapshot, no temporal covariance model or physical verification.",
    ]
    model = inputs["model"]
    P0 = np.eye(2) * float(model["prior_std"]) ** 2
    make = lambda key, matrix, ref, ids, kind, sources, evidence, method: _artifact(
        key, matrix, ref, ids, kind, sources, evidence, common_metadata, assumptions, method)
    prior = make("prior", P0, model["prior_mean"], STATE_ORDER, "parameter", [], [], "declared_isotropic_gaussian_prior")
    total = make("declared_total", [[model["total_mass_variance_kg2"]]], [model["total_mass_kg"]],
                 ["total_mass"], "parameter", [], [], "declared_independent_total_mass")
    sources = [artifact["covariance_id"], prior["covariance_id"]]
    evidence = row["evidence_ids"]
    # Same first-snapshot innovation covariance as KalmanFilter.ingest. The
    # principal submatrix is explicit; missing channels never become zeros.
    innovation_matrix = (P0 + np.asarray(row["covariance"], dtype=float))[np.ix_(observed, observed)]
    innovation = make("innovation", innovation_matrix,
                      [data["residuals"]["innovation"][i] for i in observed],
                      [row["source_ids"][i] for i in observed], "residual", sources, evidence,
                      "kalman_innovation_prior_plus_observation_covariance")
    posterior = make("posterior", data["unprojected_estimate"]["covariance"],
                     data["unprojected_estimate"]["values"], STATE_ORDER, "estimated_state",
                     sources, evidence, "existing_kalman_joseph_update_before_balance")
    reconciled = make("reconciled", data["estimate"]["covariance"], data["estimate"]["values"],
                      STATE_ORDER, "estimated_state", [posterior["covariance_id"], total["covariance_id"]],
                      evidence, "existing_balance_gate_and_reconciliation")
    reconciled["provenance"]["metadata"]["reconciliation_status"] = data["diagnostics"]["reconciliation_status"]
    reconciled["covariance_id"] = covariance_id(reconciled)
    data["state_order"] = list(STATE_ORDER)
    data["covariance_artifacts"] = {
        "observation": deepcopy(artifact), "prior": prior, "declared_total": total,
        "innovation": innovation, "posterior": posterior, "reconciled": reconciled,
    }
    return data
