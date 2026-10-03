"""Evidence-bound numerical comparison/assertions; no physical verification claim."""
from __future__ import annotations

import math
from typing import Any

from .control_contracts import (
    MAX_SAMPLES, _base, _vector, content_ref, detached, keys, number, record, text,
    validate_artifact, validate_observation, validate_state,
)

STATUSES = {"PASS", "FAIL", "INDETERMINATE"}
SCOPE = "declared_numerical_condition_only"


def _series(values: list[dict]) -> tuple | None:
    if type(values) is not list or len(values) > MAX_SAMPLES:
        raise ValueError("Require a bounded observation series")
    for value in values:
        validate_observation(value)
    if not values:
        return None
    signature = None
    previous = None
    for value in values:
        identity = value["identity"]
        current = (identity["model_id"], identity["entity_id"], value["quantity"],
                   value["unit"], value["frame"], value["clock"]["id"])
        stream = (identity["execution_id"], value["provenance"]["provider"], value["provenance"]["semantics"])
        if signature is not None and signature != (current, stream):
            raise ValueError("One comparison series must describe one quantity and execution")
        signature = (current, stream)
        stamp = value["clock"]["time_s"]
        if previous is not None and stamp <= previous:
            raise ValueError("Observation timestamps must be strictly increasing")
        previous = stamp
    return signature[0]


def _comparison(left: list, right: list, policy: dict) -> dict:
    keys(policy, {"atol", "rtol"})
    if number(policy["atol"]) < 0 or number(policy["rtol"]) < 0:
        raise ValueError("Tolerances must be nonnegative")
    a, b = _series(left), _series(right)
    unknown = {"status": "INDETERMINATE", "sample_count": 0, "component_count": 0,
               "metrics": None, "unit": None, "reason": "missing_evidence"}
    if a is None or b is None:
        return unknown
    if a != b:
        return {**unknown, "reason": "model_entity_quantity_unit_frame_or_clock_mismatch"}
    if len(left) != len(right) or [x["clock"]["time_s"] for x in left] != [x["clock"]["time_s"] for x in right]:
        return {**unknown, "reason": "time_grid_mismatch"}
    errors, excess = [], []
    width = None
    for x, y in zip(left, right):
        av, bv = _vector(x["value"]), _vector(y["value"])
        # A scalar and a one-element vector are distinct shapes.
        shape = (type(x["value"]) is list, len(av))
        if shape != (type(y["value"]) is list, len(bv)) or (width is not None and shape != width):
            return {**unknown, "reason": "shape_mismatch"}
        width = shape
        if any(value is None for value in av + bv):
            return {**unknown, "reason": "missing_sample"}
        for u, v in zip(av, bv):
            error = abs(u - v)
            tolerance = policy["atol"] + policy["rtol"] * abs(v)
            if not math.isfinite(error) or not math.isfinite(tolerance):
                return {**unknown, "reason": "numeric_range_exceeded"}
            errors.append(error)
            excess.append(error - tolerance)
    try:
        metrics = {"rmse": number(math.hypot(*errors) / math.sqrt(len(errors))),
                   "max_abs_error": number(max(errors)), "max_tolerance_excess": number(max(excess))}
    except (ValueError, OverflowError):
        return {**unknown, "reason": "numeric_range_exceeded"}
    passed = max(excess) <= 0
    return {"status": "PASS" if passed else "FAIL", "sample_count": len(left),
            "component_count": len(errors), "unit": a[3], "metrics": metrics,
            "reason": "within_tolerance" if passed else "tolerance_exceeded"}


def compare(left: list[dict], right: list[dict], *, atol: float, rtol: float = 0.0) -> dict:
    """Componentwise RMS/max error, exact timestamp grid. Right side is the reference.

    Full evidence is retained. No interpolation, unit conversion, missing-value
    imputation, independence assumption or statistical-confidence interpretation.
    """
    left, right = detached(left), detached(right)
    policy = {"atol": atol, "rtol": rtol}
    return record("comparison", left=left, right=right, policy=policy,
                  outcome=_comparison(left, right, policy), claim_scope=SCOPE)


def validate_comparison(value: dict) -> None:
    _base(value, "comparison", {"left", "right", "policy", "outcome", "claim_scope"})
    if value["claim_scope"] != SCOPE or value["outcome"] != _comparison(value["left"], value["right"], value["policy"]):
        raise ValueError("Retained comparison contradicts its evidence or policy")


