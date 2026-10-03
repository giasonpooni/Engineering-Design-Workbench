"""Reconfigurable GSIE composition; NET retains contracts and occurrence identities.

All filtering arithmetic stays in the pinned scientific provider. A saved
configuration selects a fixed declared capability, never a module or callable.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
import uuid

from . import sensor_fusion_contract as contract
from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import PinnedSubprocessAdapter, _json
from .declared_workload import DeclaredWorkflow, RESULT_SCHEMA, VERIFY_SCHEMA
from .exchange import _identity
from .telemetry import _bundle_digest, _keys, _now, byte_digest, canonical, digest

PIN = {"revision": "5241eee6dab434533bdf0cf0e824bc43b4a79831",
       "module": "geometric_state_inference.contracts", "source_root": "src"}
SOURCE_TREE = "375c031c07592d5bcb1d224780f18ceb886df4a1"
OPERATION = "ciw.sensor-fusion.v1"

# The host supplies only detached validated data to this fixed program.
_BOOTSTRAP = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from geometric_state_inference import StatePrior, Observation, LinearDynamics, LinearObservation, predict, update
from geometric_state_inference.geometry import EuclideanGeometry, SO2Geometry
request = json.loads(sys.stdin.buffer.read())
source, resolved = request['source'], request['resolved']
state = source['configuration']['state']
geometry = SO2Geometry() if state['geometry'] == 'so2_scalar_radians.v1' else EuclideanGeometry()
prior = StatePrior(**source['prior'], frame_id=state['frame'], units=state['units'], state_id=request['initial_state_id'])
results = []
for index, (batch, inputs) in enumerate(zip(source['batches'], resolved)):
    previous_id = prior.state_id
    predicted = predict(prior, LinearDynamics(batch['dynamics']['matrix'],
        batch['dynamics']['process_covariance'], inputs['dynamics_id']), batch['time'], geometry)
    diagnostics = {'status': 'prediction_only', 'innovation': [], 'innovation_covariance': [], 'residual': [], 'nis': None}
    if inputs['values']:
        observation = Observation(batch['time'], inputs['values'], batch['measurement_noise']['matrix'],
            inputs['frame'], inputs['units'], inputs['observation_id'], tuple(inputs['evidence_refs']))
        model = LinearObservation(inputs['matrix'], inputs['observation_model_id'],
            measurement_geometry=geometry, measurement_units=inputs['units'], measurement_frame_id=inputs['frame'])
        estimate = update(predicted, observation, model, geometry)
        diagnostics = {'status': 'updated', 'innovation': estimate.innovation.tolist(),
            'innovation_covariance': estimate.innovation_covariance.tolist(),
            'residual': estimate.residual.tolist(), 'nis': estimate.nis}
        prior = estimate.as_prior()
    else:
        prior = predicted
    results.append({'batch_index': index, 'configuration_id': inputs['configuration_id'],
        'configuration_ref': batch['configuration_ref'], 'epoch_index': inputs['epoch_index'],
        'time': prior.time, 'predecessor_state_id': previous_id, 'predicted_state_id': predicted.state_id,
        'state_id': prior.state_id, 'mean': prior.mean.tolist(), 'covariance': prior.covariance.tolist(),
        'diagnostics': diagnostics, 'observation_refs': inputs['evidence_refs'], 'observation_order': inputs['order']})
print(json.dumps({'schema': 'ciw.sensor-fusion-result.v1', 'initial_state_id': request['initial_state_id'],
    'state_contract': state, 'estimates': results, 'authority': request['authority']}, allow_nan=False))
'''


def algorithm_identity():
    """Replay binds the orchestration and contracts as well as the provider source."""
    files = (Path(contract.__file__), Path(__file__))
    content = b"\0".join(path.name.encode() + b"\0" + path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                         for path in files)
    return sha256(content).hexdigest()


def _request(source):
    resolved, previous, epoch = [], None, -1
    state = source["configuration"]["state"]
    from_time = source["prior"]["time"]
    for i, batch in enumerate(source["batches"]):
        inputs = contract.batch_inputs(source, i)
        configuration_id = contract.configuration_id(source["configuration"], inputs["profile"])
        epoch += configuration_id != previous
        previous = configuration_id
        resolved.append({**{k: inputs[k] for k in ("values", "matrix", "units", "order", "evidence_refs")},
            "frame": inputs["records"][0]["frame"] if inputs["records"] else state["frame"],
            "configuration_id": configuration_id, "epoch_index": epoch,
            "dynamics_id": digest({"state": state, "from_time": from_time, "to_time": batch["time"], "dynamics": batch["dynamics"]}),
            "observation_model_id": digest({"configuration_id": configuration_id, "channel_order": inputs["order"]}),
            "observation_id": digest({"time": batch["time"], "clock_id": state["clock_id"], "records": inputs["evidence_refs"],
                                      "measurement_noise": batch["measurement_noise"]})})
        from_time = batch["time"]
    return {"source": source, "resolved": resolved, "initial_state_id": contract.initial_state_id(source),
            "authority": deepcopy(contract.AUTHORITY)}


def _verification(bundle, reproduced):
    if canonical(bundle["steps"][0]["numerical_result"]) != canonical(reproduced["numerical_result"]):
        raise AdapterRefusal("FUSION_REPLAY_MISMATCH", "GSIE reproduction differs from retained fusion output")
    value = {"schema": VERIFY_SCHEMA, "subject_ref": bundle["bundle_digest"], "outcome": "passed",
             "independent": False, "method": "same_pinned_gsie_fresh_occurrence_reproduction",
             "runtime_digest": digest(bundle["runtimes"]), "reproduction": deepcopy(reproduced),
             "authority": deepcopy(contract.AUTHORITY)}
    value["verification_id"] = byte_digest(VERIFY_SCHEMA.encode() + b"\0" + canonical(value))
    return value


class SensorFusionWorkflow(DeclaredWorkflow):
    MAX_BYTES = contract.MAX_BYTES

    def __init__(self):
        self.kind, self.role, self.ROLES = "sensor-fusion", "gsie", {"gsie"}
        self.pin = PIN
        self.SOURCE_SCHEMA = contract.SOURCE_SCHEMA
        self.schema, self.operation = "ciw.sensor-fusion-session.v1", OPERATION

    def _source(self, raw):
        return contract.validate_source(raw)

    def _adapters(self, repositories, expected=None):
        if not isinstance(repositories, dict) or set(repositories) != self.ROLES:
            raise ValueError("Bind exactly the trusted GSIE provider checkout")
        retained = expected[self.role] if expected else {}
        adapter = PinnedSubprocessAdapter(repositories[self.role], PIN["revision"], PIN["module"], source_root=PIN["source_root"],
            expected_python_sha256=retained.get("python_sha256"), expected_python_version=retained.get("python_version"),
            expected_dependencies=retained.get("dependencies"), max_output_bytes=self.MAX_BYTES)
        runtime = self._runtime(adapter)
        if retained and self._runtime_projection(runtime) != self._runtime_projection(retained):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "Fusion orchestration or GSIE runtime identity changed")
        return adapter, runtime, None

    @staticmethod
    def _runtime(adapter):
        runtime = adapter.runtime_identity()
        if runtime["source_tree"] != SOURCE_TREE:
            raise AdapterRefusal("SOURCE_PIN_MISMATCH", "GSIE source tree differs from the declared capability")
        runtime["adapter_version"] += ";sensor-fusion:" + algorithm_identity()
        return runtime

    def _step(self, source, evidence_id, bound):
        adapter, runtime, _ = bound
        if self._runtime_projection(self._runtime(adapter)) != self._runtime_projection(runtime):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "Fusion runtime changed before execution")
        code, raw = adapter._run(_BOOTSTRAP, [str(adapter.source_root)], canonical(_request(source)))
        if self._runtime_projection(self._runtime(adapter)) != self._runtime_projection(runtime):
            raise AdapterRefusal("RUNTIME_PIN_MISMATCH", "Fusion runtime changed during execution")
        if code:
            raise AdapterRefusal("SENSOR_FUSION_REFUSED", "Pinned GSIE refused the declared fusion model or numerical domain")
        data = _json(raw)
        contract.validate_data(source, data)
        occurrence = "execution-" + uuid.uuid4().hex
        result = {"schema": RESULT_SCHEMA, "operation_id": OPERATION, "execution_ref": occurrence,
                  "input_refs": [evidence_id], "data": data, "authority": deepcopy(contract.AUTHORITY)}
        result["result_id"] = digest(result)
        numerical = {"operation_id": OPERATION, "data": deepcopy(data)}
        return {"runtime_ref": self.role, "operation_id": OPERATION, "execution_id": occurrence,
                "input_refs": [evidence_id], "request": deepcopy(source), "request_sha256": digest(source),
                "result": result, "result_sha256": digest(result), "result_id": result["result_id"],
                "numerical_result": numerical, "numerical_result_id": digest(numerical)}

    def _validate_step(self, step, source, evidence_id):
        _keys(step, {"runtime_ref", "operation_id", "execution_id", "input_refs", "request", "request_sha256",
                     "result", "result_sha256", "result_id", "numerical_result", "numerical_result_id"})
        if (step["runtime_ref"] != self.role or step["operation_id"] != OPERATION or step["input_refs"] != [evidence_id] or
                canonical(step["request"]) != canonical(source) or
                not isinstance(step["execution_id"], str) or not re.fullmatch(r"execution-[a-f0-9]{32}", step["execution_id"])):
            raise ValueError("Fusion step request, evidence or occurrence binding differs")
        result = step["result"]
        _keys(result, {"schema", "operation_id", "execution_ref", "input_refs", "data", "authority", "result_id"})
        contract.validate_data(source, result["data"])
        if (result["schema"] != RESULT_SCHEMA or result["operation_id"] != OPERATION or result["authority"] != contract.AUTHORITY or
                result["execution_ref"] != step["execution_id"] or result["input_refs"] != [evidence_id] or
                result["result_id"] != digest({k: v for k, v in result.items() if k != "result_id"}) or
                step["result_id"] != result["result_id"] or
                canonical(step["numerical_result"]) != canonical({"operation_id": OPERATION, "data": result["data"]})):
            raise ValueError("Fusion result binding or authority differs")
        for key, value in (("request_sha256", source), ("result_sha256", result), ("numerical_result_id", step["numerical_result"])):
            if step[key] != digest(value):
                raise ValueError("Fusion step content identity differs")

    def _check_verification(self, bundle, verification, source, evidence):
        _keys(verification, {"schema", "subject_ref", "outcome", "independent", "method", "runtime_digest",
                             "reproduction", "authority", "verification_id"})
        self._validate_step(verification["reproduction"], source, evidence)
        old, new = bundle["steps"][0], verification["reproduction"]
        if (old["execution_id"] == new["execution_id"] or old["result_id"] == new["result_id"] or
                canonical(verification) != canonical(_verification(bundle, new))):
            raise ValueError("Fusion reproduction must retain fresh occurrences and limited authority")
        _identity(verification, "verification_id")

    def _validate(self, bundle):
        raw = super()._validate(bundle)
        runtime = bundle["runtimes"][self.role]
        if (runtime["source_tree"] != SOURCE_TREE or not re.fullmatch(
                r"ciw-pinned-subprocess-v1;sensor-fusion:[a-f0-9]{64}", runtime["adapter_version"])):
            raise ValueError("Invalid retained fusion provider or orchestration identity")
        # Inspecting old artifacts does not require the current wrapper digest.
        # Re-execution compares it to the running code in _adapters.
        receipts = bundle.get("replay_receipts", [])
        if not isinstance(receipts, list) or len(receipts) > 1:
            raise ValueError("Require at most one fusion replay receipt per occurrence")
        source, evidence = self._source(raw), bundle["source"]["evidence"][0]["artifact_ref"]
        for receipt in receipts:
            _keys(receipt, {"schema", "source_bundle_digest", "replayed_bundle_digest", "numerical_match", "verification", "admission", "replay_id"})
            if (receipt["schema"] != "ciw.sensor-fusion-replay.v1" or receipt["replayed_bundle_digest"] != bundle["bundle_digest"] or
                    not isinstance(receipt["source_bundle_digest"], str) or
                    not re.fullmatch(r"sha256:[a-f0-9]{64}", receipt["source_bundle_digest"]) or
                    receipt["source_bundle_digest"] == bundle["bundle_digest"] or receipt["numerical_match"] is not True or
                    receipt["admission"] != "not_performed" or receipt["replay_id"] != digest({k: v for k, v in receipt.items() if k != "replay_id"})):
                raise ValueError("Fusion replay receipt commitment differs")
            verification = receipt["verification"]
            # A standalone receipt proves a retained binding; Workbench additionally
            # resolves its original bundle and compares the exact reproduction.
            _keys(verification, {"schema", "subject_ref", "outcome", "independent", "method", "runtime_digest", "reproduction", "authority", "verification_id"})
            if (verification["schema"] != VERIFY_SCHEMA or verification["subject_ref"] != receipt["source_bundle_digest"] or
                    verification["outcome"] != "passed" or verification["independent"] is not False or
                    verification["method"] != "same_pinned_gsie_fresh_occurrence_reproduction" or
                    verification["runtime_digest"] != digest(bundle["runtimes"]) or verification["authority"] != contract.AUTHORITY or
                    verification["reproduction"] != bundle["steps"][0]):
                raise ValueError("Fusion replay verification scope differs")
            self._validate_step(verification["reproduction"], source, evidence)
            _identity(verification, "verification_id")
        return raw

    def _execute(self, raw, bound):
        source, evidence = self._source(raw), byte_digest(raw)
        step = self._step(source, evidence, bound)
        bundle = {"schema": self.schema, "session_id": "session-" + uuid.uuid4().hex, "created_at": _now(),
                  "source": {"experiment_id": source["experiment_id"], "experiment_digest": digest(source),
                             "evidence": [{"artifact_ref": evidence, "sha256": evidence, "bytes_b64": base64.b64encode(raw).decode()}]},
                  "configuration": deepcopy(source["configuration"]), "runtimes": {self.role: deepcopy(bound[1])}, "steps": [step]}
        bundle["bundle_digest"] = _bundle_digest(bundle)
        bundle["verification"] = _verification(bundle, self._step(source, evidence, bound))
        self._validate(bundle)
        return bundle

    def replay_session(self, bundle, repositories):
        raw = self._validate(bundle)
        fresh = self._execute(raw, self._adapters(repositories, bundle["runtimes"]))
        receipt = {"schema": "ciw.sensor-fusion-replay.v1", "source_bundle_digest": bundle["bundle_digest"],
                   "replayed_bundle_digest": fresh["bundle_digest"], "numerical_match": True,
                   "verification": _verification(bundle, fresh["steps"][0]), "admission": "not_performed"}
        receipt["replay_id"] = digest(receipt)
        fresh["replay_receipts"] = [receipt]
        self._validate(fresh)
        return {"session": fresh, "replay_receipt": receipt}
