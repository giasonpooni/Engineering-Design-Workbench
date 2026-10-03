"""Bounded nonlinear estimation declarations; scientific providers own execution."""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re

from . import sensor_fusion_contract as fusion
from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import _json
from .telemetry import _keys, byte_digest, canonical, digest

SOURCE_SCHEMA = "ciw.sensor-fusion-ekf-source.v1"
DATA_SCHEMA = "ciw.sensor-fusion-ekf-result.v1"
METHOD = "jspt.analytic-gsie.error-state-ekf.v1"
SOURCE_LIMIT, MAX_BYTES = fusion.SOURCE_LIMIT, fusion.MAX_BYTES
PIN = {"revision": "5241eee6dab434533bdf0cf0e824bc43b4a79831",
       "module": "geometric_state_inference.contracts", "source_root": "src"}
SOURCE_TREE = "375c031c07592d5bcb1d224780f18ceb886df4a1"
JSPT_PIN = {"revision": "d910f5a1d7f6dd5f2dd87dfca66990f714f97b18",
            "module": "sensitivity.reference_models", "source_root": "src"}
JSPT_TREE = "5643cc8204b7aa6cbb73df6bf8984abdcec47d3b"
AUTHORITY = {**fusion.AUTHORITY, "approximation": "local_first_order_gaussian",
             "model_parameters": "caller_declared_deterministic"}
PREDICTION_FIELDS = {"dynamics_center", "dynamics_value", "dynamics_jacobian",
                     "predicted_mean", "predicted_covariance", "kernel_prediction"}
LINEARIZATION_FIELDS = PREDICTION_FIELDS | {"observation_value", "observation_jacobian",
    "correction", "post_observation_value", "kernel_update"}


def algorithm_identity():
    files = (Path(__file__), Path(__file__).with_name("sensor_fusion_ekf_kernel.py"))
    return sha256(b"\0".join(p.name.encode() + b"\0" +
        p.read_text(encoding="utf-8").replace("\r\n", "\n").encode() for p in files)).hexdigest()


def _ref(value):
    if not isinstance(value, str) or re.fullmatch(r"sha256:[a-f0-9]{64}", value) is None:
        raise ValueError("Require an exact content identity")


def _model(model, n, m, input_units, output_units):
    _keys(model, {"family", "parameters", "evidence_b64"})
    fusion.retained_bytes(model["evidence_b64"])
    family, parameters = model["family"], model["parameters"]
    if family == "affine.v1":
        _keys(parameters, {"matrix", "offset"})
        fusion.matrix(parameters["matrix"], m, n)
        fusion.vector(parameters["offset"], m)
    elif family == "quadratic.v1":
        _keys(parameters, {"hessian", "gradient"})
        if m != 1:
            raise ValueError("A quadratic reference map has exactly one output")
        fusion.matrix(parameters["hessian"], n, n)
        if parameters["hessian"] != [list(row) for row in zip(*parameters["hessian"])]:
            raise ValueError("Quadratic Hessian must be exactly symmetric; no repair")
        fusion.vector(parameters["gradient"], n)
    elif family == "componentwise-exp.v1":
        _keys(parameters, set())
        if m != n or input_units != ["1"] * n or output_units != ["1"] * n:
            raise ValueError("Exponential reference maps require dimensionless input and output coordinates")
    elif family == "planar-range.v1":
        _keys(parameters, {"position_matrix", "anchor", "minimum_range"})
        fusion.matrix(parameters["position_matrix"], 2, n)
        fusion.vector(parameters["anchor"], 2)
        if m != 1 or fusion.number(parameters["minimum_range"]) <= 0 or output_units != ["m"]:
            raise ValueError("Planar range requires one metre output and a positive excluded-domain radius")
        selected = []
        for row in parameters["position_matrix"]:
            if row.count(1) != 1 or any(value not in (0, 1) for value in row):
                raise ValueError("Range position axes must be explicit coordinate selectors")
            index = row.index(1)
            if input_units[index] != "m":
                raise ValueError("Range position axes must be in metres")
            selected.append(index)
        if len(set(selected)) != 2:
            raise ValueError("Range requires two distinct Cartesian position axes")
    else:
        raise ValueError("Unknown nonlinear model family; arbitrary code is not a declared capability")


