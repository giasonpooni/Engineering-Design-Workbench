"""Explicit linear coordinate transport; existing JSPT kernels own the arithmetic."""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re

import numpy as np

from . import sensor_fusion_contract as fusion
from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import _json
from .sensor_fusion_workflow import SensorFusionWorkflow
from .telemetry import _keys, byte_digest, canonical, digest

KIND = "sensor-fusion-transport"
OPERATION = "ciw.sensor-fusion-transport.v1"
SOURCE_SCHEMA = "ciw.sensor-fusion-transport-source.v1"
MAP_SCHEMA = "ciw.sensor-fusion-linear-map.v1"
PIN = {"revision": "d910f5a1d7f6dd5f2dd87dfca66990f714f97b18",
       "module": "sensitivity.affine", "source_root": "src"}
SOURCE_TREE = "5643cc8204b7aa6cbb73df6bf8984abdcec47d3b"
SOURCE_LIMIT = fusion.SOURCE_LIMIT
MAX_BYTES = fusion.MAX_BYTES
POLICY = {"map_semantics": "deterministic_invertible_linear_euclidean",
          "model_reconfiguration": "provider_transformed_f_q_h",
          "observation_coordinates": "unchanged", "clock": "unchanged",
          "map_uncertainty": "declared_zero", "cross_history_noise": "declared_independent",
          "state_admission": "not_performed"}
AUTHORITY = {**fusion.AUTHORITY, "coordinate_relation": "caller_declared",
             "transport": "pinned_jspt_linear_coordinate_computation"}
SELECTION_FIELDS = {"upstream_bundle_id", "upstream_result_id", "upstream_execution_id",
                    "upstream_numerical_result_id", "state_id", "batch_index"}


