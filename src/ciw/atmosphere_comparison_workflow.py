"""Retained atmospheric reference comparisons on the existing Session substrate.

Reference data remain declarations. Numerical verification, agreement with a
reference, physical validation and state admission retain separate meanings.
Saved records are inspected without activating their retained providers.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from hashlib import sha256
from pathlib import Path
import platform
import tempfile

from . import atmosphere_workflow as atmosphere
from .atmosphere_comparison_contract import make_reference_source, reference_from_source
from .control_contracts import keys, load, save_new
from .core.identities import new_identity, validate_identity
from .operations.registry import Operation
from .operations.runner import check_seal, digest, seal

COMPARE = "atmosphere.compare.v1"
VERIFY = "atmosphere.compare-verify.v1"
MAX_BUNDLE_FILE_BYTES = atmosphere.MAX_BUNDLE_FILE_BYTES
AUTHORITY = {"physical_validation": "not_established", "calibration_validation": "not_established",
             "measurement_authenticity": "not_established", "reference_independence": "not_established",
             "state_admission": "not_performed", "hardware_actuation": "not_performed"}
BENCHMARK_CLAIMS = {"numerical_scope_only": True, "published_reference_agreement_only": True,
                    "physical_validation": "not_established", "calibration_validation": "not_established",
                    "state_admission": "not_performed"}
CSV_FIELDS = ("sample_index", "height_m", "field", "unit", "model_value", "reference_value",
              "signed_difference", "absolute_difference", "engineering_allowance", "reference_bound",
              "total_allowance", "normalized_acceptance_residual", "status")
_RESULT_FIELDS = {"schema", "result_id", "execution_id", "operation_id", "evidence_id", "run_id",
                  "selection_revision", "channel", "interval_s", "created_at", "recording_file",
                  "verification_id", "verification_status", "role", "runtime", "parameters", "data",
                  "record_digest"}
_PARAMETER_FIELDS = {"atmospheric_candidate", "atmospheric_verification", "reference_source", "policy"}


def _equal(left, right) -> bool:
    return digest(left) == digest(right)


def runtime_identity(kind: str) -> dict:
    """Identify fixed installed code; stored code hashes never select a provider."""
    from . import atmosphere_comparison_contract as contract
    if kind == "comparator":
        from . import atmosphere_comparison as provider
    elif kind == "verifier":
        from . import atmosphere_comparison_verification as provider
    else:
        raise ValueError("Unsupported atmospheric comparison runtime kind")
    modules = [contract, provider, __import__(__name__, fromlist=["*"])]
    raw = b"\0".join(Path(module.__file__).name.encode() + b"\0" +
                     Path(module.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for module in modules)
    return {"provider": "ciw.atmosphere.comparison." + kind, "version": "1",
            "code_sha256": sha256(raw).hexdigest(), "source_normalization": "utf8_lf",
            "scope": "bounded_retained_atmospheric_reference_comparison_only",
            "environment": {"python": platform.python_version(), "floating_point": "binary64"}}


def _validate_runtime(operation: str, runtime: dict) -> None:
    if operation not in {COMPARE, VERIFY}:
        raise ValueError("Unsupported atmospheric comparison operation")
    keys(runtime, {"provider", "scope", "version", "source_normalization", "code_sha256", "environment"})
    kind = "comparator" if operation == COMPARE else "verifier"
    if (runtime["provider"] != "ciw.atmosphere.comparison." + kind
            or runtime["scope"] != "bounded_retained_atmospheric_reference_comparison_only"
            or runtime["version"] != "1" or runtime["source_normalization"] != "utf8_lf"):
        raise ValueError("Atmospheric comparison runtime contradicts its fixed provider profile")
    code_hash = runtime["code_sha256"]
    if (type(code_hash) is not str or len(code_hash) != 64
            or any(character not in "0123456789abcdef" for character in code_hash)):
        raise ValueError("Atmospheric comparison runtime requires a retained SHA-256 code identity")
    keys(runtime["environment"], {"python", "floating_point"})
    environment = runtime["environment"]
    if (type(environment["python"]) is not str or not environment["python"].strip()
            or len(environment["python"]) > 40 or environment["floating_point"] != "binary64"):
        raise ValueError("Atmospheric comparison runtime environment declaration differs")


def _outer(result: dict, source: dict, operation: str, role: str) -> None:
    from .session import _channel_for_run, _interval_for_run, _recording_file, _timestamp
    keys(result, _RESULT_FIELDS)
    check_seal(result)
    if (result["schema"] != "ciw.operation-result.v1" or result["operation_id"] != operation
            or result["role"] != role or result["evidence_id"] != source["evidence_id"]
            or result["run_id"] != source["run_id"] or result["verification_id"] is not None
            or result["verification_status"] != "not_verified"):
        raise ValueError("Atmospheric comparison dependency must bind its exact source and fixed operation")
    validate_identity(result["result_id"], "result")
    validate_identity(result["execution_id"], "execution")
    if (result["recording_file"] != _recording_file(source)
            or type(result["selection_revision"]) is not int or result["selection_revision"] < 0):
        raise ValueError("Atmospheric comparison dependency recording or selection binding differs")
    _timestamp(result["created_at"], "Atmospheric dependency created_at")
    _channel_for_run(source, result["channel"])
    _interval_for_run(source, result["interval_s"])
    if operation in {COMPARE, VERIFY}:
        _validate_runtime(operation, result["runtime"])
    else:
        atmosphere._validate_runtime(operation, result["runtime"])


def _source_parameters(source: dict, parameters: dict, *, fresh: bool = False):
    """Bind old occurrences and a real reference Run without numerical replay by default."""
    from . import atmosphere_comparison_contract as contract
    keys(parameters, _PARAMETER_FIELDS)
    request = atmosphere.source_request(source)
    compile_id, verify_id = atmosphere._operation_ids(request)
    candidate = atmosphere._candidate(source, {"candidate": parameters["atmospheric_candidate"]})
    _outer(candidate, source, compile_id, "backend")
    verification = parameters["atmospheric_verification"]
    _outer(verification, source, verify_id, "verification")
    if not _equal(verification["parameters"], {"candidate": candidate}):
        raise ValueError("Atmospheric comparison requires the exact retained source verification candidate")
    atmosphere.validate_payload(verify_id, verification["data"], source,
                                verification["parameters"], {})
    old_report = verification["data"]["report"]
    if old_report["qualification"]["action"] != "LOCAL":
        raise ValueError("Atmospheric comparison requires a qualified LOCAL source profile")
    reference = reference_from_source(parameters["reference_source"])
    policy = contract.validate_policy(reference, parameters["policy"])
    if fresh:
        report = atmosphere._modules(request)[2].verify(request, candidate["data"])
        if not _equal(report, old_report) or report["qualification"]["action"] != "LOCAL":
            raise ValueError("Fresh atmospheric verification differs or is not qualified LOCAL")
    bindings = {"source_evidence_id": source["evidence_id"], "source_result_id": candidate["result_id"],
                "source_execution_id": candidate["execution_id"], "source_record_digest": candidate["record_digest"],
                "verification_id": verification["data"]["verification_id"],
                "recomputed_report_digest": old_report["record_digest"],
                "reference_evidence_id": parameters["reference_source"]["evidence_id"]}
    contract.validate_inputs(request, candidate["data"], reference, policy, bindings)
    return request, candidate, verification, reference, policy, bindings


def _compare(source: dict, parameters: dict) -> dict:
    from .atmosphere_comparison import compare
    request, candidate, _, reference, policy, bindings = _source_parameters(source, parameters, fresh=True)
    return compare(request, candidate["data"], reference, policy, bindings)


def _candidate(source: dict, parameters: dict, *, fresh: bool = False):
    from .atmosphere_comparison import validate_comparison
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    _outer(candidate, source, COMPARE, "backend")
    inputs = _source_parameters(source, candidate["parameters"], fresh=fresh)
    request, old_candidate, _, reference, policy, bindings = inputs
    validate_comparison(request, old_candidate["data"], reference, policy, candidate["data"], bindings)
    return candidate, inputs


def _verify(source: dict, parameters: dict) -> dict:
    from .atmosphere_comparison_verification import verify
    candidate, inputs = _candidate(source, parameters, fresh=True)
    request, old_candidate, _, reference, policy, bindings = inputs
    return {"schema": "ciw.atmosphere-comparison-verification-payload.v1",
            "comparison_verification_id": new_identity("verification"),
            "candidate_result_id": candidate["result_id"], "candidate_execution_id": candidate["execution_id"],
            "candidate_record_digest": candidate["record_digest"],
            "report": verify(request, old_candidate["data"], reference, policy, candidate["data"], bindings),
            "authority": deepcopy(AUTHORITY)}


def operations() -> list[Operation]:
    return [Operation(COMPARE, "backend", _compare, lambda: runtime_identity("comparator")),
            Operation(VERIFY, "verification", _verify, lambda: runtime_identity("verifier"))]


def registry():
    """Add explicit trusted bindings while leaving both existing registries unchanged."""
    result = atmosphere.registry()
    for operation in operations():
        result.register(operation)
    return result


def validate_payload(operation: str, data: dict, source: dict, parameters: dict, selection: dict) -> None:
    """Validate stored content without invoking any numerical provider."""
    if operation == COMPARE:
        from .atmosphere_comparison import validate_comparison
        request, candidate, _, reference, policy, bindings = _source_parameters(source, parameters)
        validate_comparison(request, candidate["data"], reference, policy, data, bindings)
    elif operation == VERIFY:
        from .atmosphere_comparison_verification import validate_report
        candidate, inputs = _candidate(source, parameters)
        request, old_candidate, _, reference, policy, bindings = inputs
        keys(data, {"schema", "comparison_verification_id", "candidate_result_id", "candidate_execution_id",
                    "candidate_record_digest", "report", "authority"})
        validate_identity(data["comparison_verification_id"], "verification")
        if (data["schema"] != "ciw.atmosphere-comparison-verification-payload.v1"
                or not _equal(data["authority"], AUTHORITY)
                or data["candidate_result_id"] != candidate["result_id"]
                or data["candidate_execution_id"] != candidate["execution_id"]
                or data["candidate_record_digest"] != candidate["record_digest"]):
            raise ValueError("Atmospheric comparison verification identity or authority differs")
        validate_report(request, old_candidate["data"], reference, policy, candidate["data"], data["report"], bindings)
    else:
        raise ValueError("Unsupported atmospheric comparison operation")


def validate_result_dependencies(results: dict) -> None:
    """Embedded dependencies must equal actual retained scientific occurrences."""
    identities = set()
    for result in results.values():
        operation = result.get("operation_id")
        if operation in {COMPARE, VERIFY}:
            _validate_runtime(operation, result.get("runtime"))
        if operation == COMPARE:
            for field in ("atmospheric_candidate", "atmospheric_verification"):
                dependency = result["parameters"][field]
                if not _equal(results.get(dependency["result_id"]), dependency):
                    raise ValueError("Comparison atmospheric dependency differs from its retained occurrence")
        elif operation == VERIFY:
            dependency = result["parameters"]["candidate"]
            if not _equal(results.get(dependency["result_id"]), dependency):
                raise ValueError("Comparison verification candidate differs from its retained occurrence")
        if operation in {atmosphere.VERIFY, atmosphere.MOIST_VERIFY, VERIFY}:
            name = "comparison_verification_id" if operation == VERIFY else "verification_id"
            identity = result["data"][name]
            if identity in identities:
                raise ValueError("Duplicate scientific verification occurrence identity")
            identities.add(identity)


def run(original_dir: Path, reference: dict, policy: dict, destination: Path) -> dict:
    """Clone retained source occurrences and execute a comparison without recompiling."""
    from .atmosphere_comparison_contract import validate_policy, validate_reference
    from .session import Session
    reference = validate_reference(reference)
    policy = validate_policy(reference, policy)
    original, candidate, verification = atmosphere._read(original_dir)
    checked = atmosphere._verify_read(original, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Atmospheric comparison requires a freshly verified LOCAL source profile")
    parameters = {"atmospheric_candidate": deepcopy(candidate), "atmospheric_verification": deepcopy(verification),
                  "reference_source": make_reference_source(reference), "policy": policy}
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "atmosphere-request.json", atmosphere.source_request(original.run))
    save_new(destination / "reference.json", reference)
    save_new(destination / "policy.json", policy)
    save_new(destination / "preservation.json", original._atmosphere_preservation)
    session = Session(original.run, destination, operations=registry())
    session.selection = deepcopy(original.selection)
    session.results = deepcopy(original.results)
    session.executions = deepcopy(original.executions)
    for record in list(session.results.values()) + list(session.executions.values()):
        name = record.get("result_id") if record["schema"] == "ciw.operation-result.v1" else record["execution_id"]
        save_new(destination / (name + ".json"), record)
    comparison = atmosphere._execute(session, COMPARE, parameters)
    independent = None
    if comparison["status"] == "completed":
        independent = atmosphere._execute(session, VERIFY, {"candidate": comparison["result"]})
    session.save_workspace(destination / "workspace.json")
    if independent is not None and independent["status"] == "completed":
        save_new(destination / "comparison-verification.json", independent["result"]["data"])
    return inspect(destination)


def _file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Atmospheric comparison bundle files must be regular files without symlinks")
    if path.stat().st_size > MAX_BUNDLE_FILE_BYTES:
        raise ValueError("Atmospheric comparison bundle file exceeds the bounded 8 MiB budget")


def _preflight(destination: Path) -> None:
    for name in ("workspace.json", "atmosphere-request.json", "reference.json", "policy.json", "preservation.json"):
        _file(destination / name)
    optional = destination / "comparison-verification.json"
    if optional.exists() or optional.is_symlink():
        _file(optional)


def _read(destination: Path):
    """Read one bounded bundle snapshot without registration or numerical replay."""
    from .atmosphere_comparison_contract import validate_policy, validate_reference
    from .session import Session
    destination = Path(destination)
    _preflight(destination)
    with tempfile.TemporaryDirectory(prefix="atmosphere-comparison-inspect-") as temporary:
        session = Session.from_workspace(destination / "workspace.json", Path(temporary))
    validate_result_dependencies(session.results)
    request = atmosphere.source_request(session.run)
    contract, _, _, preservation_module, _ = atmosphere._modules(request)
    retained_request = contract.validate_request(load(destination / "atmosphere-request.json"))
    if not _equal(retained_request, request):
        raise ValueError("Retained comparison atmosphere request differs from source evidence")
    reference = validate_reference(load(destination / "reference.json"))
    policy = validate_policy(reference, load(destination / "policy.json"))
    compile_id, verify_id = atmosphere._operation_ids(request)
    old_candidates = [result for result in session.results.values() if result["operation_id"] == compile_id]
    old_verifications = [result for result in session.results.values() if result["operation_id"] == verify_id]
    comparisons = [result for result in session.results.values() if result["operation_id"] == COMPARE]
    verifications = [result for result in session.results.values() if result["operation_id"] == VERIFY]
    if len(old_candidates) != 1 or len(old_verifications) != 1:
        raise ValueError("Comparison bundle requires the original atmospheric candidate and verification")
    old_candidate, old_verification = old_candidates[0], old_verifications[0]
    expected_parameters = {"atmospheric_candidate": old_candidate, "atmospheric_verification": old_verification,
                           "reference_source": make_reference_source(reference), "policy": policy}
    _source_parameters(session.run, expected_parameters)
    preservation = load(destination / "preservation.json")
    preservation_module.validate(preservation, request, old_candidate["data"], old_verification["data"]["report"])
    session._atmosphere_preservation = deepcopy(preservation)
    allowed = {compile_id, verify_id, COMPARE, VERIFY}
    executions = list(session.executions.values())
    if any(entry["operation_id"] not in allowed for entry in executions):
        raise ValueError("Atmospheric comparison bundle contains an unrelated execution")
    for entry in executions:
        if entry["operation_id"] in {COMPARE, VERIFY} and entry["runtime"] is not None:
            _validate_runtime(entry["operation_id"], entry["runtime"])
    if any(result["operation_id"] not in allowed for result in session.results.values()):
        raise ValueError("Atmospheric comparison bundle contains an unrelated result")
    original_executions = [entry for entry in executions if entry["operation_id"] in {compile_id, verify_id}]
    attempts = [entry for entry in executions if entry["operation_id"] in {COMPARE, VERIFY}]
    if len(original_executions) != 2 or any(entry["status"] != "completed" for entry in original_executions):
        raise ValueError("Comparison bundle requires the two completed original atmospheric executions")
    receipt = destination / "comparison-verification.json"
    present = receipt.exists() or receipt.is_symlink()
    compare_attempts = [entry for entry in attempts if entry["operation_id"] == COMPARE]
    verify_attempts = [entry for entry in attempts if entry["operation_id"] == VERIFY]
    if len(compare_attempts) != 1 or not _equal(compare_attempts[0]["parameters"], expected_parameters):
        raise ValueError("Comparison attempt does not bind retained source, reference and policy artifacts")
    if compare_attempts[0]["status"] == "refused":
        if len(attempts) != 1 or comparisons or verifications or len(session.results) != 2 or present:
            raise ValueError("Refused comparator bundle contains unexpected results or verification receipts")
        return session, old_candidate, old_verification, None, None
    if len(comparisons) != 1 or len(verify_attempts) != 1:
        raise ValueError("Comparison bundle requires one comparator and one verification attempt")
    comparison = comparisons[0]
    if (not _equal(comparison["parameters"], expected_parameters)
            or not _equal(verify_attempts[0]["parameters"], {"candidate": comparison})):
        raise ValueError("Comparison verification does not bind the retained comparison occurrence")
    if verify_attempts[0]["status"] == "refused":
        if len(attempts) != 2 or verifications or len(session.results) != 3 or present:
            raise ValueError("Refused comparison verifier bundle contains unexpected results or receipts")
        return session, old_candidate, old_verification, comparison, None
    if len(verifications) != 1 or len(session.results) != 4 or len(executions) != 4 or not present:
        raise ValueError("Comparison bundle requires all four retained result and execution occurrences")
    verification = verifications[0]
    if not _equal(load(receipt), verification["data"]):
        raise ValueError("Comparison verification artifact differs from its retained occurrence")
    return session, old_candidate, old_verification, comparison, verification


def _bindings(session, old_candidate: dict, old_verification: dict, comparison: dict | None,
              verification: dict | None) -> dict:
    result = {"source_evidence_id": session.run["evidence_id"], "source_result_id": old_candidate["result_id"],
              "source_execution_id": old_candidate["execution_id"], "source_record_digest": old_candidate["record_digest"],
              "verification_id": old_verification["data"]["verification_id"],
              "recomputed_report_digest": old_verification["data"]["report"]["record_digest"]}
    if comparison is not None:
        result["reference_evidence_id"] = comparison["parameters"]["reference_source"]["evidence_id"]
        result["comparison_result_id"] = comparison["result_id"]
        result["comparison_execution_id"] = comparison["execution_id"]
    else:
        attempt = next(entry for entry in session.executions.values() if entry["operation_id"] == COMPARE)
        result["reference_evidence_id"] = attempt["parameters"]["reference_source"]["evidence_id"]
    if verification is not None:
        result["comparison_verification_id"] = verification["data"]["comparison_verification_id"]
    return result


def _inspection_from_read(session, old_candidate, old_verification, comparison, verification) -> dict:
    result = {"schema": "ciw.atmosphere-comparison-inspection.v1", "fresh_execution": False,
              "fresh_numerical_verification": False, **_bindings(session, old_candidate, old_verification, comparison, verification),
              "authority": deepcopy(AUTHORITY)}
    if verification is None:
        result.update(status="REFUSE", agreement_status="NOT_EVALUATED", verification_status="NOT_VERIFIED",
                      executions=[{name: deepcopy(value) for name, value in entry.items() if name != "parameters"}
                                  for entry in session.executions.values()])
        return result
    report = verification["data"]["report"]
    result.update(status=report["qualification"]["action"], agreement_status=comparison["data"]["agreement_status"],
                  verification_status=report["status"], qualification=deepcopy(report["qualification"]),
                  checks=deepcopy(report["checks"]), metrics=deepcopy(report["metrics"]),
                  comparison_digest=comparison["data"]["record_digest"],
                  comparison_verification_report_digest=report["record_digest"])
    return result


def inspect(destination: Path) -> dict:
    return _inspection_from_read(*_read(destination))


def _verify_read(session, old_candidate, old_verification, comparison, verification) -> dict:
    """Numerically audit the already validated tuple without another file read."""
    old_checked = atmosphere._verify_read(session, old_candidate, old_verification)
    if old_checked["status"] != "LOCAL":
        raise ValueError("Retained comparison source is not freshly qualified LOCAL")
    result = _inspection_from_read(session, old_candidate, old_verification, comparison, verification)
    if verification is None:
        return result
    from .atmosphere_comparison_verification import verify
    request, candidate, _, reference, policy, bindings = _source_parameters(session.run, comparison["parameters"])
    fresh = verify(request, candidate["data"], reference, policy, comparison["data"], bindings)
    if not _equal(fresh, verification["data"]["report"]):
        raise ValueError("Independent comparison recomputation differs from retained verification report")
    result["fresh_numerical_verification"] = True
    result["recomputed_comparison_report_digest"] = fresh["record_digest"]
    result["recomputed_with_runtime"] = runtime_identity("verifier")
    return result


def verify_retained(destination: Path) -> dict:
    return _verify_read(*_read(destination))


def _export_read(destination: Path):
    snapshot = _read(destination)
    checked = _verify_read(*snapshot)
    if checked["status"] != "LOCAL" or checked["verification_status"] != "PASS":
        raise ValueError("Only a numerically verified LOCAL comparison can be exported")
    return snapshot, checked


def _export_receipt(output: Path, snapshot, checked: dict) -> dict:
    return {"status": "exported", "file": str(output), "agreement_status": checked["agreement_status"],
            "verification_status": checked["verification_status"],
            **_bindings(*snapshot), "recomputed_comparison_report_digest": checked["recomputed_comparison_report_digest"],
            "authority": deepcopy(AUTHORITY)}


def export_json(destination: Path, output: Path) -> dict:
    snapshot, checked = _export_read(destination)
    _, _, _, comparison, verification = snapshot
    payload = seal({"schema": "ciw.atmosphere-comparison-export.v1", "comparison": deepcopy(comparison["data"]),
                    "verification": deepcopy(verification["data"]), "bindings": _bindings(*snapshot),
                    "authority": deepcopy(AUTHORITY)})
    save_new(output, payload)
    return _export_receipt(output, snapshot, checked)


def export_csv(destination: Path, output: Path) -> dict:
    snapshot, checked = _export_read(destination)
    comparison = snapshot[3]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(comparison["data"]["rows"])
    return _export_receipt(output, snapshot, checked)


def _benchmark_directories(destination: Path, name: str) -> tuple[Path, Path]:
    # Names are supplied exclusively by the fixed installed table, never by a
    # retained path. Reject symlink traversal through every bounded directory.
    case = destination / "cases" / name
    for directory in (destination, destination / "cases", case, case / "atmosphere", case / "comparison"):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Benchmark case directories must be retained directories without symlinks")
    return case / "atmosphere", case / "comparison"


def _benchmark_case_reads(destination: Path):
    from .atmosphere_reference_benchmark import cases
    snapshots = []
    occurrences = set()
    for case in cases():
        source_dir, comparison_dir = _benchmark_directories(destination, case["name"])
        original = atmosphere._read(source_dir)
        snapshot = _read(comparison_dir)
        source_session, source_candidate, source_verification = original
        session, old_candidate, old_verification, comparison, verification = snapshot
        if (not _equal(atmosphere.source_request(session.run), case["request"])
                or not _equal(source_session.run, session.run)
                or not _equal(source_candidate, old_candidate) or not _equal(source_verification, old_verification)
                or not _equal(source_session._atmosphere_preservation, session._atmosphere_preservation)):
            raise ValueError("Benchmark comparison differs from its actual retained atmospheric source case")
        for identity, execution in source_session.executions.items():
            if not _equal(session.executions.get(identity), execution):
                raise ValueError("Benchmark comparison changed an original atmospheric execution occurrence")
        if comparison is None:
            parameters = next(entry for entry in session.executions.values() if entry["operation_id"] == COMPARE)["parameters"]
        else:
            parameters = comparison["parameters"]
        if (not _equal(reference_from_source(parameters["reference_source"]), case["reference"])
                or not _equal(parameters["policy"], case["policy"])):
            raise ValueError("Benchmark reference or acceptance policy differs from its fixed published case")
        # A source bundle and its comparison copy intentionally share old
        # occurrences. Distinct published cases must retain distinct events.
        case_occurrences = set(session.results) | set(session.executions)
        for result in session.results.values():
            if result["operation_id"] in {atmosphere.VERIFY, atmosphere.MOIST_VERIFY, VERIFY}:
                name = "comparison_verification_id" if result["operation_id"] == VERIFY else "verification_id"
                case_occurrences.add(result["data"][name])
        if occurrences & case_occurrences:
            raise ValueError("Distinct benchmark cases cannot share scientific occurrence identities")
        occurrences.update(case_occurrences)
        snapshots.append((case, snapshot))
    return snapshots


def _benchmark_summary(snapshots) -> dict:
    entries, statuses, agreements = [], [], []
    for case, snapshot in snapshots:
        checked = _inspection_from_read(*snapshot)
        statuses.append(checked["status"])
        agreements.append(checked["agreement_status"])
        comparison, verification = snapshot[3], snapshot[4]
        row = comparison["data"]["rows"][0] if comparison is not None else None
        reference_pressure = case["reference"]["observations"][0]["quantities"]["liquid_water_saturation_pressure_pa"]["value"]
        model_pressure = row["model_value"] if row is not None else None
        entries.append({"name": case["name"], "temperature_k": case["request"]["reference"]["temperature_k"],
                        "reference_pressure_pa": reference_pressure, "model_pressure_pa": model_pressure,
                        "relative_difference": (abs(model_pressure - reference_pressure) / reference_pressure
                                                if model_pressure is not None else None),
                        "comparison_directory": "cases/" + case["name"] + "/comparison",
                        "comparison_result_id": comparison["result_id"] if comparison is not None else None,
                        "comparison_verification_id": (verification["data"]["comparison_verification_id"]
                                                       if verification is not None else None),
                        "numerical_verification_status": checked["verification_status"],
                        "comparison_digest": comparison["data"]["record_digest"] if comparison is not None else None,
                        "recomputed_verification_report_digest": (verification["data"]["report"]["record_digest"]
                                                                  if verification is not None else None)})
    status = "REFUSE" if "REFUSE" in statuses else "EXPAND" if "EXPAND" in statuses else "LOCAL"
    agreement = "FAIL" if "FAIL" in agreements else "NOT_EVALUATED" if "NOT_EVALUATED" in agreements else "PASS"
    return seal({"schema": "ciw.atmosphere-reference-benchmark.v1", "status": status,
                 "agreement_status": agreement, "case_count": len(entries), "cases": entries,
                 "claims": deepcopy(BENCHMARK_CLAIMS)})


def run_benchmark(destination: Path) -> dict:
    from .atmosphere_reference_benchmark import cases
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for case in cases():
        root = destination / "cases" / case["name"]
        atmosphere.run(case["request"], root / "atmosphere")
        run(root / "atmosphere", case["reference"], case["policy"], root / "comparison")
    summary = _benchmark_summary(_benchmark_case_reads(destination))
    save_new(destination / "benchmark.json", summary)
    return _benchmark_inspection(summary, fresh=False)


def _read_benchmark(destination: Path):
    destination = Path(destination)
    _file(destination / "benchmark.json")
    retained = load(destination / "benchmark.json")
    snapshots = _benchmark_case_reads(destination)
    expected = _benchmark_summary(snapshots)
    if not _equal(retained, expected):
        raise ValueError("Retained benchmark summary differs from actual fixed case snapshots")
    return retained, snapshots


def _benchmark_inspection(summary: dict, *, fresh: bool) -> dict:
    return {"schema": "ciw.atmosphere-reference-benchmark-inspection.v1", "status": summary["status"],
            "agreement_status": summary["agreement_status"], "case_count": summary["case_count"],
            "cases": deepcopy(summary["cases"]), "benchmark": deepcopy(summary),
            "fresh_execution": False, "fresh_numerical_verification": fresh, "authority": deepcopy(AUTHORITY)}


def inspect_benchmark(destination: Path) -> dict:
    summary, _ = _read_benchmark(destination)
    return _benchmark_inspection(summary, fresh=False)


def verify_benchmark(destination: Path) -> dict:
    summary, snapshots = _read_benchmark(destination)
    fresh = True
    for _, snapshot in snapshots:
        checked = _verify_read(*snapshot)
        fresh = fresh and checked["fresh_numerical_verification"]
    return _benchmark_inspection(summary, fresh=fresh)