def _linear_source(source):
    """Reuse the verified measurement/time/noise contract, with shape placeholders."""
    result = deepcopy(source)
    result["schema"] = fusion.SOURCE_SCHEMA
    configuration = result["configuration"]
    configuration.pop("method")
    n = len(configuration["state"]["quantity_ids"])
    for profile in configuration["configurations"]:
        for sensor in profile["sensors"]:
            sensor.pop("model")
            sensor["matrix"] = [[0] * n for _ in sensor["quantity_ids"]]
    for batch in result["batches"]:
        batch["dynamics"].pop("model")
        batch["dynamics"]["matrix"] = [[int(i == j) for j in range(n)] for i in range(n)]
    return result


def validate_source(raw):
    if not isinstance(raw, bytes) or len(raw) > SOURCE_LIMIT:
        raise ValueError("EKF source exceeds the 256 KiB budget")
    try:
        source = _json(raw)
        canonical(source)
        _keys(source, {"schema", "experiment_id", "configuration", "prior", "batches"})
        configuration = source["configuration"]
        _keys(configuration, {"state", "configurations", "noise_policy", "method"})
        if source["schema"] != SOURCE_SCHEMA or configuration["method"] != METHOD:
            raise ValueError("Require the declared analytic error-state EKF method")
        state = configuration["state"]
        if state["geometry"] != "euclidean.v1":
            raise ValueError("This EKF requires Euclidean state and measurement residuals")
        for profile in configuration["configurations"]:
            for sensor in profile["sensors"]:
                _keys(sensor, {"sensor_id", "quantity_ids", "units", "frame", "model", "model_ref", "calibration"})
        for batch in source["batches"]:
            _keys(batch["dynamics"], {"model", "process_covariance", "model_ref"})
        # The existing contract checks exact keys and all inherited scientific domains.
        fusion.validate_source(canonical(_linear_source(source)))
        n = len(state["quantity_ids"])
        for profile in configuration["configurations"]:
            for sensor in profile["sensors"]:
                _model(sensor["model"], n, len(sensor["quantity_ids"]), state["units"], sensor["units"])
        for batch in source["batches"]:
            _model(batch["dynamics"]["model"], n, n, state["units"], state["units"])
        return source
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed declared EKF source") from exc


def configuration_id(configuration, profile):
    return digest({"schema": "ciw.sensor-fusion-ekf-configuration.v1", "state": configuration["state"],
                   "method": METHOD, "noise_policy": configuration["noise_policy"], "profile": profile})


def initial_state_id(source):
    return digest({"schema": "ciw.sensor-fusion-ekf-prior.v1", "method": METHOD,
                   "state": source["configuration"]["state"], "prior": source["prior"]})


def batch_inputs(source, index):
    inputs = fusion.batch_inputs(_linear_source(source), index)
    inputs["profile"] = next(p for p in source["configuration"]["configurations"]
                             if p["name"] == source["batches"][index]["configuration_ref"])
    inputs["evidence_refs"] = list(dict.fromkeys(inputs["evidence_refs"] + [
        byte_digest(fusion.retained_bytes(s["model"]["evidence_b64"]))
        for s in inputs["profile"]["sensors"] if s["sensor_id"] in {r["sensor_id"] for r in inputs["records"]}]))
    return inputs


def _request(source):
    resolved, previous, epoch = [], None, -1
    for index, batch in enumerate(source["batches"]):
        inputs = batch_inputs(source, index)
        identity = configuration_id(source["configuration"], inputs["profile"])
        epoch += identity != previous
        previous = identity
        resolved.append({**inputs, "configuration_id": identity, "epoch_index": epoch, "batch_id": digest(batch)})
    return {"source": source, "resolved": resolved, "initial_state_id": initial_state_id(source),
            "authority": deepcopy(AUTHORITY)}


def state_identity(source, index, phase, predecessor, mean, covariance, linearization):
    batch = source["batches"][index]
    inputs = batch_inputs(source, index)
    return digest({"schema": "ciw.sensor-fusion-ekf-state.v1", "phase": phase, "method": METHOD,
        "state_contract": source["configuration"]["state"], "batch_id": digest(batch),
        "configuration_id": configuration_id(source["configuration"], inputs["profile"]),
        "predecessor_state_id": predecessor, "time": batch["time"], "mean": mean,
        "covariance": covariance, "linearization": linearization})


