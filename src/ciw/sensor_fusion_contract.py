"""Bounded, declarative fusion contracts. Validation never computes an estimate."""
from __future__ import annotations

import base64
import math
import re

import numpy as np

from .adapters.subprocess import _json
from .core.covariance import _validate_matrix
from .telemetry import _keys, byte_digest, canonical, digest

SOURCE_SCHEMA = "ciw.sensor-fusion-source.v1"
DATA_SCHEMA = "ciw.sensor-fusion-result.v1"
SOURCE_LIMIT = 262144
MAX_BYTES = 4 * 1024 * 1024
AUTHORITY = {"sensor_fusion": "declared_model_candidate", "state_admission": "not_performed",
             "physical_validation": "not_established", "observability": "not_evaluated",
             "hardware_actuation": "not_performed"}
METHODS = {"euclidean.v1": "gsie.linear-gaussian.v1",
           "so2_scalar_radians.v1": "gsie.scalar-so2-local-gaussian.v1"}


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("Require bounded nonempty text")


def number(value):
    if type(value) not in (int, float):
        raise ValueError("Require finite JSON numbers, not booleans or strings")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError("Number exceeds float64") from exc
    if not math.isfinite(result) or (type(value) is int and int(result) != value):
        raise ValueError("Number must be finite and exactly representable in float64")
    return result


def strings(value, count=None):
    if not isinstance(value, list) or not value or (count is not None and len(value) != count):
        raise ValueError("Require nonempty ordered text arrays with declared dimensions")
    for item in value:
        text(item)


def references(value):
    strings(value)
    if len(value) > 32 or len(set(value)) != len(value) or any(
        re.fullmatch(r"sha256:[a-f0-9]{64}", item) is None for item in value
    ):
        raise ValueError("Require distinct bounded evidence content references")


def vector(value, n):
    if not isinstance(value, list) or len(value) != n:
        raise ValueError("Vector dimension differs from its declared order")
    for item in value:
        number(item)


def matrix(value, rows, columns, covariance=False):
    if not isinstance(value, list) or len(value) != rows:
        raise ValueError("Matrix dimensions differ from the declared order")
    for row in value:
        vector(row, columns)
    if covariance:
        if value != [list(row) for row in zip(*value)]:
            raise ValueError("Covariance must be exactly symmetric; no repair")
        _validate_matrix(value, rows)


def retained_bytes(encoded):
    if not isinstance(encoded, str) or len(encoded) > 32768:
        raise ValueError("Require bounded retained base64 evidence bytes")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("Invalid base64 evidence") from exc
    if not raw or base64.b64encode(raw).decode() != encoded:
        raise ValueError("Require nonempty canonical base64 evidence")
    return raw


def configuration_id(configuration, profile):
    return digest({"schema": "ciw.sensor-fusion-configuration.v1", "state": configuration["state"],
                   "noise_policy": configuration["noise_policy"], "profile": profile})


def initial_state_id(source):
    return digest({"schema": "ciw.sensor-fusion-prior.v1", "state": source["configuration"]["state"],
                   "prior": source["prior"]})


def batch_inputs(source, index):
    """Resolve exact retained bytes and channel order; never infer a sensor model."""
    batch = source["batches"][index]
    profile = next(p for p in source["configuration"]["configurations"]
                   if p["name"] == batch["configuration_ref"])
    sensors = {s["sensor_id"]: s for s in profile["sensors"]}
    records, rows, units, order, refs = [], [], [], [], []
    for observation in batch["observations"]:
        raw = retained_bytes(observation["record_b64"])
        record = _json(raw)
        sensor = sensors[observation["sensor_id"]]
        records.append(record)
        rows.extend(sensor["matrix"])
        units.extend(sensor["units"])
        order.extend(sensor["sensor_id"] + "/" + q for q in sensor["quantity_ids"])
        refs.extend((byte_digest(raw), byte_digest(retained_bytes(record["raw_evidence_b64"])),
                     byte_digest(retained_bytes(sensor["calibration"]["artifact_b64"]))))
    return {"profile": profile, "records": records, "matrix": rows, "units": units,
            "order": order, "evidence_refs": list(dict.fromkeys(refs)),
            "values": [value for r in records for value in r["values"]]}