def _policy(kind: str, policy: dict) -> None:
    expected = {"less_than": {"limit", "unit"}, "bounded": {"minimum", "maximum", "unit"},
                "conserved": {"tolerance", "unit"}, "close_to": set(),
                "covariance_positive_definite": {"quantity_ids", "units", "frame", "margin"}}
    if kind not in expected:
        raise ValueError("Unknown assertion kind")
    keys(policy, expected[kind])
    for key in ("limit", "minimum", "maximum", "tolerance", "margin"):
        if key in policy:
            number(policy[key])
    if "unit" in policy:
        text(policy["unit"])
    if kind == "bounded" and policy["minimum"] > policy["maximum"]:
        raise ValueError("Assertion bounds are reversed")
    if kind == "conserved" and policy["tolerance"] < 0:
        raise ValueError("Conservation tolerance must be nonnegative")
    if kind == "covariance_positive_definite":
        text(policy["frame"])
        if policy["margin"] <= 0:
            raise ValueError("PD numerical margin must be positive")
        if type(policy["quantity_ids"]) is not list or type(policy["units"]) is not list:
            raise ValueError("PD assertion needs ordered axis/units bindings")
        if not policy["quantity_ids"] or len(policy["quantity_ids"]) != len(policy["units"]):
            raise ValueError("PD axis/units count mismatch")
        for value in policy["quantity_ids"] + policy["units"]:
            text(value)


def _evaluate(kind: str, evidence: Any, policy: dict) -> dict:
    _policy(kind, policy)
    unknown = {"status": "INDETERMINATE", "reason": "missing_evidence"}
    if evidence is None:
        return unknown
    if kind == "close_to":
        validate_comparison(evidence)
        return {"status": evidence["outcome"]["status"], "reason": evidence["outcome"]["reason"]}
    if kind == "covariance_positive_definite":
        from .core.covariance import validate_covariance_artifact
        import numpy as np
        validate_covariance_artifact(evidence, expected_quantity_ids=policy["quantity_ids"],
                                    expected_units=policy["units"], expected_frame=policy["frame"])
        diagonal = [row[i] for i, row in enumerate(evidence["matrix"])]
        if any(value == 0 for value in diagonal):
            return {"status": "FAIL", "reason": "singular_covariance"}
        scales = [math.sqrt(value) for value in diagonal]
        normalized = np.array([[(entry / scales[i]) / scales[j] for j, entry in enumerate(row)]
                               for i, row in enumerate(evidence["matrix"])])
        try:
            low = min(float(np.linalg.eigvalsh(normalized, UPLO=side).min()) for side in ("L", "U"))
        except np.linalg.LinAlgError:
            return {**unknown, "reason": "eigensolver_did_not_converge"}
        if not math.isfinite(low):
            return {**unknown, "reason": "nonfinite_eigenvalue"}
        return {"status": "PASS" if low > policy["margin"] else "INDETERMINATE",
                "reason": "positive_definite_above_margin" if low > policy["margin"] else "below_numerical_pd_margin"}
    signature = _series(evidence)
    if signature is None:
        return unknown
    if signature[3] != policy["unit"]:
        return {**unknown, "reason": "unit_mismatch"}
    vectors = [_vector(value["value"]) for value in evidence]
    if any(value is None for vector in vectors for value in vector):
        return {**unknown, "reason": "missing_sample"}
    shapes = {(type(value["value"]) is list, len(vector)) for value, vector in zip(evidence, vectors)}
    if len(shapes) != 1:
        return {**unknown, "reason": "shape_mismatch"}
    if kind == "conserved" and len(vectors) < 2:
        return {**unknown, "reason": "conservation_requires_two_samples"}
    if kind == "less_than":
        passed = all(value < policy["limit"] for vector in vectors for value in vector)
    elif kind == "bounded":
        passed = all(policy["minimum"] <= value <= policy["maximum"] for vector in vectors for value in vector)
    else:
        passed = all(abs(value - initial) <= policy["tolerance"] for vector in vectors for value, initial in zip(vector, vectors[0]))
    return {"status": "PASS" if passed else "FAIL", "reason": "condition_satisfied" if passed else "condition_violated"}