def invoke(source, gsie_adapter, jspt_adapter):
    from .sensor_fusion_ekf_kernel import BOOTSTRAP
    for adapter in (gsie_adapter, jspt_adapter):
        adapter.runtime_identity()
    code, raw = gsie_adapter._run(BOOTSTRAP, [str(gsie_adapter.source_root), str(jspt_adapter.source_root)],
                                  canonical(_request(source)))
    for adapter in (gsie_adapter, jspt_adapter):
        adapter.runtime_identity()
    if code:
        raise AdapterRefusal("SENSOR_FUSION_EKF_REFUSED", "Pinned model evaluation or error-state filtering refused the numerical domain")
    data = _json(raw)
    validate_data(source, data)
    return data


def _kernel(kernel, n):
    _keys(kernel, {"state_id", "mean", "covariance", "replay"})
    _ref(kernel["state_id"])
    fusion.vector(kernel["mean"], n)
    fusion.matrix(kernel["covariance"], n, n, True)
    replay = kernel["replay"]
    if not isinstance(replay, dict) or replay.get("schema") != "geometric-state-inference.replay.v1":
        raise ValueError("Require the retained inner GSIE linear subproblem")
    expected = byte_digest(b"geometric-state-inference.state-transition.v1\0" + canonical({
        "configuration": replay, "mean": kernel["mean"], "covariance": kernel["covariance"]}))
    if kernel["state_id"] != expected:
        raise ValueError("Inner numerical state identity differs from its retained linear subproblem")


def _prior(prior, n, time, covariance, state, prediction=None):
    _keys(prior, {"time", "mean", "covariance", "frame_id", "units", "state_id", "dynamics_model_id",
                  "predecessor_state_id", "operation_ref", "replay"})
    fusion.vector(prior["mean"], n)
    fusion.matrix(prior["covariance"], n, n, True)
    fusion.number(prior["time"])
    _ref(prior["state_id"])
    if (prior["time"] != time or prior["mean"] != [0] * n or prior["covariance"] != covariance or
            prior["units"] != state["units"] or prior["frame_id"] != state["frame"]):
        raise ValueError("Inner error-state prior must retain zero mean and the exact outer covariance and time")
    if prediction is None:
        if any(prior[k] is not None for k in ("dynamics_model_id", "predecessor_state_id", "operation_ref", "replay")):
            raise ValueError("Initial error prior cannot retain an undeclared predecessor computation")
    elif (prior["state_id"] != prediction["state_id"] or prior["replay"] != prediction["replay"] or
          prior["dynamics_model_id"] != prediction["replay"]["dynamics"]["model_id"] or
          prior["predecessor_state_id"] != prediction["replay"]["prior"]["state_id"] or
          prior["operation_ref"] != "geometric-state-inference.predict.v1"):
        raise ValueError("The update must consume the exact retained GSIE error-state prediction")


