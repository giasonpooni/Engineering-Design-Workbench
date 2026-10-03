"""Retained coordinate transport followed by an unchanged GSIE v1 continuation.

The selected upstream is an immutable input. JSPT owns the linear mapping;
GSIE owns filtering. Each wrapper and child execution has its own occurrence.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
import uuid

from . import sensor_fusion_transport as contract
from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import PinnedSubprocessAdapter
from .declared_workload import DeclaredWorkflow, RESULT_SCHEMA, VERIFY_SCHEMA
from .exchange import _identity
from .sensor_fusion_workflow import SensorFusionWorkflow
from .telemetry import _bundle_digest, _keys, _now, byte_digest, canonical, digest

DATA_SCHEMA = "ciw.sensor-fusion-transport-result.v1"
MAX_BYTES = 24 * 1024 * 1024
METHOD = "same_pinned_jspt_gsie_fresh_occurrence_reproduction"


def algorithm_identity():
    content = Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
    return sha256(contract.algorithm_identity().encode() + b"\0" + content).hexdigest()


def numerical_projection(data):
    """Keep scientific content; execution and verification occurrences stay fresh."""
    return {"operation_id": contract.OPERATION, "data": {
        "selection": deepcopy(data["selection"]), "transport": deepcopy(data["transport"]),
        "continuation": deepcopy(data["continuation"]["steps"][0]["numerical_result"]),
        "authority": deepcopy(data["authority"])}}


def _verification(bundle, reproduced):
    if canonical(bundle["steps"][0]["numerical_result"]) != canonical(reproduced["numerical_result"]):
        raise AdapterRefusal("TRANSPORT_REPLAY_MISMATCH", "Transport or continuation differs from retained output")
    value = {"schema": VERIFY_SCHEMA, "subject_ref": bundle["bundle_digest"], "outcome": "passed",
             "independent": False, "method": METHOD, "runtime_digest": digest(bundle["runtimes"]),
             "reproduction": deepcopy(reproduced), "authority": deepcopy(contract.AUTHORITY)}
    value["verification_id"] = byte_digest(VERIFY_SCHEMA.encode() + b"\0" + canonical(value))
    return value


def _parent_steps(bundle):
    yield bundle["steps"][0]
    yield bundle["verification"]["reproduction"]
    for receipt in bundle.get("replay_receipts", []):
        yield receipt["verification"]["reproduction"]


def catalog_steps(bundle):
    """Expose the new child's primary native occurrence, never re-own upstream."""
    return deepcopy(bundle["steps"][0]["result"]["data"]["continuation"]["steps"])


def native_occurrences(bundle):
    identities = set()
    for parent in _parent_steps(bundle):
        identities.add(parent["execution_id"])
        child = parent["result"]["data"]["continuation"]
        identities.add(child["steps"][0]["execution_id"])
        identities.add(child["verification"]["reproduction"]["execution_id"])
    return identities


def identity_claims(bundle):
    """Register every retained child identity, including reproduction children."""
    claims = {}

    def claim(identity, role, body):
        value = (role, deepcopy(body))
        if identity in claims and canonical(claims[identity]) != canonical(value):
            raise ValueError("Transport continuation identity collision")
        claims[identity] = value

    def step(value):
        claim(value["operation_id"], "operation", value["operation_id"])
        claim(value["execution_id"], "execution", {"step": value})
        claim(value["result_id"], "result", {"result": value["result"]})
        claim(value["numerical_result_id"], "numerical_result", value["numerical_result"])

    for parent in _parent_steps(bundle):
        child = parent["result"]["data"]["continuation"]
        body = {k: v for k, v in child.items() if k not in {"verification", "replay_receipts"}}
        claim(child["bundle_digest"], "bundle", body)
        claim(child["session_id"], "session", child["bundle_digest"])
        for evidence in child["source"]["evidence"]:
            claim(evidence["artifact_ref"], "evidence", evidence["bytes_b64"])
        step(child["steps"][0])
        proof = child["verification"]
        claim(proof["verification_id"], "verification", proof)
        step(proof["reproduction"])
    return claims


