"""Bounded nonlinear fusion with pinned model evaluation and GSIE kernels.

NET retains the declared model, approximation and occurrence identities. The
scientific arithmetic stays in the pinned providers; inspection is read-only.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
import uuid

from . import sensor_fusion_ekf as contract
from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import PinnedSubprocessAdapter
from .declared_workload import DeclaredWorkflow, RESULT_SCHEMA, VERIFY_SCHEMA, _text
from .exchange import _identity
from .telemetry import _bundle_digest, _keys, _now, byte_digest, canonical, digest

OPERATION = "ciw.sensor-fusion-ekf.v1"
METHOD = "same_pinned_gsie_jspt_fresh_occurrence_reproduction"
RUNTIME_FIELDS = {"schema", "adapter_version", "repository_root", "revision", "source_tree", "module",
                  "source_root", "python_executable", "python_sha256", "python_version", "dependencies"}


def algorithm_identity():
    content = Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
    return sha256(contract.algorithm_identity().encode() + b"\0" + content).hexdigest()


def numerical_projection(data):
    return {"operation_id": OPERATION, "data": deepcopy(data)}


def _verification(bundle, reproduced):
    if canonical(bundle["steps"][0]["numerical_result"]) != canonical(reproduced["numerical_result"]):
        raise AdapterRefusal("EKF_REPLAY_MISMATCH", "Pinned nonlinear fusion reproduction differs from retained output")
    value = {"schema": VERIFY_SCHEMA, "subject_ref": bundle["bundle_digest"], "outcome": "passed",
             "independent": False, "method": METHOD, "runtime_digest": digest(bundle["runtimes"]),
             "reproduction": deepcopy(reproduced), "authority": deepcopy(contract.AUTHORITY)}
    value["verification_id"] = byte_digest(VERIFY_SCHEMA.encode() + b"\0" + canonical(value))
    return value


class SensorFusionEKFWorkflow(DeclaredWorkflow):
    MAX_BYTES = contract.MAX_BYTES
    ROLES = {"gsie", "jspt"}

    def __init__(self):
        self.kind, self.role = "sensor-fusion-ekf", "gsie"
        self.pin, self.SOURCE_SCHEMA = contract.PIN, contract.SOURCE_SCHEMA
        self.schema, self.operation = "ciw.sensor-fusion-ekf-session.v1", OPERATION

    def _source(self, raw):
        return contract.validate_source(raw)

    @staticmethod
    def _runtime_projection(runtime):
        projection = DeclaredWorkflow._runtime_projection(runtime)
        projection["companions"] = {role: DeclaredWorkflow._runtime_projection(value)
                                    for role, value in runtime["companions"].items()}
        return projection

    @staticmethod
    def _runtime(adapter, companion):
        primary, secondary = adapter.runtime_identity(), companion.runtime_identity()
        if primary["source_tree"] != contract.SOURCE_TREE or secondary["source_tree"] != contract.JSPT_TREE:
            raise AdapterRefusal("SOURCE_PIN_MISMATCH", "Nonlinear fusion provider source differs from the declared capability")
        primary["adapter_version"] += ";sensor-fusion-ekf:" + algorithm_identity()
        primary["companions"] = {"jspt": secondary}
        return primary

    def _adapters(self, repositories, expected=None):
        if not isinstance(repositories, dict) or set(repositories) != self.ROLES:
            raise ValueError("Bind exactly the trusted GSIE and JSPT provider checkouts")
        retained = expected[self.role] if expected else {}
        secondary = retained["companions"]["jspt"] if retained else {}

        def adapter(role, pin, identity):
            return PinnedSubprocessAdapter(repositories[role], pin["revision"], pin["module"],
                source_root=pin["source_root"], expected_python_sha256=identity.get("python_sha256"),
                expected_python_version=identity.get("python_version"), expected_dependencies=identity.get("dependencies"),
                max_output_bytes=self.MAX_BYTES)

        primary = adapter("gsie", self.pin, retained)
        companion = adapter("jspt", contract.JSPT_PIN, secondary)
        runtime = self._runtime(primary, companion)
        if retained and self._runtime_projection(runtime) != self._runtime_projection(retained):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "Nonlinear fusion composition or provider runtime changed")
        return primary, runtime, companion

    def _step(self, source, evidence, bound):
        adapter, runtime, companion = bound
        if self._runtime_projection(self._runtime(adapter, companion)) != self._runtime_projection(runtime):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "Nonlinear fusion runtime changed before execution")
        data = contract.invoke(source, adapter, companion)
        if self._runtime_projection(self._runtime(adapter, companion)) != self._runtime_projection(runtime):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "Nonlinear fusion runtime changed during execution")
        contract.validate_data(source, data)
        occurrence = "execution-" + uuid.uuid4().hex
        result = {"schema": RESULT_SCHEMA, "operation_id": self.operation, "execution_ref": occurrence,
                  "input_refs": [evidence], "data": data, "authority": deepcopy(contract.AUTHORITY)}
        result["result_id"] = digest(result)
        numerical = numerical_projection(data)
        return {"runtime_ref": self.role, "operation_id": self.operation, "execution_id": occurrence,
                "input_refs": [evidence], "request": deepcopy(source), "request_sha256": digest(source),
                "result": result, "result_sha256": digest(result), "result_id": result["result_id"],
                "numerical_result": numerical, "numerical_result_id": digest(numerical)}

    def _validate_step(self, step, source, evidence):
        _keys(step, {"runtime_ref", "operation_id", "execution_id", "input_refs", "request", "request_sha256",
                     "result", "result_sha256", "result_id", "numerical_result", "numerical_result_id"})
        if (step["runtime_ref"] != self.role or step["operation_id"] != self.operation or step["input_refs"] != [evidence] or
                canonical(step["request"]) != canonical(source) or not isinstance(step["execution_id"], str) or
                not re.fullmatch(r"execution-[a-f0-9]{32}", step["execution_id"])):
            raise ValueError("Nonlinear fusion request, evidence or occurrence binding differs")
        result = step["result"]
        _keys(result, {"schema", "operation_id", "execution_ref", "input_refs", "data", "authority", "result_id"})
        contract.validate_data(source, result["data"])
        if (result["schema"] != RESULT_SCHEMA or result["operation_id"] != self.operation or
                result["execution_ref"] != step["execution_id"] or result["input_refs"] != [evidence] or
                result["authority"] != contract.AUTHORITY or result["result_id"] != step["result_id"] or
                result["result_id"] != digest({k: v for k, v in result.items() if k != "result_id"}) or
                canonical(step["numerical_result"]) != canonical(numerical_projection(result["data"]))):
            raise ValueError("Nonlinear fusion result binding or authority differs")
        for key, value in (("request_sha256", source), ("result_sha256", result),
                           ("numerical_result_id", step["numerical_result"])):
            if step[key] != digest(value):
                raise ValueError("Nonlinear fusion content identity differs")

    def _check_verification(self, bundle, verification, source, evidence):
        _keys(verification, {"schema", "subject_ref", "outcome", "independent", "method", "runtime_digest",
                             "reproduction", "authority", "verification_id"})
        reproduced = verification["reproduction"]
        self._validate_step(reproduced, source, evidence)
        old = bundle["steps"][0]
        if (old["execution_id"] == reproduced["execution_id"] or old["result_id"] == reproduced["result_id"] or
                canonical(verification) != canonical(_verification(bundle, reproduced))):
            raise ValueError("Nonlinear fusion verification requires fresh occurrences and limited authority")
        _identity(verification, "verification_id")

    def _validate_runtime(self, runtime):
        _keys(runtime, RUNTIME_FIELDS | {"companions"})
        _keys(runtime["companions"], {"jspt"})
        companion = runtime["companions"]["jspt"]
        _keys(companion, RUNTIME_FIELDS)
        for value, pin, tree, pattern in (
                (runtime, self.pin, contract.SOURCE_TREE, r"ciw-pinned-subprocess-v1;sensor-fusion-ekf:[a-f0-9]{64}"),
                (companion, contract.JSPT_PIN, contract.JSPT_TREE, r"ciw-pinned-subprocess-v1")):
            if (value["schema"] != "ciw.subprocess-runtime.v1" or any(value[k] != pin[k] for k in pin) or
                    value["source_tree"] != tree or not isinstance(value["adapter_version"], str) or
                    not re.fullmatch(pattern, value["adapter_version"]) or not isinstance(value["python_sha256"], str) or
                    not re.fullmatch(r"[a-f0-9]{64}", value["python_sha256"]) or not isinstance(value["dependencies"], dict)):
                raise ValueError("Unapproved nonlinear fusion runtime identity")
            for key in ("repository_root", "python_executable", "python_version"):
                _text(value[key])

    def _validate(self, bundle):
        try:
            _keys(bundle, {"schema", "session_id", "created_at", "source", "configuration", "runtimes", "steps",
                           "bundle_digest", "verification"}, {"replay_receipts"})
            if (len(canonical(bundle)) > self.MAX_BYTES or bundle["schema"] != self.schema or
                    bundle["bundle_digest"] != _bundle_digest(bundle) or not isinstance(bundle["session_id"], str) or
                    not re.fullmatch(r"session-[a-f0-9]{32}", bundle["session_id"])):
                raise ValueError("Nonlinear fusion session binding differs")
            _text(bundle["created_at"])
            evidence, = bundle["source"]["evidence"]
            raw = base64.b64decode(evidence["bytes_b64"], validate=True)
            source = self._source(raw)
            expected = {"artifact_ref": byte_digest(raw), "sha256": byte_digest(raw),
                        "bytes_b64": base64.b64encode(raw).decode()}
            if (evidence != expected or bundle["source"] != {"experiment_id": source["experiment_id"],
                    "experiment_digest": digest(source), "evidence": [expected]} or
                    canonical(bundle["configuration"]) != canonical(source["configuration"]) or
                    set(bundle["runtimes"]) != {self.role}):
                raise ValueError("Nonlinear fusion source, configuration or runtime binding differs")
            self._validate_runtime(bundle["runtimes"][self.role])
            step, = bundle["steps"]
            self._validate_step(step, source, evidence["artifact_ref"])
            self._check_verification(bundle, bundle["verification"], source, evidence["artifact_ref"])
            receipts = bundle.get("replay_receipts", [])
            if not isinstance(receipts, list) or len(receipts) > 1:
                raise ValueError("Require at most one nonlinear fusion replay receipt")
            for receipt in receipts:
                _keys(receipt, {"schema", "source_bundle_digest", "replayed_bundle_digest", "numerical_match",
                                "verification", "admission", "replay_id"})
                if (receipt["schema"] != "ciw.sensor-fusion-ekf-replay.v1" or
                        receipt["replayed_bundle_digest"] != bundle["bundle_digest"] or
                        not isinstance(receipt["source_bundle_digest"], str) or
                        not re.fullmatch(r"sha256:[a-f0-9]{64}", receipt["source_bundle_digest"]) or
                        receipt["source_bundle_digest"] == bundle["bundle_digest"] or receipt["numerical_match"] is not True or
                        receipt["admission"] != "not_performed" or
                        receipt["replay_id"] != digest({k: v for k, v in receipt.items() if k != "replay_id"})):
                    raise ValueError("Nonlinear fusion replay receipt commitment differs")
                expected_proof = _verification(bundle, step)
                expected_proof["subject_ref"] = receipt["source_bundle_digest"]
                expected_proof["verification_id"] = byte_digest(VERIFY_SCHEMA.encode() + b"\0" + canonical(
                    {k: v for k, v in expected_proof.items() if k != "verification_id"}))
                if canonical(receipt["verification"]) != canonical(expected_proof):
                    raise ValueError("Replay verification must bind this exact fresh nonlinear fusion occurrence")
            return raw
        except (KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
            raise ValueError("Malformed nonlinear fusion session") from exc

    def _execute(self, raw, bound):
        source, evidence = self._source(raw), byte_digest(raw)
        step = self._step(source, evidence, bound)
        bundle = {"schema": self.schema, "session_id": "session-" + uuid.uuid4().hex, "created_at": _now(),
                  "source": {"experiment_id": source["experiment_id"], "experiment_digest": digest(source),
                             "evidence": [{"artifact_ref": evidence, "sha256": evidence,
                                          "bytes_b64": base64.b64encode(raw).decode()}]},
                  "configuration": deepcopy(source["configuration"]), "runtimes": {self.role: deepcopy(bound[1])},
                  "steps": [step]}
        bundle["bundle_digest"] = _bundle_digest(bundle)
        bundle["verification"] = _verification(bundle, self._step(source, evidence, bound))
        self._validate(bundle)
        return bundle

    def replay_session(self, bundle, repositories):
        raw = self._validate(bundle)
        fresh = self._execute(raw, self._adapters(repositories, bundle["runtimes"]))
        receipt = {"schema": "ciw.sensor-fusion-ekf-replay.v1", "source_bundle_digest": bundle["bundle_digest"],
                   "replayed_bundle_digest": fresh["bundle_digest"], "numerical_match": True,
                   "verification": _verification(bundle, fresh["steps"][0]), "admission": "not_performed"}
        receipt["replay_id"] = digest(receipt)
        fresh["replay_receipts"] = [receipt]
        self._check_verification(bundle, receipt["verification"], self._source(raw), byte_digest(raw))
        self._validate(fresh)
        return {"session": fresh, "replay_receipt": receipt}


workflow = SensorFusionEKFWorkflow()
create_session = workflow.create_session
replay_session = workflow.replay_session