def validate_data(source, data):
    """Check retained numeric domains and semantic bindings, without model execution."""
    _keys(data, {"schema", "method", "initial_state_id", "state_contract", "estimates", "authority"})
    state = source["configuration"]["state"]
    if (data["schema"] != DATA_SCHEMA or data["method"] != METHOD or data["authority"] != AUTHORITY or
            data["state_contract"] != state or data["initial_state_id"] != initial_state_id(source)):
        raise ValueError("EKF method, state or limited authority differs")
    # Reuse existing result shape, covariance, diagnostics and evidence checks.
    projected_source = _linear_source(source)
    projected = deepcopy(data)
    projected.pop("method")
    projected.update(schema=fusion.DATA_SCHEMA, authority=fusion.AUTHORITY,
                     initial_state_id=fusion.initial_state_id(projected_source))
    n = len(state["quantity_ids"])
    if not isinstance(data["estimates"], list) or len(data["estimates"]) != len(source["batches"]):
        raise ValueError("EKF result must retain exactly one estimate per declared batch")
    previous_mean, previous_covariance, previous_time = (source["prior"][k] for k in ("mean", "covariance", "time"))
    predecessor = data["initial_state_id"]
    for index, (batch, estimate) in enumerate(zip(source["batches"], data["estimates"], strict=True)):
        _keys(estimate, {"batch_index", "configuration_id", "configuration_ref", "epoch_index", "time", "predecessor_state_id",
                         "predicted_state_id", "state_id", "mean", "covariance", "diagnostics", "observation_refs",
                         "observation_order", "linearization"})
        if estimate["predecessor_state_id"] != predecessor:
            raise ValueError("The nonlinear state chain must start at the exact declared prior")
        fusion.vector(estimate["mean"], n)
        fusion.matrix(estimate["covariance"], n, n, True)
        linearization = estimate["linearization"]
        _keys(linearization, LINEARIZATION_FIELDS)
        inputs = batch_inputs(source, index)
        m = len(inputs["values"])
        for key in ("dynamics_center", "dynamics_value", "predicted_mean", "correction"):
            fusion.vector(linearization[key], n)
        fusion.matrix(linearization["dynamics_jacobian"], n, n)
        fusion.matrix(linearization["predicted_covariance"], n, n, True)
        for key in ("observation_value", "post_observation_value"):
            fusion.vector(linearization[key], m)
        fusion.matrix(linearization["observation_jacobian"], m, n)
        if (linearization["dynamics_center"] != previous_mean or
                linearization["dynamics_value"] != linearization["predicted_mean"]):
            raise ValueError("Dynamics linearization must use the exact preceding posterior center")
        prediction = linearization["kernel_prediction"]
        _kernel(prediction, n)
        replay = prediction["replay"]
        _keys(replay, {"schema", "operation_ref", "prior", "time", "dynamics", "state_geometry"})
        _prior(replay["prior"], n, previous_time, previous_covariance, state)
        _keys(replay["dynamics"], {"matrix", "process_covariance", "model_id"})
        fusion.number(replay["time"])
        fusion.matrix(replay["dynamics"]["matrix"], n, n)
        fusion.matrix(replay["dynamics"]["process_covariance"], n, n, True)
        _ref(replay["dynamics"]["model_id"])
        error_prior_id = digest({"schema": "ciw.sensor-fusion-ekf-error-prior.v1", "phase": "prediction-prior",
            "method": METHOD, "predecessor_state_id": predecessor, "batch_id": digest(batch)})
        dynamics_id = digest({"schema": "ciw.sensor-fusion-ekf-linearized-dynamics.v1",
            "predecessor_state_id": predecessor, "batch_id": digest(batch),
            "center": linearization["dynamics_center"], "model": batch["dynamics"]})
        if (replay["operation_ref"] != "geometric-state-inference.predict.v1" or replay["time"] != batch["time"] or
                replay["state_geometry"] != "euclidean.v1" or prediction["mean"] != [0] * n or
                prediction["covariance"] != linearization["predicted_covariance"] or
                replay["dynamics"]["matrix"] != linearization["dynamics_jacobian"] or
                replay["dynamics"]["process_covariance"] != batch["dynamics"]["process_covariance"] or
                replay["prior"]["state_id"] != error_prior_id or replay["dynamics"]["model_id"] != dynamics_id):
            raise ValueError("Retained prediction kernel must consume the declared Jacobian and Q")
        prediction_fields = {k: linearization[k] for k in PREDICTION_FIELDS}
        expected_prediction = state_identity(source, index, "prediction", estimate["predecessor_state_id"],
            linearization["predicted_mean"], linearization["predicted_covariance"], prediction_fields)
        if estimate["predicted_state_id"] != expected_prediction or estimate["predicted_state_id"] == prediction["state_id"]:
            raise ValueError("Actual predicted state must have its own nonlinear numerical identity")
        diagnostics = estimate["diagnostics"]
        _keys(diagnostics, {"status", "innovation", "innovation_covariance", "residual", "linearized_residual", "nis"})
        fusion.vector(diagnostics["linearized_residual"], m)
        if m:
            update = linearization["kernel_update"]
            _kernel(update, n)
            replay = update["replay"]
            _keys(replay, {"schema", "operation_ref", "prior", "observation", "model", "state_geometry", "noise_policy"})
            _prior(replay["prior"], n, batch["time"], linearization["predicted_covariance"], state, prediction)
            _keys(replay["observation"], {"time", "values", "covariance", "frame_id", "units", "observation_id", "evidence_refs"})
            _keys(replay["model"], {"matrix", "model_id", "measurement_geometry", "measurement_units", "measurement_frame_id"})
            fusion.number(replay["observation"]["time"])
            fusion.vector(replay["observation"]["values"], m)
            fusion.matrix(replay["observation"]["covariance"], m, m, True)
            fusion.matrix(replay["model"]["matrix"], m, n)
            observation_id = digest({"schema": "ciw.sensor-fusion-ekf-linearized-observation.v1",
                "batch_id": digest(batch), "predecessor_state_id": estimate["predicted_state_id"],
                "values": inputs["values"], "observation_value": linearization["observation_value"],
                "innovation": diagnostics["innovation"]})
            observation_model_id = digest({"schema": "ciw.sensor-fusion-ekf-linearized-observation-model.v1",
                "batch_id": digest(batch), "configuration_id": estimate["configuration_id"],
                "predecessor_state_id": estimate["predicted_state_id"], "matrix": linearization["observation_jacobian"]})
            if (replay["operation_ref"] != "geometric-state-inference.update.v1" or replay["state_geometry"] != "euclidean.v1" or
                    replay["noise_policy"] != "measurement_independent_of_prior" or
                    replay["observation"]["values"] != diagnostics["innovation"] or
                    replay["observation"]["time"] != batch["time"] or
                    replay["observation"]["covariance"] != batch["measurement_noise"]["matrix"] or
                    replay["observation"]["units"] != inputs["units"] or replay["observation"]["frame_id"] != inputs["records"][0]["frame"] or
                    replay["observation"]["evidence_refs"] != inputs["evidence_refs"] or
                    replay["model"]["matrix"] != linearization["observation_jacobian"] or
                    replay["model"]["measurement_units"] != inputs["units"] or
                    replay["model"]["measurement_frame_id"] != inputs["records"][0]["frame"] or
                    replay["model"]["measurement_geometry"] != "euclidean.v1" or
                    update["mean"] != linearization["correction"] or update["covariance"] != estimate["covariance"] or
                    replay["observation"]["observation_id"] != observation_id or replay["model"]["model_id"] != observation_model_id):
                raise ValueError("Retained joint update kernel must consume the declared innovation, Jacobian and R")
            for value in (replay["model"]["model_id"], replay["observation"]["observation_id"]):
                _ref(value)
            if (estimate["state_id"] != state_identity(source, index, "update", estimate["predicted_state_id"],
                    estimate["mean"], estimate["covariance"], linearization) or estimate["state_id"] == update["state_id"]):
                raise ValueError("Actual posterior must have its own nonlinear numerical identity")
            if (estimate["mean"] != [a + b for a, b in zip(linearization["predicted_mean"], linearization["correction"])] or
                    diagnostics["innovation"] != [a - b for a, b in zip(inputs["values"], linearization["observation_value"])] or
                    diagnostics["residual"] != [a - b for a, b in zip(inputs["values"], linearization["post_observation_value"])]):
                raise ValueError("Retained state correction, innovation or nonlinear residual differs from its declared operands")
        elif (linearization["kernel_update"] is not None or linearization["correction"] != [0] * n or
                estimate["mean"] != linearization["predicted_mean"] or estimate["covariance"] != linearization["predicted_covariance"]):
            raise ValueError("A prediction-only batch cannot retain a correction or measurement kernel")
        item = projected["estimates"][index]
        item.pop("linearization")
        item["diagnostics"].pop("linearized_residual")
        old_inputs = fusion.batch_inputs(projected_source, index)
        item["configuration_id"] = fusion.configuration_id(projected_source["configuration"], old_inputs["profile"])
        item["observation_refs"] = old_inputs["evidence_refs"]
        if index == 0:
            item["predecessor_state_id"] = projected["initial_state_id"]
        if (estimate["configuration_id"] != configuration_id(source["configuration"], inputs["profile"]) or
                estimate["observation_refs"] != inputs["evidence_refs"]):
            raise ValueError("Nonlinear model configuration or evidence linkage differs")
        previous_mean, previous_covariance, previous_time = estimate["mean"], estimate["covariance"], batch["time"]
        predecessor = estimate["state_id"]
    fusion.validate_data(projected_source, projected)
