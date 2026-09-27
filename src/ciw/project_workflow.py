"""Provider-free CIW adapter for the typed project graph.

The project-model contract declares components, signals, computations, results
and evidence without executing them. This adapter wraps that contract in the
shared operation lifecycle: validate a retained project source, emit a
deterministic inspection result, then support save/reopen without provider
execution and fresh replay with a new occurrence. Authority remains
not_performed for execution, physical validation and state admission.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
import uuid

from . import project_model as project
from .adapters.subprocess import _json
from .exchange import _identity
from .telemetry import _bundle_digest, _now, byte_digest, canonical, digest, _keys

KIND = "project-graph"
SCHEMA = "ciw.project-graph-session.v1"
SOURCE_SCHEMA = "ciw.project-graph-source.v1"
DATA_SCHEMA = "ciw.project-graph-workbench-data.v1"
RESULT_SCHEMA = "ciw.project-graph-workbench-result.v1"
VERIFY_SCHEMA = "ciw.project-graph-verification.v1"
OPERATION = "ciw.project-graph.v1"
ROLE = "project"
ROLES = set()
MAX_BYTES = project.MAX_BYTES
SOURCE_LIMIT = project.MAX_BYTES
CONFIGURATION = {
    "activation": "read_only",
    "execution": "not_performed",
    "physical_validation": "not_performed",
    "state_admission": "not_performed",
}
AUTHORITY = {
    "execution": "not_performed",
    "physical_validation": "not_performed",
    "state_admission": "not_performed",
}
CLAIM_SCOPE = "declared_project_graph_inspection_under_provider_free_contract"


def _text(value, limit=512):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Require bounded nonempty text")


def _algorithm_identity():
    files = [Path(project.__file__), Path(__file__)]
    content = b"\0".join(
        path.name.encode("utf-8") + b"\0" +
        path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
        for path in files
    )
    return {
        "profile": "ciw.project-graph.python-reference.v1",
        "code_sha256": sha256(content).hexdigest(),
        "source_normalization": "utf8_lf",
    }


def runtime_identity():
    return {
        "schema": "ciw.python-reference-runtime.v1",
        "role": ROLE,
        "profile": "ciw.project-graph.python-reference.v1",
        "algorithm": _algorithm_identity(),
        "execution_scope": "independent_python_reference_only",
        "execution": "not_performed",
        "physical_validation": "not_performed",
        "state_admission": "not_performed",
    }


def _runtime_projection(value):
    return deepcopy(value)


def _adapters(repositories, expected=None):
    if not isinstance(repositories, dict) or repositories:
        raise ValueError("The provider-free project reference accepts no repository bindings")
    runtime = runtime_identity()
    if expected is not None:
        expected_runtime = expected.get(ROLE, expected) if isinstance(expected, dict) else expected
        if _runtime_projection(runtime) != _runtime_projection(expected_runtime):
            raise ValueError("Project reference runtime identity differs from the retained execution")
    return None, runtime


def validate_source(raw):
    """Validate exact source bytes and the retained project graph."""
    if type(raw) is not bytes or not 1 <= len(raw) <= SOURCE_LIMIT:
        raise ValueError("Project graph source requires bounded exact JSON bytes")
    source = _json(raw)
    _keys(source, {"schema", "experiment_id", "configuration", "project"})
    if source["schema"] != SOURCE_SCHEMA or canonical(source["configuration"]) != canonical(CONFIGURATION):
        raise ValueError("Unsupported project graph source or authority policy")
    _text(source["experiment_id"], 128)
    project.validate(source["project"])
    if len(canonical(source)) > SOURCE_LIMIT:
        raise ValueError("Project graph source exceeds the byte budget")
    return deepcopy(source)


def _native_data(source):
    artifact = source["project"]
    inspection = project.inspect(artifact)
    return {
        "schema": DATA_SCHEMA,
        "operation_id": OPERATION,
        "project_id": artifact["project_id"],
        "project_revision": artifact["revision"],
        "inspection": inspection,
        "claim_scope": CLAIM_SCOPE,
        "authority": deepcopy(AUTHORITY),
    }


def _step(source, evidence_id, runtime, execution_id=None):
    occurrence = execution_id or "execution-" + uuid.uuid4().hex
    data = _native_data(source)
    result = {
        "schema": RESULT_SCHEMA,
        "operation_id": OPERATION,
        "execution_ref": occurrence,
        "input_refs": [evidence_id],
        "data": data,
        "authority": deepcopy(AUTHORITY),
    }
    result["result_id"] = digest(result)
    numerical = {"operation_id": OPERATION, "data": deepcopy(data)}
    return {
        "runtime_ref": ROLE,
        "operation_id": OPERATION,
        "execution_id": occurrence,
        "input_refs": [evidence_id],
        "request": {"project_id": source["project"]["project_id"],
                    "project_revision": source["project"]["revision"]},
        "request_sha256": digest({"project_id": source["project"]["project_id"],
                                  "project_revision": source["project"]["revision"]}),
        "result": result,
        "result_sha256": digest(result),
        "result_id": result["result_id"],
        "numerical_result": numerical,
        "numerical_result_id": digest(numerical),
    }


def _validate_step(step, source, evidence_id):
    _keys(step, {"runtime_ref", "operation_id", "execution_id", "input_refs", "request", "request_sha256",
                 "result", "result_sha256", "result_id", "numerical_result", "numerical_result_id"})
    expected_request = {"project_id": source["project"]["project_id"],
                        "project_revision": source["project"]["revision"]}
    if (step["runtime_ref"] != ROLE or step["operation_id"] != OPERATION or
            not re.fullmatch(r"execution-[a-f0-9]{32}", step["execution_id"]) or
            step["input_refs"] != [evidence_id] or
            canonical(step["request"]) != canonical(expected_request) or
            step["request_sha256"] != digest(expected_request)):
        raise ValueError("Project step request or occurrence binding differs")
    result = step["result"]
    _keys(result, {"schema", "operation_id", "execution_ref", "input_refs", "data", "authority", "result_id"})
    if (result["schema"] != RESULT_SCHEMA or result["operation_id"] != OPERATION or
            result["execution_ref"] != step["execution_id"] or result["input_refs"] != [evidence_id] or
            result["authority"] != AUTHORITY or
            result["result_id"] != digest({k: v for k, v in result.items() if k != "result_id"})):
        raise ValueError("Project native result envelope differs")
    expected_data = _native_data(source)
    if canonical(result["data"]) != canonical(expected_data):
        raise ValueError("Project native result differs from deterministic inspection")
    numerical = {"operation_id": OPERATION, "data": result["data"]}
    if step["numerical_result"] != numerical or step["numerical_result_id"] != digest(numerical):
        raise ValueError("Project numerical result identity differs")
    if step["result_id"] != result["result_id"] or step["result_sha256"] != digest(result):
        raise ValueError("Project step result commitment differs")


def _verification(bundle, reproduced):
    if canonical(bundle["steps"][0]["numerical_result"]) != canonical(reproduced["numerical_result"]):
        raise ValueError("Project replay numerical result differs")
    value = {
        "schema": VERIFY_SCHEMA,
        "subject_ref": bundle["bundle_digest"],
        "outcome": "passed",
        "independent": False,
        "method": "same_python_reference_fresh_occurrence_reproduction",
        "runtime_digest": digest(bundle["runtimes"]),
        "reproduction": deepcopy(reproduced),
        "authority": deepcopy(AUTHORITY),
    }
    value["verification_id"] = byte_digest(VERIFY_SCHEMA.encode() + b"\0" + canonical(value))
    return value


class ProjectGraphWorkflow:
    MAX_BYTES = MAX_BYTES
    kind = KIND
    role = ROLE
    ROLES = ROLES
    SOURCE_SCHEMA = SOURCE_SCHEMA
    schema = SCHEMA
    operation = OPERATION

    def _source(self, raw):
        return validate_source(raw)

    def _adapters(self, repositories, expected=None):
        return _adapters(repositories, expected)

    @staticmethod
    def _runtime_projection(value):
        return _runtime_projection(value)

    def _step(self, source, evidence_id, bound):
        _, runtime = bound
        return _step(source, evidence_id, runtime)

    @staticmethod
    def _validate_step(step, source, evidence_id):
        return _validate_step(step, source, evidence_id)

    def _check_verification(self, bundle, verification, source, evidence):
        _keys(verification, {"schema", "subject_ref", "outcome", "independent", "method", "runtime_digest",
                             "reproduction", "authority", "verification_id"})
        if (verification["schema"] != VERIFY_SCHEMA or verification["subject_ref"] != bundle["bundle_digest"] or
                verification["outcome"] != "passed" or verification["independent"] is not False or
                verification["method"] != "same_python_reference_fresh_occurrence_reproduction" or
                verification["authority"] != AUTHORITY):
            raise ValueError("Project verification scope differs")
        _validate_step(verification["reproduction"], source, evidence)
        old, new = bundle["steps"][0], verification["reproduction"]
        if (old["execution_id"] == new["execution_id"] or old["result_id"] == new["result_id"] or
                verification != _verification(bundle, new)):
            raise ValueError("Project verification must bind a fresh occurrence")
        _identity(verification, "verification_id")

    def _validate(self, bundle):
        try:
            _keys(bundle, {"schema", "session_id", "created_at", "source", "configuration", "runtimes",
                           "steps", "bundle_digest", "verification"}, {"replay_receipts"})
            if (len(canonical(bundle)) > MAX_BYTES or bundle["schema"] != SCHEMA or
                    bundle["bundle_digest"] != _bundle_digest(bundle) or
                    not re.fullmatch(r"session-[a-f0-9]{32}", bundle["session_id"])):
                raise ValueError("Project bundle identity or size differs")
            _text(bundle["created_at"])
            evidence, = bundle["source"]["evidence"]
            raw = base64.b64decode(evidence["bytes_b64"], validate=True)
            source = self._source(raw)
            expected_evidence = {"artifact_ref": byte_digest(raw), "sha256": byte_digest(raw),
                                 "bytes_b64": base64.b64encode(raw).decode()}
            if (evidence != expected_evidence or bundle["source"] != {
                    "experiment_id": source["experiment_id"], "experiment_digest": digest(source),
                    "evidence": [evidence]} or canonical(bundle["configuration"]) != canonical(CONFIGURATION)):
                raise ValueError("Project source or configuration binding differs")
            _keys(bundle["runtimes"], {ROLE})
            runtime = bundle["runtimes"][ROLE]
            expected_runtime = runtime_identity()
            if runtime != expected_runtime:
                _keys(runtime, set(expected_runtime))
                if (runtime["schema"] != expected_runtime["schema"] or runtime["role"] != ROLE or
                        runtime["profile"] != expected_runtime["profile"] or
                        runtime["execution_scope"] != expected_runtime["execution_scope"] or
                        runtime["execution"] != expected_runtime["execution"] or
                        runtime["physical_validation"] != expected_runtime["physical_validation"] or
                        runtime["state_admission"] != expected_runtime["state_admission"]):
                    raise ValueError("Unapproved project reference runtime")
                algorithm = runtime["algorithm"]
                _keys(algorithm, {"profile", "code_sha256", "source_normalization"})
                if (algorithm["profile"] != expected_runtime["algorithm"]["profile"] or
                        algorithm["source_normalization"] != "utf8_lf" or
                        not re.fullmatch(r"[a-f0-9]{64}", algorithm["code_sha256"])):
                    raise ValueError("Malformed project reference algorithm identity")
            step, = bundle["steps"]
            self._validate_step(step, source, evidence["artifact_ref"])
            self._check_verification(bundle, bundle["verification"], source, evidence["artifact_ref"])
            receipts = bundle.get("replay_receipts", [])
            if not isinstance(receipts, list) or len(receipts) > 1:
                raise ValueError("At most one project replay receipt belongs to an occurrence")
            for receipt in receipts:
                _keys(receipt, {"schema", "source_bundle_digest", "replayed_bundle_digest", "numerical_match",
                                "verification", "admission", "replay_id"})
                if (receipt["schema"] != "ciw." + KIND + "-replay.v1" or
                        receipt["replayed_bundle_digest"] != bundle["bundle_digest"] or
                        receipt["source_bundle_digest"] == bundle["bundle_digest"] or
                        receipt["numerical_match"] is not True or receipt["admission"] != "not_performed" or
                        receipt["replay_id"] != digest({k: v for k, v in receipt.items() if k != "replay_id"})):
                    raise ValueError("Invalid project replay receipt")
                verification = receipt["verification"]
                _keys(verification, {"schema", "subject_ref", "outcome", "independent", "method", "runtime_digest",
                                     "reproduction", "authority", "verification_id"})
                if (verification["schema"] != VERIFY_SCHEMA or
                        verification["subject_ref"] != receipt["source_bundle_digest"] or
                        verification["outcome"] != "passed" or verification["independent"] is not False or
                        verification["method"] != "same_python_reference_fresh_occurrence_reproduction" or
                        verification["authority"] != AUTHORITY):
                    raise ValueError("Invalid project replay verification scope")
                _validate_step(verification["reproduction"], source, evidence["artifact_ref"])
                _identity(verification, "verification_id")
            return raw
        except (KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
            raise ValueError("Malformed retained project graph session") from exc

    def _execute(self, raw, runtime):
        source = self._source(raw)
        evidence = byte_digest(raw)
        step = _step(source, evidence, runtime)
        bundle = {
            "schema": SCHEMA,
            "session_id": "session-" + uuid.uuid4().hex,
            "created_at": _now(),
            "source": {"experiment_id": source["experiment_id"], "experiment_digest": digest(source),
                       "evidence": [{"artifact_ref": evidence, "sha256": evidence,
                                     "bytes_b64": base64.b64encode(raw).decode()}]},
            "configuration": deepcopy(CONFIGURATION),
            "runtimes": {ROLE: deepcopy(runtime)},
            "steps": [step],
        }
        bundle["bundle_digest"] = _bundle_digest(bundle)
        bundle["verification"] = _verification(bundle, _step(source, evidence, runtime))
        self._validate(bundle)
        return bundle

    def create_session(self, raw, repositories):
        self._source(raw)
        return self._execute(raw, self._adapters(repositories)[1])

    def replay_session(self, bundle, repositories):
        raw = self._validate(bundle)
        runtime = self._adapters(repositories, bundle["runtimes"])[1]
        fresh = self._execute(raw, runtime)
        receipt = {
            "schema": "ciw." + KIND + "-replay.v1",
            "source_bundle_digest": bundle["bundle_digest"],
            "replayed_bundle_digest": fresh["bundle_digest"],
            "numerical_match": True,
            "verification": _verification(bundle, fresh["steps"][0]),
            "admission": "not_performed",
        }
        receipt["replay_id"] = digest(receipt)
        fresh["replay_receipts"] = [receipt]
        self._validate(fresh)
        return {"session": fresh, "replay_receipt": receipt}
