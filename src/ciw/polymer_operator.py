"""Operator views and finite installed-tool qualification on retained NET evidence."""
from __future__ import annotations

from copy import deepcopy
import csv
from html import escape
import json
from pathlib import Path
import platform

from .control_contracts import bytes_ref, save_new
from .operations.runner import digest
from .polymer_contract import AUTHORITY, PROCESSES, example_request, validate_request
from . import polymer_workflow as workflow


def summarize(inspection: dict) -> dict:
    """Project already validated inspection data; never calculate a new assessment."""
    assessment = inspection.get("assessment") or {}
    metrology = assessment.get("metrology") or {}
    engineering = assessment.get("engineering") or {}
    control = assessment.get("control") or {}
    context = (inspection.get("copilot") or {}).get("context") or {}
    verification = inspection.get("verification") or {}
    simulation = (inspection.get("simulation") or {}).get("simulation") or {}
    return {"schema": "ciw.polymer-operator-summary.v1", "status": inspection["status"],
            "workflow_status": inspection["status"],
            "numerical_audit_status": verification.get("report", {}).get("status", "NOT_AVAILABLE"),
            "part_conformity": metrology.get("status", "NOT_AVAILABLE"),
            "evidence_id": inspection["evidence_id"], "identity": deepcopy(inspection["identity"]),
            "process": assessment.get("process"), "source_kind": inspection["source_kind"],
            "ingress_ref": inspection.get("ingress_ref"),
            "ingress_scope": "native_marginal_sample_projection_nominal_time_membership_joint_covariance_retained" if inspection.get("ingress_ref") else "direct_caller_declared_quantitative_features",
            "measurement_condition": metrology.get("measurement_condition"),
            "quantities": deepcopy(metrology.get("quantities", [])),
            "cooling_status": engineering.get("cooling", {}).get("status", "NOT_AVAILABLE"),
            "control_proposal_status": control.get("status", "NOT_AVAILABLE"),
            "copilot_context_status": context.get("status", "NOT_AVAILABLE"),
            "copilot_abstention_reasons": deepcopy(context.get("abstention_reasons", [])),
            "simulation_status": simulation.get("status", "NOT_AVAILABLE"),
            "occurrences": deepcopy(inspection["occurrences"]),
            "verification_id": verification.get("verification_id"),
            "scope": "retained_measurement_decisions_reference_models_and_toy_control",
            "authority": deepcopy(AUTHORITY)}


def summary(directory: Path) -> dict:
    return summarize(workflow.inspect(directory))


def _table(headings, rows) -> str:
    head = "".join("<th>" + escape(str(value)) + "</th>" for value in headings)
    body = "".join("<tr>" + "".join("<td>" + escape(str(value)) + "</td>" for value in row)
                   + "</tr>" for row in rows)
    return "<table><thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table>"


