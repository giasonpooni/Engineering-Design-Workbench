"""Retained fluid/material boundary balances on existing NET event identities.

The operator binds the existing FSRT runtime explicitly. Saved evidence can be
inspected or independently checked without loading that runtime or its paths.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path
import platform
import re
import tempfile

from .adapters.protocol import InstrumentManifest
from .control_contracts import bytes_ref, keys, save_new
from .core.identities import evidence_id, new_identity, validate_evidence_identity, validate_identity
from .core.records import validate_run_structure
from .operations.registry import Operation
from .operations.runner import check_seal, digest

ASSESS = "leakage.assess-balance.v1"
VERIFY = "leakage.verify-balance.v1"
OPERATIONS = {ASSESS, VERIFY}
MAX_WORKSPACE_BYTES = 24 * 1024 * 1024
AUTHORITY = {"physical_validation": "not_established", "calibration_traceability": "not_established",
             "causal_leak_identification": "not_established", "state_admission": "not_performed",
             "hardware_actuation": "not_performed", "llm_inference": "not_performed"}
EXPLANATIONS = ["unmetered fluid or material escape", "unrecorded purge, rejects or other transfers",
                "inventory measurement error", "transfer meter bias", "incorrect boundary or interval support"]


def runtime_identity(kind: str, backend=None) -> dict:
    from . import leakage_contract, leakage_native, leakage_verification
    modules = [leakage_contract, leakage_native, leakage_verification, __import__(__name__, fromlist=["*"])]
    raw = b"\0".join(Path(m.__file__).name.encode() + b"\0" +
                      Path(m.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                      for m in modules)
    value = {"provider": "ciw.leakage." + kind, "version": "1", "code_sha256": sha256(raw).hexdigest(),
             "source_normalization": "utf8_lf", "scope": "offline_declared_boundary_balance_no_cause_or_actuation",
             "environment": {"python": platform.python_version(), "floating_point": "binary64"}}
    if backend is not None:
        value["native"] = backend.runtime_identity()
    return value


def validate_runtime(operation: str, value: dict | None, *, allow_absent: bool = False) -> None:
    if value is None and allow_absent:
        return
    required = {"provider", "version", "code_sha256", "source_normalization", "scope", "environment"}
    keys(value, required | ({"native"} if operation == ASSESS else set()))
    kind = "assessment" if operation == ASSESS else "verification"
    if (operation not in OPERATIONS or value["provider"] != "ciw.leakage." + kind
            or value["version"] != "1" or not re.fullmatch(r"[0-9a-f]{64}", str(value["code_sha256"]))
            or value["source_normalization"] != "utf8_lf"
            or value["scope"] != "offline_declared_boundary_balance_no_cause_or_actuation"):
        raise ValueError("Leakage runtime contradicts its fixed operation contract")
    keys(value["environment"], {"python", "floating_point"})
    if (not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(value["environment"]["python"]))
            or value["environment"]["floating_point"] != "binary64"):
        raise ValueError("Malformed leakage host environment")
    if operation == ASSESS:
        from .leakage_native import validate_runtime as validate_native_runtime
        validate_native_runtime(value["native"])


def _validate_polymer_binding(binding: dict | None, request: dict) -> None:
    if binding is None:
        return
    from . import polymer_workflow
    from .operations.runner import validate_execution
    from .session import _recording_file, _validate_saved_result
    keys(binding, {"schema", "source", "assessment", "execution"})
    if binding["schema"] != "ciw.leakage-polymer-evidence.v1":
        raise ValueError("Unsupported polymer leakage coupling schema")
    source, candidate, execution = binding["source"], binding["assessment"], binding["execution"]
    parent = polymer_workflow.source_request(source)
    polymer_workflow._candidate(source, {"assessment": candidate})
    revision = candidate["selection_revision"]
    _validate_saved_result(candidate, source, revision, _recording_file(source))
    validate_execution(execution, source, revision, {candidate["result_id"]: candidate})
    if execution["status"] != "completed" or execution["result_id"] != candidate["result_id"]:
        raise ValueError("Polymer coupling requires the completed retained assessment occurrence")
    for field in ("identity", "process", "frame", "source_kind"):
        if request[field] != parent[field]:
            raise ValueError("Leakage and polymer " + field + " differ")
    if (request["clock"]["id"] != parent["clock"]["id"]
            or not parent["clock"]["start_s"] <= request["edges_s"][0]
            or not request["edges_s"][-1] <= parent["clock"]["end_s"]):
        raise ValueError("Leakage support must lie inside the same declared polymer cycle clock")


def _polymer_binding(directory: Path | None, request: dict) -> dict | None:
    if directory is None:
        return None
    from . import polymer_workflow
    session, _ = polymer_workflow._read(directory)
    candidate = next((r for r in session.results.values() if r["operation_id"] == polymer_workflow.ASSESS), None)
    if candidate is None:
        raise ValueError("Polymer workspace has no completed retained assessment")
    binding = {"schema": "ciw.leakage-polymer-evidence.v1", "source": deepcopy(session.run),
               "assessment": deepcopy(candidate), "execution": deepcopy(session.executions[candidate["execution_id"]])}
    _validate_polymer_binding(binding, request)
    return binding


def _binding_view(binding: dict | None) -> dict | None:
    if binding is None:
        return None
    result = binding["assessment"]
    return {"schema": "ciw.leakage-polymer-binding.v1", "binding_ref": digest(binding),
            "evidence_id": binding["source"]["evidence_id"], "assessment_result_id": result["result_id"],
            "assessment_execution_id": result["execution_id"], "assessment_record_digest": result["record_digest"],
            "scope": "same_declared_cycle_and_boundary_support_not_causal_coupling"}


def make_source(request: dict, *, polymer_binding: dict | None = None) -> dict:
    from .leakage_contract import validate_request
    request = validate_request(request)
    _validate_polymer_binding(polymer_binding, request)
    manifest = InstrumentManifest(instrument_id="fluid-material-leakage-evidence.v1", role="retained_boundary_balance",
        units={"balance_declaration": "1"}, frames=(request["frame"],),
        sampling={"kind": "one_balance_declaration", "time_semantics": "synthetic_selection_envelope"},
        supported_operations=(ASSESS, VERIFY), calibration_requirements={"authority": "declared covariance; traceability not established"})
    source = {"run_schema": "run.v1", "run_id": "run-leakage-" + digest(request)[7:23],
              "instrument": manifest.instrument_id,
              "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
                           "coordinate_frame": request["frame"], "manifest": manifest.to_dict(),
                           "leakage_request": request, "leakage_polymer_binding": deepcopy(polymer_binding),
                           "provenance": {"source": request["source_kind"], "generator": "ciw.leakage_workflow.make_source",
                                          "generator_version": 1}},
              "time_s": [0.0], "channels": {"balance_declaration": {"unit": "1", "values": [1.0]}}, "render": {}}
    source["evidence_id"] = evidence_id(source)
    return source


def source_request(source: dict) -> dict:
    from .leakage_contract import validate_request
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = validate_request(source["metadata"]["leakage_request"])
    if source != make_source(request, polymer_binding=source["metadata"].get("leakage_polymer_binding")):
        raise ValueError("Leakage source differs from its exact retained declaration")
    return request


def decision_projection(request: dict, calculation: dict) -> dict:
    """Label a caller-declared uncertainty band; do not infer a leak cause."""
    from .leakage_verification import rounding_guards
    guards = rounding_guards(request, calculation)
    policy = request["decision_policy"]
    threshold, factor = policy["loss_threshold"], policy["coverage_factor"]
    def row(series, index, guard):
        mean = -series["residual"][index]
        variance = series["covariance"][index][index]
        radius = factor * math.sqrt(variance)
        lower, upper = mean - radius, mean + radius
        # Include source-derived native arithmetic error and outward rounding
        # at every decision-boundary operation. A lawful numerical difference
        # cannot alone turn an exact threshold boundary into a resolved loss.
        upper_variance = math.nextafter(variance + guard["covariance_diagonal_error_bound"], math.inf)
        upper_radius = math.nextafter(factor * math.nextafter(math.sqrt(upper_variance), math.inf), math.inf)
        decision_lower = math.nextafter(math.nextafter(mean - guard["residual_error_bound"], -math.inf) - upper_radius, -math.inf)
        decision_upper = math.nextafter(math.nextafter(mean + guard["residual_error_bound"], math.inf) + upper_radius, math.inf)
        if not all(math.isfinite(x) for x in (mean, radius, lower, upper, decision_lower, decision_upper)):
            raise ValueError("Leakage decision overflows its declared finite uncertainty band")
        status = ("UNACCOUNTED_LOSS" if decision_lower > threshold else "UNACCOUNTED_GAIN" if decision_upper < -threshold
                  else "WITHIN_DECLARED_BAND" if -threshold <= decision_lower and decision_upper <= threshold else "INDETERMINATE")
        return {**deepcopy(series["support"][index]), "loss_estimate": mean,
                "declared_interval": [lower, upper], "decision_interval": [decision_lower, decision_upper],
                "numerical_guard": deepcopy(guard), "status": status}
    window = row(calculation["cumulative"], -1, guards["cumulative"][-1])
    return {"schema": "ciw.leakage-decision.v1", "unit": request["unit"], "status": window["status"],
            "intervals": [row(calculation["interval"], i, guards["interval"][i]) for i in range(len(calculation["interval"]["residual"]))],
            "window": window, "policy_ref": digest(policy),
            "scope": "declared_uncertainty_band_not_a_calibrated_probability", "cause_status": "NOT_ISOLATED",
            "competing_explanations": deepcopy(EXPLANATIONS)}


def _assess(source: dict, parameters: dict, backend) -> dict:
    keys(parameters, set())
    request = source_request(source)
    if backend is None:
        raise ValueError("An operator-bound pinned FSRT backend is required")
    calculation = backend.calculate(request)
    from .leakage_verification import validate_calculation
    validate_calculation(request, calculation)
    return {"schema": "ciw.leakage-assessment-payload.v1", "request_ref": digest(request),
            "calculation": calculation, "decision": decision_projection(request, calculation),
            "polymer_binding": _binding_view(source["metadata"]["leakage_polymer_binding"]),
            "authority": deepcopy(AUTHORITY)}


def _candidate(source: dict, parameters: dict) -> dict:
    keys(parameters, {"assessment"})
    candidate = parameters["assessment"]
    check_seal(candidate)
    if (candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != ASSESS
            or candidate.get("role") != "backend" or candidate.get("evidence_id") != source["evidence_id"]
            or candidate.get("run_id") != source["run_id"] or candidate.get("parameters") != {}):
        raise ValueError("Require the exact source-bound leakage assessment occurrence")
    validate_identity(candidate.get("execution_id"), "execution")
    validate_identity(candidate.get("result_id"), "result")
    validate_runtime(ASSESS, candidate["runtime"])
    _validate_assessment(source, candidate["data"])
    if candidate["runtime"]["native"] != candidate["data"]["calculation"]["runtime"]:
        raise ValueError("Native leakage calculation differs from its assessment runtime")
    return deepcopy(candidate)


def _validate_assessment(source: dict, data: dict) -> None:
    from .leakage_verification import validate_calculation
    request = source_request(source)
    keys(data, {"schema", "request_ref", "calculation", "decision", "polymer_binding", "authority"})
    if (data["schema"] != "ciw.leakage-assessment-payload.v1" or data["request_ref"] != digest(request)
            or data["authority"] != AUTHORITY
            or data["polymer_binding"] != _binding_view(source["metadata"]["leakage_polymer_binding"])):
        raise ValueError("Leakage assessment evidence or authority binding differs")
    validate_calculation(request, data["calculation"])
    if data["decision"] != decision_projection(request, data["calculation"]):
        raise ValueError("Leakage decision differs from its declared balance and uncertainty policy")


def _verify(source: dict, parameters: dict) -> dict:
    from .leakage_verification import verify
    candidate = _candidate(source, parameters)
    return {"schema": "ciw.leakage-verification-payload.v1", "verification_id": new_identity("verification"),
            "assessment_result_id": candidate["result_id"], "assessment_execution_id": candidate["execution_id"],
            "assessment_record_digest": candidate["record_digest"], "request_ref": digest(source_request(source)),
            "report": verify(source_request(source), candidate["data"]["calculation"]), "authority": deepcopy(AUTHORITY)}


def operations(backend=None) -> list[Operation]:
    return [Operation(ASSESS, "backend", lambda s, p: _assess(s, p, backend), lambda: runtime_identity("assessment", backend)),
            Operation(VERIFY, "verification", _verify, lambda: runtime_identity("verification"))]


def registry(backend):
    from .operations.registry import default_registry
    value = default_registry()
    for operation in operations(backend):
        value.register(operation)
    return value


def capability_registry(backend=None, *, bind: bool = False):
    from .control_plane import CapabilityRegistry, Port
    if bind and backend is None:
        raise ValueError("Binding leakage execution requires an explicit pinned backend")
    value = CapabilityRegistry()
    for operation in operations(backend):
        manifest = InstrumentManifest(instrument_id=operation.operation_id, role=operation.role, units={}, frames=(),
            sampling={"kind": "retained_boundary_balance"}, supported_operations=(operation.operation_id,),
            calibration_requirements={"authority": "no machine actuation or causal leak isolation"})
        value.advertise(manifest, runtime=operation.runtime_identity(),
            capabilities={operation.operation_id: ["leakage.balance.assess" if operation.operation_id == ASSESS else "leakage.balance.verify"]},
            inputs={operation.operation_id: {"assessment": Port("ciw.operation-result.v1").to_dict()}
                    if operation.operation_id == VERIFY else {}})
        if bind:
            value.bind(operation)
    return value


def validate_payload(operation: str, data: dict, source: dict, parameters: dict, selection: dict) -> None:
    request = source_request(source)
    if operation == ASSESS:
        keys(parameters, set())
        _validate_assessment(source, data)
        return
    if operation != VERIFY:
        raise ValueError("Unsupported leakage operation")
    candidate = _candidate(source, parameters)
    keys(data, {"schema", "verification_id", "assessment_result_id", "assessment_execution_id",
                "assessment_record_digest", "request_ref", "report", "authority"})
    if (data["schema"] != "ciw.leakage-verification-payload.v1" or data["request_ref"] != digest(request)
            or data["authority"] != AUTHORITY or data["assessment_result_id"] != candidate["result_id"]
            or data["assessment_execution_id"] != candidate["execution_id"]
            or data["assessment_record_digest"] != candidate["record_digest"]):
        raise ValueError("Leakage audit differs from its retained assessment")
    validate_identity(data["verification_id"], "verification")
    from .leakage_verification import validate_report
    validate_report(data["report"])
    if (data["report"]["request_ref"] != digest(request)
            or data["report"]["calculation_ref"] != digest(candidate["data"]["calculation"])
            or data["report"]["decision_policy_ref"] != digest(request["decision_policy"])):
        raise ValueError("Leakage numerical audit report has different scientific references")


def validate_live_dependency(parameters: dict, retained_results: dict) -> None:
    keys(parameters, {"assessment"})
    candidate = parameters["assessment"]
    if (type(candidate) is not dict or type(candidate.get("result_id")) is not str
            or retained_results.get(candidate["result_id"]) != candidate):
        raise ValueError("Leakage dependency is not the actually retained assessment occurrence")


def validate_result_dependencies(results: dict) -> None:
    verification_ids = set()
    for result in results.values():
        operation = result.get("operation_id")
        if operation not in OPERATIONS:
            continue
        validate_runtime(operation, result["runtime"])
        if operation == ASSESS:
            if result["runtime"]["native"] != result["data"]["calculation"]["runtime"]:
                raise ValueError("Leakage result/runtime binding differs")
            continue
        validate_live_dependency(result["parameters"], results)
        identity = result["data"]["verification_id"]
        if identity in verification_ids:
            raise ValueError("Duplicate leakage verification occurrence identity")
        verification_ids.add(identity)


def run(request: dict, destination: Path, *, backend, polymer_directory: Path | None = None,
        _retained_binding: dict | None = None) -> dict:
    from .leakage_contract import validate_request, save_file
    from .polymer_workflow import _execute
    from .session import Session
    if backend is None:
        raise ValueError("Running leakage requires an explicit pinned native backend")
    request = validate_request(request)
    if polymer_directory is not None and _retained_binding is not None:
        raise ValueError("Supply one retained polymer coupling source")
    binding = _polymer_binding(polymer_directory, request) if polymer_directory is not None else _retained_binding
    source = make_source(request, polymer_binding=binding)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_file(destination / "request.json", request)
    session = Session(source, destination, operations=registry(backend))
    assessment = _execute(session, ASSESS, {})
    if assessment["status"] == "completed":
        _execute(session, VERIFY, {"assessment": assessment["result"]})
    session.save_workspace(destination / "workspace.json")
    return inspect(destination)


def _read(destination: Path):
    from .leakage_contract import MAX_BYTES, load_file
    from .session import Session
    from .adapters.subprocess import _json
    destination = Path(destination)
    for name, budget in (("request.json", MAX_BYTES), ("workspace.json", MAX_WORKSPACE_BYTES)):
        path = destination / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > budget:
            raise ValueError("Require bounded regular leakage bundle files")
        with path.open("rb") as stream:
            raw = stream.read(budget + 1)
        if not 0 < len(raw) <= budget:
            raise ValueError("Leakage bundle exceeds its exact byte budget")
        _json(raw)
    with tempfile.TemporaryDirectory(prefix="leakage-inspect-") as directory:
        session = Session.from_workspace(destination / "workspace.json", Path(directory))
    request = source_request(session.run)
    if digest(load_file(destination / "request.json")) != digest(request):
        raise ValueError("Retained leakage request differs from its source evidence")
    attempts = list(session.executions.values())
    if not attempts or [e["operation_id"] for e in attempts] not in ([ASSESS], [ASSESS, VERIFY]):
        raise ValueError("Require exactly the ordered leakage balance and numerical-audit attempts")
    if attempts[0]["status"] == "refused":
        if len(attempts) != 1 or session.results:
            raise ValueError("Refused leakage assessment cannot have dependent results")
    elif len(attempts) != 2:
        raise ValueError("Completed leakage balance requires its numerical-audit attempt")
    return session, request


def inspect(destination: Path) -> dict:
    session, request = _read(destination)
    results = {r["operation_id"]: r for r in session.results.values()}
    assessment = results.get(ASSESS, {}).get("data")
    verification = results.get(VERIFY, {}).get("data")
    completed = all(e["status"] == "completed" for e in session.executions.values())
    verified = (verification or {}).get("report", {}).get("status") == "PASS"
    return {"schema": "ciw.leakage-inspection.v1", "status": "PASS" if completed and verified else "REFUSE",
            "workflow_status": "PASS" if completed and verified else "REFUSE",
            "numerical_audit_status": (verification or {}).get("report", {}).get("status", "NOT_AVAILABLE"),
            "balance_status": (assessment or {}).get("decision", {}).get("status", "NOT_AVAILABLE"),
            "evidence_id": session.run["evidence_id"], "request_ref": digest(request),
            "identity": deepcopy(request["identity"]), "process": request["process"],
            "source_kind": request["source_kind"], "boundary_id": request["boundary_id"], "basis": request["basis"],
            "unit": request["unit"], "assessment": deepcopy(assessment), "verification": deepcopy(verification),
            "polymer_binding": _binding_view(session.run["metadata"]["leakage_polymer_binding"]),
            "occurrences": [{"operation_id": e["operation_id"], "execution_id": e["execution_id"],
                             "result_id": e["result_id"], "status": e["status"],
                             **({"refusal": e["refusal"]} if "refusal" in e else {})} for e in session.executions.values()],
            "fresh_execution": False, "fresh_numerical_verification": False, "authority": deepcopy(AUTHORITY)}


def verify_retained(destination: Path) -> dict:
    from .leakage_verification import verify
    session, request = _read(destination)
    candidate = next((r for r in session.results.values() if r["operation_id"] == ASSESS), None)
    if candidate is None:
        return inspect(destination)
    report = verify(request, candidate["data"]["calculation"])
    return {"schema": "ciw.leakage-fresh-verification.v1", "verification_id": new_identity("verification"),
            "assessment_result_id": candidate["result_id"], "assessment_execution_id": candidate["execution_id"],
            "assessment_record_digest": candidate["record_digest"], "source_evidence_id": session.run["evidence_id"],
            "status": report["status"], "report": report, "fresh_numerical_verification": True,
            "authority": deepcopy(AUTHORITY)}


def replay(destination: Path, output: Path, *, backend) -> dict:
    session, request = _read(destination)
    original = next((r for r in session.results.values() if r["operation_id"] == ASSESS), None)
    if original is not None:
        old, fresh = original["data"]["calculation"]["runtime"], backend.runtime_identity()
        for field in ("schema", "adapter_version", "revision", "source_tree", "module", "source_root",
                      "python_sha256", "python_version", "dependencies"):
            if old[field] != fresh[field]:
                raise ValueError("Replay requires the retained native source, interpreter and dependency identities")
    result = run(request, output, backend=backend, _retained_binding=session.run["metadata"]["leakage_polymer_binding"])
    result["replay_source_evidence_id"] = session.run["evidence_id"]
    return result


def export(directory: Path, destination: Path) -> dict:
    session, request = _read(directory)
    inspection = inspect(directory)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "inspection.json", inspection)
    save_new(destination / "request.json", request)
    # Retain the full uncertainty/runtime/coupling graph alongside the CSV view.
    workspace_bytes = (Path(directory) / "workspace.json").read_bytes()
    with (destination / "workspace.json").open("xb") as stream:
        stream.write(workspace_bytes)
    with (destination / "balance.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["scope", "start_s", "end_s", "unit", "loss_estimate", "declared_lower", "declared_upper",
                         "decision_lower", "decision_upper", "status"])
        decision = (inspection.get("assessment") or {}).get("decision")
        if decision:
            for scope, rows in (("interval", decision["intervals"]), ("whole_window", [decision["window"]])):
                for row in rows:
                    writer.writerow([scope, row["start_s"], row["end_s"], request["unit"], row["loss_estimate"],
                                     *row["declared_interval"], *row["decision_interval"], row["status"]])
    text = escape(json.dumps(inspection, indent=2, allow_nan=False))
    html = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>NET fluid and material balance</title><style>body{font:16px/1.5 system-ui;max-width:1050px;margin:2rem auto;padding:0 1rem;color:#172b38}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}table{border-collapse:collapse}th,td{border:1px solid #ccd8df;padding:.7rem}</style><main>'
            '<h1>Fluid and material balance</h1><p>' + escape(request["boundary_id"]) + '</p><table><tr><th>Workflow</th><th>Numerical audit</th><th>Boundary accounting</th></tr><tr><td>'
            + escape(inspection["workflow_status"]) + '</td><td>' + escape(inspection["numerical_audit_status"]) + '</td><td>'
            + escape(inspection["balance_status"]) + '</td></tr></table><p>A boundary deficit has competing explanations; its cause and location are not isolated. '
            'Uncertainty bands follow the declared policy. Physical validation and calibration traceability are not established.</p>'
            '<details><summary>Full retained assessment and numerical audit</summary><pre>' + text + '</pre></details></main></html>')
    with (destination / "report.html").open("x", encoding="utf-8") as stream:
        stream.write(html)
    artifacts = [{"path": p.name, "sha256": bytes_ref(p.read_bytes()), "size_bytes": p.stat().st_size}
                 for p in sorted(destination.iterdir())]
    result = {"schema": "ciw.leakage-export.v1", "status": "created", "source_evidence_id": session.run["evidence_id"],
              "source_workspace_ref": bytes_ref(workspace_bytes), "artifacts": artifacts,
              "csv_limitations": "marginal bands only; full covariance and evidence remain in workspace.json", "authority": deepcopy(AUTHORITY)}
    save_new(destination / "manifest.json", result)
    return result


def doctor(backend) -> dict:
    from .operations.registry import default_registry
    native = backend.runtime_identity()
    catalog = capability_registry(backend).catalog()
    checks = {"native_pinned_runtime_available": True,
              "two_fixed_operations_advertised": set(catalog["operations"]) == OPERATIONS,
              "no_implicit_bindings": all(not row["bound"] for row in catalog["operations"].values()),
              "no_default_execution_grants": not OPERATIONS.intersection(row["operation_id"] for row in default_registry().describe())}
    return {"schema": "ciw.leakage-tool-readiness.v1", "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "native_runtime": native, "scope": "source_and_tool_contracts_use_qualify_for_finite_execution",
            "authority": deepcopy(AUTHORITY)}


def qualify(destination: Path, *, backend) -> dict:
    from .leakage_contract import example_request
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    checks = [{"name": "pinned_tool_contracts", "passed": doctor(backend)["status"] == "PASS"}]
    for basis in ("volume", "mass"):
        directory = destination / basis
        initial = run(example_request(basis), directory, backend=backend)
        oldbytes = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
        fresh = verify_retained(directory)
        repeated = replay(directory, destination / (basis + "-replay"), backend=backend)
        artifact = export(directory, destination / (basis + "-report"))
        checks.extend([
            {"name": basis + ":native_balance_and_independent_audit", "passed": initial["status"] == "PASS"},
            {"name": basis + ":unaccounted_loss_not_cause", "passed": initial["balance_status"] == "UNACCOUNTED_LOSS" and initial["assessment"]["decision"]["cause_status"] == "NOT_ISOLATED"},
            {"name": basis + ":retained_full_covariance", "passed": initial["assessment"]["calculation"]["raw"]["covariance"] == example_request(basis)["covariance"]["matrix"]},
            {"name": basis + ":read_only_fresh_audit", "passed": fresh["status"] == "PASS" and fresh["verification_id"] != initial["verification"]["verification_id"] and all((directory / name).read_bytes() == raw for name, raw in oldbytes.items())},
            {"name": basis + ":replay_same_evidence_fresh_occurrences", "passed": repeated["status"] == "PASS" and repeated["evidence_id"] == initial["evidence_id"] and {x["execution_id"] for x in initial["occurrences"]}.isdisjoint(x["execution_id"] for x in repeated["occurrences"])},
            {"name": basis + ":export_preserves_covariance_workspace", "passed": artifact["status"] == "created" and any(x["path"] == "workspace.json" for x in artifact["artifacts"])},
        ])
        from .agent_mcp import from_profile, leakage_config
        profile = leakage_config(destination / (basis + "-agent"), basis)
        host = from_profile(profile, instrument="leakage", leakage_backend=backend)
        executed = host.call("net_execute", {"source": "source", "graph": "baseline", "attempt": "original"})
        retry = host.call("net_execute", {"source": "source", "graph": "baseline", "attempt": "original"})
        replayed = host.call("net_replay", {"original_attempt": "original", "new_attempt": "replay"})
        from .session import read_json
        retained = read_json(profile.parent / "agent-output/original/workspace.json")
        audits = [r for r in retained["results"] if r["operation_id"] == VERIFY]
        checks.extend([
            {"name": basis + ":typed_agent_native_graph", "passed": executed["status"] == "completed" and len(executed["execution_ids"]) == 2 and len(audits) == 1 and audits[0]["data"]["report"]["status"] == "PASS"},
            {"name": basis + ":idempotent_agent_retry", "passed": retry["reused_response"] is True and retry["execution_ids"] == executed["execution_ids"]},
            {"name": basis + ":fresh_agent_replay", "passed": replayed["status"] == "completed" and set(executed["execution_ids"]).isdisjoint(replayed["execution_ids"])},
        ])
    report = {"schema": "ciw.leakage-tool-qualification.v1", "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
              "checks": checks, "runtime": runtime_identity("qualification", backend),
              "scope": "finite_native_reference_workflows_not_factory_or_physical_validation", "authority": deepcopy(AUTHORITY)}
    save_new(destination / "qualification.json", report)
    return report
