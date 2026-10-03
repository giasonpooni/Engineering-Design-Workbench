"""Synthetic, bounded demo declarations and read-only scientific plot projections.

The demo changes declared priors and noise covariances, never observation bytes,
provider algorithms or physical calibration claims. Plots are projections of
validated retained results; drawing them does not execute or admit state.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from importlib.resources import files
import json
import math

from .sensor_fusion_ekf import METHOD, validate_source
from .sensor_fusion_ekf_workflow import OPERATION, SensorFusionEKFWorkflow
from .telemetry import byte_digest, canonical

_COLORS = ("#96f6ca", "#93bcff", "#c6a7ff", "#ffbb82")
_LIMITATIONS = [
    "Synthetic observations and calibration artifacts; no physical sensor or device is connected.",
    "Estimates and uncertainty are conditional on declared models, noise and local linearization.",
    "Replay checks numerical reproduction with the same pinned providers; independent verification is false.",
    "Physical validation and state admission are not performed; no industrial control is authorized.",
]


def _fixture(example):
    if not isinstance(example, str) or example not in {"metrology", "thermal", "range"}:
        raise ValueError("Select a supported example: metrology, thermal or range.")
    return files("ciw").joinpath("demo_fixtures", example + ".json").read_bytes()


def _parameter(identifier, label, unit, minimum, maximum, step, default, help_text):
    return {"id": identifier, "label": label, "unit": unit, "min": minimum,
            "max": maximum, "step": step, "default": default, "help": help_text}


def catalog():
    """Return fresh, JSON-serializable descriptions of the fixed synthetic examples."""
    descriptions = {
        "metrology": {
            "name": "Metrology", "summary": "Fuse a direct thermometer with a nonlinear voltage proxy.",
            "state": "Normalized temperature x = (T − 300 K) / 100 K; plots show T in kelvins.",
            "dynamics": "Discrete drift x_next = 0.995 x + 0.025, one-second intervals.",
            "sensors": "Direct reference T = 100 x + 300 K; proxy V = 0.1 x² + 0.5 x V.",
            "uncertainty": "Full correlated K/V measurement covariance; local Gaussian EKF posterior.",
            "timing": "Four forward batches at 1–4 s; prediction-only at 2 s and proxy-only at 3 s.",
            "extra": "The voltage response is illustrative, not a validated polymer constitutive law. The quadratic channel can be globally ambiguous.",
        },
        "thermal": {
            "name": "Thermal observation", "summary": "Observe a heated core and cooling shell with thermometer dropout.",
            "state": "Core and shell temperatures in kelvins, ordered [core, shell].",
            "dynamics": "Discrete two-capacity RC model: capacities 1000/400 J/K, conductances 8/5 W/K, heater 80 W, ambient 293.15 K.",
            "sensors": "Direct core/shell thermometers; one shell-only update and one prediction-only batch.",
            "uncertainty": "Correlated core/shell covariances. Deterministic RC parameters and fixed input offsets; affine behavior within the EKF lane.",
            "timing": "Four forward batches at 5, 10, 15 and 20 s; declared exact nominal clock and constant-input discretization.",
            "extra": "RC parameters and inputs are synthetic. Parameter uncertainty is declared zero; this is not a qualified mold or polymer thermal model.",
        },
        "range": {
            "name": "Range tracking", "summary": "Track planar motion using true ranges to two synthetic anchors.",
            "state": "Cartesian [x, y, vx, vy] in [m, m, m/s, m/s].",
            "dynamics": "Constant-velocity Cartesian transition at one-second intervals.",
            "sensors": "Euclidean range to west/east anchors in metres, with correlated measurement noise.",
            "uncertainty": "Local Gaussian EKF posterior and full position/velocity covariance. Range readings are not Cartesian position observations.",
            "timing": "Four forward batches at 1–4 s; east-only at 2 s and prediction-only at 3 s.",
            "extra": "Range derivatives are undefined at an anchor. Evaluation refuses centers inside the declared exclusion radius; global observability is not certified.",
        },
    }
    output = []
    for example, description in descriptions.items():
        source = validate_source(_fixture(example))
        shift = (_parameter("position_shift", "Initial x-position shift", "m", -2, 2, .1, 0,
                    "Shift only the initial x estimate; retained synthetic ranges stay fixed.")
                 if example == "range" else
                 _parameter("temperature_shift", "Initial temperature shift", "K", -20, 20, .5, 0,
                    "Shift the initial temperature estimate; observations stay fixed." +
                    (" Both core and shell shift together." if example == "thermal" else " A 1 K shift is 0.01 normalized state units.")))
        parameters = [shift,
            _parameter("prior_scale", "Prior covariance multiplier", "×", .25, 4, .25, 1,
                       "Multiply the full initial covariance, including cross-covariances. Standard deviations scale by the square root."),
            _parameter("process_scale", "Process covariance multiplier", "×", .1, 4, .1, 1,
                       "Multiply the declared discrete process covariance Q for every interval. It is not a continuous-time noise rate."),
            _parameter("measurement_scale", "Measurement covariance multiplier", "×", .25, 4, .25, 1,
                       "Multiply the full active measurement covariance R, preserving correlation coefficients and unit products. Readings stay fixed; data is not resampled."),
        ]
        output.append({"id": example, "name": description["name"], "summary": description["summary"],
            "synthetic": True, "operation": OPERATION, "method": METHOD,
            "problem": {key: description[key] for key in ("state", "dynamics", "sensors", "uncertainty", "timing")} |
                       {"limitations": [description["extra"], *_LIMITATIONS]},
            "parameters": parameters, "state_contract": deepcopy(source["configuration"]["state"]),
            "batch_count": len(source["batches"]),
            "parameter_scope": "Changes affect the declared prior/noise model, not the retained synthetic observations or sensor maps."})
    return output


def _values(example, parameters):
    _fixture(example)  # Bound example IDs before looking at caller data.
    if not isinstance(parameters, dict):
        raise ValueError("Parameters must be an object of supported numeric controls.")
    definition = next(item for item in catalog() if item["id"] == example)
    controls = {item["id"]: item for item in definition["parameters"]}
    if set(parameters) - set(controls):
        raise ValueError("Unknown parameter; use only the controls declared for this example.")
    values = {}
    for identifier, control in controls.items():
        value = parameters.get(identifier, control["default"])
        if type(value) not in (int, float):
            raise ValueError(control["label"] + " must be a finite number.")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite or not control["min"] <= value <= control["max"]:
            raise ValueError(f"{control['label']} must be between {control['min']} and {control['max']} {control['unit']}.")
        values[identifier] = value
    return values, controls


def _scale(matrix, factor):
    return [[value * factor for value in row] for row in matrix]


def source_for(example, parameters):
    """Build a coherent declaration within the fixed demo's supported controls.

    A changed source retains its unchanged acquisition bytes and original model
    evidence. New exact evidence bytes declare the synthetic prior and noise
    assumptions, and new references bind those declarations rather than pointing
    at an unchanged fixture declaration.
    """
    values, controls = _values(example, parameters)
    raw = _fixture(example)
    source = validate_source(raw)
    if all(values[key] == control["default"] for key, control in controls.items()):
        return source
    shift = values.get("temperature_shift", values.get("position_shift", 0))
    if example == "metrology":
        source["prior"]["mean"][0] += shift / 100
    elif example == "thermal":
        source["prior"]["mean"] = [value + shift for value in source["prior"]["mean"]]
    else:
        source["prior"]["mean"][0] += shift
    source["prior"]["covariance"] = _scale(source["prior"]["covariance"], values["prior_scale"])
    source["experiment_id"] = "synthetic:demo:" + example + ":" + byte_digest(canonical(values)).split(":")[1][:16]
    declaration_refs = []
    noise_policy = {key: value for key, value in source["configuration"]["noise_policy"].items() if key != "evidence_refs"}
    for index, batch in enumerate(source["batches"]):
        dynamics = batch["dynamics"]
        dynamics["process_covariance"] = _scale(dynamics["process_covariance"], values["process_scale"])
        noise = batch["measurement_noise"]
        if noise is not None:
            noise["matrix"] = _scale(noise["matrix"], values["measurement_scale"])
        evidence = {"schema": "ciw.demo-model-and-uncertainty-declaration.v1", "origin": "synthetic_demo",
            "claim_scope": "caller_declared_not_physically_validated", "fixture_ref": byte_digest(raw),
            "original_model_evidence_b64": dynamics["model"]["evidence_b64"],
            "original_model_ref": dynamics["model_ref"], "parameters": values, "prior": source["prior"],
            "batch_index": index, "time": batch["time"], "noise_policy": noise_policy,
            "process_covariance": dynamics["process_covariance"],
            "measurement_noise": None if noise is None else {key: value for key, value in noise.items() if key != "evidence_refs"},
            "observation_bytes": "unchanged_from_synthetic_fixture", "physical_validation": "not_established"}
        evidence_bytes = canonical(evidence)
        reference = byte_digest(evidence_bytes)
        declaration_refs.append(reference)
        dynamics["model"]["evidence_b64"] = base64.b64encode(evidence_bytes).decode()
        dynamics["model_ref"] = "synthetic:demo:" + example + ":batch-" + str(index) + ":" + reference.split(":")[1][:16]
        if noise is not None:
            noise["evidence_refs"] = [reference]
    source["configuration"]["noise_policy"]["evidence_refs"] = declaration_refs
    return validate_source(canonical(source))


def _series(name, kind, points, color):
    return {"name": name, "kind": kind, "color": color, "points": points}


def _plot(identifier, title, x_label, y_label, series, help_text):
    return {"id": identifier, "title": title, "x_label": x_label, "y_label": y_label,
            "series": series, "help": help_text}


def _sigma(variance):
    if variance < 0:
        raise ValueError("Cannot plot a negative declared variance.")
    return math.sqrt(variance)


def _state_plot(source, estimates, index, title, unit, observed, *, scale=1, offset=0):
    rows = [{"time": source["prior"]["time"], "mean": source["prior"]["mean"],
             "covariance": source["prior"]["covariance"]}, *estimates]
    line, bands = [], []
    for row in rows:
        mean = scale * row["mean"][index] + offset
        margin = 2 * abs(scale) * _sigma(row["covariance"][index][index])
        point = {"x": row["time"], "y": mean}
        line.append(point)
        bands.append({**point, "lower": mean - margin, "upper": mean + margin})
    color = _COLORS[index % len(_COLORS)]
    return _plot("state-" + str(index), title, "Time (s)", title + " (" + unit + ")", [
        _series("Marginal ±2σ", "band", bands, color),
        _series("Estimate (prior at t=0)", "line", line, color),
        _series("Synthetic observations", "points", observed, _COLORS[3])],
        "Bands show marginal ±2σ conditional on declared models/noise and local linearization; empirical coverage is not established. Prediction-only intervals retain estimates without inventing observations.")


def _observation_plot(source, estimates, sensor_id, title, unit, color):
    observed, predicted, posterior, bands = [], [], [], []
    for batch, estimate in zip(source["batches"], estimates, strict=True):
        entries = [(record, i) for record, i in _channels(batch) if record["sensor_id"] == sensor_id]
        if not entries:
            gap = {"x": batch["time"], "y": None}
            predicted.append(gap)
            posterior.append(gap)
            bands.append({**gap, "lower": None, "upper": None})
            continue
        record, index = entries[0]
        linear = estimate["linearization"]
        prior_value = linear["observation_value"][index]
        posterior_value = linear["post_observation_value"][index]
        margin = 2 * _sigma(estimate["diagnostics"]["innovation_covariance"][index][index])
        observed.append({"x": batch["time"], "y": record["values"][0]})
        predicted.append({"x": batch["time"], "y": prior_value})
        posterior.append({"x": batch["time"], "y": posterior_value})
        bands.append({"x": batch["time"], "y": prior_value, "lower": prior_value - margin, "upper": prior_value + margin})
    return _plot("observation-" + sensor_id, title, "Time (s)", title + " (" + unit + ")", [
        _series("Predictive measurement ±2σ", "band", bands, color),
        _series("Predicted measurement", "line", predicted, color),
        _series("Posterior model response", "line", posterior, _COLORS[2]),
        _series("Synthetic observations", "points", observed, _COLORS[3])],
        "Predicted and posterior responses come from the retained sensor map. Predictive bands use the local innovation covariance, including measurement noise. Missing channels remain gaps; range readings do not measure x/y positions.")


def _channels(batch):
    """Yield decoded records and their first scalar index in retained channel order."""
    index = 0
    for observation in batch["observations"]:
        record = json.loads(base64.b64decode(observation["record_b64"], validate=True))
        yield record, index
        index += len(record["values"])


def _residual_plots(diagnostics):
    declared = {channel["id"]: channel["unit"] for row in diagnostics for channel in row["channels"]}
    plots = []
    for identifier, unit in declared.items():
        innovation, residual = [], []
        for row in diagnostics:
            channel = next((channel for channel in row["channels"] if channel["id"] == identifier), None)
            innovation.append({"x": row["time"], "y": None if channel is None else channel["innovation"]})
            residual.append({"x": row["time"], "y": None if channel is None else channel["residual"]})
        plots.append(_plot("residual-" + identifier.replace("/", "-"), identifier + " residuals", "Time (s)",
            "Residual (" + unit + ")", [
                _series("Innovation", "line", innovation, _COLORS[1]),
                _series("Nonlinear posterior residual", "line", residual, _COLORS[2])],
            "Innovation is observation minus predicted sensor response. Posterior residual uses the true retained nonlinear sensor response, not the linearized residual. Missing channels remain gaps; magnitudes with different units are not compared on one axis."))
    return plots


def project(bundle, example):
    """Inspect and project an intact retained execution without provider execution."""
    expected = validate_source(_fixture(example))
    raw = SensorFusionEKFWorkflow()._validate(bundle)
    source = validate_source(raw)
    if source["configuration"]["state"] != expected["configuration"]["state"]:
        raise ValueError("The retained execution does not belong to the selected demo example.")
    step, = bundle["steps"]
    data = step["result"]["data"]
    estimates = data["estimates"]
    observations, diagnostics = [], []
    observed_by_sensor = {}
    for batch, estimate in zip(source["batches"], estimates, strict=True):
        channels = []
        for record, first in _channels(batch):
            observations.append(deepcopy(record))
            observed_by_sensor.setdefault(record["sensor_id"], []).append({"x": record["time"], "y": record["values"][0]})
            for j, value in enumerate(record["values"]):
                index = first + j
                diagnostic = estimate["diagnostics"]
                channels.append({"id": record["sensor_id"] + "/" + record["quantity_ids"][j],
                    "unit": record["units"][j], "observed": value,
                    "predicted": estimate["linearization"]["observation_value"][index],
                    "posterior": estimate["linearization"]["post_observation_value"][index],
                    "innovation": diagnostic["innovation"][index], "residual": diagnostic["residual"][index],
                    "linearized_residual": diagnostic["linearized_residual"][index]})
        diagnostics.append({"time": batch["time"], "status": estimate["diagnostics"]["status"],
            "configuration": estimate["configuration_ref"], "channel_count": len(channels),
            "nis": estimate["diagnostics"]["nis"], "nis_unit": "1", "channels": channels,
            "help": "NIS is a joint local-model diagnostic, not an outlier gate, observability proof or physical validation."})
    if example == "metrology":
        plots = [_state_plot(source, estimates, 0, "Temperature", "K", observed_by_sensor.get("reference", []), scale=100, offset=300),
                 _observation_plot(source, estimates, "proxy", "Proxy voltage", "V", _COLORS[1])]
    elif example == "thermal":
        plots = [_state_plot(source, estimates, i, name, "K", observed_by_sensor.get(sensor, []))
                 for i, name, sensor in ((0, "Core temperature", "core"), (1, "Shell temperature", "shell"))]
    else:
        rows = [source["prior"], *estimates]
        trajectory = [{"x": row["mean"][0], "y": row["mean"][1], "time": row.get("time", 0)} for row in rows]
        sensors = {sensor["sensor_id"]: sensor for profile in source["configuration"]["configurations"] for sensor in profile["sensors"]}
        anchors = [{"x": sensor["model"]["parameters"]["anchor"][0], "y": sensor["model"]["parameters"]["anchor"][1],
                    "label": sensor_id} for sensor_id, sensor in sensors.items()]
        plots = [_plot("trajectory", "Estimated planar trajectory", "x-position (m)", "y-position (m)", [
            _series("Estimated positions", "line", trajectory, _COLORS[0]),
            _series("Fixed synthetic anchors", "points", anchors, _COLORS[1])],
            "These are Cartesian state estimates. Range readings appear in separate anchor plots; they are not position observations. Both axes use metres; preserve equal geometric scale when rendering.")]
        plots[0]["equal_scale"] = True
        plots.extend(_state_plot(source, estimates, i, title, "m", []) for i, title in ((0, "x-position"), (1, "y-position")))
        plots.extend(_observation_plot(source, estimates, sensor_id, sensor_id.title() + " anchor range", "m", _COLORS[i])
                     for i, sensor_id in enumerate(("west", "east")))
    verification = bundle["verification"]
    providers = []
    primary = bundle["runtimes"]["gsie"]
    for role, runtime in (("gsie", primary), ("jspt", primary["companions"]["jspt"])):
        providers.append({"role": role, **{key: deepcopy(runtime[key]) for key in
            ("revision", "source_tree", "python_sha256", "python_version", "dependencies", "adapter_version")}})
    return {"example": example, "synthetic": True, "plots": plots,
        "residual_plots": _residual_plots(diagnostics), "diagnostics": diagnostics,
        "identities": {"evidence": bundle["source"]["evidence"][0]["artifact_ref"], "operation": step["operation_id"],
            "execution": step["execution_id"], "verification": verification["verification_id"],
            "bundle": bundle["bundle_digest"], "numerical_result": step["numerical_result_id"],
            "result": step["result_id"], "session": bundle["session_id"]},
        "authority": deepcopy(data["authority"]),
        "verification": {key: deepcopy(verification[key]) for key in
            ("outcome", "independent", "method", "subject_ref", "verification_id")},
        "replay_scope": "Fresh occurrences reproduce exact canonical numerical output with the same pinned providers. This is not independent or physical validation; state admission is not performed.",
        "limitations": deepcopy(next(item for item in catalog() if item["id"] == example)["problem"]["limitations"]),
        "state_contract": deepcopy(data["state_contract"]), "configuration": deepcopy(source),
        "observations": observations, "estimates": deepcopy(estimates), "providers": providers}
