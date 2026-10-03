"""Needle V1: immutable local intervention with dependency-closure recomputation.

V1 targets one existing node parameter in a retained ciw.experiment.v1 graph.
It creates a new candidate experiment, computes the declared dependency closure,
reuses unaffected retained results, reruns only the closure, and emits a typed
delta projection.

Needle does not mutate canonical state, rewrite the baseline run, infer causal
effects from dependency edges, or authorize execution beyond the caller-supplied
bound registry/session.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import math
from typing import Any
import uuid

from .control_checks import inspect_record
from .control_contracts import content_ref, detached, keys, record, text
from .control_plane import _outputs, experiment, plan_graph
from .core.identities import content_identity
from .operations.runner import check_seal

MAX_DELTA_PATHS = 128


def _bounded_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 16:
        raise ValueError("Needle replacement JSON exceeds nesting bound")
    if value is None or type(value) in (str, bool):
        if type(value) is str and len(value) > 8192:
            raise ValueError("Needle replacement string exceeds bound")
        return deepcopy(value)
    if type(value) in (int, float):
        if isinstance(value, bool):
            return value
        numeric = float(value)
        if not math.isfinite(numeric) or abs(numeric) > 1e150:
            raise ValueError("Needle replacement number must be finite/bounded")
        return deepcopy(value)
    if type(value) is list:
        if len(value) > 4096:
            raise ValueError("Needle replacement list exceeds bound")
        return [_bounded_json(item, depth=depth + 1) for item in value]
    if type(value) is dict:
        if len(value) > 1024:
            raise ValueError("Needle replacement object exceeds bound")
        result = {}
        for key, item in value.items():
            key = text(key)
            result[key] = _bounded_json(item, depth=depth + 1)
        return result
    raise ValueError("Needle replacement must be bounded JSON data")


def _target(value: Any) -> dict:
    keys(value, {"kind", "node_id", "parameter"})
    if value["kind"] != "NODE_PARAMETER":
        raise ValueError("Needle V1 supports NODE_PARAMETER targets only")
    return {
        "kind": "NODE_PARAMETER",
        "node_id": text(value["node_id"]),
        "parameter": text(value["parameter"]),
    }


def plan_from_spec(baseline_graph_run: dict, spec: dict) -> dict:
    inspect_record(baseline_graph_run)
    if baseline_graph_run["schema"] != "ciw.graph-run.v1":
        raise ValueError("Needle baseline must be a retained graph-run")
    if baseline_graph_run["status"] != "completed":
        raise ValueError("Needle V1 requires a completed baseline graph-run")
    keys(spec, {"needle_id", "target", "replacement", "propagation"})
    if spec["propagation"] != {
        "relation": "DEPENDENCY",
        "scope": "DESCENDANTS_INCLUSIVE",
    }:
        raise ValueError("Needle V1 propagation must be DEPENDENCY/DESCENDANTS_INCLUSIVE")
    target = _target(spec["target"])
    graph = baseline_graph_run["experiment"]
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    if target["node_id"] not in nodes:
        raise ValueError("Needle target node is absent from baseline experiment")
    node = nodes[target["node_id"]]
    if target["parameter"] not in node["parameters"]:
        raise ValueError("Needle V1 can replace only an existing node parameter")
    replacement = _bounded_json(spec["replacement"])
    if replacement == node["parameters"][target["parameter"]]:
        raise ValueError("Needle replacement must differ from the baseline value")
    value = record(
        "needle-plan",
        needle_id=text(spec["needle_id"]),
        baseline_graph_run_ref=baseline_graph_run["record_digest"],
        target=target,
        before=deepcopy(node["parameters"][target["parameter"]]),
        replacement=replacement,
        propagation=deepcopy(spec["propagation"]),
        claims={
            "local_intervention": True,
            "dependency_not_causality": True,
            "baseline_mutated": False,
            "canonical_state_mutated": False,
            "execution_authority": False,
        },
    )
    validate_plan(value)
    return value


def validate_plan(value: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "needle_id", "baseline_graph_run_ref",
        "target", "before", "replacement", "propagation", "claims",
    })
    if value["schema"] != "ciw.needle-plan.v1":
        raise ValueError("Wrong Needle plan schema")
    check_seal(value)
    text(value["needle_id"])
    content_ref(value["baseline_graph_run_ref"])
    _target(value["target"])
    _bounded_json(value["before"])
    _bounded_json(value["replacement"])
    if value["before"] == value["replacement"]:
        raise ValueError("Needle before/replacement values must differ")
    if value["propagation"] != {
        "relation": "DEPENDENCY",
        "scope": "DESCENDANTS_INCLUSIVE",
    }:
        raise ValueError("Unsupported Needle propagation policy")
    if value["claims"] != {
        "local_intervention": True,
        "dependency_not_causality": True,
        "baseline_mutated": False,
        "canonical_state_mutated": False,
        "execution_authority": False,
    }:
        raise ValueError("Needle plan claims exceed intervention authority")
    return detached(value)


def dependency_closure(graph: dict, target_node_id: str) -> list[str]:
    from .control_plane import _experiment
    order = _experiment(graph)
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    if target_node_id not in nodes:
        raise ValueError("Needle target node is absent from experiment")
    successors = {name: set() for name in nodes}
    for node in graph["nodes"]:
        dependencies = set(node["depends_on"]) | {
            edge["node_id"] for edge in node["inputs"].values()
        }
        for dependency in dependencies:
            successors[dependency].add(node["node_id"])
    reached = {target_node_id}
    queue = deque([target_node_id])
    while queue:
        current = queue.popleft()
        for child in sorted(successors[current]):
            if child not in reached:
                reached.add(child)
                queue.append(child)
    return [name for name in order if name in reached]


def candidate_experiment(baseline_graph_run: dict, plan: dict) -> dict:
    inspect_record(baseline_graph_run)
    plan = validate_plan(plan)
    if baseline_graph_run["record_digest"] != plan["baseline_graph_run_ref"]:
        raise ValueError("Needle plan targets a different baseline graph-run")
    baseline = baseline_graph_run["experiment"]
    nodes = deepcopy(baseline["nodes"])
    target = plan["target"]
    found = False
    for node in nodes:
        if node["node_id"] == target["node_id"]:
            if target["parameter"] not in node["parameters"]:
                raise ValueError("Needle target parameter disappeared from baseline graph")
            if node["parameters"][target["parameter"]] != plan["before"]:
                raise ValueError("Needle baseline parameter differs from retained plan")
            node["parameters"][target["parameter"]] = deepcopy(plan["replacement"])
            found = True
            break
    if not found:
        raise ValueError("Needle target node disappeared from baseline graph")
    return experiment(
        f"{baseline['experiment_id']}.needle.{plan['needle_id']}",
        model_id=baseline["model_id"],
        nodes=nodes,
        parameters=deepcopy(baseline["parameters"]),
        parent_checkpoint=baseline["parent_checkpoint"],
    )


def _baseline_payload(item: dict) -> dict:
    if item.get("status") != "completed":
        raise ValueError("Needle reuse requires completed baseline node results")
    keys(item, {"status", "execution", "result"})
    check_seal(item["execution"])
    check_seal(item["result"])
    return detached(item)


def execute_needle(session, baseline_graph_run: dict, plan: dict, registry) -> dict:
    inspect_record(baseline_graph_run)
    plan = validate_plan(plan)
    if baseline_graph_run["record_digest"] != plan["baseline_graph_run_ref"]:
        raise ValueError("Needle plan targets a different baseline graph-run")
    if baseline_graph_run["status"] != "completed":
        raise ValueError("Needle V1 requires a completed baseline graph-run")
    if session.run["evidence_id"] != baseline_graph_run["source_evidence_id"]:
        raise ValueError("Needle session source evidence differs from baseline")
    if session.operations is not registry.operations:
        raise ValueError("Needle session must use the explicitly bound registry")

    candidate = candidate_experiment(baseline_graph_run, plan)
    order = plan_graph(candidate, registry)
    closure = dependency_closure(candidate, plan["target"]["node_id"])
    affected = set(closure)
    nodes = {node["node_id"]: node for node in candidate["nodes"]}
    contracts = {
        node["operation_id"]: registry.contract(node["operation_id"])
        for node in candidate["nodes"]
    }
    for operation_id in contracts:
        registry.operations.get(operation_id)

    outputs: dict[str, dict] = {}
    outcomes: dict[str, dict] = {}
    reused_nodes = []
    rerun_nodes = []

    for name in order:
        node = nodes[name]
        if name not in affected:
            retained = _baseline_payload(baseline_graph_run["nodes"][name])
            outputs[name] = _outputs(retained, contracts[node["operation_id"]])
            outcomes[name] = {
                "status": "reused",
                "baseline_execution_id": retained["execution"]["execution_id"],
                "baseline_result_id": retained["result"]["result_id"],
                "baseline_result_ref": content_identity(retained["result"]),
            }
            reused_nodes.append(name)
            continue

        dependencies = set(node["depends_on"]) | {
            edge["node_id"] for edge in node["inputs"].values()
        }
        blocked = []
        for dependency in dependencies:
            if dependency in affected:
                if outcomes.get(dependency, {}).get("status") != "completed":
                    blocked.append(dependency)
            elif dependency not in outputs:
                blocked.append(dependency)
        if blocked:
            outcomes[name] = {"status": "blocked", "dependencies": sorted(blocked)}
            continue

        parameters = {**candidate["parameters"], **node["parameters"]}
        for key, edge in node["inputs"].items():
            parameters[key] = deepcopy(outputs[edge["node_id"]][edge["port"]])
        response = session.handle({
            "protocol_version": 1,
            "request_id": uuid.uuid4().hex,
            "type": "operation.execute",
            "payload": {
                "operation_id": node["operation_id"],
                "parameters": parameters,
            },
        })
        if response["type"] == "error":
            outcomes[name] = {"status": "error", "refusal": response["payload"]}
            continue
        payload = detached(response["payload"])
        outcomes[name] = payload
        if payload["status"] != "completed":
            continue
        try:
            outputs[name] = _outputs(payload, contracts[node["operation_id"]])
        except (KeyError, TypeError, ValueError) as exc:
            outcomes[name] = {
                "status": "output_rejected",
                "reason": str(exc),
                "retained": payload,
            }
            continue
        rerun_nodes.append(name)

    status = "completed" if all(
        item["status"] in {"completed", "reused"} for item in outcomes.values()
    ) else "incomplete"
    value = record(
        "needle-run",
        needle_plan_ref=plan["record_digest"],
        baseline_graph_run_ref=baseline_graph_run["record_digest"],
        source_evidence_id=baseline_graph_run["source_evidence_id"],
        session_id=session.session_id,
        candidate_experiment=candidate,
        dependency_closure=closure,
        reused_nodes=reused_nodes,
        rerun_nodes=rerun_nodes,
        nodes=outcomes,
        status=status,
        claims={
            "selective_recomputation": True,
            "dependency_not_causality": True,
            "baseline_mutated": False,
            "canonical_state_mutated": False,
            "state_admission": False,
            "execution_authority": False,
        },
    )
    validate_needle_run(value, baseline_graph_run)
    return value


def validate_needle_run(value: dict, baseline_graph_run: dict | None = None) -> dict:
    keys(value, {
        "schema", "record_digest", "needle_plan_ref", "baseline_graph_run_ref",
        "source_evidence_id", "session_id", "candidate_experiment",
        "dependency_closure", "reused_nodes", "rerun_nodes", "nodes",
        "status", "claims",
    })
    if value["schema"] != "ciw.needle-run.v1":
        raise ValueError("Wrong Needle run schema")
    check_seal(value)
    content_ref(value["needle_plan_ref"])
    content_ref(value["baseline_graph_run_ref"])
    content_ref(value["source_evidence_id"])
    text(value["session_id"])
    from .control_plane import _experiment
    order = _experiment(value["candidate_experiment"])
    if type(value["dependency_closure"]) is not list or not value["dependency_closure"]:
        raise ValueError("Needle run requires a nonempty dependency closure")
    if any(name not in order for name in value["dependency_closure"]):
        raise ValueError("Needle closure references unknown candidate node")
    if value["dependency_closure"] != [
        name for name in order if name in set(value["dependency_closure"])
    ]:
        raise ValueError("Needle dependency closure must follow experiment order")
    for label in ("reused_nodes", "rerun_nodes"):
        rows = value[label]
        if type(rows) is not list or len(rows) != len(set(rows)):
            raise ValueError(f"{label} must be a unique list")
        if any(name not in order for name in rows):
            raise ValueError(f"{label} references unknown node")
    if set(value["reused_nodes"]) & set(value["rerun_nodes"]):
        raise ValueError("Needle node cannot be both reused and rerun")
    if set(value["rerun_nodes"]) - set(value["dependency_closure"]):
        raise ValueError("Needle rerun nodes must be inside dependency closure")
    if set(value["reused_nodes"]) & set(value["dependency_closure"]):
        raise ValueError("Needle reused nodes cannot be inside dependency closure")
    if set(value["nodes"]) != set(order):
        raise ValueError("Needle run node outcomes differ from candidate experiment")
    expected = "completed" if all(
        item.get("status") in {"completed", "reused"}
        for item in value["nodes"].values()
    ) else "incomplete"
    if value["status"] != expected:
        raise ValueError("Needle aggregate status contradicts node outcomes")
    for name in value["reused_nodes"]:
        item = value["nodes"][name]
        keys(item, {
            "status", "baseline_execution_id", "baseline_result_id",
            "baseline_result_ref",
        })
        if item["status"] != "reused":
            raise ValueError("Needle reused-node status mismatch")
        for field in ("baseline_execution_id", "baseline_result_id"):
            text(item[field])
        content_ref(item["baseline_result_ref"])
    for name in value["rerun_nodes"]:
        item = value["nodes"][name]
        if item.get("status") != "completed":
            raise ValueError("Needle rerun node must retain a completed execution")
        keys(item, {"status", "execution", "result"})
        check_seal(item["execution"])
        check_seal(item["result"])
    if baseline_graph_run is not None:
        inspect_record(baseline_graph_run)
        if baseline_graph_run["record_digest"] != value["baseline_graph_run_ref"]:
            raise ValueError("Needle run references a different baseline")
        if baseline_graph_run["source_evidence_id"] != value["source_evidence_id"]:
            raise ValueError("Needle run source evidence differs from baseline")
        for name in value["reused_nodes"]:
            baseline = _baseline_payload(baseline_graph_run["nodes"][name])
            item = value["nodes"][name]
            if item["baseline_execution_id"] != baseline["execution"]["execution_id"]:
                raise ValueError("Reused execution identity differs from baseline")
            if item["baseline_result_id"] != baseline["result"]["result_id"]:
                raise ValueError("Reused result identity differs from baseline")
            if item["baseline_result_ref"] != content_identity(baseline["result"]):
                raise ValueError("Reused result content identity differs from baseline")
    if value["claims"] != {
        "selective_recomputation": True,
        "dependency_not_causality": True,
        "baseline_mutated": False,
        "canonical_state_mutated": False,
        "state_admission": False,
        "execution_authority": False,
    }:
        raise ValueError("Needle run claims exceed selective-recomputation scope")
    return detached(value)


def _numeric_delta(before: Any, after: Any, path: str = "$", paths=None) -> dict:
    if paths is None:
        paths = []
    summary = {
        "numeric_leaf_count": 0,
        "changed_numeric_leaf_count": 0,
        "max_abs_numeric_delta": 0.0,
        "changed_scalar_count": 0,
        "shape_changed": False,
    }

    def walk(left: Any, right: Any, current: str):
        if type(left) in (int, float) and not isinstance(left, bool) and type(right) in (int, float) and not isinstance(right, bool):
            summary["numeric_leaf_count"] += 1
            delta = abs(float(right) - float(left))
            if delta != 0.0:
                summary["changed_numeric_leaf_count"] += 1
                summary["max_abs_numeric_delta"] = max(summary["max_abs_numeric_delta"], delta)
                if len(paths) < MAX_DELTA_PATHS:
                    paths.append({"path": current, "before": left, "after": right})
            return
        if type(left) is dict and type(right) is dict:
            if set(left) != set(right):
                summary["shape_changed"] = True
                if len(paths) < MAX_DELTA_PATHS:
                    paths.append({"path": current, "before_keys": sorted(left), "after_keys": sorted(right)})
            for key in sorted(set(left) & set(right)):
                walk(left[key], right[key], f"{current}.{key}")
            return
        if type(left) is list and type(right) is list:
            if len(left) != len(right):
                summary["shape_changed"] = True
                if len(paths) < MAX_DELTA_PATHS:
                    paths.append({"path": current, "before_length": len(left), "after_length": len(right)})
            for index, (a, b) in enumerate(zip(left, right)):
                walk(a, b, f"{current}[{index}]")
            return
        if left != right:
            summary["changed_scalar_count"] += 1
            if len(paths) < MAX_DELTA_PATHS:
                paths.append({"path": current, "before": left, "after": right})

    walk(before, after, path)
    return {**summary, "sample_changed_paths": paths}


def delta_projection(baseline_graph_run: dict, needle_run: dict) -> dict:
    inspect_record(baseline_graph_run)
    validate_needle_run(needle_run, baseline_graph_run)
    candidate_nodes = {
        node["node_id"]: node
        for node in needle_run["candidate_experiment"]["nodes"]
    }
    baseline_nodes = {
        node["node_id"]: node
        for node in baseline_graph_run["experiment"]["nodes"]
    }
    rows = []
    for node in needle_run["candidate_experiment"]["nodes"]:
        node_id = node["node_id"]
        if node_id in needle_run["reused_nodes"]:
            baseline = _baseline_payload(baseline_graph_run["nodes"][node_id])
            rows.append({
                "node_id": node_id,
                "operation_id": baseline_nodes[node_id]["operation_id"],
                "recomputation": "REUSED",
                "baseline_result_ref": content_identity(baseline["result"]),
                "candidate_result_ref": content_identity(baseline["result"]),
                "data_changed": False,
                "delta": {
                    "numeric_leaf_count": 0,
                    "changed_numeric_leaf_count": 0,
                    "max_abs_numeric_delta": 0.0,
                    "changed_scalar_count": 0,
                    "shape_changed": False,
                    "sample_changed_paths": [],
                },
            })
            continue
        baseline = _baseline_payload(baseline_graph_run["nodes"][node_id])
        candidate = needle_run["nodes"][node_id]
        if candidate.get("status") != "completed":
            rows.append({
                "node_id": node_id,
                "operation_id": candidate_nodes[node_id]["operation_id"],
                "recomputation": "RERUN_UNRESOLVED",
                "baseline_result_ref": content_identity(baseline["result"]),
                "candidate_result_ref": None,
                "data_changed": None,
                "delta": None,
            })
            continue
        before_data = baseline["result"]["data"]
        after_data = candidate["result"]["data"]
        rows.append({
            "node_id": node_id,
            "operation_id": candidate_nodes[node_id]["operation_id"],
            "recomputation": "RERUN",
            "baseline_result_ref": content_identity(baseline["result"]),
            "candidate_result_ref": content_identity(candidate["result"]),
            "data_changed": before_data != after_data,
            "delta": _numeric_delta(before_data, after_data),
        })
    value = record(
        "needle-delta",
        baseline_graph_run_ref=baseline_graph_run["record_digest"],
        needle_run_ref=needle_run["record_digest"],
        target_node_id=needle_run["dependency_closure"][0],
        dependency_closure=deepcopy(needle_run["dependency_closure"]),
        nodes=rows,
        summary={
            "reused_nodes": len(needle_run["reused_nodes"]),
            "rerun_nodes": len(needle_run["rerun_nodes"]),
            "changed_output_nodes": sum(row["data_changed"] is True for row in rows),
            "unchanged_output_nodes": sum(row["data_changed"] is False for row in rows),
            "unresolved_output_nodes": sum(row["data_changed"] is None for row in rows),
        },
        claims={
            "delta_projection": True,
            "dependency_effects_observed": True,
            "causal_effects_established": False,
            "canonical_state_mutated": False,
            "execution_authority": False,
        },
    )
    validate_delta(value)
    return value


def validate_delta(value: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "baseline_graph_run_ref", "needle_run_ref",
        "target_node_id", "dependency_closure", "nodes", "summary", "claims",
    })
    if value["schema"] != "ciw.needle-delta.v1":
        raise ValueError("Wrong Needle delta schema")
    check_seal(value)
    content_ref(value["baseline_graph_run_ref"])
    content_ref(value["needle_run_ref"])
    text(value["target_node_id"])
    if type(value["dependency_closure"]) is not list or not value["dependency_closure"]:
        raise ValueError("Needle delta requires dependency closure")
    for name in value["dependency_closure"]:
        text(name)
    if type(value["nodes"]) is not list or not value["nodes"]:
        raise ValueError("Needle delta requires node rows")
    seen = set()
    for row in value["nodes"]:
        keys(row, {
            "node_id", "operation_id", "recomputation",
            "baseline_result_ref", "candidate_result_ref",
            "data_changed", "delta",
        })
        node_id = text(row["node_id"])
        if node_id in seen:
            raise ValueError("Duplicate Needle delta node")
        seen.add(node_id)
        text(row["operation_id"])
        if row["recomputation"] not in {"REUSED", "RERUN", "RERUN_UNRESOLVED"}:
            raise ValueError("Unknown Needle recomputation state")
        content_ref(row["baseline_result_ref"])
        if row["candidate_result_ref"] is not None:
            content_ref(row["candidate_result_ref"])
        if row["data_changed"] not in {True, False, None}:
            raise ValueError("Needle data_changed must be true/false/null")
    keys(value["summary"], {
        "reused_nodes", "rerun_nodes", "changed_output_nodes",
        "unchanged_output_nodes", "unresolved_output_nodes",
    })
    for item in value["summary"].values():
        if type(item) is not int or item < 0:
            raise ValueError("Needle delta summary counts must be nonnegative integers")
    if value["claims"] != {
        "delta_projection": True,
        "dependency_effects_observed": True,
        "causal_effects_established": False,
        "canonical_state_mutated": False,
        "execution_authority": False,
    }:
        raise ValueError("Needle delta claims exceed observational scope")
    return detached(value)