def verify(name: str, kind: str, evidence: Any, **policy: Any) -> dict:
    """An ordinary evidence-backed assertion, not a CIW verification occurrence."""
    evidence, policy = detached(evidence), detached(policy)
    return record("verification", name=text(name), kind=kind, evidence=evidence, policy=policy,
                  outcome=_evaluate(kind, evidence, policy), claim_scope=SCOPE,
                  verification_id=None, state_admission="not_performed")


def validate_verification(value: dict) -> None:
    _base(value, "verification", {"name", "kind", "evidence", "policy", "outcome", "claim_scope",
                                 "verification_id", "state_admission"})
    text(value["name"])
    if (value["claim_scope"] != SCOPE or value["verification_id"] is not None
            or value["state_admission"] != "not_performed"
            or value["outcome"] != _evaluate(value["kind"], value["evidence"], value["policy"])):
        raise ValueError("Assertion outcome or authority contradicts its retained evidence")


def overall(checks: list[dict]) -> str:
    for value in checks:
        validate_verification(value)
    statuses = [value["outcome"]["status"] for value in checks]
    if "FAIL" in statuses:
        return "FAIL"
    return "PASS" if statuses and all(status == "PASS" for status in statuses) else "INDETERMINATE"


def inspect_record(value: dict) -> dict:
    """Data-only validation. Never import a provider based on saved content."""
    schema = value.get("schema") if type(value) is dict else None
    validators = {"ciw.state.v1": validate_state, "ciw.observation.v1": validate_observation,
                  "ciw.artifact.v1": validate_artifact, "ciw.comparison.v1": validate_comparison,
                  "ciw.verification.v1": validate_verification}
    if schema in validators:
        validators[schema](value)
    elif schema == "ciw.check-report.v1":
        from .check_suite import validate_report
        validate_report(value)
    elif schema == "ciw.check-plan.v1":
        from .check_suite import validate_plan
        from .core.identities import content_identity
        validate_plan(value)
        return {"schema": schema, "plan_id": content_identity(value),
                "integrity": "validated_declaration", "outcome": {"status": "not_evaluated"},
                "physical_validation": "not_performed", "state_admission": "not_performed",
                "record": detached(value)}
    elif schema in {"ciw.thermal-math-inspection.v1", "ciw.thermal-math-inspection.v2"}:
        from .math_inspector import validate_report
        validate_report(value)
    elif schema == "ciw.thermal-observation-view.v1":
        from .scientific_observations import validate_view
        validate_view(value)
    elif schema == "ciw.observation-stream.v1":
        from .control_plane import ObservationBus
        _base(value, "observation-stream", {"observations"})
        if type(value["observations"]) is not list or len(value["observations"]) > MAX_SAMPLES:
            raise ValueError("Invalid retained observation stream")
        bus = ObservationBus(max(1, len(value["observations"])))
        for item in value["observations"]:
            bus.publish(item)
    elif schema == "ciw.parameter-space.v1":
        from .control_plane import ParameterSpace
        ParameterSpace.from_dict(value)
    elif schema == "ciw.experiment.v1":
        from .control_plane import _experiment
        _experiment(value)
    elif schema == "ciw.checkpoint.v1":
        from .control_checkpoint import validate_checkpoint
        validate_checkpoint(value)
    elif schema == "ciw.graph-run.v1":
        _inspect_graph(value)
    else:
        raise ValueError("Unsupported NET control record schema")
    return {"schema": schema, "record_digest": value["record_digest"], "integrity": "checked",
            "outcome": ({"status": value["summary"]["status"]} if schema == "ciw.check-report.v1"
                        else value.get("outcome", {"status": value.get("status", "not_evaluated")})),
            "physical_validation": "not_performed", "state_admission": "not_performed",
            "reproducibility": "not_established_by_inspection", "record": detached(value)}