def _report(view: dict, inspection: dict) -> str:
    quantities = _table(["Quantity", "Unit", "Decision", "Declared interval", "Reason"],
                        [[q["quantity"], q["unit"], q["status"], q["interval"], q["reason"]]
                         for q in view["quantities"]])
    statuses = _table(["Check", "Result"], [[key.replace("_", " "), view[key]] for key in
        ("workflow_status", "numerical_audit_status", "part_conformity", "cooling_status",
         "control_proposal_status", "copilot_context_status", "simulation_status")])
    occurrences = _table(["Operation", "Status", "Execution", "Result"],
                        [[o["operation_id"], o["status"], o["execution_id"], o["result_id"]]
                         for o in view["occurrences"]])
    title = escape(str(view["identity"]["cycle_id"]))
    context = (inspection.get("copilot") or {}).get("context") or {}
    leads = _table(["Quantity", "Document", "Investigation lead"],
                   [[row["quantity"], row["document_id"], row["hypothesis"]]
                    for row in context.get("ranked_hypotheses", [])])
    details = escape(json.dumps(inspection, indent=2, allow_nan=False))
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NET polymer cycle report</title><style>
body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172b38;background:#f5f8fa}
h1,h2{color:#143b4c}table{border-collapse:collapse;width:100%;background:white;margin:1rem 0}
th,td{border:1px solid #ccd8df;padding:.6rem;text-align:left;overflow-wrap:anywhere}th{background:#e7eff3}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}code{overflow-wrap:anywhere}
details{background:white;border:1px solid #ccd8df;padding:1rem} .scope{border-left:4px solid #137f92;padding:1rem;background:white}
</style><main><h1>Polymer cycle: """ + title + "</h1><p>" + escape(str(view["process"])) + " · " + escape(view["source_kind"]) + """</p>
<p class="scope">Workflow completion and numerical audit are separate from part conformity.
Physical validation and calibration traceability are not established. Control is simulation only;
copilot output contains cited investigation leads.</p><h2>Decisions</h2>""" + statuses + "<h2>Metrology</h2>" + quantities + "<h2>Copilot context</h2>" + leads + "<h2>Retained occurrences</h2>" + occurrences + "<p>Evidence: <code>" + escape(view["evidence_id"]) + "</code></p><details><summary>Full validated retained data</summary><pre>" + details + "</pre></details></main></html>"


def export(directory: Path, destination: Path) -> dict:
    """Write a create-only report/CSV projection without mutating retained evidence."""
    session, request = workflow._read(directory)
    inspection = workflow.inspect(directory)
    view = summarize(inspection)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "summary.json", view)
    latest = {row["sensor_id"]: row for row in (inspection.get("assessment") or {}).get("metrology", {}).get("measurements", [])}
    columns = ["cycle_id", "part_id", "process", "source_kind", "measurement_condition", "sensor_id",
               "quantity", "unit", "time_s", "value", "standard_uncertainty", "is_latest_sample",
               "latest_channel_status", "calibration_ref", "clock_ref", "source_ref"]
    with (destination / "measurements.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for sensor in request["sensors"]:
            for index, sample in enumerate(sensor["samples"]):
                writer.writerow({"cycle_id": request["identity"]["cycle_id"], "part_id": request["identity"]["part_id"],
                    "process": request["process"], "source_kind": request["source_kind"],
                    "measurement_condition": request["measurement_condition"],
                    **{key: sensor[key] for key in ("sensor_id", "quantity", "unit", "calibration_ref", "clock_ref", "source_ref")},
                    **sample, "is_latest_sample": index == len(sensor["samples"]) - 1,
                    "latest_channel_status": latest.get(sensor["sensor_id"], {}).get("status", "NOT_AVAILABLE")})
    with (destination / "report.html").open("x", encoding="utf-8") as stream:
        stream.write(_report(view, inspection))
    # The full ingress remains evidence; CSV is expressly a marginal projection.
    if "polymer_ingress" in session.run["metadata"]:
        from .polymer_ingress import save_file
        save_file(destination / "ingress.json", session.run["metadata"]["polymer_ingress"])
    artifacts = [{"path": path.name, "sha256": bytes_ref(path.read_bytes()), "size_bytes": path.stat().st_size}
                 for path in sorted(destination.iterdir())]
    manifest = {"schema": "ciw.polymer-export.v1", "status": "created", "source_evidence_id": view["evidence_id"],
                "source_request_ref": digest(request), "source_workspace_ref": bytes_ref((Path(directory) / "workspace.json").read_bytes()),
                "artifacts": artifacts, "csv_semantics": "exact_retained_samples_with_declared_marginal_standard_uncertainty",
                "csv_limitations": "CSV does not encode joint covariance; retained ingress preserves the native covariance when supplied",
                "authority": deepcopy(AUTHORITY)}
    save_new(destination / "manifest.json", manifest)
    return manifest


def doctor() -> dict:
    """Inspect fixed local tool contracts; create no bindings or execution grants."""
    from .operations.registry import default_registry
    catalog = workflow.capability_registry().catalog()
    default_ids = {row["operation_id"] for row in default_registry().describe()}
    contracts = {name: {"role": catalog["providers"][row["provider"]]["role"],
                       "inputs": row["inputs"], "bound": row["bound"], "runtime": row["runtime"]}
                 for name, row in catalog["operations"].items()}
    checks = {"python_supported": tuple(__import__("sys").version_info[:2]) >= (3, 11),
              "four_fixed_operations_advertised": set(contracts) == workflow.OPERATIONS,
              "no_default_execution_grants": not default_ids.intersection(workflow.OPERATIONS),
              "no_implicit_bindings": all(row["bound"] is False for row in contracts.values())}
    return {"schema": "ciw.polymer-tool-readiness.v1", "status": "PASS" if all(checks.values()) else "FAIL",
            "python": platform.python_version(), "checks": checks, "operations": contracts,
            "scope": "local_tool_contracts_only_use_qualify_to_execute_finite_workflows",
            "authority": deepcopy(AUTHORITY)}


def demo(process: str, destination: Path) -> dict:
    if process not in PROCESSES:
        raise ValueError("Unsupported polymer process")
    destination = Path(destination)
    inspection = workflow.run(example_request(process), destination)
    manifest = export(destination, destination / "report")
    receipt = workflow.verify_retained(destination)
    save_new(destination / "fresh-verification.json", receipt)
    result = summarize(inspection)
    result["artifacts"] = {"workspace": str(destination / "workspace.json"), "report": str(destination / "report" / "report.html"),
                           "measurements": str(destination / "report" / "measurements.csv"),
                           "verification_receipt": str(destination / "fresh-verification.json")}
    result["export_ref"] = digest(manifest)
    return result


def qualify(destination: Path, *, ingress: dict | None = None) -> dict:
    """Finite readiness gate for the installed reference instrument, not factory trials."""
    destination = Path(destination)
    if ingress is not None:
        from . import polymer_ingress
        ingress = polymer_ingress.validate(ingress)
    destination.mkdir(parents=True, exist_ok=False)
    checks = []
    readiness = doctor()
    checks.append({"name": "fixed_tool_contracts", "passed": readiness["status"] == "PASS"})
    for process in sorted(PROCESSES):
        original = destination / process
        view = demo(process, original)
        original_bytes = {p.relative_to(original): p.read_bytes() for p in original.rglob("*") if p.is_file()}
        inspection = workflow.inspect(original)
        repeated = workflow.replay(original, destination / (process + "-replay"))
        fresh = workflow.verify_retained(original)
        first_ids = {o["execution_id"] for o in inspection["occurrences"]}
        repeat_ids = {o["execution_id"] for o in repeated["occurrences"]}
        checks.extend([
            {"name": process + ":complete_and_numerically_verified", "passed": view["workflow_status"] == "PASS" and view["numerical_audit_status"] == "PASS"},
            {"name": process + ":part_nonconformance_separate", "passed": view["part_conformity"] == "NONCONFORMING"},
            {"name": process + ":scoped_copilot_context", "passed": view["copilot_context_status"] == "CONTEXT_READY"},
            {"name": process + ":replay_evidence_and_fresh_occurrences", "passed": repeated["status"] == "PASS" and repeated["evidence_id"] == inspection["evidence_id"] and first_ids.isdisjoint(repeat_ids) and repeated["assessment"] == inspection["assessment"]},
            {"name": process + ":fresh_read_only_audit", "passed": fresh["status"] == "PASS" and fresh["verification_id"] != inspection["verification"]["verification_id"] and all((original / name).read_bytes() == raw for name, raw in original_bytes.items())},
        ])
        from .agent_mcp import from_profile, polymer_config
        profile = polymer_config(destination / (process + "-agent"), process)
        host = from_profile(profile, instrument="polymer")
        executed = host.call("net_execute", {"source": "source", "graph": "baseline", "attempt": "original"})
        retry = host.call("net_execute", {"source": "source", "graph": "baseline", "attempt": "original"})
        replayed = host.call("net_replay", {"original_attempt": "original", "new_attempt": "replay"})
        retained = json.loads((profile.parent / "agent-output/original/workspace.json").read_text(encoding="utf-8"))
        audits = [r for r in retained["results"] if r["operation_id"] == workflow.VERIFY]
        checks.extend([
            {"name": process + ":complete_typed_agent_graph", "passed": executed["status"] == "completed" and len(executed["execution_ids"]) == 4 and len(audits) == 1 and audits[0]["data"]["report"]["status"] == "PASS"},
            {"name": process + ":idempotent_agent_retry", "passed": retry["reused_response"] is True and retry["execution_ids"] == executed["execution_ids"]},
            {"name": process + ":fresh_agent_replay", "passed": replayed["status"] == "completed" and set(executed["execution_ids"]).isdisjoint(replayed["execution_ids"])},
        ])
    if ingress is not None:
        from . import polymer_ingress
        imported = destination / "native-ingress"
        inspection = workflow.run(polymer_ingress.derive(ingress), imported, ingress=ingress)
        export(imported, imported / "report")
        repeated = workflow.replay(imported, destination / "native-ingress-replay")
        checks.append({"name": "native_ingress:retention_audit_and_replay", "passed": inspection["status"] == repeated["status"] == "PASS" and inspection["evidence_id"] == repeated["evidence_id"] and inspection["ingress_ref"] == repeated["ingress_ref"] == digest(ingress)})
    malformed = example_request()
    malformed["schema"] = "invalid"
    try:
        validate_request(malformed)
    except ValueError:
        refused = True
    else:
        refused = False
    checks.append({"name": "malformed_ingress_refused", "passed": refused})
    report = {"schema": "ciw.polymer-tool-qualification.v1", "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
              "scope": "finite_installed_reference_workflows_not_physical_validation", "checks": checks,
              "native_ingress_ref": digest(ingress) if ingress is not None else None,
              "runtime": workflow.runtime_identity("qualification"), "authority": deepcopy(AUTHORITY)}
    save_new(destination / "qualification.json", report)
    return report