class SensorFusionTransportWorkflow(DeclaredWorkflow):
    MAX_BYTES = MAX_BYTES
    ROLES = {"jspt", "gsie"}

    def __init__(self):
        self.kind, self.role = contract.KIND, "jspt"
        self.pin, self.SOURCE_SCHEMA = contract.PIN, contract.SOURCE_SCHEMA
        self.schema, self.operation = "ciw.sensor-fusion-transport-session.v1", contract.OPERATION

    def _source(self, raw):
        return contract.validate_source(raw)

    @staticmethod
    def _runtime_projection(runtime):
        primary = DeclaredWorkflow._runtime_projection(runtime)
        primary["companions"] = {role: DeclaredWorkflow._runtime_projection(value)
                                 for role, value in runtime["companions"].items()}
        return primary

    @staticmethod
    def _runtime(adapter, companion):
        runtime = adapter.runtime_identity()
        if runtime["source_tree"] != contract.SOURCE_TREE:
            raise AdapterRefusal("SOURCE_PIN_MISMATCH", "JSPT source tree differs from the transport capability")
        runtime["adapter_version"] += ";sensor-fusion-transport:" + algorithm_identity()
        runtime["companions"] = {"gsie": deepcopy(companion)}
        return runtime

    def _adapters(self, repositories, expected=None):
        if not isinstance(repositories, dict) or set(repositories) != self.ROLES:
            raise ValueError("Bind exactly the trusted JSPT and GSIE provider checkouts")
        retained = expected[self.role] if expected else {}
        child_expected = {"gsie": retained["companions"]["gsie"]} if retained else None
        child_bound = SensorFusionWorkflow()._adapters({"gsie": repositories["gsie"]}, child_expected)
        adapter = PinnedSubprocessAdapter(repositories["jspt"], self.pin["revision"], self.pin["module"],
            source_root=self.pin["source_root"], expected_python_sha256=retained.get("python_sha256"),
            expected_python_version=retained.get("python_version"),
            expected_dependencies=retained.get("dependencies"), max_output_bytes=self.MAX_BYTES)
        runtime = self._runtime(adapter, child_bound[1])
        if retained and self._runtime_projection(runtime) != self._runtime_projection(retained):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "Transport composition or provider identity changed")
        return adapter, runtime, {"gsie": repositories["gsie"]}

    @staticmethod
    def _refs(source, evidence):
        return [evidence, source["selection"]["upstream_result_id"], source["selection"]["state_id"]]

    def _step(self, source, evidence, bound, upstream):
        adapter, runtime, repositories = bound
        companion = runtime["companions"]["gsie"]
        if self._runtime_projection(self._runtime(adapter, companion)) != self._runtime_projection(runtime):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "Transport runtime changed before execution")
        transported = contract.invoke(source, upstream, adapter)
        contract.validate_transport(source, upstream, transported)
        child_raw = base64.b64decode(transported["continuation_source_b64"], validate=True)
        child = SensorFusionWorkflow().create_session(child_raw, repositories)
        if (DeclaredWorkflow._runtime_projection(child["runtimes"]["gsie"]) !=
                DeclaredWorkflow._runtime_projection(companion)):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "GSIE continuation runtime changed during composition")
        if self._runtime_projection(self._runtime(adapter, companion)) != self._runtime_projection(runtime):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "Transport runtime changed during execution")
        data = {"schema": DATA_SCHEMA, "selection": deepcopy(source["selection"]),
                "transport": transported, "continuation": child, "authority": deepcopy(contract.AUTHORITY)}
        occurrence = "execution-" + uuid.uuid4().hex
        refs = self._refs(source, evidence)
        result = {"schema": RESULT_SCHEMA, "operation_id": self.operation, "execution_ref": occurrence,
                  "input_refs": refs, "data": data, "authority": deepcopy(contract.AUTHORITY)}
        result["result_id"] = digest(result)
        numerical = numerical_projection(data)
        return {"runtime_ref": self.role, "operation_id": self.operation, "execution_id": occurrence,
                "input_refs": refs, "request": deepcopy(source), "request_sha256": digest(source),
                "result": result, "result_sha256": digest(result), "result_id": result["result_id"],
                "numerical_result": numerical, "numerical_result_id": digest(numerical)}

    def _validate_step(self, step, source, evidence, upstream):
        _keys(step, {"runtime_ref", "operation_id", "execution_id", "input_refs", "request", "request_sha256",
                     "result", "result_sha256", "result_id", "numerical_result", "numerical_result_id"})
        refs = self._refs(source, evidence)
        if (step["runtime_ref"] != self.role or step["operation_id"] != self.operation or step["input_refs"] != refs or
                canonical(step["request"]) != canonical(source) or not isinstance(step["execution_id"], str) or
                not re.fullmatch(r"execution-[a-f0-9]{32}", step["execution_id"])):
            raise ValueError("Transport request, evidence or execution binding differs")
        result = step["result"]
        _keys(result, {"schema", "operation_id", "execution_ref", "input_refs", "data", "authority", "result_id"})
        data = result["data"]
        _keys(data, {"schema", "selection", "transport", "continuation", "authority"})
        if data["schema"] != DATA_SCHEMA or data["selection"] != source["selection"] or data["authority"] != contract.AUTHORITY:
            raise ValueError("Transport selection or limited authority differs")
        contract.validate_transport(source, upstream, data["transport"])
        child = data["continuation"]
        child_raw = SensorFusionWorkflow()._validate(child)
        if (child_raw != base64.b64decode(data["transport"]["continuation_source_b64"], validate=True) or
                child["steps"][0]["result"]["data"]["initial_state_id"] != data["transport"]["mapped_state_id"] or
                child.get("replay_receipts")):
            raise ValueError("Continuation must consume the exact transported prior and source bytes")
        if (result["schema"] != RESULT_SCHEMA or result["operation_id"] != self.operation or
                result["execution_ref"] != step["execution_id"] or result["input_refs"] != refs or
                result["authority"] != contract.AUTHORITY or result["result_id"] != step["result_id"] or
                result["result_id"] != digest({k: v for k, v in result.items() if k != "result_id"}) or
                canonical(step["numerical_result"]) != canonical(numerical_projection(data))):
            raise ValueError("Transport result or numerical identity differs")
        for key, value in (("request_sha256", source), ("result_sha256", result),
                           ("numerical_result_id", step["numerical_result"])):
            if step[key] != digest(value):
                raise ValueError("Transport content identity differs")

    def _check_verification(self, bundle, verification, source, evidence):
        _keys(verification, {"schema", "subject_ref", "outcome", "independent", "method", "runtime_digest",
                             "reproduction", "authority", "verification_id"})
        reproduced = verification["reproduction"]
        self._validate_step(reproduced, source, evidence, bundle["upstream_fusion"])
        old = bundle["steps"][0]
        if (old["execution_id"] == reproduced["execution_id"] or old["result_id"] == reproduced["result_id"] or
                canonical(verification) != canonical(_verification(bundle, reproduced))):
            raise ValueError("Transport verification requires fresh composed occurrences and limited authority")
        _identity(verification, "verification_id")

    def validate_upstream(self, bundle, upstream):
        if canonical(bundle["upstream_fusion"]) != canonical(upstream):
            raise ValueError("Transport upstream must exactly match the selected retained fusion bundle")
        source = self._source(base64.b64decode(bundle["source"]["evidence"][0]["bytes_b64"], validate=True))
        contract.prepare(source, upstream)
        return deepcopy(source["selection"])

    def _validate_runtime(self, runtime):
        from .sensor_fusion_workflow import PIN as GSIE_PIN, SOURCE_TREE as GSIE_TREE
        _keys(runtime, {"schema", "adapter_version", "repository_root", "revision", "source_tree", "module",
                        "source_root", "python_executable", "python_sha256", "python_version", "dependencies", "companions"})
        if (runtime["schema"] != "ciw.subprocess-runtime.v1" or any(runtime[k] != self.pin[k] for k in self.pin) or
                runtime["source_tree"] != contract.SOURCE_TREE or not isinstance(runtime["adapter_version"], str) or
                not re.fullmatch(r"ciw-pinned-subprocess-v1;sensor-fusion-transport:[a-f0-9]{64}", runtime["adapter_version"])):
            raise ValueError("Unapproved JSPT transport runtime identity")
        _keys(runtime["companions"], {"gsie"})
        companion = runtime["companions"]["gsie"]
        _keys(companion, {"schema", "adapter_version", "repository_root", "revision", "source_tree", "module",
                          "source_root", "python_executable", "python_sha256", "python_version", "dependencies"})
        if (companion["schema"] != "ciw.subprocess-runtime.v1" or any(companion[k] != GSIE_PIN[k] for k in GSIE_PIN) or
                companion["source_tree"] != GSIE_TREE or not isinstance(companion["adapter_version"], str) or
                not re.fullmatch(r"ciw-pinned-subprocess-v1;sensor-fusion:[a-f0-9]{64}", companion["adapter_version"])):
            raise ValueError("Unapproved GSIE continuation runtime identity")
        for value in (runtime, companion):
            if (not isinstance(value["python_sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", value["python_sha256"]) or
                    not isinstance(value["dependencies"], dict)):
                raise ValueError("Invalid transport interpreter or dependency identities")
            for key in ("repository_root", "python_executable", "python_version"):
                if not isinstance(value[key], str) or not value[key].strip():
                    raise ValueError("Require explicit retained runtime metadata")

    def _validate(self, bundle):
        try:
            _keys(bundle, {"schema", "session_id", "created_at", "source", "configuration", "runtimes", "steps",
                           "bundle_digest", "verification", "upstream_fusion"}, {"replay_receipts"})
            if (len(canonical(bundle)) > self.MAX_BYTES or bundle["schema"] != self.schema or
                    bundle["bundle_digest"] != _bundle_digest(bundle) or not isinstance(bundle["session_id"], str) or
                    not re.fullmatch(r"session-[a-f0-9]{32}", bundle["session_id"]) or
                    not isinstance(bundle["created_at"], str) or not bundle["created_at"].strip()):
                raise ValueError("Transport bundle commitment or occurrence differs")
            evidence, = bundle["source"]["evidence"]
            raw = base64.b64decode(evidence["bytes_b64"], validate=True)
            source = self._source(raw)
            expected_evidence = {"artifact_ref": byte_digest(raw), "sha256": byte_digest(raw),
                                 "bytes_b64": base64.b64encode(raw).decode()}
            if (evidence != expected_evidence or bundle["source"] != {"experiment_id": source["experiment_id"],
                    "experiment_digest": digest(source), "evidence": [expected_evidence]} or
                    bundle["configuration"] != contract.POLICY or set(bundle["runtimes"]) != {self.role}):
                raise ValueError("Transport source, configuration or runtime binding differs")
            self.validate_upstream(bundle, bundle["upstream_fusion"])
            runtime = bundle["runtimes"][self.role]
            self._validate_runtime(runtime)
            step, = bundle["steps"]
            self._validate_step(step, source, evidence["artifact_ref"], bundle["upstream_fusion"])
            self._check_verification(bundle, bundle["verification"], source, evidence["artifact_ref"])
            occurrences = []
            sessions = [bundle["session_id"]]
            for parent in (step, bundle["verification"]["reproduction"]):
                child = parent["result"]["data"]["continuation"]
                sessions.append(child["session_id"])
                occurrences += [parent["execution_id"], child["steps"][0]["execution_id"],
                                child["verification"]["reproduction"]["execution_id"]]
                if (DeclaredWorkflow._runtime_projection(child["runtimes"]["gsie"]) !=
                        DeclaredWorkflow._runtime_projection(runtime["companions"]["gsie"])):
                    raise ValueError("Continuation provider differs from the composed runtime")
            if len(set(occurrences)) != len(occurrences) or len(set(sessions)) != len(sessions):
                raise ValueError("Transport and child executions and sessions require distinct occurrences")
            upstream = bundle["upstream_fusion"]
            upstream_occurrences = {upstream["steps"][0]["execution_id"],
                                    upstream["verification"]["reproduction"]["execution_id"]}
            if upstream_occurrences.intersection(occurrences) or upstream["session_id"] in sessions:
                raise ValueError("Transport cannot reuse an upstream occurrence")
            receipts = bundle.get("replay_receipts", [])
            if not isinstance(receipts, list) or len(receipts) > 1:
                raise ValueError("Require at most one transport replay receipt")
            for receipt in receipts:
                _keys(receipt, {"schema", "source_bundle_digest", "replayed_bundle_digest", "numerical_match",
                                "verification", "admission", "replay_id"})
                if (receipt["schema"] != "ciw.sensor-fusion-transport-replay.v1" or
                        receipt["replayed_bundle_digest"] != bundle["bundle_digest"] or
                        not isinstance(receipt["source_bundle_digest"], str) or
                        not re.fullmatch(r"sha256:[a-f0-9]{64}", receipt["source_bundle_digest"]) or
                        receipt["source_bundle_digest"] == bundle["bundle_digest"] or receipt["numerical_match"] is not True or
                        receipt["admission"] != "not_performed" or
                        receipt["replay_id"] != digest({k: v for k, v in receipt.items() if k != "replay_id"})):
                    raise ValueError("Transport replay receipt commitment differs")
                expected = _verification(bundle, step)
                expected["subject_ref"] = receipt["source_bundle_digest"]
                expected["verification_id"] = byte_digest(VERIFY_SCHEMA.encode() + b"\0" + canonical(
                    {k: v for k, v in expected.items() if k != "verification_id"}))
                if canonical(receipt["verification"]) != canonical(expected):
                    raise ValueError("Replay verification must bind this exact fresh composition")
            identity_claims(bundle)
            return raw
        except (KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
            raise ValueError("Malformed sensor-fusion transport session") from exc

    def _execute_selected(self, raw, upstream, bound):
        source = self._source(raw)
        contract.prepare(source, upstream)
        evidence = byte_digest(raw)
        step = self._step(source, evidence, bound, upstream)
        bundle = {"schema": self.schema, "session_id": "session-" + uuid.uuid4().hex, "created_at": _now(),
                  "source": {"experiment_id": source["experiment_id"], "experiment_digest": digest(source),
                             "evidence": [{"artifact_ref": evidence, "sha256": evidence,
                                          "bytes_b64": base64.b64encode(raw).decode()}]},
                  "configuration": deepcopy(contract.POLICY), "runtimes": {self.role: deepcopy(bound[1])},
                  "steps": [step], "upstream_fusion": deepcopy(upstream)}
        bundle["bundle_digest"] = _bundle_digest(bundle)
        bundle["verification"] = _verification(bundle, self._step(source, evidence, bound, upstream))
        self._validate(bundle)
        return bundle

    def create_session(self, raw, upstream, repositories):
        contract.prepare(self._source(raw), upstream)
        return self._execute_selected(raw, upstream, self._adapters(repositories))

    def replay_session(self, bundle, repositories):
        raw = self._validate(bundle)
        fresh = self._execute_selected(raw, bundle["upstream_fusion"], self._adapters(repositories, bundle["runtimes"]))
        receipt = {"schema": "ciw.sensor-fusion-transport-replay.v1", "source_bundle_digest": bundle["bundle_digest"],
                   "replayed_bundle_digest": fresh["bundle_digest"], "numerical_match": True,
                   "verification": _verification(bundle, fresh["steps"][0]), "admission": "not_performed"}
        receipt["replay_id"] = digest(receipt)
        fresh["replay_receipts"] = [receipt]
        self._check_verification(bundle, receipt["verification"], self._source(raw), byte_digest(raw))
        self._validate(fresh)
        return {"session": fresh, "replay_receipt": receipt}


workflow = SensorFusionTransportWorkflow()
create_session = workflow.create_session
replay_session = workflow.replay_session
