"""Retained heading-candidate comparison over the existing curved-path operation.

The provider owns the transfer, validity and covariance calculations. This
module owns bounded candidate orchestration and accounting on retained values.
It introduces no operation, execution, proof, admission or workspace format.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import math
from pathlib import Path
import re

from .adapters.subprocess import _json
from .geodesic_reference import GeodesicReferenceWorkflow, FRAME
from .linear_response import response_arithmetic
from .telemetry import canonical, digest

SCHEMA = "ciw.curved-path-study.v1"
REQUEST_SCHEMA = "ciw.curved-path-study-request.v1"
KIND = "curved-path-transfer"
OPERATION = "ciw.curved-path-transfer.v1"
MAX_BYTES = 256 * 1024
AUTHORITY = {
    "kind": "retained_curved_path_candidate_comparison",
    "numerical_replay": "not_performed_by_inspection",
    "physical_validation": "not_established", "state_admission": "not_performed",
    "hardware_actuation": "not_performed", "optimality": "not_claimed",
}


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("Curved-path study requires exactly the declared fields")


def _same(actual, expected, message):
    if canonical(actual) != canonical(expected):
        raise ValueError(message)


def _bounded(value):
    try:
        raw = canonical(value)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ValueError("Study requires bounded finite JSON") from exc
    if len(raw) > MAX_BYTES:
        raise ValueError("Study exceeds its byte budget")
    return raw


def _identifier(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value) is None:
        raise ValueError("Study and candidate identifiers require 1..64 letters, digits, dots, underscores or hyphens")


def _number(value, bound):
    try:
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > bound:
            raise ValueError("Study numbers must be finite, non-Boolean and within bounds")
        return float(value)
    except OverflowError as exc:
        raise ValueError("Study number exceeds its domain") from exc


def _request(request):
    _bounded(request)
    _keys(request, {"schema", "study_id", "baseline_bundle_id", "candidates", "sample_index", "limits"})
    if request["schema"] != REQUEST_SCHEMA:
        raise ValueError("Unsupported curved-path study request")
    _identifier(request["study_id"])
    if type(request["baseline_bundle_id"]) is not str or not 1 <= len(request["baseline_bundle_id"]) <= 128:
        raise ValueError("Select an exact retained baseline bundle identity")
    if type(request["sample_index"]) is not int or not 0 <= request["sample_index"] < 128:
        raise ValueError("Select an integer sample index within the bounded grid")
    candidates = request["candidates"]
    if type(candidates) is not list or not 1 <= len(candidates) <= 8:
        raise ValueError("Declare one to eight heading candidates")
    identities = {"baseline"}
    for candidate in candidates:
        _keys(candidate, {"candidate_id", "initial_heading_radian"})
        _identifier(candidate["candidate_id"])
        if candidate["candidate_id"] in identities:
            raise ValueError("Candidate identities must be unique and cannot be baseline")
        identities.add(candidate["candidate_id"])
        _number(candidate["initial_heading_radian"], .1)
    limits = request["limits"]
    _keys(limits, {"max_abs_lateral", "max_abs_heading", "units"})
    for key in ("max_abs_lateral", "max_abs_heading"):
        if _number(limits[key], 1e6) <= 0:
            raise ValueError("Sample comparison limits must be positive")
    _keys(limits["units"], {"length", "angle"})
    if limits["units"]["length"] not in ("m", "mm", "normalized_length") or limits["units"]["angle"] != "radian":
        raise ValueError("Declare compatible length and radian units")
    return deepcopy(request)


def make_request(baseline_bundle_id, candidates, *, sample_index, limits, study_id):
    """Build a heading-only request; run preflight also checks retained validity."""
    return _request({"schema": REQUEST_SCHEMA, "study_id": study_id,
        "baseline_bundle_id": baseline_bundle_id, "candidates": candidates,
        "sample_index": sample_index, "limits": limits})


def _resolve(workbench, bundle_id):
    summaries = [row for row in workbench.list_bundles() if row["bundle_id"] == bundle_id]
    if len(summaries) != 1 or summaries[0]["kind"] != KIND or summaries[0]["operation_id"] != OPERATION:
        raise ValueError("Study requires an exact retained curved-path-transfer bundle")
    descriptor = workbench.get_source(summaries[0]["source_id"])
    bundle = workbench.get_bundle(bundle_id)
    workflow = GeodesicReferenceWorkflow(KIND)
    raw = workflow._validate(bundle)  # Structural validation; never binds a runtime.
    _same(base64.b64decode(descriptor["bytes_b64"], validate=True).hex(), raw.hex(),
          "Retained source bytes differ from the selected bundle")
    source = workflow._source(raw)
    step = bundle["steps"][0]
    refs = {"source_id": descriptor["source_id"], "evidence_id": descriptor["evidence_id"],
        "bundle_id": bundle_id, "operation_id": step["operation_id"],
        "execution_id": step["execution_id"], "result_id": step["result_id"],
        "numerical_result_id": step["numerical_result_id"],
        "verification_id": bundle["verification"]["verification_id"],
        "runtime_digest": digest(workflow._runtime_projection(bundle["runtimes"]["csg"]))}
    return source, step["result"]["data"], refs


def _preflight(workbench, request):
    request = _request(request)
    source, data, refs = _resolve(workbench, request["baseline_bundle_id"])
    if source["initial_perturbation"][0] != 0:
        raise ValueError("This study requires zero initial lateral displacement; native validity covers heading only")
    if request["sample_index"] >= len(source["arclength"]):
        raise ValueError("Selected sample is outside the retained arclength grid")
    _same(request["limits"]["units"], source["units"], "Limit units must match the retained source without conversion")
    limit = data["record"]["validity"]["max_heading"]
    headings = [source["initial_perturbation"][1]] + [c["initial_heading_radian"] for c in request["candidates"]]
    if any(abs(value) > limit for value in headings):
        raise ValueError("A heading lies outside the retained native heading validity bound")
    # Validate every derived declaration before any source is added or executed.
    for candidate in request["candidates"]:
        GeodesicReferenceWorkflow(KIND)._source(canonical(_candidate_source(source, request, candidate)))
    return request, source, data, refs


def _candidate_source(source, request, candidate):
    value = deepcopy(source)
    value["experiment_id"] = request["study_id"] + "/" + candidate["candidate_id"]
    value["initial_perturbation"] = [0, candidate["initial_heading_radian"]]
    return value


def _summary(data, limits):
    lateral = max(abs(value) for value in data["separation"])
    heading = max(abs(value) for value in data["heading_change"])
    record = data["record"]
    return {"max_abs_lateral": lateral, "max_abs_heading": heading,
        "units": deepcopy(record["units"]),
        "sampled_limits": {"lateral": "within" if lateral <= limits["max_abs_lateral"] else "exceeds",
                           "heading": "within" if heading <= limits["max_abs_heading"] else "exceeds"},
        "endpoint": {"state": [data["separation"][-1], data["heading_change"][-1]],
                     "covariance": deepcopy(data["propagated_covariance"][-1])},
        "max_abs_determinant_drift": max(abs(value - 1) for value in data["determinant"]),
        "validity": deepcopy(record["validity"]), "resolution": deepcopy(record["resolution"]),
        "calibration": deepcopy(record["calibration"]),
        "covariance_scope": "conditional_marginal_at_each_arclength"}


def _semantics(source, index):
    unit = source["units"]["length"]
    return {"coordinate_order": ["lateral", "heading"], "units": [unit, "radian"],
        "jacobian_units": [["1", unit + "/radian"], ["radian/" + unit, "1"]],
        "frame": FRAME, "independent_variable": "arclength", "sample_index": index,
        "sample_arclength": source["arclength"][index], "scope": "same_linearized_model_consistency",
        "study_ancestry": "declared_parent_digest_not_resolved_by_inspection",
        "covariance": "assumed_conditional_marginals; joint_cross_arclength_and_candidate_covariance_not_supplied",
        "limits_scope": "predicted_samples_only_without_uncertainty_or_integration_error_margin"}


def _response(source, baseline, candidate, heading, index):
    record = baseline["record"]
    return response_arithmetic(
        [baseline["separation"][index], baseline["heading_change"][index]],
        [[record["a"][index], record["b"][index]], [record["a_rate"][index], record["b_rate"][index]]],
        [0, heading - source["initial_perturbation"][1]],
        [candidate["separation"][index], candidate["heading_change"][index]])


def _rows(workbench, request, baseline_source, baseline_data, baseline_refs, bundle_ids):
    if len(bundle_ids) != len(request["candidates"]):
        raise ValueError("Each candidate needs its own retained occurrence")
    rows = []
    seen = {field: {baseline_refs[field]} for field in ("bundle_id", "execution_id", "result_id")}
    for candidate, bundle_id in zip(request["candidates"], bundle_ids):
        source, data, refs = _resolve(workbench, bundle_id)
        _same(source, _candidate_source(baseline_source, request, candidate), "Candidate source differs from the fixed study declaration")
        if refs["runtime_digest"] != baseline_refs["runtime_digest"]:
            raise ValueError("Candidate runtime differs from the baseline computational identity")
        for field, values in seen.items():
            if refs[field] in values:
                raise ValueError("Each candidate needs distinct bundle, execution and result occurrences")
            values.add(refs[field])
        rows.append({"candidate_id": candidate["candidate_id"], "references": refs,
            "summary": _summary(data, request["limits"]),
            "response": _response(baseline_source, baseline_data, data, candidate["initial_heading_radian"], request["sample_index"])})
    return rows


def _assemble_study(workbench, request, bundle_ids, replay_of=None):
    request, source, data, refs = _preflight(workbench, request)
    value = {"schema": SCHEMA, "request": request,
        "baseline": {"candidate_id": "baseline", "references": refs, "summary": _summary(data, request["limits"])},
        "candidates": _rows(workbench, request, source, data, refs, bundle_ids),
        "semantics": _semantics(source, request["sample_index"]), "authority": deepcopy(AUTHORITY), "replay_of": replay_of}
    value["study_digest"] = digest(value)
    _bounded(value)
    return value


def run_study(workbench, request):
    """Execute every heading through the native operation; retain completed runs.

    This is not an atomic multi-execution transaction. If a later run refuses,
    earlier retained occurrences remain available; no completed study is emitted.
    """
    request, source, _, _ = _preflight(workbench, request)
    bundles = []
    for candidate in request["candidates"]:
        raw = canonical(_candidate_source(source, request, candidate))
        descriptor = workbench.add_source({"kind": KIND,
            "label": request["study_id"] + "/" + candidate["candidate_id"],
            "bytes_b64": base64.b64encode(raw).decode("ascii")})
        result = workbench.execute({"operation_id": OPERATION, "source_id": descriptor["source_id"]})
        bundles.append(result["bundle_id"])
    return _assemble_study(workbench, request, bundles)


def inspect_study(workbench, record):
    """Check references and arithmetic from retained values, without a provider."""
    _bounded(record)
    _keys(record, {"schema", "request", "baseline", "candidates", "semantics", "authority", "replay_of", "study_digest"})
    if record["schema"] != SCHEMA or record["study_digest"] != digest({k: v for k, v in record.items() if k != "study_digest"}):
        raise ValueError("Study schema or content digest mismatch")
    replay_of = record["replay_of"]
    if replay_of is not None and (type(replay_of) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", replay_of) is None):
        raise ValueError("Replay parent must be a study content digest")
    request, source, data, refs = _preflight(workbench, record["request"])
    _same(record["authority"], AUTHORITY, "Study authority cannot be elevated")
    _same(record["semantics"], _semantics(source, request["sample_index"]), "Study meaning differs from retained declarations")
    _same(record["baseline"], {"candidate_id": "baseline", "references": refs,
        "summary": _summary(data, request["limits"])}, "Baseline reference or summary differs from retained data")
    rows = record["candidates"]
    if type(rows) is not list or len(rows) != len(request["candidates"]):
        raise ValueError("Study candidates differ from request")
    for row in rows:
        _keys(row, {"candidate_id", "references", "summary", "response"})
        _keys(row["references"], refs.keys())
    if replay_of is not None:
        for row in [record["baseline"], *rows]:
            native = workbench.get_bundle(row["references"]["bundle_id"])
            if len(native.get("replay_receipts", [])) != 1:
                raise ValueError("A replay study requires actual native replay receipts for every occurrence")
    expected = _rows(workbench, request, source, data, refs, [row["references"]["bundle_id"] for row in rows])
    _same(rows, expected, "Candidate references, summaries or response accounting differ from retained values")
    return deepcopy(record)


def save_study(path, workbench, record):
    raw = _bounded(inspect_study(workbench, record))
    with Path(path).open("xb") as stream:
        stream.write(raw)


def load_study(path, workbench):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Study exceeds its byte budget")
    value = _json(raw)
    if raw != _bounded(value):
        raise ValueError("Retained study must use canonical JSON bytes")
    return inspect_study(workbench, value)


def replay_study(workbench, record):
    """Fresh native occurrences using the original exact sources and runtime pins."""
    original = inspect_study(workbench, record)
    baseline = workbench.replay({"bundle_id": original["baseline"]["references"]["bundle_id"]})["bundle"]
    bundles = [workbench.replay({"bundle_id": row["references"]["bundle_id"]})["bundle"]["bundle_id"]
               for row in original["candidates"]]
    request = deepcopy(original["request"])
    request["baseline_bundle_id"] = baseline["bundle_id"]
    return _assemble_study(workbench, request, bundles, original["study_digest"])
