"""Retained, declared-input irrigation planning with separate verification occurrences.

Reported observations remain evidence declarations. Planning does not acquire
sensor data, operate valves, or admit a computed result as physical state.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from hashlib import sha256
import html
import io
import json
import os
from pathlib import Path
import platform
import re
import stat
import tempfile

from .adapters.protocol import InstrumentManifest
from .control_contracts import content_ref, json_tree, keys, save_new
from .core.identities import evidence_id, new_identity, validate_evidence_identity, validate_identity
from .core.records import validate_run_structure
from . import irrigation_contract as contract
from .operations.registry import Operation
from .operations.runner import check_seal, digest

FRAME = "irrigation.configuration_declaration.v1"
PLAN = "irrigation.plan.v1"
VERIFY = "irrigation.verify.v1"
OPERATIONS = (PLAN, VERIFY)
MAX_BUNDLE_FILE_BYTES = 32 * 1024 * 1024
MAX_DECLARATION_FILE_BYTES = 8 * 1024 * 1024
AUTHORITY = {
    "physical_validation": "not_established", "live_sensor_acquisition": "not_performed",
    "hardware_actuation": "not_performed", "state_admission": "not_performed",
    "learned_forecast": "not_established", "richards_pde_solution": "not_performed",
    "fertigation_chemistry": "not_established",
}


def runtime_identity(kind: str) -> dict:
    """Identify installed trusted code; historical provenance activates nothing."""
    import numpy as np
    if kind == "planner":
        from . import irrigation_solver as provider, irrigation_metrology as metrology
        modules = [contract, provider, metrology]
    elif kind == "verifier":
        from . import irrigation_verification as provider, irrigation_reference as reference
        modules = [contract, provider, reference]
    else:
        raise ValueError("Unsupported irrigation runtime kind")
    modules.append(__import__(__name__, fromlist=["*"]))
    raw = b"\0".join(Path(item.__file__).name.encode() + b"\0" +
                     Path(item.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for item in modules)
    return {"provider": "ciw.irrigation." + kind, "version": "1",
            "code_sha256": sha256(raw).hexdigest(), "source_normalization": "utf8_lf",
            "scope": contract.SCOPE,
            "environment": {"python": platform.python_version(), "numpy": np.__version__, "floating_point": "binary64"}}


def validate_runtime(operation: str, runtime: dict | None, *, allow_absent: bool = False) -> None:
    if operation not in OPERATIONS:
        raise ValueError("Unsupported irrigation operation")
    if runtime is None and allow_absent:
        return
    keys(runtime, {"provider", "version", "code_sha256", "source_normalization", "scope", "environment"})
    kind = "planner" if operation == PLAN else "verifier"
    if (runtime["provider"] != "ciw.irrigation." + kind or runtime["version"] != "1"
            or runtime["source_normalization"] != "utf8_lf" or runtime["scope"] != contract.SCOPE):
        raise ValueError("Irrigation runtime provider, version or scope binding differs")
    content_ref("sha256:" + runtime["code_sha256"] if type(runtime["code_sha256"]) is str else None)
    keys(runtime["environment"], {"python", "numpy", "floating_point"})
    version = runtime["environment"]["python"]
    if (type(version) is not str or len(version) > 80
            or re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}[A-Za-z0-9.+-]*", version) is None
            or runtime["environment"]["floating_point"] != "binary64"):
        raise ValueError("Irrigation runtime environment binding differs")
    numpy_version = runtime["environment"]["numpy"]
    if (type(numpy_version) is not str or len(numpy_version) > 80
            or re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}[A-Za-z0-9.+-]*", numpy_version) is None):
        raise ValueError("Irrigation runtime NumPy version must be a bounded version string")


def make_source(request: dict) -> dict:
    request = contract.validate_request(request)
    manifest = InstrumentManifest(
        instrument_id="irrigation-configuration-declaration.v1",
        role="declared_model_configuration", units={"configuration_declaration": "1"},
        frames=(FRAME,), sampling={"kind": "one_configuration_declaration",
                                   "time_semantics": "selection_envelope_not_weather_or_model_clock"},
        supported_operations=OPERATIONS,
        calibration_requirements={"observations": "request retains declared calibration and source references; no live acquisition"},
    )
    source = {"run_schema": "run.v1", "run_id": "run-irrigation-" + digest(request)[7:23],
              "instrument": manifest.instrument_id,
              "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
                           "coordinate_frame": FRAME, "manifest": manifest.to_dict(), "irrigation_request": request,
                           "provenance": {"source": "exact model configuration and reported observation declarations; no acquired channels or computed trajectory",
                                          "generator": "ciw.irrigation_workflow.make_source", "generator_version": 1}},
              "time_s": [0.0], "channels": {"configuration_declaration": {"unit": "1", "values": [0.0]}},
              "render": {}}
    source["evidence_id"] = evidence_id(source)
    return source


def source_request(source: dict) -> dict:
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = source["metadata"]["irrigation_request"]
    if digest(source) != digest(make_source(request)):
        raise ValueError("Irrigation source must be the exact configuration and observation declaration")
    return deepcopy(request)


def _plan(source: dict, parameters: dict) -> dict:
    keys(parameters, set())
    from .irrigation_solver import simulate
    return simulate(source_request(source))


def _candidate(source: dict, parameters: dict) -> dict:
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    check_seal(candidate)
    if (candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != PLAN
            or candidate.get("role") != "backend" or candidate.get("evidence_id") != source["evidence_id"]
            or candidate.get("run_id") != source["run_id"] or candidate.get("parameters") != {}
            or candidate.get("channel") != "configuration_declaration" or candidate.get("interval_s") != [0.0, 1.0]):
        raise ValueError("Irrigation candidate must bind the exact declared source and full planning selection")
    validate_identity(candidate.get("result_id"), "result")
    validate_identity(candidate.get("execution_id"), "execution")
    validate_runtime(PLAN, candidate.get("runtime"))
    contract.validate_result(source_request(source), candidate["data"])
    return candidate


def _verify(source: dict, parameters: dict) -> dict:
    from .irrigation_verification import verify
    candidate = _candidate(source, parameters)
    return {"schema": "ciw.irrigation-verification-payload.v1", "verification_id": new_identity("verification"),
            "candidate_result_id": candidate["result_id"], "candidate_execution_id": candidate["execution_id"],
            "candidate_record_digest": candidate["record_digest"], "source_evidence_id": source["evidence_id"],
            "report": verify(source_request(source), candidate["data"]), "authority": deepcopy(AUTHORITY)}


def operations() -> list[Operation]:
    return [Operation(PLAN, "backend", _plan, lambda: runtime_identity("planner")),
            Operation(VERIFY, "verification", _verify, lambda: runtime_identity("verifier"))]


def registry():
    """Bind the two trusted operations explicitly; saved files bind no providers."""
    from .operations.registry import default_registry
    result = default_registry()
    for operation in operations():
        result.register(operation)
    return result


def validate_payload(operation: str, data: dict, source: dict, parameters: dict, selection: dict) -> None:
    """Validate retained structure and bindings without evaluating any model."""
    if selection.get("channel") != "configuration_declaration" or selection.get("interval_s") != [0.0, 1.0]:
        raise ValueError("Irrigation operations require the full declared configuration selection")
    request = source_request(source)
    if operation == PLAN:
        keys(parameters, set())
        contract.validate_result(request, data)
        return
    if operation != VERIFY:
        raise ValueError("Unsupported irrigation operation")
    candidate = _candidate(source, parameters)
    keys(data, {"schema", "verification_id", "candidate_result_id", "candidate_execution_id",
                "candidate_record_digest", "source_evidence_id", "report", "authority"})
    validate_identity(data["verification_id"], "verification")
    if (data["schema"] != "ciw.irrigation-verification-payload.v1" or data["authority"] != AUTHORITY
            or data["source_evidence_id"] != source["evidence_id"]
            or data["candidate_result_id"] != candidate["result_id"]
            or data["candidate_execution_id"] != candidate["execution_id"]
            or data["candidate_record_digest"] != candidate["record_digest"]):
        raise ValueError("Irrigation verification identity or authority binding differs")
    from .irrigation_verification import validate_report
    validate_report(request, candidate["data"], data["report"])


def validate_live_dependency(parameters: dict, retained_results: dict) -> None:
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    if (type(candidate) is not dict or type(candidate.get("result_id")) is not str
            or retained_results.get(candidate["result_id"]) != candidate):
        raise ValueError("Irrigation verification requires the actually retained planning occurrence")


def validate_result_dependencies(results: dict) -> None:
    identities = set()
    for result in results.values():
        if result.get("operation_id") not in OPERATIONS:
            continue
        validate_runtime(result["operation_id"], result.get("runtime"))
        if result["operation_id"] != VERIFY:
            continue
        validate_live_dependency(result["parameters"], results)
        identity = result["data"]["verification_id"]
        if identity in identities:
            raise ValueError("Duplicate irrigation verification occurrence identity")
        identities.add(identity)


def _execute(session, operation: str, parameters: dict) -> dict:
    reply = session.handle({"protocol_version": 1, "request_id": "irrigation-workload", "type": "operation.execute",
                            "payload": {"operation_id": operation, "parameters": parameters}})
    if reply["type"] != "response":
        raise ValueError(reply["payload"]["message"])
    return reply["payload"]


def run(request: dict, destination: Path) -> dict:
    from .session import Session
    source = make_source(request)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "request.json", source_request(source))
    session = Session(source, destination, operations=registry())
    candidate = _execute(session, PLAN, {})
    if candidate["status"] == "completed":
        verification = _execute(session, VERIFY, {"candidate": candidate["result"]})
        if verification["status"] == "completed":
            save_new(destination / "verification.json", verification["result"]["data"])
    session.save_workspace(destination / "workspace.json")
    return inspect(destination)


def load_regular(path: Path, *, max_bytes: int = MAX_DECLARATION_FILE_BYTES) -> dict:
    """Bound reads and refuse symlinks, devices, pipes, duplicate keys and NaN."""
    from .session import loads_json
    path = Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Irrigation files must be regular files without symlinks")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        actual = os.fstat(descriptor)
        if not stat.S_ISREG(actual.st_mode):
            raise ValueError("Irrigation files must be regular files without symlinks")
        if actual.st_size > max_bytes:
            raise ValueError("Irrigation file exceeds the bounded byte budget")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(max_bytes + 1)
        if not raw or len(raw) > max_bytes:
            raise ValueError("Irrigation file exceeds byte budget or is empty")
    finally:
        os.close(descriptor)
    value = loads_json(raw.decode("utf-8"))
    json_tree(value)
    return value


def _read(destination: Path):
    from .session import Session
    destination = Path(destination)
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("Irrigation bundle requires a regular directory without symlinks")
    artifacts = {"workspace.json": load_regular(destination / "workspace.json", max_bytes=MAX_BUNDLE_FILE_BYTES),
                 "request.json": load_regular(destination / "request.json")}
    if artifacts["workspace.json"].get("workspace_version") != 2:
        raise ValueError("Irrigation bundles require the exact recording-operation workspace version 2")
    receipt = destination / "verification.json"
    if receipt.exists() or receipt.is_symlink():
        artifacts["verification.json"] = load_regular(receipt)
    with tempfile.TemporaryDirectory(prefix="irrigation-inspect-") as temporary:
        root = Path(temporary)
        snapshot = root / "snapshot.json"
        snapshot.write_text(json.dumps(artifacts["workspace.json"], allow_nan=False), encoding="utf-8")
        session = Session.from_workspace(snapshot, root / "restored")
    request = source_request(session.run)
    if digest(contract.validate_request(artifacts["request.json"])) != digest(request):
        raise ValueError("Retained irrigation request differs from exact source declaration")
    candidates = [row for row in session.results.values() if row["operation_id"] == PLAN]
    verifications = [row for row in session.results.values() if row["operation_id"] == VERIFY]
    executions = list(session.executions.values())
    if any(row["operation_id"] not in OPERATIONS for row in executions):
        raise ValueError("Irrigation bundle contains an unrelated execution")
    has_receipt = "verification.json" in artifacts
    if len(executions) == 1 and executions[0]["operation_id"] == PLAN and executions[0]["status"] == "refused":
        if session.results or has_receipt:
            raise ValueError("Refused irrigation planner bundle cannot contain results or a receipt")
        return session, None, None
    if (len(executions) == 2 and len(candidates) == 1 and not verifications
            and sum(row["operation_id"] == VERIFY and row["status"] == "refused" for row in executions) == 1):
        if len(session.results) != 1 or has_receipt:
            raise ValueError("Refused irrigation verifier bundle contains unexpected results or a receipt")
        return session, candidates[0], None
    if len(candidates) != 1 or len(verifications) != 1 or len(session.results) != 2 or len(executions) != 2:
        raise ValueError("Irrigation bundle requires exactly one plan and one independent verification occurrence")
    candidate, verification = candidates[0], verifications[0]
    if verification["parameters"]["candidate"] != candidate:
        raise ValueError("Irrigation verification differs from retained planning occurrence")
    if digest(artifacts.get("verification.json")) != digest(verification["data"]):
        raise ValueError("Irrigation receipt differs from retained verification result")
    return session, candidate, verification


def _inspection_from_read(session, candidate: dict | None, verification: dict | None) -> dict:
    base = {"schema": "ciw.irrigation-inspection.v1", "scope": contract.SCOPE,
            "evidence_id": session.run["evidence_id"],
            "fresh_execution": False, "fresh_numerical_verification": False, "authority": deepcopy(AUTHORITY)}
    if verification is None:
        base.update(status="REFUSE", executions=[{key: deepcopy(value) for key, value in row.items() if key != "parameters"}
                                                 for row in session.executions.values()])
        return base
    report = verification["data"]["report"]
    base.update(status=report["qualification"]["action"], qualification=deepcopy(report["qualification"]),
                planning_status=candidate["data"]["planning_status"],
                operation_id=PLAN, execution_id=candidate["execution_id"], result_id=candidate["result_id"],
                verification_operation_id=VERIFY, verification_execution_id=verification["execution_id"],
                verification_id=verification["data"]["verification_id"], checks=deepcopy(report["checks"]),
                metrics=deepcopy(report["metrics"]))
    return base


def inspect(destination: Path) -> dict:
    return _inspection_from_read(*_read(destination))


def _verify_read(session, candidate: dict | None, verification: dict | None) -> dict:
    from .session import Session
    if verification is None:
        return _inspection_from_read(session, candidate, verification)
    with tempfile.TemporaryDirectory(prefix="irrigation-verify-") as temporary:
        audit = Session(session.run, Path(temporary), operations=registry())
        audit.results[candidate["result_id"]] = deepcopy(candidate)
        audit.selection = deepcopy(session.selection)
        fresh = _execute(audit, VERIFY, {"candidate": candidate})
    if fresh["status"] != "completed":
        raise ValueError("Fresh independent irrigation verification refused: " + fresh["execution"]["refusal"]["message"])
    result = fresh["result"]
    if digest(result["data"]["report"]) != digest(verification["data"]["report"]):
        raise ValueError("Fresh independent irrigation verification differs from retained report")
    checked = _inspection_from_read(session, candidate, verification)
    checked.update(fresh_execution=True, fresh_numerical_verification=True,
                   fresh_verification_id=result["data"]["verification_id"],
                   fresh_verification_execution_id=result["execution_id"], fresh_verification_result_id=result["result_id"],
                   fresh_verification_record=deepcopy(result["data"]),
                   recomputed_report_digest=result["data"]["report"]["record_digest"],
                   recomputed_with_runtime=deepcopy(result["runtime"]))
    return checked


def verify_retained(destination: Path) -> dict:
    return _verify_read(*_read(destination))


def replay(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Replay requires a freshly numerically qualified LOCAL irrigation bundle")
    result = run(source_request(session.run), output)
    _, replay_candidate, _ = _read(output)
    if replay_candidate is None or digest(replay_candidate["data"]) != digest(candidate["data"]):
        raise ValueError("Fresh irrigation replay differs from retained deterministic planning data")
    result.update(replay_source_evidence_id=session.run["evidence_id"],
                  replay_source_result_id=candidate["result_id"],
                  replay_source_fresh_verification_id=checked["fresh_verification_id"],
                  reproducible_planning_data=True)
    return result


CSV_COLUMNS = (
    "day_index", "date", "zone_id", "priority_index", "planning_status", "reasons", "et0_mm",
    "pump_window_relative_start_h", "pump_duration_h", "pump_window_relative_end_h",
    "requested_gross_m3", "allocated_gross_m3", "requested_net_mm", "allocated_net_mm", "unmet_net_mm",
    "depletion_start_mm", "depletion_end_mm", "rainfall_mm", "runoff_mm", "capillary_rise_mm",
    "stress_coefficient", "potential_crop_et_mm", "actual_crop_et_mm", "unmet_crop_et_mm",
    "deep_percolation_mm", "balance_residual_mm", "screening_lower_start_mm", "screening_upper_start_mm",
    "screening_lower_end_mm", "screening_upper_end_mm", "projection_is_descriptive_only",
)


def _csv_rows(request: dict, result: dict):
    """Present sequential relative pump-window proposals, never valve commands."""
    for day_index, day in enumerate(result["days"]):
        offset = 0.0
        for priority_index, zone in enumerate(day["zones"]):
            duration = zone["allocated_gross_m3"] / request["pump"]["rate_m3_h"]
            values = dict(zone, day_index=day_index, date=day["date"], priority_index=priority_index,
                          et0_mm=day["et0_mm"], pump_window_relative_start_h=offset,
                          pump_duration_h=duration, pump_window_relative_end_h=offset + duration)
            yield [json.dumps(values[name], allow_nan=False) if name == "reasons" else values[name]
                   for name in CSV_COLUMNS]
            offset += duration


def _save_text_new(output: Path, text: str) -> None:
    """Publish a bounded text export atomically without replacing any target."""
    output = Path(output)
    raw = text.encode("utf-8")
    if len(raw) > MAX_DECLARATION_FILE_BYTES:
        raise ValueError("Irrigation export exceeds the bounded byte budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".irrigation-", dir=output.parent) as temporary:
        staged = Path(temporary) / "export"
        with staged.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, output)


def _export_receipt(session, candidate: dict, checked: dict, output: Path, media_type: str) -> dict:
    return {"status": "exported", "planning_status": checked["planning_status"], "file": str(output),
            "media_type": media_type, "scope": contract.SCOPE,
            "source_evidence_id": session.run["evidence_id"], "source_result_id": candidate["result_id"],
            "source_execution_id": candidate["execution_id"], "source_record_digest": candidate["record_digest"],
            "retained_verification_id": checked["verification_id"],
            "fresh_verification_id": checked["fresh_verification_id"],
            "fresh_verification_execution_id": checked["fresh_verification_execution_id"],
            "fresh_verification_result_id": checked["fresh_verification_result_id"],
            "recomputed_report_digest": checked["recomputed_report_digest"], "authority": deepcopy(AUTHORITY)}


def export_csv(destination: Path, output: Path) -> dict:
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a freshly numerically qualified LOCAL irrigation proposal can be exported")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(CSV_COLUMNS)
    writer.writerows(_csv_rows(source_request(session.run), candidate["data"]))
    _save_text_new(output, stream.getvalue())
    return _export_receipt(session, candidate, checked, output, "text/csv")


def _display(value) -> str:
    if type(value) is float:
        return format(value, ".8g")
    if type(value) in (dict, list):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    return str(value)


def _table(headers, rows) -> str:
    return "<table><thead><tr>" + "".join("<th>" + html.escape(str(value)) + "</th>" for value in headers) + \
        "</tr></thead><tbody>" + "".join("<tr>" + "".join("<td>" + html.escape(_display(value)) + "</td>"
                                                       for value in row) + "</tr>" for row in rows) + "</tbody></table>"


def export_html(destination: Path, output: Path) -> dict:
    """Write a self-contained operator report from a fresh independent audit."""
    session, candidate, verification = _read(destination)
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Only a freshly numerically qualified LOCAL irrigation proposal can be reported")
    request, result = source_request(session.run), candidate["data"]
    report = checked["fresh_verification_record"]["report"]
    esc = lambda value: html.escape(_display(value))
    parts = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
             "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
             "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">",
             "<title>NET irrigation proposal</title><style>",
             "body{font:16px/1.5 system-ui,sans-serif;color:#18312a;background:#f3f6f1;margin:0}"
             "main{max-width:1280px;padding:32px;margin:auto}h1,h2{line-height:1.2}"
             "section{background:white;padding:20px;margin:20px 0;border:1px solid #ccd9ca;border-radius:8px;overflow:auto}"
             "table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:8px;border-bottom:1px solid #dbe3d9;text-align:left;vertical-align:top}"
             "th{background:#e7eee3}td{overflow-wrap:anywhere}.status{font-size:20px;font-weight:700}"
             "code{overflow-wrap:anywhere}p{max-width:100ch}.note{color:#455b50}",
             "</style></head><body><main><h1>NET daily irrigation proposal</h1>",
             "<p class=\"status\">Numerical qualification: LOCAL · Planning: " + esc(result["planning_status"]) + "</p>",
             "<p>Simulation-only schedule from declared inputs. Pump times below are relative hours within the declared daily window; they are proposals for review and contain no absolute valve command.</p>",
             "<p class=\"note\">Daily root-zone bucket with FAO-56 reference evapotranspiration, a single crop coefficient, declared early-day wetting and same-day drainage. This calculation does not solve Richards' equation or establish field performance.</p>",
             "<section><h2>Inputs and daily limits</h2>"]
    parts.append(_table(("Declaration", "Value"), (
        ("Scope", contract.SCOPE), ("Source kind", request["source"]["kind"]),
        ("Source reference", request["source"]["source_ref"]), ("As of UTC", request["as_of"]),
        ("Maximum observation age (h)", request["max_age_hours"]),
        ("Pump rate (m3/h)", request["pump"]["rate_m3_h"]),
        ("Daily pump window (h)", request["pump"]["available_hours_per_day"]),
        ("Daily gross-water budget (m3)", request["pump"]["water_budget_m3_per_day"]),
        ("Application efficiency (fraction)", request["pump"]["efficiency"]),
        ("Pump parameter reference", request["pump"]["parameter_ref"]),
    )))
    parts.append("</section><section><h2>Initial soil projection and planning holds</h2><p>Screening intervals propagate only the declared initial soil uncertainty with k=2, conditional on fixed weather and parameters. No coverage probability or weather forecast confidence is established. Zone list order defines allocation priority.</p>")
    parts.append(_table(("Zone", "Priority", "Status", "Reasons", "TAW (mm)", "RAW (mm)", "Depletion (mm)", "Standard uncertainty (mm)", "Screening lower (mm)", "Screening upper (mm)", "Descriptive only"),
                        ([row[name] for name in ("zone_id", "priority_index", "planning_status", "reasons", "taw_mm", "raw_mm", "depletion_mm", "standard_uncertainty_mm", "screening_lower_mm", "screening_upper_mm", "projection_is_descriptive_only")]
                         for row in result["initial_zones"])))
    parts.append("<h2>Declared soil, crop and geometry parameters</h2>")
    parts.append(_table(("Zone", "Area (m2)", "Field capacity (m3/m3)", "Wilting point (m3/m3)", "Root depth (m)", "Crop coefficient", "Depletion fraction", "Target depletion (mm)", "Maximum net irrigation (mm/day)", "Capillary rise (mm/day)", "Parameter reference"),
                        ([row[name] for name in ("zone_id", "area_m2", "theta_fc", "theta_wp", "root_depth_m", "crop_coefficient", "depletion_fraction", "target_depletion_mm", "max_daily_net_mm", "capillary_rise_mm_per_day", "parameter_ref")]
                         for row in request["zones"])))
    parts.append("</section><section><h2>Observation and calibration declarations</h2>")
    observations = []
    as_of = contract.utc_datetime(request["as_of"])
    for zone in request["zones"]:
        for row in zone["soil_measurements"]["observations"]:
            observations.append((zone["zone_id"], row["observation_id"], row["calibrated_theta_m3_m3"],
                                 row["observed_at"], (as_of - contract.utc_datetime(row["observed_at"])).total_seconds() / 3600.0,
                                 row["calibrated_until"], row["calibration_ref"], row["clock_ref"]))
    parts.append(_table(("Zone", "Observation", "Theta (m3/m3)", "Observed UTC", "Age (h)", "Calibrated until UTC", "Calibration reference", "Clock reference"), observations))
    parts.append("<p>These references are retained declarations; this report does not authenticate their referenced records.</p></section><section><h2>Daily budget and reference evapotranspiration</h2>")
    parts.append(_table(("Date", "ET0 (mm/day)", "Available gross (m3)", "Allocated gross (m3)", "Remaining gross (m3)", "Pump duration (h)", "Unmet gross (m3)", "Weather reference"),
                        ((day["date"], day["et0_mm"], day["available_gross_m3"], day["allocated_gross_m3"],
                          day["remaining_gross_m3"], day["pump_hours"], day["unmet_gross_m3"], weather["weather_ref"])
                         for day, weather in zip(result["days"], request["weather"]))))
    parts.append("<h2>Declared daily weather inputs</h2>")
    parts.append(_table(("Date", "Tmin (degC)", "Tmax (degC)", "Pressure (kPa)", "Wind at 2 m (m/s)", "Net radiation (MJ/m2/day)", "Soil heat flux (MJ/m2/day)", "Actual vapour pressure (kPa)", "Rainfall (mm)", "Runoff (mm)"),
                        ([row[name] for name in ("date", "temp_min_c", "temp_max_c", "pressure_kpa", "wind_2m_m_s", "net_radiation_mj_m2_day", "soil_heat_flux_mj_m2_day", "actual_vapour_pressure_kpa", "rainfall_mm", "runoff_mm")]
                         for row in request["weather"])))
    parts.append("</section><section><h2>Sequential pump-window proposal and water balance</h2>")
    selected = ("date", "zone_id", "planning_status", "reasons", "pump_window_relative_start_h", "pump_duration_h", "pump_window_relative_end_h",
                "allocated_gross_m3", "allocated_net_mm", "unmet_net_mm", "actual_crop_et_mm", "deep_percolation_mm", "depletion_end_mm", "balance_residual_mm")
    labels = ("Date", "Zone", "Status", "Reasons", "Relative start (h)", "Duration (h)", "Relative end (h)",
              "Gross proposal (m3)", "Net irrigation (mm)", "Unmet irrigation (mm)", "Actual crop ET (mm)", "Deep percolation (mm)", "End depletion (mm)", "Balance residual (mm)")
    indices = [CSV_COLUMNS.index(name) for name in selected]
    parts.append(_table(labels, ([row[index] for index in indices] for row in _csv_rows(request, result))))
    parts.append("</section><section><h2>Reported flow and pressure indicators</h2><p>Residual indicators can have several causes. They do not uniquely diagnose leaks, clogs or stuck valves.</p>")
    parts.append(_table(("Telemetry", "Zone", "Quality", "Reasons", "Flow residual (m3/h)", "Pressure residual (kPa)", "Indicators"),
                        ([row[name] for name in ("telemetry_id", "zone_id", "quality_status", "reasons", "flow_residual_m3_h", "pressure_residual_kpa", "indicators")]
                         for row in result["telemetry"])))
    parts.append(_table(("Telemetry", "Commanded open", "Expected flow (m3/h)", "Reported flow (m3/h)", "Flow tolerance (m3/h)", "Expected pressure (kPa)", "Reported pressure (kPa)", "Pressure tolerance (kPa)"),
                        ([row[name] for name in ("telemetry_id", "commanded_open", "expected_flow_m3_h", "observed_flow_m3_h", "flow_tolerance_m3_h", "expected_pressure_kpa", "observed_pressure_kpa", "pressure_tolerance_kpa")]
                         for row in request["telemetry"])))
    parts.append(_table(("Telemetry", "Observed UTC", "Age (h)", "Calibrated until UTC", "Calibration reference", "Clock reference"),
                        ((row["telemetry_id"], row["observed_at"],
                          (as_of - contract.utc_datetime(row["observed_at"])).total_seconds() / 3600.0,
                          row["calibrated_until"], row["calibration_ref"], row["clock_ref"])
                         for row in request["telemetry"])))
    parts.append("</section><section><h2>Fresh independent numerical audit</h2>")
    parts.append(_table(("Check", "Scaled residual", "Tolerance", "Status"),
                        ((row["name"], row["value"], row["tolerance"], row["status"]) for row in report["checks"])))
    parts.append(_table(("Summary metric", "Value"), report["metrics"]["summary"].items()))
    identities = _export_receipt(session, candidate, checked, output, "text/html")
    parts.append(_table(("Identity", "Value"), ((name, value) for name, value in identities.items()
                                              if name not in {"authority", "status", "file", "media_type", "planning_status"})))
    parts.append("</section><section><h2>Authority</h2>" + _table(("Boundary", "Status"), AUTHORITY.items()) +
                 "</section></main></body></html>")
    _save_text_new(output, "".join(parts))
    return identities