def validate_source(raw):
    if not isinstance(raw, bytes) or len(raw) > SOURCE_LIMIT:
        raise ValueError("Fusion source exceeds the 256 KiB budget")
    source = _json(raw)
    canonical(source)
    _keys(source, {"schema", "experiment_id", "configuration", "prior", "batches"})
    if source["schema"] != SOURCE_SCHEMA:
        raise ValueError("Unsupported sensor-fusion source schema")
    text(source["experiment_id"])
    configuration = source["configuration"]
    _keys(configuration, {"state", "configurations", "noise_policy"})
    state = configuration["state"]
    _keys(state, {"quantity_ids", "units", "frame", "geometry", "clock_id"})
    strings(state["quantity_ids"])
    n = len(state["quantity_ids"])
    if n > 16 or len(set(state["quantity_ids"])) != n:
        raise ValueError("Require 1..16 distinct ordered state quantities")
    strings(state["units"], n)
    for key in ("frame", "clock_id"):
        text(state[key])
    if not isinstance(state["geometry"], str) or state["geometry"] not in METHODS:
        raise ValueError("Unsupported filter geometry; bind a declared capability")
    angle = state["geometry"] == "so2_scalar_radians.v1"
    if angle and (n != 1 or state["units"] != ["rad"]):
        raise ValueError("Scalar SO2 requires one angle in radians")
    noise = configuration["noise_policy"]
    _keys(noise, {"prior_measurement_crosscovariance", "process_measurement_crosscovariance", "process_prior_crosscovariance", "across_batches", "evidence_refs"})
    if (noise["prior_measurement_crosscovariance"] != "declared_zero" or
            noise["process_measurement_crosscovariance"] != "declared_zero" or
            noise["process_prior_crosscovariance"] != "declared_zero" or
            noise["across_batches"] != "declared_independent"):
        raise ValueError("This GSIE profile requires explicit prior/process and temporal noise independence")
    references(noise["evidence_refs"])
    profiles = configuration["configurations"]
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 16:
        raise ValueError("Require 1..16 named configuration profiles")
    names = []
    for profile in profiles:
        _keys(profile, {"name", "sensors"})
        text(profile["name"])
        names.append(profile["name"])
        if not isinstance(profile["sensors"], list) or not 1 <= len(profile["sensors"]) <= 16:
            raise ValueError("Require 1..16 declared sensor adapters per configuration")
        ids = []
        for sensor in profile["sensors"]:
            _keys(sensor, {"sensor_id", "quantity_ids", "units", "frame", "matrix", "model_ref", "calibration"})
            text(sensor["sensor_id"])
            if "/" in sensor["sensor_id"]:
                raise ValueError("Sensor IDs cannot contain channel separators")
            ids.append(sensor["sensor_id"])
            strings(sensor["quantity_ids"])
            m = len(sensor["quantity_ids"])
            if m > 16 or len(set(sensor["quantity_ids"])) != m or any("/" in q for q in sensor["quantity_ids"]):
                raise ValueError("Require distinct bounded measurement quantities without separators")
            strings(sensor["units"], m)
            text(sensor["frame"])
            text(sensor["model_ref"])
            matrix(sensor["matrix"], m, n)
            if angle and (sensor["matrix"] != [[1]] or sensor["units"] != ["rad"]):
                raise ValueError("Scalar SO2 requires identity H and angular observations")
            calibration = sensor["calibration"]
            _keys(calibration, {"artifact_b64", "valid_interval", "claim_scope"})
            retained_bytes(calibration["artifact_b64"])
            vector(calibration["valid_interval"], 2)
            if calibration["valid_interval"][0] >= calibration["valid_interval"][1]:
                raise ValueError("Calibration validity interval must increase")
            if calibration["claim_scope"] != "caller_declared_not_verified":
                raise ValueError("Calibration lineage is caller-declared, not physically verified")
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate sensor adapter IDs")
    if len(set(names)) != len(names):
        raise ValueError("Duplicate configuration names")
    prior = source["prior"]
    _keys(prior, {"time", "mean", "covariance"})
    number(prior["time"])
    vector(prior["mean"], n)
    matrix(prior["covariance"], n, n, True)
    if angle and not -math.pi <= prior["mean"][0] < math.pi:
        raise ValueError("Initial SO2 mean must be in its declared principal angle chart")
    batches = source["batches"]
    if not isinstance(batches, list) or not 1 <= len(batches) <= 16:
        raise ValueError("Require 1..16 strictly forward fusion batches")
    time, consumed, acquisitions = prior["time"], set(), set()
    for i, batch in enumerate(batches):
        _keys(batch, {"time", "configuration_ref", "dynamics", "observations", "measurement_noise"})
        number(batch["time"])
        if batch["time"] <= time:
            raise ValueError("Batch times must advance strictly; delayed observations require a separate capability")
        time = batch["time"]
        if batch["configuration_ref"] not in names:
            raise ValueError("Unknown configuration reference")
        dynamics = batch["dynamics"]
        _keys(dynamics, {"matrix", "process_covariance", "model_ref"})
        text(dynamics["model_ref"])
        matrix(dynamics["matrix"], n, n)
        matrix(dynamics["process_covariance"], n, n, True)
        if angle and dynamics["matrix"] != [[1]]:
            raise ValueError("Scalar SO2 requires identity dynamics")
        observations = batch["observations"]
        if not isinstance(observations, list) or len(observations) > 16:
            raise ValueError("Require a bounded sensor observation batch")
        profile = next(p for p in profiles if p["name"] == batch["configuration_ref"])
        sensors = {s["sensor_id"]: s for s in profile["sensors"]}
        seen, frames = set(), set()
        for observation in observations:
            _keys(observation, {"sensor_id", "record_b64"})
            sensor_id = observation["sensor_id"]
            if not isinstance(sensor_id, str) or sensor_id not in sensors or sensor_id in seen:
                raise ValueError("Unknown or duplicate active sensor")
            seen.add(sensor_id)
            record_raw = retained_bytes(observation["record_b64"])
            record_id = byte_digest(record_raw)
            if record_id in consumed:
                raise ValueError("Duplicate evidence cannot be assimilated twice")
            consumed.add(record_id)
            record = _json(record_raw)
            _keys(record, {"schema", "sensor_id", "acquisition_id", "time", "clock_id", "quantity_ids", "units", "frame", "values", "calibration_ref", "raw_evidence_b64"})
            text(record["acquisition_id"])
            if record["acquisition_id"] in acquisitions:
                raise ValueError("Duplicate acquisition cannot be assimilated twice")
            acquisitions.add(record["acquisition_id"])
            sensor = sensors[sensor_id]
            if record["schema"] != "ciw.fusion-observation.v1" or record["sensor_id"] != sensor_id:
                raise ValueError("Observation adapter binding mismatch")
            number(record["time"])
            if record["time"] != time or record["clock_id"] != state["clock_id"]:
                raise ValueError("Observation event time and clock must match exactly")
            for key in ("quantity_ids", "units", "frame"):
                if record[key] != sensor[key]:
                    raise ValueError("Observation quantity order, units or frame differ from the declared sensor map")
            frames.add(record["frame"])
            vector(record["values"], len(sensor["quantity_ids"]))
            calibration = sensor["calibration"]
            if (record["calibration_ref"] != byte_digest(retained_bytes(calibration["artifact_b64"])) or
                    not calibration["valid_interval"][0] <= time < calibration["valid_interval"][1]):
                raise ValueError("Observation calibration commitment or nominal-time validity differs")
            retained_bytes(record["raw_evidence_b64"])
        if len(frames) > 1:
            raise ValueError("Joint observations require one declared measurement frame; transform explicitly first")
        inputs = batch_inputs(source, i)
        m = len(inputs["order"])
        if m > 16 or (angle and m > 1):
            raise ValueError("Channel budget exceeded; scalar SO2 supports one measurement per batch")
        joint = batch["measurement_noise"]
        if not m:
            if joint is not None:
                raise ValueError("Prediction-only batches have no measurement covariance")
            continue
        _keys(joint, {"channel_order", "matrix", "cross_sensor_policy", "evidence_refs"})
        if joint["channel_order"] != inputs["order"]:
            raise ValueError("Joint covariance axes must follow the exact observation order")
        matrix(joint["matrix"], m, m, True)
        references(joint["evidence_refs"])
        if (not isinstance(joint["cross_sensor_policy"], str) or
                joint["cross_sensor_policy"] not in {"full_joint_declared", "declared_independent"}):
            raise ValueError("Unknown cross-sensor covariance is not supported")
        if joint["cross_sensor_policy"] == "declared_independent":
            owners = [q.split("/", 1)[0] for q in inputs["order"]]
            if any(joint["matrix"][a][b] != 0 for a in range(m) for b in range(m) if owners[a] != owners[b]):
                raise ValueError("Declared independent sensors require exactly zero cross blocks")
    return source