def _inspect_graph(value: dict) -> None:
    """Check retained dispatch bindings, not scientific payloads or source authenticity.

    The separate Session workspace reader remains authoritative for run.v1 and
    operation-specific data validation. Hashes cannot authenticate a producer.
    """
    from .control_plane import _plan_contracts, _outputs
    from .operations.runner import check_seal
    import re
    _base(value, "graph-run", {"experiment", "contracts", "session_id", "source_evidence_id", "order", "nodes", "status"})
    graph, contracts = value["experiment"], value["contracts"]
    order = _plan_contracts(graph, contracts)
    text(value["session_id"])
    content_ref(value["source_evidence_id"])
    keys(value["nodes"], set(order))
    if value["order"] != order:
        raise ValueError("Graph run order differs from its experiment")
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    outputs, execution_ids, result_ids = {}, set(), set()
    for name in order:
        node, item = nodes[name], value["nodes"][name]
        if type(item) is not dict:
            raise ValueError("Graph node outcome must be an object")
        deps = set(node["depends_on"]) | {edge["node_id"] for edge in node["inputs"].values()}
        blocked = sorted(dep for dep in deps if value["nodes"][dep]["status"] != "completed")
        if blocked:
            if item != {"status": "blocked", "dependencies": blocked}:
                raise ValueError("Graph dispatched a blocked dependency")
            continue
        if item.get("status") == "error":
            keys(item, {"status", "refusal"})
            keys(item["refusal"], {"code", "message"})
            for field in item["refusal"].values():
                text(field)
            continue
        retained = item
        if item.get("status") == "output_rejected":
            keys(item, {"status", "reason", "retained"})
            text(item["reason"])
            retained = item["retained"]
            if retained.get("status") != "completed":
                raise ValueError("Output rejection requires an original completed execution")
        keys(retained, {"status", "execution", "result"})
        execution, result = retained["execution"], retained["result"]
        check_seal(execution)
        if (execution.get("schema") != "ciw.execution.v1"
                or execution.get("operation_id") != node["operation_id"]
                or execution.get("evidence_id") != value["source_evidence_id"]
                or execution.get("status") != retained["status"]):
            raise ValueError("Graph execution binding mismatch")
        eid = execution.get("execution_id")
        if type(eid) is not str or not re.fullmatch(r"execution-[0-9a-f]{32}", eid) or eid in execution_ids:
            raise ValueError("Duplicate or invalid execution occurrence")
        execution_ids.add(eid)
        parameters = {**graph["parameters"], **node["parameters"]}
        for key, edge in node["inputs"].items():
            parameters[key] = outputs[edge["node_id"]][edge["port"]]
        # Analysis selection defaults belong to CIW, not this graph dispatcher.
        actual = execution.get("parameters")
        if type(actual) is not dict:
            raise ValueError("Missing execution parameters")
        extras = set(actual) - set(parameters)
        if extras - {"channel", "interval_s"} or any(actual.get(key) != val for key, val in parameters.items()):
            raise ValueError("Execution parameters contradict the captured graph inputs")
        if any(actual[key] != execution.get(key) for key in extras):
            raise ValueError("Selection defaults contradict the execution")
        if retained["status"] == "refused":
            if result is not None or execution.get("result_id") is not None:
                raise ValueError("A refused execution cannot have a result")
            refusal = execution.get("refusal")
            if type(refusal) is not dict or not {"code", "message"} <= set(refusal) <= {"code", "message", "reason_code"}:
                raise ValueError("Refused execution must retain a reason")
            for field in refusal.values():
                text(field)
            continue
        if retained["status"] != "completed" or "refusal" in execution:
            raise ValueError("Unsupported graph execution status")
        check_seal(result)
        rid = result.get("result_id")
        if (result.get("schema") != "ciw.operation-result.v1" or type(rid) is not str
                or not re.fullmatch(r"result-[0-9a-f]{32}", rid) or rid in result_ids
                or rid != execution.get("result_id")):
            raise ValueError("Duplicate or invalid result occurrence")
        result_ids.add(rid)
        for key in ("execution_id", "operation_id", "evidence_id", "run_id", "runtime", "parameters",
                    "created_at", "selection_revision", "channel", "interval_s"):
            if result.get(key) != execution.get(key):
                raise ValueError(f"Graph execution/result {key} mismatch")
        if result.get("verification_id") is not None or result.get("verification_status") != "not_verified":
            raise ValueError("Ordinary graph result cannot claim a verification occurrence")
        try:
            extracted = _outputs(retained, contracts[node["operation_id"]])
        except (KeyError, TypeError, ValueError) as exc:
            if item["status"] != "output_rejected" or item["reason"] != str(exc):
                raise ValueError("Invalid output cannot be marked completed") from exc
        else:
            if item["status"] != "completed":
                raise ValueError("Retained output rejection has no supporting mismatch")
            outputs[name] = extracted
    expected = "completed" if all(item["status"] == "completed" for item in value["nodes"].values()) else "incomplete"
    if value["status"] != expected:
        raise ValueError("Graph aggregate status contradicts its nodes")
