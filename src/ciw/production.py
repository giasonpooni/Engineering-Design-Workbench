"""Bounded production work orders over the existing NET graph runner.

Jobs contain ordinary experiments, not a second engine or evidence ledger.
Workers are operator-supplied allowlists over CapabilityRegistry. A saved plan
cannot load code, start a shell, choose a credential, or authorize publication.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import logging
import re
import tempfile
from typing import Callable
import uuid

from .control_contracts import (
    _base, bytes_ref, content_ref, detached, keys, save_new, text,
)
from .control_checks import inspect_record
from .control_plane import CapabilityRegistry, _experiment, _plan_contracts, experiment, plan_graph, run_graph
from .core.identities import validate_evidence_identity, validate_identity
from .instruments import validate_run
from .operations.runner import seal

LOG = logging.getLogger(__name__)

MAX_JOBS = 64
MAX_ATTEMPTS = 3
MAX_OPERATIONS = 256
AUTHORITY = {"verification_id": None, "state_admission": "not_performed",
             "publication": "not_performed", "claim_scope": "declared_production_checks_only"}


@dataclass(frozen=True)
class Worker:
    """A logical worker lane; permissions are not recovered from a saved file."""
    worker_id: str
    operations: tuple[str, ...]


@dataclass(frozen=True)
class Gate:
    """Explicit trusted check implementation, separate from generative workers."""
    gate_id: str
    runtime: dict
    validate_policy: Callable[[dict], None]
    evaluate: Callable[[dict | None, dict], dict]


def _bounded_count(value: int, maximum: int) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"Require an integer in 1..{maximum}")


def _unique_names(value: list, *, empty: bool = False) -> None:
    if type(value) is not list or len(value) > MAX_JOBS or (not value and not empty):
        raise ValueError("Require a bounded list of names")
    for name in value:
        text(name)
    if len(set(value)) != len(value):
        raise ValueError("Duplicate name")


def _shape(graph: dict) -> dict:
    # Repairs may change parameter values, never model, code routes, edges or checks.
    return {"model_id": graph["model_id"], "parent_checkpoint": graph["parent_checkpoint"],
            "nodes": [{k: v for k, v in n.items() if k != "parameters"} for n in graph["nodes"]]}


def validate_plan(value: dict) -> list[str]:
    _base(value, "production-plan", {"plan_id", "project_id", "source_evidence_id", "jobs"})
    text(value["plan_id"])
    text(value["project_id"])
    content_ref(value["source_evidence_id"])
    jobs = value["jobs"]
    if type(jobs) is not list:
        raise ValueError("Jobs must be a list")
    _bounded_count(len(jobs), MAX_JOBS)
    nodes, count = [], 0
    for job in jobs:
        keys(job, {"job_id", "worker_id", "requires", "depends_on", "attempts", "checks"})
        text(job["job_id"])
        text(job["worker_id"])
        _unique_names(job["requires"])
        _unique_names(job["depends_on"], empty=True)
        if type(job["attempts"]) is not list:
            raise ValueError("Attempts must be a list")
        _bounded_count(len(job["attempts"]), MAX_ATTEMPTS)
        for graph in job["attempts"]:
            inspect_record(graph)
            if graph["schema"] != "ciw.experiment.v1":
                raise ValueError("A production attempt must be an existing NET experiment")
            count += len(graph["nodes"])
        original = job["attempts"][0]
        if any(_shape(graph) != _shape(original) for graph in job["attempts"]):
            raise ValueError("A declared repair may change parameters only")
        if type(job["checks"]) is not list or not 1 <= len(job["checks"]) <= 32:
            raise ValueError("Declare 1..32 immutable acceptance checks")
        names, checked = set(), set()
        for check in job["checks"]:
            keys(check, {"check_id", "node_id", "gate_id", "policy"})
            for field in ("check_id", "node_id", "gate_id"):
                text(check[field])
            if check["check_id"] in names or type(check["policy"]) is not dict:
                raise ValueError("Duplicate check or invalid policy")
            names.add(check["check_id"])
            checked.add(check["node_id"])
        graph_names = {n["node_id"] for n in original["nodes"]}
        upstream = {d for n in original["nodes"] for d in n["depends_on"]}
        upstream |= {e["node_id"] for n in original["nodes"] for e in n["inputs"].values()}
        if checked - graph_names or (graph_names - upstream) - checked:
            raise ValueError("Every graph sink needs a check; check targets must exist")
        nodes.append({"node_id": job["job_id"], "operation_id": original["nodes"][0]["operation_id"],
                      "parameters": {}, "inputs": {}, "depends_on": job["depends_on"]})
    if count > MAX_OPERATIONS:
        raise ValueError("Production plan exceeds total operation budget")
    # Reuse the original bounded DAG validator/order, rather than another graph library.
    return _experiment(experiment(value["plan_id"], model_id=value["project_id"], nodes=nodes))


def plan(plan_id: str, *, project_id: str, source_evidence_id: str, jobs: list[dict]) -> dict:
    value = seal(detached({"schema": "ciw.production-plan.v1", "plan_id": plan_id,
                          "project_id": project_id, "source_evidence_id": source_evidence_id,
                          "jobs": [detached(job) for job in jobs]}))
    validate_plan(value)
    return value


def _gate_bindings(gates: dict[str, Gate]) -> dict:
    if type(gates) is not dict or not 1 <= len(gates) <= 32:
        raise ValueError("Require explicit trusted acceptance gates")
    result = {}
    for name, gate in gates.items():
        if not isinstance(gate, Gate) or text(name) != gate.gate_id or not gate.runtime:
            raise ValueError("Invalid acceptance binding")
        if type(gate.runtime) is not dict or not callable(gate.evaluate) or not callable(gate.validate_policy):
            raise ValueError("Invalid acceptance implementation")
        result[name] = detached(gate.runtime)
    return result


def preflight(value: dict, registry: CapabilityRegistry, workers: tuple[Worker, ...],
              gates: dict[str, Gate], *, max_operations: int = 128) -> dict:
    """Validate all alternatives/bindings before creating the destination or dispatching."""
    order = validate_plan(value)
    _bounded_count(max_operations, MAX_OPERATIONS)
    if type(workers) is not tuple or not 1 <= len(workers) <= 16:
        raise ValueError("Require 1..16 explicit worker lanes")
    contracts, worker_views = {}, {}
    for worker in workers:
        if not isinstance(worker, Worker) or text(worker.worker_id) in worker_views:
            raise ValueError("Invalid or duplicate worker")
        if type(worker.operations) is not tuple:
            raise ValueError("Worker operations must be an immutable tuple")
        _unique_names(list(worker.operations))
        worker_views[worker.worker_id] = list(worker.operations)
        for name in worker.operations:
            contract = registry.contract(name)
            operation = registry.operations.get(name)
            if detached(operation.runtime_identity()) != contract["runtime"]:
                raise ValueError("Worker runtime differs from its bound contract")
            contracts[name] = contract
    bound_gates = _gate_bindings(gates)
    reserved = 0
    for job in value["jobs"]:
        if job["worker_id"] not in worker_views:
            raise ValueError("Worker is not explicitly bound")
        for graph in job["attempts"]:
            plan_graph(graph, registry)
            ops = {node["operation_id"] for node in graph["nodes"]}
            if ops - set(worker_views[job["worker_id"]]):
                raise ValueError("Operation outside worker allowlist")
            capabilities = {c for op in ops for c in contracts[op]["capabilities"]}
            if set(job["requires"]) - capabilities:
                raise ValueError("Selected operations do not supply required capabilities")
            reserved += len(graph["nodes"])
        for check in job["checks"]:
            if check["gate_id"] not in gates:
                raise ValueError("Acceptance gate is not explicitly bound")
            gates[check["gate_id"]].validate_policy(deepcopy(check["policy"]))
    if reserved > max_operations:
        raise ValueError("All possible attempts exceed the operator's operation budget")
    return seal({"schema": "ciw.production-bindings.v1", "workers": worker_views,
                 "contracts": contracts, "gates": bound_gates, "order": order,
                 "reserved_operations": reserved, "max_operations": max_operations,
                 "authorizes_execution": False})


def _status(statuses: list[str]) -> str:
    if "FAIL" in statuses:
        return "FAIL"
    return "PASS" if statuses and all(s == "PASS" for s in statuses) else "INDETERMINATE"


def acceptance(graph: dict, checks: list[dict], gates: dict[str, Gate]) -> dict:
    """Checks are pure calculations on detached retained results, never engine calls."""
    inspect_record(graph)
    bindings = _gate_bindings(gates)
    outcomes = []
    for check in checks:
        gate = gates[check["gate_id"]]
        gate.validate_policy(deepcopy(check["policy"]))
        node = graph["nodes"][check["node_id"]]
        result = node.get("result") if node["status"] == "completed" else None
        if graph["status"] != "completed":
            verdict = {"status": "INDETERMINATE", "detail": "graph_did_not_complete"}
        else:
            verdict = detached(gate.evaluate(deepcopy(result), deepcopy(check["policy"])))
        if _gate_bindings(gates) != bindings:
            raise ValueError("Acceptance implementation identity changed during evaluation")
        keys(verdict, {"status", "detail"})
        if verdict["status"] not in {"PASS", "FAIL", "INDETERMINATE"}:
            raise ValueError("Acceptance gate returned an invalid outcome")
        outcomes.append({"check": deepcopy(check), "source_result_id": None if result is None else result["result_id"],
                         "source_record_digest": None if result is None else result["record_digest"],
                         "gate_runtime": detached(gate.runtime), **verdict})
    return seal({"schema": "ciw.production-acceptance.v1", "graph_digest": graph["record_digest"],
                 "checks": outcomes, "status": _status([row["status"] for row in outcomes]),
                 "authority": deepcopy(AUTHORITY)})


def _outcome(graph: dict, checked: dict) -> str:
    if graph["status"] != "completed":
        return "refused"
    return {"PASS": "accepted", "FAIL": "rejected", "INDETERMINATE": "held"}[checked["status"]]


def _write(root: Path, name: str, value: dict) -> dict:
    save_new(root / name, value)
    return {"name": name, "sha256": bytes_ref((root / name).read_bytes())}


def _read(root: Path, name: str, reference: dict | None = None) -> dict:
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("Production records must be regular, non-symlink files")
    with path.open("rb") as handle:
        raw = handle.read(8 * 1024 * 1024 + 1)
    if not 0 < len(raw) <= 8 * 1024 * 1024:
        raise ValueError("Production record exceeds 8 MiB")
    if reference is not None:
        keys(reference, {"name", "sha256"})
        if reference["name"] != name or bytes_ref(raw) != reference["sha256"]:
            raise ValueError("Production file reference mismatch")
    from .session import loads_json
    value = loads_json(raw.decode("utf-8"))
    return detached(value)


def run_production(source: dict, value: dict, registry: CapabilityRegistry,
                   workers: tuple[Worker, ...], gates: dict[str, Gate], output_dir: Path,
                   *, max_operations: int = 128) -> dict:
    """Local, single-controller execution. Refusal/missingness never triggers blind retries.

    Only a failed declared acceptance check may select the next predeclared
    parameter variant. Every attempt gets fresh original CIW execution/result IDs.
    There is no background daemon, parallel Session mutation or automatic merge.
    """
    from .session import Session
    source, value = detached(source), detached(value)
    validate_run(source)
    validate_evidence_identity(source)
    bindings = preflight(value, registry, workers, gates, max_operations=max_operations)
    if value["source_evidence_id"] != source["evidence_id"]:
        raise ValueError("Work order source evidence differs from the bound recording")
    root = Path(output_dir)
    if root.is_symlink():
        raise ValueError("Production destination cannot be a symlink")
    root.mkdir(parents=True, exist_ok=False)
    plan_ref = _write(root, "plan.json", value)
    bindings_ref = _write(root, "bindings.json", bindings)
    session = Session(source, root / "session", operations=registry.operations)
    outcomes, sequence = {}, 0
    try:
        for job_id in bindings["order"]:
            job = next(j for j in value["jobs"] if j["job_id"] == job_id)
            blocked = [name for name in job["depends_on"] if outcomes[name]["status"] != "accepted"]
            if blocked:
                outcomes[job_id] = {"status": "blocked", "blocked_by": sorted(blocked), "attempts": []}
                continue
            refs = []
            for index, spec in enumerate(job["attempts"]):
                # Registry/gate drift cannot silently change a previously accepted plan.
                if preflight(value, registry, workers, gates, max_operations=max_operations) != bindings:
                    raise ValueError("Production bindings changed after preflight")
                graph = run_graph(session, spec, registry)
                sequence += 1
                prefix = f"attempt-{sequence:04d}"
                graph_ref = _write(root, prefix + "-graph.json", graph)
                session.save_workspace(root / "session" / "workspace.json")
                checked = acceptance(graph, job["checks"], gates)
                check_ref = _write(root, prefix + "-checks.json", checked)
                receipt = seal({"schema": "ciw.production-attempt.v1", "job_id": job_id,
                    "attempt_index": index, "worker_id": job["worker_id"], "plan_digest": value["record_digest"],
                    "graph": graph_ref, "acceptance": check_ref, "status": _outcome(graph, checked)})
                refs.append(_write(root, prefix + ".json", receipt))
                session.save_workspace(root / "session" / "workspace.json")
                if receipt["status"] != "rejected":
                    break
            outcomes[job_id] = {"status": receipt["status"], "blocked_by": [], "attempts": refs}
        session.save_workspace(root / "session" / "workspace.json")
        report = seal({"schema": "ciw.production-run.v1", "production_id": "production-" + uuid.uuid4().hex,
            "session_id": session.session_id, "plan": plan_ref, "bindings": bindings_ref,
            "workspace_sha256": bytes_ref((root / "session" / "workspace.json").read_bytes()),
            "jobs": outcomes, "status": "completed" if all(x["status"] == "accepted" for x in outcomes.values()) else "incomplete",
            "attempt_count": sequence, "execution_count": len(session.executions),
            "result_count": len(session.results), "authority": deepcopy(AUTHORITY)})
        _write(root, "production.json", report)
        return report
    except BaseException:
        # Retain original history on interruption without masking the original failure.
        # No complete campaign report means interrupted, never automatically resumed.
        try:
            session.save_workspace(root / "session" / "workspace.json")
        except Exception:
            LOG.exception("Could not checkpoint interrupted production history")
        raise


def inspect_production(output_dir: Path, gates: dict[str, Gate]) -> dict:
    """Recheck original records, dependencies and all acceptance outcomes without providers."""
    from .session import Session
    root = Path(output_dir)
    if root.is_symlink() or (root / "session").is_symlink():
        raise ValueError("Production record directories cannot be symlinks")
    report = _read(root, "production.json")
    _base(report, "production-run", {"production_id", "session_id", "plan", "bindings", "workspace_sha256",
                                    "jobs", "status", "attempt_count", "execution_count", "result_count", "authority"})
    value = _read(root, "plan.json", report["plan"])
    order = validate_plan(value)
    bindings = _read(root, "bindings.json", report["bindings"])
    _base(bindings, "production-bindings", {"workers", "contracts", "gates", "order",
                                          "reserved_operations", "max_operations", "authorizes_execution"})
    if bindings["gates"] != _gate_bindings(gates) or bindings["authorizes_execution"] is not False:
        raise ValueError("Retained check implementation differs from explicit inspection binding")
    if order != bindings["order"] or report["authority"] != AUTHORITY:
        raise ValueError("Production order or authority mismatch")
    if type(report["production_id"]) is not str or re.fullmatch(r"production-[0-9a-f]{32}", report["production_id"]) is None:
        raise ValueError("Invalid production occurrence identity")
    validate_identity(report["session_id"], "session")
    for name in ("attempt_count", "execution_count", "result_count"):
        if type(report[name]) is not int or not 0 <= report[name] <= MAX_OPERATIONS:
            raise ValueError("Invalid production count")
    if type(bindings["workers"]) is not dict or not 1 <= len(bindings["workers"]) <= 16:
        raise ValueError("Invalid retained worker lanes")
    for name, allowed in bindings["workers"].items():
        text(name)
        _unique_names(allowed)
    keys(bindings["contracts"], {op for allowed in bindings["workers"].values() for op in allowed})
    if type(bindings["reserved_operations"]) is not int:
        raise ValueError("Invalid reserved operation count")
    for job in value["jobs"]:
        if job["worker_id"] not in bindings["workers"]:
            raise ValueError("Missing retained worker")
        for graph in job["attempts"]:
            ops = {node["operation_id"] for node in graph["nodes"]}
            if ops - set(bindings["workers"][job["worker_id"]]):
                raise ValueError("Retained attempt exceeds worker allowlist")
            _plan_contracts(graph, {op: bindings["contracts"][op] for op in ops})
            if set(job["requires"]) - {c for op in ops for c in bindings["contracts"][op]["capabilities"]}:
                raise ValueError("Retained attempt lacks required capabilities")
        for check in job["checks"]:
            if check["gate_id"] not in gates:
                raise ValueError("Missing retained gate binding")
            gates[check["gate_id"]].validate_policy(deepcopy(check["policy"]))
    keys(report["jobs"], set(order))
    # Freeze the workspace once; native game/provider validators must be explicitly
    # registered by the host before this data-only reader is called.
    workspace = _read(root / "session", "workspace.json",
                      {"name": "workspace.json", "sha256": report["workspace_sha256"]})
    with tempfile.TemporaryDirectory(prefix="net-production-inspect-") as directory:
        frozen = Path(directory) / "workspace.json"
        save_new(frozen, workspace)
        session = Session.from_workspace(frozen, Path(directory) / "reopened")
        if session.run["evidence_id"] != value["source_evidence_id"]:
            raise ValueError("Production source mismatch")
        sequence, executions, results = 0, set(), set()
        for job_id in order:
            job = next(j for j in value["jobs"] if j["job_id"] == job_id)
            outcome = report["jobs"][job_id]
            keys(outcome, {"status", "blocked_by", "attempts"})
            blocked = sorted(name for name in job["depends_on"] if report["jobs"][name]["status"] != "accepted")
            if blocked:
                if outcome != {"status": "blocked", "blocked_by": blocked, "attempts": []}:
                    raise ValueError("A blocked production job was dispatched")
                continue
            if outcome["blocked_by"] or type(outcome["attempts"]) is not list or not 1 <= len(outcome["attempts"]) <= len(job["attempts"]):
                raise ValueError("Invalid production attempt history")
            final = None
            for index, reference in enumerate(outcome["attempts"]):
                if index and final != "rejected":
                    raise ValueError("Only declared failed acceptance permits a repair")
                sequence += 1
                prefix = f"attempt-{sequence:04d}"
                receipt = _read(root, prefix + ".json", reference)
                _base(receipt, "production-attempt", {"job_id", "attempt_index", "worker_id", "plan_digest", "graph", "acceptance", "status"})
                if type(receipt["attempt_index"]) is not int:
                    raise ValueError("Invalid attempt index")
                if (receipt["job_id"], receipt["attempt_index"], receipt["worker_id"], receipt["plan_digest"]) != (job_id, index, job["worker_id"], value["record_digest"]):
                    raise ValueError("Attempt work-order binding mismatch")
                graph = _read(root, prefix + "-graph.json", receipt["graph"])
                inspect_record(graph)
                if graph["experiment"] != job["attempts"][index] or graph["session_id"] != report["session_id"] or graph["source_evidence_id"] != value["source_evidence_id"]:
                    raise ValueError("Attempt graph/source/occurrence mismatch")
                used = set(graph["contracts"])
                if job["worker_id"] not in bindings["workers"] or used - set(bindings["workers"][job["worker_id"]]):
                    raise ValueError("Attempt exceeded retained worker allowlist")
                for op, contract in graph["contracts"].items():
                    if contract != bindings["contracts"].get(op):
                        raise ValueError("Attempt contract differs from preflight")
                capabilities = {c for contract in graph["contracts"].values() for c in contract["capabilities"]}
                if set(job["requires"]) - capabilities:
                    raise ValueError("Attempt lacks required capabilities")
                for node in graph["nodes"].values():
                    payload = node.get("retained", node)
                    execution, result = payload.get("execution"), payload.get("result")
                    if execution is not None:
                        name = execution["execution_id"]
                        if name in executions or session.executions.get(name) != execution:
                            raise ValueError("Attempt reused or substituted an execution")
                        executions.add(name)
                    if result is not None:
                        name = result["result_id"]
                        if name in results or session.results.get(name) != result:
                            raise ValueError("Attempt reused or substituted a result")
                        results.add(name)
                checked = _read(root, prefix + "-checks.json", receipt["acceptance"])
                if checked != acceptance(graph, job["checks"], gates):
                    raise ValueError("Retained acceptance contradicts original evidence/policy")
                final = _outcome(graph, checked)
                if final != receipt["status"]:
                    raise ValueError("Attempt disposition contradicts checks")
            if final != outcome["status"] or (final == "rejected" and len(outcome["attempts"]) != len(job["attempts"])):
                raise ValueError("Work order did not follow its complete declared repair policy")
        reserved = sum(len(g["nodes"]) for j in value["jobs"] for g in j["attempts"])
        _bounded_count(bindings["max_operations"], MAX_OPERATIONS)
        if reserved != bindings["reserved_operations"] or reserved > bindings["max_operations"]:
            raise ValueError("Production budget mismatch")
        if executions != set(session.executions) or results != set(session.results):
            raise ValueError("Unaccounted production history")
        if (sequence, len(executions), len(results)) != (report["attempt_count"], report["execution_count"], report["result_count"]):
            raise ValueError("Production counts mismatch")
        expected = "completed" if all(x["status"] == "accepted" for x in report["jobs"].values()) else "incomplete"
        if report["status"] != expected:
            raise ValueError("Production summary mismatch")
    return {"schema": "ciw.production-inspection.v1", "integrity": "checked", "fresh_execution": False,
            "status": report["status"], "jobs": deepcopy(report["jobs"]),
            "attempt_count": sequence, "execution_count": len(executions), "result_count": len(results),
            "authority": deepcopy(AUTHORITY)}
