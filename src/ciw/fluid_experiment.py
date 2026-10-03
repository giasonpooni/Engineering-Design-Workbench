"""Explicit experiment comparison on the existing Session evidence substrate."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import stat
import tempfile
from . import fluid_experiment_contract as c
from .adapters.protocol import InstrumentManifest
from .control_contracts import keys, json_tree, content_ref, save_new
from .core.identities import evidence_id, validate_evidence_identity, validate_identity, new_identity
from .core.records import validate_run_structure
from .operations.runner import digest, seal, check_seal
from .operations.registry import Operation

COMPARE_OPERATION = c.COMPARE_OPERATION
VERIFY_OPERATION = c.VERIFY_OPERATION
INSTRUMENT = c.INSTRUMENT
MAX_BUNDLE_BYTES = 64 * 1024 * 1024


def template(profile="reservoir"):
    return c.template(profile)


def _bytes(path, limit=c.MAX_INPUT_BYTES):
    path = Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Experiment inputs must be bounded regular files without links")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        actual = os.fstat(descriptor)
        if not stat.S_ISREG(actual.st_mode) or not 0 < actual.st_size <= limit:
            raise ValueError("Experiment input exceeds regular-file byte budget")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        if not 0 < len(raw) <= limit:
            raise ValueError("Experiment input exceeds byte budget")
        return raw
    finally:
        os.close(descriptor)


def _make_source(csv_raw, metadata_raw):
    from .session import loads_json
    metadata = c.validate_metadata(loads_json(metadata_raw))
    rows = c.parse_csv(csv_raw, metadata)
    channels = metadata["observation_operator"]["channels"]
    manifest = InstrumentManifest(instrument_id=INSTRUMENT, role="declared_observation_evidence",
        units={row["column"]: row["unit"] for row in channels}, frames=(c.FRAME,),
        sampling={"kind": "explicit_csv_acquisition_times", "time_semantics": "declared_acquisition_clock_not_model_clock"},
        supported_operations=(COMPARE_OPERATION, VERIFY_OPERATION),
        calibration_requirements={"calibration": "content-addressed operator declarations; authenticity not established"})
    source = {"run_schema": "run.v1", "run_id": "run-fluid-experiment-" + metadata["csv_sha256"][7:23], "instrument": INSTRUMENT,
        "metadata": {"duration_s": rows[-1]["time_s"] + 1.0, "sample_count": len(rows), "sample_rate_hz": None,
                     "coordinate_frame": c.FRAME, "manifest": manifest.to_dict(),
                     "fluid_experiment": {"csv_utf8": csv_raw, "metadata_utf8": metadata_raw,
                       "csv_sha256": metadata["csv_sha256"], "metadata_sha256": "sha256:" + sha256(metadata_raw.encode()).hexdigest()},
                     "provenance": deepcopy(metadata["provenance"])},
        "time_s": [row["time_s"] for row in rows],
        "channels": {channel["column"]: {"unit": channel["unit"], "values": [row["values"][index] for row in rows]} for index, channel in enumerate(channels)}, "render": {}}
    source["evidence_id"] = evidence_id(source)
    return source


def source_data(source):
    from .session import loads_json
    validate_source(source)
    artifact = source["metadata"]["fluid_experiment"]
    metadata = c.validate_metadata(loads_json(artifact["metadata_utf8"]))
    return metadata, c.parse_csv(artifact["csv_utf8"], metadata)


def validate_source(source):
    validate_run_structure(source)
    validate_evidence_identity(source)
    artifact = source["metadata"].get("fluid_experiment")
    keys(artifact, {"csv_utf8", "metadata_utf8", "csv_sha256", "metadata_sha256"})
    for name in ("csv_utf8", "metadata_utf8"):
        if type(artifact[name]) is not str or not 0 < len(artifact[name].encode("utf-8")) <= c.MAX_INPUT_BYTES:
            raise ValueError("Retained experiment input exceeds exact byte budget")
    reconstructed = _make_source(artifact["csv_utf8"], artifact["metadata_utf8"])
    if digest(source) != digest(reconstructed):
        raise ValueError("Experiment source must exactly retain the CSV observations and metadata bytes")
    from .session import loads_json
    split = loads_json(artifact["metadata_utf8"])["split"]
    if {source["evidence_id"], artifact["metadata_sha256"], artifact["csv_sha256"]}.intersection(split["calibration_refs"] + split["parameter_fit_refs"]):
        raise ValueError("Held-out source or file reference overlaps calibration or parameter fitting")


def runtime_identity(kind):
    import numpy as np
    from . import fluid_experiment_statistics as stats
    modules = [c, stats, __import__(__name__, fromlist=["*"])]
    if kind == "verification":
        from . import fluid_reservoir_contract, fluid_reservoir_verification, fluid_reservoir_reference, fluid_workflow, fluid_contract
        modules += [fluid_reservoir_contract, fluid_reservoir_verification, fluid_reservoir_reference, fluid_workflow, fluid_contract]
    raw = b"\0".join(Path(item.__file__).name.encode() + b"\0" + Path(item.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode() for item in modules)
    return {"provider": "ciw.fluid.experiment." + kind, "version": "1", "code_sha256": sha256(raw).hexdigest(), "source_normalization": "utf8_lf",
            "scope": "heldout_lumped_reservoir_gaussian_compatibility", "environment": {"python": platform.python_version(), "numpy": np.__version__, "floating_point": "binary64"}}


def validate_runtime(operation, runtime, *, allow_absent=False):
    kind = {COMPARE_OPERATION: "comparison", VERIFY_OPERATION: "verification"}.get(operation)
    if kind is None:
        raise ValueError("Unsupported experimental operation")
    if runtime is None and allow_absent:
        return
    keys(runtime, {"provider", "version", "code_sha256", "source_normalization", "scope", "environment"})
    if runtime["provider"] != "ciw.fluid.experiment." + kind or runtime["version"] != "1" or runtime["source_normalization"] != "utf8_lf" or runtime["scope"] != "heldout_lumped_reservoir_gaussian_compatibility":
        raise ValueError("Experiment runtime identity differs")
    content_ref("sha256:" + runtime["code_sha256"] if type(runtime["code_sha256"]) is str else None)
    keys(runtime["environment"], {"python", "numpy", "floating_point"})
    if any(type(runtime["environment"][key]) is not str or re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}[A-Za-z0-9.+-]*", runtime["environment"][key]) is None for key in ("python", "numpy")) or runtime["environment"]["floating_point"] != "binary64":
        raise ValueError("Invalid experimental runtime version")


def validate_model(model):
    from . import fluid_workflow as fluid
    from . import fluid_contract
    keys(model, {"schema", "source", "candidate", "fresh_verification", "fresh_verification_execution_id", "fresh_verification_result_id", "verification_runtime", "record_digest"})
    check_seal(model)
    if model["schema"] != "ciw.fluid-experiment-model-dependency.v1":
        raise ValueError("Wrong foreign model dependency schema")
    request = fluid.source_request(model["source"])
    if fluid_contract.profile_for_request(request) != "reservoir":
        raise ValueError("EXPAND: no qualified experimental spatial operator for this fluid profile")
    fluid._candidate(model["source"], {"candidate": model["candidate"]})
    fluid.validate_payload("fluid.reservoir.verify.v1", model["fresh_verification"], model["source"], {"candidate": model["candidate"]}, {})
    fluid.validate_runtime("fluid.reservoir.verify.v1", model["verification_runtime"])
    for name, kind in (("fresh_verification_execution_id", "execution"), ("fresh_verification_result_id", "result")):
        validate_identity(model[name], kind)
    if model["fresh_verification"]["report"]["qualification"]["action"] != "LOCAL":
        raise ValueError("Experimental comparison requires a freshly qualified LOCAL model")
    return request


def _model_for_source(source, parameters):
    keys(parameters, {"model"})
    model = parameters["model"]
    request = validate_model(model)
    metadata, rows = source_data(source)
    if metadata["target_request_digest"] != digest(request):
        raise ValueError("Held-out observation declaration targets a different fixed model request")
    return metadata, rows, model


def _compare(source, parameters):
    from .fluid_experiment_statistics import compute
    metadata, rows, model = _model_for_source(source, parameters)
    return compute(source, metadata, rows, model)


def _candidate(source, parameters):
    keys(parameters, {"candidate"})
    candidate = parameters["candidate"]
    check_seal(candidate)
    if candidate.get("schema") != "ciw.operation-result.v1" or candidate.get("operation_id") != COMPARE_OPERATION or candidate.get("role") != "backend" or candidate.get("evidence_id") != source["evidence_id"] or candidate.get("run_id") != source["run_id"]:
        raise ValueError("Experimental candidate must bind its exact source and comparison occurrence")
    validate_identity(candidate.get("result_id"), "result")
    validate_identity(candidate.get("execution_id"), "execution")
    validate_runtime(COMPARE_OPERATION, candidate.get("runtime"))
    metadata, rows, model = _model_for_source(source, candidate["parameters"])
    c.validate_comparison(source, model, candidate["data"])
    if candidate.get("interval_s") != [0.0, source["metadata"]["duration_s"]]:
        raise ValueError("Experiment operations require the complete declared observation interval")
    return candidate, metadata, rows, model


def _verify(source, parameters):
    from . import fluid_workflow as fluid
    from .session import Session
    from .fluid_experiment_statistics import compute
    import numpy as np
    candidate, metadata, rows, model = _candidate(source, parameters)
    validate_model(model)
    with tempfile.TemporaryDirectory(prefix="fluid-experiment-model-verify-") as temporary:
        audit = Session(model["source"], Path(temporary), operations=fluid.registry())
        audit.results[model["candidate"]["result_id"]] = deepcopy(model["candidate"])
        reply = _execute(audit, "fluid.reservoir.verify.v1", {"candidate": model["candidate"]})
    if reply["status"] != "completed":
        raise ValueError("Fresh model qualification refused during experimental verification")
    model_result = reply["result"]
    fresh_model = {"record": deepcopy(model_result["data"]), "execution_id": model_result["execution_id"],
                   "result_id": model_result["result_id"], "runtime": deepcopy(model_result["runtime"])}
    model_ok = fresh_model["record"]["report"]["qualification"]["action"] == "LOCAL"
    recomputed = compute(source, metadata, rows, model, independent=True)
    data = candidate["data"]
    projection_ok = all(np.allclose(data[key], recomputed[key], rtol=1e-10, atol=1e-12) for key in ("predicted", "residual", "prediction_slopes"))
    statistics_ok = True
    for key in ("chi_square", "upper_tail_probability", "critical_chi_square"):
        stored, fresh = data["statistics"][key], recomputed["statistics"][key]
        statistics_ok &= (stored is None and fresh is None) or (stored is not None and fresh is not None and math_isclose(stored, fresh))
    covariance_ok = all((data["covariance"][key] is None and recomputed["covariance"][key] is None) or
        (data["covariance"][key] is not None and recomputed["covariance"][key] is not None and data["covariance"][key] == recomputed["covariance"][key]) for key in ("clock_common_offset", "total"))
    checks = {"fresh_model_LOCAL": bool(model_ok), "independent_projection": bool(projection_ok), "independent_eigen_whitening": bool(statistics_ok), "complete_covariance": bool(covariance_ok), "empirical_outcome": data["outcome"] == recomputed["outcome"]}
    report = seal({"schema": c.REPORT_SCHEMA, "candidate_digest": data["record_digest"], "evidence_id": source["evidence_id"],
                   "model_digest": model["record_digest"], "method": "independent_bracket_interpolation_eigen_whitening.v1", "checks": checks,
                   "status": "PASS" if all(checks.values()) else "FAIL", "qualification": "LOCAL" if all(checks.values()) else "REFUSE",
                   "outcome": recomputed["outcome"], "conditional_measured_support": recomputed["support"]["conditional_measured_support"] if all(checks.values()) else False,
                   "authority": deepcopy(c.AUTHORITY)})
    return {"schema": "ciw.fluid-experiment-verification-payload.v1", "verification_id": new_identity("verification"),
            "candidate_result_id": candidate["result_id"], "candidate_execution_id": candidate["execution_id"],
            "candidate_record_digest": candidate["record_digest"], "source_evidence_id": source["evidence_id"], "report": report, "fresh_model_verification": fresh_model, "authority": deepcopy(c.AUTHORITY)}


def math_isclose(a, b):
    import math
    return math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-10)


def validate_payload(operation, data, source, parameters, selection):
    validate_source(source)
    if selection.get("interval_s") != [0.0, source["metadata"]["duration_s"]]:
        raise ValueError("Experiment operations require the complete declared observation interval")
    if operation == COMPARE_OPERATION:
        metadata, rows, model = _model_for_source(source, parameters)
        c.validate_comparison(source, model, data)
        return
    if operation != VERIFY_OPERATION:
        raise ValueError("Unsupported experimental operation")
    candidate, metadata, rows, model = _candidate(source, parameters)
    keys(data, {"schema", "verification_id", "candidate_result_id", "candidate_execution_id", "candidate_record_digest", "source_evidence_id", "report", "fresh_model_verification", "authority"})
    validate_identity(data["verification_id"], "verification")
    if data["schema"] != "ciw.fluid-experiment-verification-payload.v1" or data["candidate_result_id"] != candidate["result_id"] or data["candidate_execution_id"] != candidate["execution_id"] or data["candidate_record_digest"] != candidate["record_digest"] or data["source_evidence_id"] != source["evidence_id"] or data["authority"] != c.AUTHORITY:
        raise ValueError("Experimental verification identity binding differs")
    from . import fluid_workflow as fluid
    witness = data["fresh_model_verification"]
    keys(witness, {"record", "execution_id", "result_id", "runtime"})
    validate_identity(witness["execution_id"], "execution")
    validate_identity(witness["result_id"], "result")
    fluid.validate_runtime("fluid.reservoir.verify.v1", witness["runtime"])
    fluid.validate_payload("fluid.reservoir.verify.v1", witness["record"], model["source"], {"candidate": model["candidate"]}, {})
    if witness["record"]["verification_id"] == model["fresh_verification"]["verification_id"]:
        raise ValueError("Fresh model verification must have a distinct occurrence identity")
    report = data["report"]
    keys(report, {"schema", "candidate_digest", "evidence_id", "model_digest", "method", "checks", "status", "qualification", "outcome", "conditional_measured_support", "authority", "record_digest"})
    check_seal(report)
    keys(report["checks"], {"fresh_model_LOCAL", "independent_projection", "independent_eigen_whitening", "complete_covariance", "empirical_outcome"})
    if any(type(value) is not bool for value in report["checks"].values()):
        raise ValueError("Verification checks must be explicit booleans")
    if report["checks"]["fresh_model_LOCAL"] != (witness["record"]["report"]["qualification"]["action"] == "LOCAL"):
        raise ValueError("Model qualification check differs from fresh model witness")
    passed = all(report["checks"].values())
    if report["schema"] != c.REPORT_SCHEMA or report["candidate_digest"] != candidate["data"]["record_digest"] or report["evidence_id"] != source["evidence_id"] or report["model_digest"] != model["record_digest"] or report["method"] != "independent_bracket_interpolation_eigen_whitening.v1" or report["status"] != ("PASS" if passed else "FAIL") or report["qualification"] != ("LOCAL" if passed else "REFUSE") or report["outcome"] not in c.OUTCOMES or report["authority"] != c.AUTHORITY:
        raise ValueError("Retained experiment verification report binding differs")
    expected = passed and metadata["provenance"]["source_kind"] == "declared_measured" and report["outcome"] == "EMPIRICALLY_COMPATIBLE"
    if report["conditional_measured_support"] is not expected:
        raise ValueError("Synthetic fixtures cannot gain measured support")


def validate_live_dependency(parameters, retained):
    candidate = parameters.get("candidate")
    if type(candidate) is not dict or retained.get(candidate.get("result_id")) != candidate:
        raise ValueError("Experimental verification requires its exact retained comparison occurrence")


def validate_result_dependencies(results):
    identities = set()
    for result in results.values():
        if result.get("operation_id") not in {COMPARE_OPERATION, VERIFY_OPERATION}:
            continue
        validate_runtime(result["operation_id"], result.get("runtime"))
        if result["operation_id"] == VERIFY_OPERATION:
            validate_live_dependency(result["parameters"], results)
            identity = result["data"]["verification_id"]
            if identity in identities:
                raise ValueError("Duplicate experimental verification occurrence")
            identities.add(identity)


def registry():
    from .operations.registry import default_registry
    result = default_registry()
    result.register(Operation(COMPARE_OPERATION, "backend", _compare, lambda: runtime_identity("comparison")))
    result.register(Operation(VERIFY_OPERATION, "verification", _verify, lambda: runtime_identity("verification")))
    return result


def _execute(session, operation, parameters):
    from .fluid_workflow import _execute as execute
    return execute(session, operation, parameters)


def ingest(csv_path, metadata_path, destination):
    from .session import Session
    from .fluid_experiment_statistics import validate_covariances
    csv_raw = _bytes(csv_path).decode("utf-8")
    metadata_raw = _bytes(metadata_path).decode("utf-8")
    source = _make_source(csv_raw, metadata_raw)
    metadata, rows = source_data(source)
    validate_covariances(metadata)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    # Exact input bytes are also retained inside run.v1; these files are receipts.
    with (destination / "observations.csv").open("x", encoding="utf-8", newline="") as stream:
        stream.write(csv_raw)
    with (destination / "metadata.json").open("x", encoding="utf-8", newline="") as stream:
        stream.write(metadata_raw)
    session = Session(source, destination)
    session.save_workspace(destination / "workspace.json")
    return inspect(destination)


def _load(destination):
    from .session import Session
    from .fluid_workflow import load_regular
    destination = Path(destination)
    value = load_regular(destination / "workspace.json", max_bytes=MAX_BUNDLE_BYTES)
    with tempfile.TemporaryDirectory(prefix="fluid-experiment-inspect-") as temporary:
        root = Path(temporary)
        snapshot = root / "snapshot.json"
        snapshot.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
        session = Session.from_workspace(snapshot, root / "restored")
    validate_source(session.run)
    artifact = session.run["metadata"]["fluid_experiment"]
    if _bytes(destination / "observations.csv").decode("utf-8") != artifact["csv_utf8"] or _bytes(destination / "metadata.json").decode("utf-8") != artifact["metadata_utf8"]:
        raise ValueError("Observation receipts differ from exact retained evidence bytes")
    candidates = [row for row in session.results.values() if row["operation_id"] == COMPARE_OPERATION]
    verifications = [row for row in session.results.values() if row["operation_id"] == VERIFY_OPERATION]
    if any(row["operation_id"] not in {COMPARE_OPERATION, VERIFY_OPERATION} for row in session.executions.values()):
        raise ValueError("Experiment bundle contains unrelated execution")
    if not session.executions and not session.results:
        return session, None, None
    if len(candidates) != 1 or len(verifications) != 1 or len(session.results) != 2 or len(session.executions) != 2:
        raise ValueError("Experiment bundle requires one comparison and one independent verification")
    candidate, verification = candidates[0], verifications[0]
    if verification["parameters"]["candidate"] != candidate:
        raise ValueError("Experiment verification differs from retained candidate")
    if load_regular(destination / "verification.json") != verification["data"]:
        raise ValueError("Experiment verification receipt differs from retained occurrence")
    return session, candidate, verification


def _summary(session, candidate, verification):
    metadata, rows = source_data(session.run)
    result = {"schema": "ciw.fluid-experiment-inspection.v1", "evidence_id": session.run["evidence_id"], "source_kind": metadata["provenance"]["source_kind"],
              "profile": metadata["profile"], "status": "INGESTED", "fresh_execution": False, "fresh_numerical_verification": False, "authority": deepcopy(c.AUTHORITY)}
    if candidate is not None:
        report = verification["data"]["report"]
        result.update(status=report["qualification"], operation_id=candidate["operation_id"], execution_id=candidate["execution_id"], result_id=candidate["result_id"],
                      verification_operation_id=verification["operation_id"], verification_execution_id=verification["execution_id"], verification_id=verification["data"]["verification_id"],
                      outcome=report["outcome"], conditional_measured_support=report["conditional_measured_support"], statistics=deepcopy(candidate["data"]["statistics"]), checks=deepcopy(report["checks"]))
    return result


def inspect(destination):
    return _summary(*_load(destination))


def compare(model_bundle, measurement_bundle, destination):
    from .session import Session
    from . import fluid_workflow as fluid
    model_session, model_candidate, model_verification = fluid._read(Path(model_bundle))
    checked = fluid._verify_read(model_session, model_candidate, model_verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Comparison requires freshly verified LOCAL model")
    model = seal({"schema": "ciw.fluid-experiment-model-dependency.v1", "source": deepcopy(model_session.run), "candidate": deepcopy(model_candidate),
                  "fresh_verification": deepcopy(checked["fresh_verification_record"]), "fresh_verification_execution_id": checked["fresh_verification_execution_id"],
                  "fresh_verification_result_id": checked["fresh_verification_result_id"], "verification_runtime": deepcopy(checked["recomputed_with_runtime"])})
    validate_model(model)
    measurements, candidate, verification = _load(Path(measurement_bundle))
    if candidate is not None:
        raise ValueError("Comparison requires an ingestion-only measurement bundle")
    metadata, rows, model = _model_for_source(measurements.run, {"model": model})
    # Domain/covariance preflight precedes create-only output. This is execution,
    # not static inspect, and never silently extrapolates or fits parameters.
    from .fluid_experiment_statistics import compute
    compute(measurements.run, metadata, rows, model)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    artifact = measurements.run["metadata"]["fluid_experiment"]
    for name, key in (("observations.csv", "csv_utf8"), ("metadata.json", "metadata_utf8")):
        with (destination / name).open("x", encoding="utf-8", newline="") as stream:
            stream.write(artifact[key])
    session = Session(measurements.run, destination, operations=registry())
    comparison = _execute(session, COMPARE_OPERATION, {"model": model})
    if comparison["status"] != "completed":
        raise ValueError("Comparison refused: " + comparison["execution"]["refusal"]["message"])
    verified = _execute(session, VERIFY_OPERATION, {"candidate": comparison["result"]})
    if verified["status"] != "completed":
        raise ValueError("Comparison verification refused: " + verified["execution"]["refusal"]["message"])
    session.save_workspace(destination / "workspace.json")
    save_new(destination / "verification.json", verified["result"]["data"])
    return inspect(destination)


def verify_retained(destination):
    from .session import Session
    session, candidate, verification = _load(destination)
    if candidate is None:
        raise ValueError("An ingested dataset has no comparison to verify")
    with tempfile.TemporaryDirectory(prefix="fluid-experiment-verify-") as temporary:
        audit = Session(session.run, Path(temporary), operations=registry())
        audit.results[candidate["result_id"]] = deepcopy(candidate)
        fresh = _execute(audit, VERIFY_OPERATION, {"candidate": candidate})
    if fresh["status"] != "completed":
        raise ValueError("Fresh independent experiment verification refused")
    result = fresh["result"]
    if result["data"]["report"]["qualification"] != "LOCAL" or result["data"]["report"]["outcome"] != verification["data"]["report"]["outcome"]:
        raise ValueError("Fresh independent comparison verification differs from retained outcome")
    checked = _summary(session, candidate, verification)
    checked.update(fresh_execution=True, fresh_numerical_verification=True, fresh_verification_id=result["data"]["verification_id"],
                   fresh_verification_execution_id=result["execution_id"], fresh_verification_result_id=result["result_id"],
                   fresh_verification_record=deepcopy(result["data"]), recomputed_with_runtime=deepcopy(result["runtime"]))
    return checked
