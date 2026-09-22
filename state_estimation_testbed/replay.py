"""Content binding for native CIW scientific sessions, not a replay executor.

The existing verification-artifact v1 envelope is retained.  Numerical replay
is checked only against outputs supplied by a caller-controlled trusted replay
executor.  Neither hashes nor an untrusted receipt establish physical truth.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from collections.abc import Mapping

from .contracts import (
    ContractError, OBSERVATION_SCHEMA, RESULT_SCHEMA, VERIFICATION_SCHEMA,
    _instant, _record, _text, _texts, validate_observation_batch,
    validate_result_artifact, validate_verification_artifact,
)

_EXCLUDED = frozenset({"bundle_digest", "verification", "replay_receipts"})
MAX_SESSION_BYTES = 8_388_608
MAX_STEPS = 32
MAX_COMPONENTS = 64
TELEMETRY_SESSION_SCHEMA = "ciw.telemetry-session.v1"
CALIBRATED_OBSERVABLE_SESSION_SCHEMA = "ciw.calibrated-observable-session.v1"
CALIBRATED_WINDOW_SESSION_SCHEMA = "ciw.calibrated-window-session.v1"


def _json_value(value: object, path: str = "value", depth: int = 0) -> None:
    if depth > 64:
        raise ContractError("JSON nesting exceeds 64 levels")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{path} must not contain nonfinite numbers")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _json_value(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError(f"{path} keys must be strings")
            _json_value(item, f"{path}.{key}", depth + 1)
        return
    raise ContractError(f"{path} is not a JSON value")


def canonical_bytes(value: object) -> bytes:
    """Strict Python JSON profile; not advertised as cross-language JCS."""
    _json_value(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise ContractError("value is not canonicalizable JSON") from exc


def content_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def bytes_digest(value: bytes) -> str:
    if not isinstance(value, bytes):
        raise ContractError("evidence must be exact bytes")
    return "sha256:" + hashlib.sha256(value).hexdigest()


def replay_bundle_digest(bundle: Mapping[str, object]) -> str:
    return content_digest({key: value for key, value in bundle.items() if key not in _EXCLUDED})


def _digest(value: object, name: str) -> str:
    text = _text(value, name)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", text):
        raise ContractError(f"{name} must be sha256:<64 lowercase hex>")
    return text


def _blob(value: object, name: str) -> bytes:
    try:
        return base64.b64decode(_text(value, name), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ContractError(f"{name} must be valid base64") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decoded_json(blob: bytes) -> object:
    def checked_float(literal: str) -> float:
        number = float(literal)
        if number == 0.0 and any(character in "123456789" for character in literal.lower().split("e")[0]):
            raise ContractError("nonzero JSON number underflowed to zero")
        return number

    try:
        value = json.loads(blob, object_pairs_hook=_unique_object, parse_float=checked_float)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("source bytes must be strict JSON") from exc
    _json_value(value)
    return value


def _exchange(value: object) -> list[str]:
    """Validate every embedded known exchange artifact without inventing one."""
    missing: list[str] = []
    if isinstance(value, Mapping):
        schema = value.get("schema")
        if schema in {OBSERVATION_SCHEMA, RESULT_SCHEMA}:
            components = value.get("components")
            if not isinstance(components, list) or not 1 <= len(components) <= MAX_COMPONENTS:
                raise ContractError("replay exchange components must contain 1 to 64 quantities")
        if schema == OBSERVATION_SCHEMA:
            result = validate_observation_batch(value)
            if result.effective_rank is None:
                missing.append(str(value["batch_id"]))
        elif schema == RESULT_SCHEMA:
            result = validate_result_artifact(value)
            payload = {key: item for key, item in value.items() if key != "result_id"}
            expected_id = "sha256:" + hashlib.sha256(
                RESULT_SCHEMA.encode("utf-8") + b"\x00" + canonical_bytes(payload)
            ).hexdigest()
            if value["result_id"] != expected_id:
                raise ContractError("result artifact identity does not bind its content")
            if result.effective_rank is None:
                missing.append(str(value["result_id"]))
        for item in value.values():
            missing.extend(_exchange(item))
    elif isinstance(value, list):
        for item in value:
            missing.extend(_exchange(item))
    return missing


def verify_replay_bundle(
    bundle: object, *, replay_results: Mapping[str, object] | None = None,
    verifier_ref: str = "set:replay-binding.v1", created_at: str | None = None,
) -> dict[str, object]:
    """Validate bindings and compare fresh replay numerical outputs, if supplied.

    Malformed/tampered bundles raise ``ContractError``.  Missing replay yields
    an indeterminate receipt, never a pass.  Callers must obtain replay_results
    from independently configured pinned executors, never from bundle paths
    or a caller-supplied receipt.  This function does not run foreign code.
    """
    session = _record(bundle, "replay bundle")
    if len(canonical_bytes(session)) > MAX_SESSION_BYTES:
        raise ContractError("replay session exceeds byte budget")
    session_schema = session.get("schema")
    if session_schema not in {TELEMETRY_SESSION_SCHEMA, CALIBRATED_OBSERVABLE_SESSION_SCHEMA, CALIBRATED_WINDOW_SESSION_SCHEMA}:
        raise ContractError("unsupported native CIW replay session schema")
    session_id = _text(session.get("session_id"), "session_id")
    instant = _instant(session.get("created_at"), "created_at")
    claimed = _digest(session.get("bundle_digest"), "bundle_digest")
    if claimed != replay_bundle_digest(session):
        raise ContractError("bundle_digest does not bind the supplied session")
    source = _record(session.get("source"), "source")
    batch = None
    experiment = None
    if session_schema == TELEMETRY_SESSION_SCHEMA:
        batch = _record(source.get("batch"), "source.batch")
        _exchange(batch)
        if batch.get("schema") != OBSERVATION_SCHEMA:
            raise ContractError("source.batch must be an observation-batch v1 artifact")
        batch_blob = _blob(source.get("batch_bytes_b64"), "source.batch_bytes_b64")
        if canonical_bytes(_decoded_json(batch_blob)) != canonical_bytes(batch):
            raise ContractError("source batch bytes do not match batch")
        # batch_sha256 names exact retained bytes, not a reconstructed serialization.
        if _digest(source.get("batch_sha256"), "source.batch_sha256") != bytes_digest(batch_blob):
            raise ContractError("source.batch_sha256 does not bind retained batch bytes")
    raw_evidence = source.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ContractError("source.evidence must be a non-empty array")
    evidence_digests: dict[str, str] = {}
    for index, value in enumerate(raw_evidence):
        evidence = _record(value, f"source.evidence[{index}]")
        ref = _text(evidence.get("artifact_ref"), "evidence.artifact_ref")
        if ref in evidence_digests:
            raise ContractError("evidence identities must be unique")
        digest = _digest(evidence.get("sha256"), "evidence.sha256")
        if bytes_digest(_blob(evidence.get("bytes_b64"), "evidence.bytes_b64")) != digest:
            raise ContractError("evidence digest does not bind retained bytes")
        evidence_digests[ref] = digest
    if session_schema == TELEMETRY_SESSION_SCHEMA:
        assert batch is not None
        retained_refs = set(batch["source_artifact_refs"]) | set(batch["covariance"]["source_refs"])
        if not retained_refs <= evidence_digests.keys():
            raise ContractError("source batch references missing retained evidence")
        if batch["batch_id"] in evidence_digests or session_id in evidence_digests:
            raise ContractError("session, batch, and evidence identities must differ")
    else:
        if len(raw_evidence) != 1:
            raise ContractError("calibrated-observable session requires exactly one experiment artifact")
        experiment_blob = _blob(raw_evidence[0].get("bytes_b64"), "evidence.bytes_b64")
        experiment = _record(_decoded_json(experiment_blob), "calibrated-observable experiment")
        expected_source = ("ciw.calibrated-window-source.v1" if session_schema == CALIBRATED_WINDOW_SESSION_SCHEMA
                           else "fsrt.calibrated-observable-two-channel.v1")
        if experiment.get("schema") != expected_source:
            raise ContractError("unsupported calibrated-observable experiment schema")
        experiment_id = _text(experiment.get("experiment_id"), "experiment.experiment_id")
        if source.get("experiment_id") != experiment_id:
            raise ContractError("source experiment identity differs from retained bytes")
        if _digest(source.get("experiment_digest"), "source.experiment_digest") != content_digest(experiment):
            raise ContractError("source experiment digest does not bind retained experiment content")
        if session_id in evidence_digests:
            raise ContractError("session and experiment evidence identities must differ")
    configuration = _record(session.get("configuration"), "configuration")
    if not configuration:
        raise ContractError("configuration must retain declared model/prior/settings")
    if experiment is not None and canonical_bytes(configuration) != canonical_bytes(
        _record(experiment.get("configuration"), "experiment.configuration")
    ):
        raise ContractError("session configuration differs from retained experiment configuration")
    runtimes = _record(session.get("runtimes"), "runtimes")
    if not runtimes:
        raise ContractError("runtimes must retain source pins")
    for role, value in runtimes.items():
        _text(role, "runtime role")
        runtime = _record(value, f"runtimes.{role}")
        if runtime.get("schema") != "ciw.subprocess-runtime.v1":
            raise ContractError("runtime must use existing CIW subprocess manifest")
        for field in ("revision", "source_tree"):
            if not re.fullmatch(r"[0-9a-f]{40}", _text(runtime.get(field), f"runtime.{field}")):
                raise ContractError(f"runtime.{field} must be a full Git SHA-1 pin")
        if not re.fullmatch(r"[0-9a-f]{64}", _text(runtime.get("python_sha256"), "runtime.python_sha256")):
            raise ContractError("runtime.python_sha256 must bind interpreter bytes")
        _text(runtime.get("python_version"), "runtime.python_version")
        _record(runtime.get("dependencies"), "runtime.dependencies")
    steps = session.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ContractError("steps must contain 1 to 32 ordered operations")
    if session_schema == CALIBRATED_WINDOW_SESSION_SCHEMA:
        expected_graph = [("tbrt", "ciw.tbrt-window.v1"), ("mcur", "ciw.mcur-window.v1"),
                          ("stfe", "stfe.window-mean.v1"), ("gsie", "ciw.gsie-predict-update.v1")]
        if ([(step.get("runtime_ref"), step.get("operation_id")) for step in steps] != expected_graph
                or set(runtimes) != {"tbrt", "mcur", "stfe", "gsie", "set"}):
            raise ContractError("calibrated window requires its exact four-operation graph and five runtimes")
        refs = list(evidence_digests)
        expected_inputs = [refs, refs + [steps[0].get("result_id")],
                           [steps[0].get("result_id"), steps[1].get("result_id")], [steps[2].get("result_id")]]
        if [step.get("input_refs") for step in steps] != expected_inputs:
            raise ContractError("calibrated window input graph differs from retained lineage")
    available = set(evidence_digests)
    # First-step requests/results must bind the retained source; a reference
    # to evidence alone cannot establish a projection or declaration link.
    occurrences: set[str] = set()
    result_ids: set[str] = set()
    numerical_ids: dict[str, str] = {}
    operation_pins: list[dict[str, object]] = []
    replay_matches = True
    for index, value in enumerate(steps):
        step = _record(value, f"steps[{index}]")
        operation_id = _text(step.get("operation_id"), "step.operation_id")
        execution_id = _text(step.get("execution_id"), "step.execution_id")
        result_id = _text(step.get("result_id"), "step.result_id")
        role = _text(step.get("runtime_ref"), "step.runtime_ref")
        if role not in runtimes:
            raise ContractError("step runtime_ref must resolve to a retained pin")
        input_refs = _texts(step.get("input_refs"), "step.input_refs")
        if not set(input_refs) <= available:
            raise ContractError("step input references must resolve to earlier results or retained evidence")
        if execution_id in occurrences | available | result_ids | {session_id, operation_id, result_id}:
            raise ContractError("execution identities must be distinct occurrences")
        if result_id in available | occurrences | {session_id, operation_id}:
            raise ContractError("result identities must differ from evidence, inputs, operations and executions")
        request = _record(step.get("request"), "step.request")
        result = _record(step.get("result"), "step.result")
        numerical = _record(step.get("numerical_result"), "step.numerical_result")
        native_operation = operation_id
        if operation_id == "ciw.gsie-predict-update.v1":
            # One explicitly declared CIW script: do not relabel the native
            # update artifact as prediction+update or permit generic aliases.
            if (role != "gsie" or result.get("schema") != "ciw.estimation-step.v1"
                    or result.get("operation_id") != operation_id
                    or result.get("component_operations") != [
                        "geometric-state-inference.predict.v1",
                        "geometric-state-inference.update.v1"]):
                raise ContractError("GSIE composite must declare the exact predict then update operations")
            native_operation = "geometric-state-inference.update.v1"
            native = _record(result.get("result_artifact"), "composite.result_artifact")
            if native.get("operation_ref") != native_operation:
                raise ContractError("GSIE composite must retain the native update operation identity")
        for subject, expected_operation in ((request, operation_id), (result, operation_id),
                                            (numerical, operation_id),
                                            (result.get("result_artifact", {}), native_operation)):
            declared = _record(subject, "operation subject")
            for field in ("operation_id", "operation_ref"):
                if field in declared and declared[field] != expected_operation:
                    raise ContractError("step operation identity differs from retained operation declaration")
        for field, subject in (("request_sha256", request), ("result_sha256", result),
                               ("numerical_result_id", numerical)):
            if _digest(step.get(field), f"step.{field}") != content_digest(subject):
                raise ContractError(f"step.{field} does not bind retained content")
        native_id = result.get("result_id", result.get("batch_id"))
        if native_id is not None and native_id != result_id:
            raise ContractError("step result_id differs from artifact identity")
        if "execution_ref" in result and result["execution_ref"] != execution_id:
            raise ContractError("result execution_ref differs from step occurrence")
        if "execution_id" in result and result["execution_id"] != execution_id:
            raise ContractError("result execution_id differs from step occurrence")
        if "input_refs" in result and list(result["input_refs"]) != list(input_refs):
            raise ContractError("result input_refs differ from step graph")
        if result.get("schema") == "ciw.calibrated-operation-result.v1":
            if (set(result) != {"schema", "operation_id", "execution_ref", "input_refs", "data", "result_id"}
                    or result.get("operation_id") != operation_id
                    or result_id != content_digest(
                        {key: item for key, item in result.items() if key != "result_id"})):
                raise ContractError("calibrated operation result identity does not bind its content")
        if index == 0:
            if session_schema == TELEMETRY_SESSION_SCHEMA:
                if role != "ppda" or canonical_bytes(result) != canonical_bytes(batch):
                    raise ContractError("first step must be pinned PPDA projection of retained evidence into source batch")
            elif session_schema == CALIBRATED_WINDOW_SESSION_SCHEMA:
                if (request != {"source": experiment} or result.get("schema") != "ciw.calibrated-operation-result.v1"
                        or numerical != {"operation_id": operation_id, "data": result.get("data")}):
                    raise ContractError("clock request must bind exact calibrated-window source bytes and numerical projection")
            else:
                if (role != "fsrt" or operation_id != "fsrt.declare-calibrated-two-channel.v1"
                        or list(input_refs) != list(evidence_digests)):
                    raise ContractError("first calibrated-observable step must bind the FSRT declaration to retained experiment bytes")
                inputs = _record(request.get("inputs"), "FSRT request.inputs")
                if (set(request) != {"schema", "operation_id", "inputs"}
                        or set(inputs) != {"experiment", "execution_id"}
                        or request.get("schema") != "ciw.adapter-request.v1"
                        or request.get("operation_id") != operation_id
                        or inputs.get("execution_id") != execution_id
                        or canonical_bytes(inputs.get("experiment")) != canonical_bytes(experiment)):
                    raise ContractError("FSRT request must bind retained experiment content and execution identity")
                assert experiment is not None
                declaration_schema = "fsrt.calibrated-observable-declaration.v1"
                channels = experiment.get("channels")
                if not isinstance(channels, list) or len(channels) != 2:
                    raise ContractError("retained experiment must declare two channels")
                channel_order = [_text(_record(channel, "experiment channel").get("channel_id"),
                                       "experiment channel.channel_id") for channel in channels]
                claim_scope = _text(experiment.get("claim_scope"), "experiment.claim_scope")
                experiment_domain_digest = "sha256:" + hashlib.sha256(
                    experiment["schema"].encode("utf-8") + b"\x00" + canonical_bytes(experiment)
                ).hexdigest()
                if (result.get("schema") != declaration_schema
                        or result.get("result_id") != result_id
                        or result.get("operation_id") != operation_id
                        or result.get("execution_id") != execution_id
                        or result.get("experiment_id") != experiment["experiment_id"]
                        or result.get("experiment_digest") != experiment_domain_digest
                        or result.get("channel_order") != channel_order
                        or result.get("claim_scope") != claim_scope):
                    raise ContractError("FSRT declaration must bind retained experiment content and execution identity")
                expected_declaration_id = "sha256:" + hashlib.sha256(
                    declaration_schema.encode("utf-8") + b"\x00" + canonical_bytes(
                        {key: item for key, item in result.items() if key != "result_id"}
                    )
                ).hexdigest()
                if result_id != expected_declaration_id:
                    raise ContractError("FSRT declaration result identity does not bind its content")
                expected_numerical = {"operation_id": operation_id, "data": {
                    key: item for key, item in result.items()
                    if key not in {"schema", "operation_id", "execution_id", "result_id"}
                }}
                if canonical_bytes(numerical) != canonical_bytes(expected_numerical):
                    raise ContractError("FSRT numerical projection differs from retained declaration")
        if set(numerical) & {"execution_ref", "execution_id", "created_at", "result_id"}:
            raise ContractError("numerical_result must exclude occurrence identity")
        if replay_results is not None:
            if execution_id not in replay_results:
                raise ContractError("fresh replay results are missing a step execution")
            replay_matches &= content_digest(replay_results[execution_id]) == step["numerical_result_id"]
        _exchange(request)
        _exchange(result)
        available.add(result_id)
        occurrences.add(execution_id)
        result_ids.add(result_id)
        numerical_ids[execution_id] = step["numerical_result_id"]
        operation_pins.append({"operation_id": operation_id, "runtime_ref": role,
                               "runtime_digest": content_digest(runtimes[role]),
                               "request_digest": step["request_sha256"]})
    if replay_results is not None and set(replay_results) != occurrences:
        raise ContractError("fresh replay result keys must match execution identities exactly")
    checks = [{"name": "retained-content-and-exchange-binding", "outcome": "passed",
               "basis": "Exact evidence bytes, declared source, request/result digests, operation/runtime pins and ordered input graph."},
              {"name": "numerical-replay", "outcome": "indeterminate" if replay_results is None else
               ("passed" if replay_matches else "failed"),
               "basis": "Exact canonical numerical-output comparison against caller-controlled fresh replay; SET does not execute producers."}]
    outcome = checks[-1]["outcome"]
    receipt: dict[str, object] = {
        "schema": VERIFICATION_SCHEMA, "subject_ref": claimed,
        "verifier_ref": _text(verifier_ref, "verifier_ref"),
        "created_at": _instant(created_at, "created_at") if created_at is not None else instant,
        "checks": checks, "outcome": outcome, "independent": False,
        "limitations": ["Computational binding/replay only; no physical truth, calibration, model adequacy, unique fault isolation, or admission authority.",
                        "Runtime declarations must be checked against independently configured trusted source/interpreter pins by the replay executor.",
                        "A replay receipt is not a signature or independent attestation; do not trust a receipt supplied by the subject."],
        "binding": {"bundle_digest": claimed, "evidence_digests": evidence_digests,
                    "operation_pins": operation_pins, "numerical_result_ids": numerical_ids,
                    "configuration_digest": content_digest(configuration),
                    "execution_ids": sorted(occurrences)},
    }
    # Keep the existing exchange artifact identity profile (schema domain
    # separator + canonical body), not the native-session digest profile.
    receipt["verification_id"] = "sha256:" + hashlib.sha256(
        VERIFICATION_SCHEMA.encode("utf-8") + b"\x00" + canonical_bytes(receipt)
    ).hexdigest()
    validate_verification_artifact(receipt)
    return receipt