def validate_data(source, data):
    """Offline scientific bindings and domains, without replaying provider arithmetic."""
    _keys(data, {"schema", "initial_state_id", "state_contract", "estimates", "authority"})
    state = source["configuration"]["state"]
    if (data["schema"] != DATA_SCHEMA or data["authority"] != AUTHORITY or
            data["state_contract"] != state or data["initial_state_id"] != initial_state_id(source)):
        raise ValueError("Fusion result state or authority binding differs")
    estimates = data["estimates"]
    if not isinstance(estimates, list) or len(estimates) != len(source["batches"]):
        raise ValueError("Fusion result batch count differs")
    n, predecessor, previous_config, epoch = len(state["quantity_ids"]), data["initial_state_id"], None, -1
    for i, (batch, estimate) in enumerate(zip(source["batches"], estimates)):
        _keys(estimate, {"batch_index", "configuration_id", "configuration_ref", "epoch_index", "time", "predecessor_state_id",
                         "predicted_state_id", "state_id", "mean", "covariance", "diagnostics", "observation_refs", "observation_order"})
        inputs = batch_inputs(source, i)
        config_id = configuration_id(source["configuration"], inputs["profile"])
        epoch += config_id != previous_config
        previous_config = config_id
        if (type(estimate["batch_index"]) is not int or estimate["batch_index"] != i or
                type(estimate["epoch_index"]) is not int or estimate["epoch_index"] != epoch or
                estimate["configuration_id"] != config_id or estimate["configuration_ref"] != batch["configuration_ref"] or
                type(estimate["time"]) not in (int, float) or estimate["time"] != batch["time"] or
                estimate["predecessor_state_id"] != predecessor or estimate["observation_order"] != inputs["order"] or
                estimate["observation_refs"] != inputs["evidence_refs"]):
            raise ValueError("Fusion result configuration, time or evidence linkage differs")
        for key in ("predicted_state_id", "state_id"):
            if not isinstance(estimate[key], str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", estimate[key]):
                raise ValueError("Invalid provider numerical state identity")
        if estimate["predicted_state_id"] == predecessor:
            raise ValueError("Prediction must retain a new numerical transition identity")
        vector(estimate["mean"], n)
        matrix(estimate["covariance"], n, n, True)
        diagnostics = estimate["diagnostics"]
        _keys(diagnostics, {"status", "innovation", "innovation_covariance", "residual", "nis"})
        m = len(inputs["order"])
        if m:
            if diagnostics["status"] != "updated":
                raise ValueError("Observed batch must retain update diagnostics")
            vector(diagnostics["innovation"], m)
            vector(diagnostics["residual"], m)
            matrix(diagnostics["innovation_covariance"], m, m, True)
            try:
                np.linalg.cholesky(np.asarray(diagnostics["innovation_covariance"], dtype=float))
            except np.linalg.LinAlgError as exc:
                raise ValueError("Successful update requires positive definite innovation covariance") from exc
            if estimate["state_id"] == estimate["predicted_state_id"]:
                raise ValueError("Update must retain a new numerical transition identity")
            if number(diagnostics["nis"]) < 0:
                raise ValueError("NIS must be nonnegative")
        elif (diagnostics != {"status": "prediction_only", "innovation": [], "innovation_covariance": [], "residual": [], "nis": None}
              or estimate["state_id"] != estimate["predicted_state_id"]):
            raise ValueError("Prediction-only result cannot claim an observation update")
        if state["geometry"] == "so2_scalar_radians.v1" and not -math.pi <= estimate["mean"][0] < math.pi:
            raise ValueError("SO2 result must retain its principal angle chart")
        predecessor = estimate["state_id"]