def algorithm_identity():
    return sha256(Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest()


def _content_ref(value):
    if not isinstance(value, str) or re.fullmatch(r"sha256:[a-f0-9]{64}", value) is None:
        raise ValueError("Require an exact content identity")


def _state(state):
    _keys(state, {"quantity_ids", "units", "frame", "geometry", "clock_id"})
    fusion.strings(state["quantity_ids"])
    n = len(state["quantity_ids"])
    if n > 16 or len(set(state["quantity_ids"])) != n:
        raise ValueError("Require 1..16 distinct target state coordinates")
    fusion.strings(state["units"], n)
    fusion.text(state["frame"])
    fusion.text(state["clock_id"])
    if state["geometry"] != "euclidean.v1":
        raise ValueError("Linear coordinate transport currently requires Euclidean geometry")
    return n


def validate_source(raw):
    if not isinstance(raw, bytes) or len(raw) > SOURCE_LIMIT:
        raise ValueError("Transport source exceeds the 256 KiB budget")
    source = _json(raw)
    canonical(source)
    _keys(source, {"schema", "experiment_id", "configuration", "selection", "transport", "continuation"})
    if source["schema"] != SOURCE_SCHEMA or canonical(source["configuration"]) != canonical(POLICY):
        raise ValueError("Require the declared linear coordinate transport scope")
    fusion.text(source["experiment_id"])
    selection = source["selection"]
    _keys(selection, SELECTION_FIELDS)
    for key in ("upstream_bundle_id", "upstream_result_id", "upstream_numerical_result_id", "state_id"):
        _content_ref(selection[key])
    if (not isinstance(selection["upstream_execution_id"], str) or
            re.fullmatch(r"execution-[a-f0-9]{32}", selection["upstream_execution_id"]) is None or
            type(selection["batch_index"]) is not int or not 0 <= selection["batch_index"] < 16):
        raise ValueError("Require an exact upstream execution and final batch selector")
    transport = source["transport"]
    _keys(transport, {"matrix", "target_state", "map_evidence_b64"})
    n = _state(transport["target_state"])
    fusion.matrix(transport["matrix"], n, n)
    fusion.retained_bytes(transport["map_evidence_b64"])
    try:
        condition = float(np.linalg.cond(np.asarray(transport["matrix"], dtype=float)))
    except np.linalg.LinAlgError as exc:
        raise ValueError("Coordinate-map condition could not be resolved") from exc
    if not np.isfinite(condition) or condition > 1e12:
        raise ValueError("Coordinate map must be invertible with condition number <= 1e12")
    continuation = source["continuation"]
    _keys(continuation, {"configuration", "batches"})
    if not isinstance(continuation["configuration"], dict):
        raise ValueError("Require a declared original-basis continuation configuration")
    origin = continuation["configuration"].get("state")
    if _state(origin) != n or origin["clock_id"] != transport["target_state"]["clock_id"]:
        raise ValueError("Coordinate transport preserves state dimension and clock")
    batches = continuation["batches"]
    if not isinstance(batches, list) or not batches or not isinstance(batches[0], dict) or "time" not in batches[0]:
        raise ValueError("Require future continuation batches in the original state basis")
    first = fusion.number(batches[0]["time"])
    with np.errstate(over="ignore"):
        dummy_time = float(np.nextafter(first, -np.inf))
    if not np.isfinite(dummy_time):
        raise ValueError("Continuation has no representable preceding timestamp")
    # A structural v1 check at source.add needs no upstream/runtime. prepare
    # replaces this placeholder with the exact selected final posterior.
    dummy = {"schema": fusion.SOURCE_SCHEMA, "experiment_id": source["experiment_id"],
             **deepcopy(continuation), "prior": {"time": dummy_time, "mean": [0] * n,
              "covariance": [[int(i == j) for j in range(n)] for i in range(n)]}}
    fusion.validate_source(canonical(dummy))
    return source


def prepare(source, upstream):
    """Bind the exact retained final posterior; callers cannot supply a new prior."""
    validate_source(canonical(source))
    raw = SensorFusionWorkflow()._validate(upstream)
    step, = upstream["steps"]
    data = step["result"]["data"]
    state = data["estimates"][-1]
    selection = source["selection"]
    expected = {"upstream_bundle_id": upstream["bundle_digest"], "upstream_result_id": step["result_id"],
                "upstream_execution_id": step["execution_id"], "upstream_numerical_result_id": step["numerical_result_id"],
                "state_id": state["state_id"], "batch_index": state["batch_index"]}
    if canonical(selection) != canonical(expected):
        raise ValueError("Select the exact retained final fusion posterior and its occurrences")
    if canonical(source["continuation"]["configuration"]["state"]) != canonical(data["state_contract"]):
        raise ValueError("Continuation model must use the selected upstream state basis")
    original = {"schema": fusion.SOURCE_SCHEMA, "experiment_id": source["experiment_id"],
                **deepcopy(source["continuation"]), "prior": {"time": state["time"],
                "mean": deepcopy(state["mean"]), "covariance": deepcopy(state["covariance"])}}
    fusion.validate_source(canonical(original))
    old_source = fusion.validate_source(raw)
    acquired, records = set(), set()
    for batch in old_source["batches"]:
        for observation in batch["observations"]:
            record_raw = fusion.retained_bytes(observation["record_b64"])
            acquired.add(_json(record_raw)["acquisition_id"])
            records.add(byte_digest(record_raw))
    for batch in original["batches"]:
        for observation in batch["observations"]:
            record_raw = fusion.retained_bytes(observation["record_b64"])
            if byte_digest(record_raw) in records or _json(record_raw)["acquisition_id"] in acquired:
                raise ValueError("Continuation cannot re-assimilate an upstream acquisition")
    return original


def map_identity(source):
    return digest({"schema": "ciw.sensor-fusion-linear-map-declaration.v1", "selection": source["selection"],
                   "matrix": source["transport"]["matrix"], "target_state": source["transport"]["target_state"],
                   "map_evidence_id": byte_digest(fusion.retained_bytes(source["transport"]["map_evidence_b64"]))})


def model_identity(map_id, model_ref):
    return digest({"schema": "ciw.transported-linear-model.v1", "map_id": map_id, "original_model_ref": model_ref})


_BOOTSTRAP = r'''
import json, sys
from copy import deepcopy
import numpy as np
sys.path.insert(0, sys.argv[1])
from sensitivity.affine import GaussianState, transform_state
from sensitivity.coordinates import AffineCoordinates, transform_jacobian, push_covariance, check_mean_fidelity
request = json.loads(sys.stdin.buffer.read())
source = deepcopy(request['original'])
t = np.asarray(request['matrix'], dtype=float)
n = len(source['prior']['mean'])
chart = AffineCoordinates(T=t, S=np.eye(n))
mapped = transform_state(GaussianState(source['prior']['mean'], source['prior']['covariance']), chart)
source['prior'] = {'time': source['prior']['time'], 'mean': mapped.mean.tolist(), 'covariance': mapped.covariance.tolist()}
source['configuration']['state'] = request['target_state']
def model_map(original, coordinate, name):
    original = np.asarray(original, dtype=float)
    # Invertibility alone does not prevent coefficient cancellation/underflow.
    with np.errstate(over='raise', invalid='raise', divide='raise', under='raise'):
        result = transform_jacobian(original, coordinate)
        inverse = AffineCoordinates(T=coordinate.T_inv, S=coordinate.S_inv)
        recovered = transform_jacobian(result, inverse)
    if not np.all(np.isfinite(result)): raise ValueError('Nonfinite transported model')
    for index in range(original.shape[1]):
        check_mean_fidelity(original[:, index], recovered[:, index],
            np.zeros((original.shape[0], original.shape[0])), name + ' column')
    return result.tolist()
for profile in source['configuration']['configurations']:
    for sensor in profile['sensors']:
        coordinate = AffineCoordinates(T=t, S=np.eye(len(sensor['matrix'])))
        sensor['matrix'] = model_map(sensor['matrix'], coordinate, 'H')
        sensor['model_ref'] = request['sensor_model_ids'][profile['name']][sensor['sensor_id']]
dynamics_chart = AffineCoordinates(T=t, S=t)
for index, batch in enumerate(source['batches']):
    dynamics = batch['dynamics']
    dynamics['matrix'] = model_map(dynamics['matrix'], dynamics_chart, 'F')
    dynamics['process_covariance'] = push_covariance(t, dynamics['process_covariance'], name='process covariance').tolist()
    dynamics['model_ref'] = request['dynamics_model_ids'][index]
print(json.dumps(source, allow_nan=False))
'''


def invoke(source, upstream, adapter):
    original = prepare(source, upstream)
    map_id = map_identity(source)
    request = {"original": original, "matrix": source["transport"]["matrix"],
               "target_state": source["transport"]["target_state"],
               "sensor_model_ids": {p["name"]: {s["sensor_id"]: model_identity(map_id, s["model_ref"])
                 for s in p["sensors"]} for p in original["configuration"]["configurations"]},
               "dynamics_model_ids": [model_identity(map_id, b["dynamics"]["model_ref"]) for b in original["batches"]]}
    adapter.runtime_identity()
    code, raw = adapter._run(_BOOTSTRAP, [str(adapter.source_root)], canonical(request))
    adapter.runtime_identity()
    if code:
        raise AdapterRefusal("FUSION_TRANSPORT_REFUSED", "Pinned JSPT refused the coordinate map or transported numerical model")
    generated = fusion.validate_source(canonical(_json(raw)))
    retained = canonical(generated)
    data = {"schema": MAP_SCHEMA, "source_state_id": source["selection"]["state_id"],
            "target_state": deepcopy(source["transport"]["target_state"]), "mapped_prior": deepcopy(generated["prior"]),
            "mapped_state_id": fusion.initial_state_id(generated), "continuation_source_b64": base64.b64encode(retained).decode(),
            "continuation_source_id": byte_digest(retained), "map_id": map_id}
    validate_transport(source, upstream, data)
    return data


def validate_transport(source, upstream, data):
    """Inspect retained semantic bindings without redoing provider arithmetic."""
    original = prepare(source, upstream)
    _keys(data, {"schema", "source_state_id", "target_state", "mapped_prior", "mapped_state_id",
                 "continuation_source_b64", "continuation_source_id", "map_id"})
    if (data["schema"] != MAP_SCHEMA or data["source_state_id"] != source["selection"]["state_id"] or
            canonical(data["target_state"]) != canonical(source["transport"]["target_state"]) or data["map_id"] != map_identity(source)):
        raise ValueError("Transport declaration, origin state or target binding differs")
    encoded = data["continuation_source_b64"]
    if not isinstance(encoded, str) or len(encoded) > 4 * SOURCE_LIMIT // 3 + 4:
        raise ValueError("Transported source exceeds byte budget")
    raw = base64.b64decode(encoded, validate=True)
    if base64.b64encode(raw).decode() != encoded or data["continuation_source_id"] != byte_digest(raw):
        raise ValueError("Transported continuation source commitment differs")
    generated = fusion.validate_source(raw)
    if canonical(generated) != raw:
        raise ValueError("Require the exact canonical transported source bytes")
    if (canonical(data["mapped_prior"]) != canonical(generated["prior"]) or
            generated["prior"]["time"] != original["prior"]["time"] or
            data["mapped_state_id"] != fusion.initial_state_id(generated)):
        raise ValueError("Transported prior and child initial-state identity differ")
    expected = deepcopy(original)
    expected["prior"] = deepcopy(generated["prior"])
    expected["configuration"]["state"] = deepcopy(data["target_state"])
    # Measurements, R, calibration, active sensors, times and assumptions remain
    # exact; only these listed provider-computed numerical outputs may differ.
    try:
        for p, mapped_p in zip(expected["configuration"]["configurations"], generated["configuration"]["configurations"], strict=True):
            for sensor, mapped_sensor in zip(p["sensors"], mapped_p["sensors"], strict=True):
                sensor["matrix"] = deepcopy(mapped_sensor["matrix"])
                sensor["model_ref"] = model_identity(data["map_id"], sensor["model_ref"])
        for batch, mapped_batch in zip(expected["batches"], generated["batches"], strict=True):
            batch["dynamics"]["matrix"] = deepcopy(mapped_batch["dynamics"]["matrix"])
            batch["dynamics"]["process_covariance"] = deepcopy(mapped_batch["dynamics"]["process_covariance"])
            batch["dynamics"]["model_ref"] = model_identity(data["map_id"], batch["dynamics"]["model_ref"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Transported model structure differs from its declared source") from exc
    if canonical(generated) != canonical(expected):
        raise ValueError("Transport may change only the declared prior, state coordinates and F/Q/H")
