"""JSON covariance operation provider; numerical authority remains in JSPT.

Only an explicit matrix is accepted. No payload can select a Python module,
model source, symbolic expression, file path or executable.
"""

from __future__ import annotations

from copy import deepcopy
import json
import sys
from typing import Any

import numpy as np

from .coordinates import push_covariance
from .covariance import _require_psd, first_order_covariance
from .covariance_artifact import (
    MAX_DIMENSION, _string, _strings, canonical, content_id, make_covariance_artifact,
    matrix, validate_covariance_artifact, vector,
)

OPERATION_ID = "jspt.covariance-propagate.v1"
RESULT_SCHEMA = "jspt.covariance-result.v1"
REQUEST_SCHEMA = "ciw.adapter-request.v1"
RESPONSE_SCHEMA = "ciw.adapter-response.v1"
_INPUT_FIELDS = {
    "covariance", "jacobian", "output_quantity_ids", "output_units", "output_frame",
    "output_reference_values", "map_kind",
}
_MAP_KINDS = {"linear", "local_linearization", "weighted_aggregation", "coordinate_change"}
_INPUT_LIMIT = 4 * 1024 * 1024


class CovarianceRefusal(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def propagate_covariance(inputs: dict) -> dict:
    """Push a declared covariance through a caller-declared ordered Jacobian.

    For aggregation, each Jacobian row is one explicit vector of weights. Means,
    physical units, the Jacobian's validity and independence assumptions remain
    caller declarations. Full cross-covariance is retained, including zero and
    rank-deficient directions; no diagonal approximation is introduced.
    """
    if not isinstance(inputs, dict) or set(inputs) != _INPUT_FIELDS:
        raise ValueError("Covariance propagation requires exactly the declared v1 input fields")
    source = validate_covariance_artifact(inputs["covariance"])
    map_kind = inputs["map_kind"]
    if not isinstance(map_kind, str) or map_kind not in _MAP_KINDS:
        raise ValueError("map_kind must be linear, local_linearization, weighted_aggregation or coordinate_change")
    output_quantities = _strings(inputs["output_quantity_ids"], "output_quantity_ids", unique=True)
    output_size, input_size = len(output_quantities), len(source["quantity_ids"])
    if not 1 <= output_size <= MAX_DIMENSION:
        raise ValueError(f"Output dimension must be between 1 and {MAX_DIMENSION}")
    output_units = _strings(inputs["output_units"], "output_units", size=output_size)
    output_frame = _string(inputs["output_frame"], "output_frame")
    vector(inputs["output_reference_values"], output_size, "output_reference_values")
    jacobian = matrix(inputs["jacobian"], output_size, input_size, "jacobian")
    covariance = matrix(source["matrix"], input_size, input_size, "covariance.matrix")
    if map_kind == "coordinate_change" and output_size != input_size:
        raise ValueError("coordinate_change requires a square invertible chart; use linear or weighted_aggregation for reductions")
    kernel = "sensitivity.coordinates.push_covariance" if map_kind == "coordinate_change" else "sensitivity.covariance.first_order_covariance"
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            propagated = (push_covariance(jacobian, covariance) if map_kind == "coordinate_change"
                          else first_order_covariance(jacobian, covariance))
        if not np.all(np.isfinite(propagated)):
            raise ValueError("propagated covariance is not finite")
        _require_psd(propagated, "propagated covariance")
    except (ValueError, np.linalg.LinAlgError, FloatingPointError, OverflowError) as exc:
        raise CovarianceRefusal("numerical_refusal", str(exc)) from exc
    mapping_declaration = {
        "operation_id": OPERATION_ID, "source_covariance_id": source["covariance_id"],
        **{key: deepcopy(value) for key, value in inputs.items() if key != "covariance"},
    }
    local = map_kind == "local_linearization"
    assumptions = list(source["assumptions"]) + [
        "Jacobian columns follow input quantity_ids; rows follow output_quantity_ids.",
        "Jacobian coefficients and input/output reference values are caller declarations.",
        "Coefficient units are output_units[row]/input units[column]; units are declared, not inferred.",
        ("The supplied Jacobian is a local first-order approximation at input reference_values."
         if local else "The covariance push is exact for the declared fixed linear map in exact arithmetic."),
    ]
    output = make_covariance_artifact(
        quantity_ids=deepcopy(output_quantities), units=deepcopy(output_units), frame=output_frame,
        reference_values=deepcopy(inputs["output_reference_values"]), matrix=propagated.tolist(),
        method=("first_order_covariance_pushforward" if local else "linear_covariance_pushforward"),
        basis={"kind": "coordinate", "id": content_id(mapping_declaration)},
        provenance={
            "provider": "JSPT:" + OPERATION_ID,
            "source_evidence_ids": deepcopy(source["provenance"]["source_evidence_ids"]),
            "source_covariance_ids": [source["covariance_id"]],
            "metadata": {
                "kernel": kernel, "map_kind": map_kind, "jacobian_source": "caller_declared",
                "jacobian": deepcopy(inputs["jacobian"]),
                "input_quantity_ids": deepcopy(source["quantity_ids"]),
                "input_units": deepcopy(source["units"]), "input_frame": source["frame"],
                "input_basis": deepcopy(source["basis"]),
                "linearization_point": deepcopy(source["reference_values"]),
                "reference_values_source": "caller_declared",
                "source_uncertainty_context": deepcopy(source["provenance"].get("metadata", {})),
            },
        }, assumptions=assumptions,
    )
    return {
        "schema": RESULT_SCHEMA, "operation_id": OPERATION_ID, "map_kind": map_kind,
        "jacobian_source": "caller_declared", "jacobian": deepcopy(inputs["jacobian"]),
        "input_covariance": source, "output_covariance": output,
        "linearization_point": deepcopy(source["reference_values"]),
        "output_reference_values": deepcopy(inputs["output_reference_values"]),
        "checks": {
            "input_positive_semidefinite": True, "output_positive_semidefinite": True,
            "input_covariance_symmetrized": not np.array_equal(covariance, covariance.T),
            "coordinate_chart_guarded": map_kind == "coordinate_change",
            "jacobian_verified": False, "reference_values_verified": False,
            "physical_units_verified": False, "monte_carlo_performed": False,
        },
        "limits": [
            "This operation propagates an explicit caller-declared Jacobian; it does not compute or verify derivatives.",
            "Reference values and physical unit/frame compatibility are caller declarations, not physical validation.",
            "No nonlinear Monte Carlo comparison, model adequacy check, certificate or execution authorization is produced.",
        ],
    }


def _refusal(code: str, message: str) -> dict:
    return {"schema": RESPONSE_SCHEMA, "status": "refused", "refusal": {"code": code, "message": message}}


def handle_request(request: Any) -> dict:
    try:
        if (not isinstance(request, dict) or set(request) != {"schema", "operation_id", "inputs"}
                or request["schema"] != REQUEST_SCHEMA):
            raise ValueError("Expected a ciw.adapter-request.v1 operation envelope")
        if request["operation_id"] != OPERATION_ID:
            return _refusal("operation_unavailable", "This provider only supports " + OPERATION_ID)
        return {"schema": RESPONSE_SCHEMA, "status": "ok", "data": propagate_covariance(request["inputs"])}
    except CovarianceRefusal as exc:
        return _refusal(exc.code, str(exc))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, np.linalg.LinAlgError) as exc:
        return _refusal("invalid_input", str(exc) or "Invalid covariance declaration")


def main() -> int:
    def unique_pairs(items):
        record = {}
        for key, value in items:
            if key in record:
                raise ValueError("Duplicate JSON key: " + key)
            record[key] = value
        return record

    def reject_constant(value):
        raise ValueError("Nonfinite JSON constant: " + value)

    try:
        payload = sys.stdin.buffer.read(_INPUT_LIMIT + 1)
        if len(payload) > _INPUT_LIMIT:
            raise ValueError("Request exceeds the 4 MiB input limit")
        request = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_pairs, parse_constant=reject_constant)
        response = handle_request(request)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        response = _refusal("invalid_json", str(exc) or "Invalid JSON request")
    sys.stdout.write(canonical(response).decode("ascii") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
