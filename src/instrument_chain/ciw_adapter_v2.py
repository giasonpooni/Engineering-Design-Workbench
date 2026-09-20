"""Additive calibration covariance provenance; v1 remains the numerical path.

The basis declares which effects a covariance contains, with source identity
and evidence references. It does not authenticate those references or establish
metrological traceability. Unrepresented exclusions remain explicit limitations.
"""

from __future__ import annotations

from copy import deepcopy

import numpy as np

from .ciw_adapter import (
    MAX_RECORDS, REQUEST_SCHEMA, RESPONSE_SCHEMA, Refusal, _covariance, _object, calibrate,
)
from .digest import canonical_digest
from .manifest import loads

OPERATION_ID = "rci.calibrate.v2"
BINDING_SCHEMA = "rci-calibration-binding.v2"
BASIS_SCHEMA = "rci-covariance-basis.v1"
_KINDS = {"fitting", "reference_standard", "shared_systematic"}
_PROVENANCE = {"reason", "evidence_ids", "dependency_ids", "shared_source_ids"}


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise Refusal("covariance_basis_ambiguous", f"{label} must be a non-empty string without surrounding whitespace")
    return value


def _ids(value: object, label: str, *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise Refusal("covariance_basis_ambiguous", f"{label} must be an explicit {'non-empty ' if required else ''}identifier array")
    for identifier in value:
        _text(identifier, label)
    if len(set(value)) != len(value):
        raise Refusal("covariance_basis_ambiguous", f"{label} contains duplicate identifiers")
    return value


def _provenance(record: dict, label: str) -> set[str]:
    _text(record["reason"], f"{label}.reason")
    _ids(record["evidence_ids"], f"{label}.evidence_ids", required=True)
    dependencies = _ids(record["dependency_ids"], f"{label}.dependency_ids")
    shared = _ids(record["shared_source_ids"], f"{label}.shared_source_ids")
    return set(dependencies) | set(shared)


def validate_covariance_basis(binding: dict, raw_covariance: object) -> dict:
    """Validate disjoint additive components and return a provenance summary.

    Different identifiers do not prove independence: the separate independence
    declaration and its evidence are mandatory even when source sets differ.
    """
    if not isinstance(binding, dict) or "covariance_basis" not in binding:
        raise Refusal("covariance_basis_missing", "v2 requires an explicit covariance_basis")
    basis = _object(binding["covariance_basis"], {
        "schema", "parameter_components", "raw", "residual", "independence",
    }, set(), "covariance_basis")
    if basis["schema"] != BASIS_SCHEMA:
        raise Refusal("covariance_basis_ambiguous", f"Expected covariance basis schema {BASIS_SCHEMA}")
    components = basis["parameter_components"]
    if not isinstance(components, list) or not components:
        raise Refusal("covariance_basis_ambiguous", "Parameter covariance components must be declared")
    by_id = {}
    seen_kinds = set()
    contributions = []
    additive_sources = []
    evidence_ids, dependency_ids, shared_source_ids = set(), set(), set()
    exclusions, represented = [], []
    for component in components:
        _object(component, _PROVENANCE | {
            "component_id", "kind", "status", "covariance", "represented_by",
        }, set(), "parameter component")
        identifier = _text(component["component_id"], "component_id")
        if identifier in by_id:
            raise Refusal("covariance_basis_ambiguous", "Duplicate parameter component_id")
        by_id[identifier] = component
        if component["kind"] not in _KINDS:
            raise Refusal("covariance_basis_ambiguous", "Unknown parameter component kind")
        seen_kinds.add(component["kind"])
        source_ids = _provenance(component, identifier)
        evidence_ids.update(component["evidence_ids"])
        dependency_ids.update(component["dependency_ids"])
        shared_source_ids.update(component["shared_source_ids"])
        if component["status"] == "included":
            if component["represented_by"] is not None:
                raise Refusal("covariance_double_counting", "Included components cannot also be represented by another component")
            covariance = _covariance(component["covariance"], 2, identifier)
            if not source_ids:
                raise Refusal("covariance_basis_ambiguous", "Included components require at least one dependency or shared source identifier")
            contributions.append(covariance)
            additive_sources.append((identifier, source_ids))
        elif component["status"] == "excluded":
            if component["covariance"] is not None:
                raise Refusal("covariance_double_counting", "Excluded components must have null covariance")
            if component["represented_by"] is None:
                exclusions.append(identifier)
            else:
                _text(component["represented_by"], "represented_by")
                represented.append(identifier)
        else:
            raise Refusal("covariance_basis_ambiguous", "Component status must be included or excluded")
    if seen_kinds != _KINDS:
        raise Refusal("covariance_basis_missing", "Fitting, reference_standard, and shared_systematic must each be explicitly covered")
    if not contributions:
        raise Refusal("covariance_basis_ambiguous", "At least one included parameter component is required, including for explicitly zero uncertainty")
    for identifier in represented:
        component = by_id[identifier]
        target = by_id.get(component["represented_by"])
        if target is None or target["status"] != "included":
            raise Refusal("covariance_basis_ambiguous", "represented_by must name a directly included component")
        sources = set(component["dependency_ids"]) | set(component["shared_source_ids"])
        target_sources = set(target["dependency_ids"]) | set(target["shared_source_ids"])
        if not sources or not sources <= target_sources:
            raise Refusal("covariance_basis_ambiguous", "Represented source identifiers must be contained in the named included component")
    for name in ("raw", "residual"):
        record = _object(basis[name], _PROVENANCE | ({"scope"} if name == "residual" else set()), set(), name)
        source_ids = _provenance(record, name)
        if not source_ids:
            raise Refusal("covariance_basis_ambiguous", f"{name} requires at least one dependency or shared source identifier")
        if name == "residual" and record["scope"] != "additional_independent_output_residual":
            raise Refusal("covariance_double_counting", "Residual sigma must exclude parameter and raw contributions")
        additive_sources.append((name, source_ids))
        evidence_ids.update(record["evidence_ids"])
        dependency_ids.update(record["dependency_ids"])
        shared_source_ids.update(record["shared_source_ids"])
    for i, (name, sources) in enumerate(additive_sources):
        for other_name, other_sources in additive_sources[:i]:
            if sources & other_sources:
                raise Refusal("unsupported_dependence", f"{name} and {other_name} share source identities; correlated additive components require a joint model")
    for identifier in exclusions:
        component = by_id[identifier]
        sources = set(component["dependency_ids"]) | set(component["shared_source_ids"])
        if any(sources & included_sources for _, included_sources in additive_sources):
            raise Refusal("covariance_basis_ambiguous", "An excluded source already appears in an additive component; name its represented_by component explicitly")
    independence = _object(basis["independence"], {
        "parameter_components", "raw_parameter", "residual_other", "reason", "evidence_ids",
    }, set(), "independence")
    for name in ("parameter_components", "raw_parameter", "residual_other"):
        if independence[name] is not True:
            raise Refusal("unsupported_dependence", f"{name} independence must be explicitly supported; dependence or unknown is not implemented")
    _text(independence["reason"], "independence.reason")
    _ids(independence["evidence_ids"], "independence.evidence_ids", required=True)
    evidence_ids.update(independence["evidence_ids"])
    total = _covariance(binding["parameter_covariance"], 2, "parameter_covariance")
    summed = np.sum(contributions, axis=0)
    # Compare in the declared parameter scales rather than one global tolerance.
    standard_deviation = np.sqrt(np.diag(total))
    zero = standard_deviation == 0
    if np.any(summed[zero, :] != 0) or np.any(summed[:, zero] != 0):
        raise Refusal("covariance_basis_mismatch", "Component sum does not equal parameter_covariance")
    standard_deviation[zero] = 1
    difference = (summed - total) / standard_deviation[:, None] / standard_deviation[None, :]
    if not np.all(np.isfinite(difference)) or np.any(np.abs(difference) > np.finfo(float).eps * len(contributions) * 64):
        raise Refusal("covariance_basis_mismatch", "Included component matrices must sum to parameter_covariance without unallocated covariance")
    # Validate the actual raw matrix before reporting its basis as applicable.
    if not isinstance(raw_covariance, list) or not raw_covariance:
        raise Refusal("covariance_basis_ambiguous", "Raw covariance must be explicit and non-empty")
    _covariance(raw_covariance, len(raw_covariance), "raw_covariance")
    return {
        "scope": "declared_components_only", "completeness_claimed": False,
        "excluded_component_ids": exclusions, "represented_component_ids": represented,
        "evidence_ids": sorted(evidence_ids), "dependency_ids": sorted(dependency_ids),
        "shared_source_ids": sorted(shared_source_ids),
    }


def calibrate_v2(inputs: dict) -> dict:
    _object(inputs, {"assembly_toml", "records", "raw_covariance"}, {"calibration"}, "inputs")
    if not isinstance(inputs["records"], list) or not 1 <= len(inputs["records"]) <= MAX_RECORDS:
        raise ValueError(f"records must contain between 1 and {MAX_RECORDS} observations")
    if not isinstance(inputs["raw_covariance"], list) or len(inputs["raw_covariance"]) != len(inputs["records"]):
        raise ValueError("raw_covariance dimensions must match records")
    binding = inputs.get("calibration")
    if binding is None:
        raise Refusal("calibration_missing", "An explicit calibration binding is required")
    if not isinstance(binding, dict) or binding.get("schema") != BINDING_SCHEMA:
        raise Refusal("calibration_mismatch", f"Expected {BINDING_SCHEMA}")
    summary = validate_covariance_basis(binding, inputs["raw_covariance"])
    projected = deepcopy(inputs)
    del projected["calibration"]["covariance_basis"]
    projected["calibration"]["schema"] = "rci-calibration-binding.v1"
    data = calibrate(projected)
    cal = loads(inputs["assembly_toml"]).calibration
    basis = deepcopy(binding["covariance_basis"])
    basis_digest = canonical_digest(basis)
    uncertainty = data["uncertainty"]
    uncertainty.update({
        "parameterization": {
            "name": "scale_zero_raw", "order": ["scale", "zero_raw"],
            "values": list(cal.theta), "units": uncertainty["parameter_units"],
        },
        "covariance_basis": basis, "covariance_basis_digest": basis_digest,
        "covariance_coverage": summary,
        "dependency_ids": summary["dependency_ids"], "shared_source_ids": summary["shared_source_ids"],
    })
    uncertainty_digest = canonical_digest(uncertainty)
    calibration_digest = canonical_digest(binding)
    for record in data["records"]:
        del record["derived_evidence_digest"]
        record.update({
            "schema": "measurement-record.v2", "calibration_digest": calibration_digest,
            "uncertainty_digest": uncertainty_digest, "covariance_basis_digest": basis_digest,
            "acquisition_applicability": {
                "observed_at": record["observed_at"], "applicable": True,
                "valid_from": binding["valid_from"], "valid_until": binding["valid_until"],
                "basis": "caller_declared_acquisition_time",
            },
        })
        record["derived_evidence_digest"] = canonical_digest(record)
    data.update({
        "schema": "measurement-record-batch.v2", "uncertainty_digest": uncertainty_digest,
        "calibration": deepcopy(binding), "calibration_digest": calibration_digest,
        "covariance_basis_digest": basis_digest,
    })
    return data


def handle_request(request: object) -> dict:
    try:
        _object(request, {"schema", "operation_id", "inputs"}, set(), "request")
        if request["schema"] != REQUEST_SCHEMA or request["operation_id"] != OPERATION_ID:
            raise ValueError("Unsupported request schema or operation_id")
        return {"schema": RESPONSE_SCHEMA, "status": "ok", "data": calibrate_v2(request["inputs"])}
    except Refusal as exc:
        return {"schema": RESPONSE_SCHEMA, "status": "refused", "refusal": {
            "code": "calibration_unavailable", "reason_code": exc.reason, "message": str(exc),
        }}
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as exc:
        return {"schema": RESPONSE_SCHEMA, "status": "refused", "refusal": {
            "code": "invalid_request", "message": str(exc),
        }}
