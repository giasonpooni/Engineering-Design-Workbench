"""Demo controls and projections preserve real instrument meaning and evidence."""
import base64
from copy import deepcopy
import json
import math
import os
from pathlib import Path

import pytest

from ciw.demo_catalog import catalog, project, source_for
from ciw.sensor_fusion_ekf_workflow import SensorFusionEKFWorkflow
from ciw.telemetry import byte_digest, canonical
from scripts.monorepo import provider_worktrees

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ("metrology", "thermal", "range")


def fixture(example):
    return json.loads((ROOT / "examples" / f"sensor-fusion-ekf-{example}.json").read_bytes())


def test_catalog_is_complete_isolated_and_exact_fixtures_are_packaged():
    first = catalog()
    assert [entry["id"] for entry in first] == list(EXAMPLES)
    assert all(entry["synthetic"] and entry["parameters"] and entry["problem"]["limitations"] for entry in first)
    for entry in first:
        packaged = ROOT / "src" / "ciw" / "demo_fixtures" / (entry["id"] + ".json")
        original = ROOT / "examples" / ("sensor-fusion-ekf-" + entry["id"] + ".json")
        assert packaged.read_bytes() == original.read_bytes()
        assert source_for(entry["id"], {}) == fixture(entry["id"])
        assert source_for(entry["id"], {p["id"]: p["default"] for p in entry["parameters"]}) == fixture(entry["id"])
    first[0]["parameters"][0]["default"] = 10000
    assert catalog()[0]["parameters"][0]["default"] == 0


@pytest.mark.parametrize("example", EXAMPLES)
def test_changed_prior_and_full_covariances_retain_observation_and_model_bytes(example):
    original = fixture(example)
    shift_key = "position_shift" if example == "range" else "temperature_shift"
    parameters = {shift_key: 1, "prior_scale": 2, "process_scale": .5, "measurement_scale": 3}
    source = source_for(example, parameters)
    assert source["experiment_id"].startswith("synthetic:demo:" + example)
    expected_mean = deepcopy(original["prior"]["mean"])
    if example == "metrology":
        expected_mean[0] += .01
    elif example == "thermal":
        expected_mean = [mean + 1 for mean in expected_mean]
    else:
        expected_mean[0] += 1
    assert source["prior"]["mean"] == expected_mean
    assert source["prior"]["covariance"] == [[2 * value for value in row] for row in original["prior"]["covariance"]]
    references = []
    for old, new in zip(original["batches"], source["batches"], strict=True):
        assert new["observations"] == old["observations"]
        assert new["dynamics"]["model"]["parameters"] == old["dynamics"]["model"]["parameters"]
        assert new["dynamics"]["process_covariance"] == [[.5 * value for value in row] for row in old["dynamics"]["process_covariance"]]
        raw = base64.b64decode(new["dynamics"]["model"]["evidence_b64"])
        declaration = json.loads(raw)
        assert declaration["original_model_evidence_b64"] == old["dynamics"]["model"]["evidence_b64"]
        assert declaration["parameters"] == parameters
        assert declaration["prior"] == source["prior"]
        assert declaration["process_covariance"] == new["dynamics"]["process_covariance"]
        references.append(byte_digest(raw))
        if old["measurement_noise"] is None:
            assert new["measurement_noise"] is None
            assert declaration["measurement_noise"] is None
        else:
            assert new["measurement_noise"]["matrix"] == [[3 * value for value in row] for row in old["measurement_noise"]["matrix"]]
            assert new["measurement_noise"]["evidence_refs"] == [byte_digest(raw)]
            assert declaration["measurement_noise"]["matrix"] == new["measurement_noise"]["matrix"]
    assert source["configuration"]["noise_policy"]["evidence_refs"] == references


@pytest.mark.parametrize("parameters", [None, [], {"unknown": 1}, {"prior_scale": True},
    {"prior_scale": "1"}, {"prior_scale": math.nan}, {"prior_scale": math.inf},
    {"prior_scale": -math.inf}, {"prior_scale": 0}, {"prior_scale": 4.00001},
    {"prior_scale": 10**1000}, {"process_scale": .099}, {"measurement_scale": .249},
    {"temperature_shift": -20.01}])
def test_invalid_controls_are_refused_without_provider_execution(parameters):
    with pytest.raises(ValueError):
        source_for("metrology", parameters)


@pytest.mark.parametrize("example", [None, "", "../range", "angular"])
def test_unsupported_example_refused(example):
    with pytest.raises(ValueError):
        source_for(example, {})


@pytest.fixture(scope="module")
def providers():
    history = Path(os.environ.get("CIW_TEST_PROVIDER_HISTORY_ROOT", ROOT))
    with provider_worktrees(history, roles=["gsie", "jspt"]) as bindings:
        yield bindings


@pytest.fixture(scope="module", params=EXAMPLES)
def execution(request, providers):
    example = request.param
    bundle = SensorFusionEKFWorkflow().create_session(canonical(source_for(example, {})), providers)
    return example, bundle


def test_projection_uses_verified_real_results_and_separate_identities(execution):
    example, bundle = execution
    result = project(bundle, example)
    step = bundle["steps"][0]
    assert result["identities"]["execution"] == step["execution_id"]
    assert result["identities"]["numerical_result"] == step["numerical_result_id"]
    assert result["identities"]["evidence"] == bundle["source"]["evidence"][0]["artifact_ref"]
    assert result["identities"]["verification"] == bundle["verification"]["verification_id"]
    assert result["authority"]["state_admission"] == "not_performed"
    assert result["verification"]["independent"] is False
    assert result["verification"]["outcome"] == "passed"
    assert len(result["diagnostics"]) == 4
    assert result["residual_plots"]
    assert result["estimates"] == step["result"]["data"]["estimates"]
    assert {provider["role"] for provider in result["providers"]} == {"gsie", "jspt"}
    assert all("repository_root" not in provider for provider in result["providers"])
    before = deepcopy(bundle)
    result["estimates"][0]["mean"][0] = 100000
    assert bundle == before


def test_residual_plots_use_true_residuals_and_channel_units(execution):
    example, bundle = execution
    result = project(bundle, example)
    for plot in result["residual_plots"]:
        identifier = plot["title"].removesuffix(" residuals")
        first = next(channel for row in result["diagnostics"] for channel in row["channels"] if channel["id"] == identifier)
        assert plot["y_label"] == "Residual (" + first["unit"] + ")"
        for row, innovation, residual in zip(result["diagnostics"], plot["series"][0]["points"], plot["series"][1]["points"], strict=True):
            channel = next((channel for channel in row["channels"] if channel["id"] == identifier), None)
            assert innovation["x"] == residual["x"] == row["time"]
            assert innovation["y"] == (None if channel is None else channel["innovation"])
            assert residual["y"] == (None if channel is None else channel["residual"])


def test_prediction_only_and_dropout_remain_absent(execution):
    example, bundle = execution
    result = project(bundle, example)
    prediction_only, = [row for row in result["diagnostics"] if row["status"] == "prediction_only"]
    assert prediction_only["nis"] is None
    assert prediction_only["channel_count"] == 0
    assert prediction_only["channels"] == []
    for plot in result["plots"]:
        observed, = [series for series in plot["series"] if series["name"] == "Synthetic observations"] if any(
            series["name"] == "Synthetic observations" for series in plot["series"]) else [None]
        if observed:
            assert prediction_only["time"] not in [point["x"] for point in observed["points"]]
        if plot["id"].startswith("observation-"):
            prediction = next(series for series in plot["series"] if series["name"] == "Predicted measurement")
            point, = [point for point in prediction["points"] if point["x"] == prediction_only["time"]]
            assert point["y"] is None


def test_scientific_plot_units_and_covariance_propagation(execution):
    example, bundle = execution
    result = project(bundle, example)
    source = fixture(example)
    estimate = bundle["steps"][0]["result"]["data"]["estimates"][0]
    if example == "metrology":
        temperature = result["plots"][0]
        assert temperature["y_label"].endswith("(K)")
        band = temperature["series"][0]["points"][1]
        assert band["y"] == 100 * estimate["mean"][0] + 300
        assert band["upper"] - band["y"] == pytest.approx(200 * math.sqrt(estimate["covariance"][0][0]))
        reference = json.loads(base64.b64decode(source["batches"][0]["observations"][0]["record_b64"]))
        assert temperature["series"][2]["points"][0]["y"] == reference["values"][0]
        proxy = result["plots"][1]
        assert proxy["y_label"].endswith("(V)")
        predicted = next(series for series in proxy["series"] if series["name"] == "Predicted measurement")
        assert predicted["points"][0]["y"] == estimate["linearization"]["observation_value"][1]
    elif example == "thermal":
        assert all(plot["y_label"].endswith("(K)") for plot in result["plots"])
        assert result["plots"][1]["series"][1]["points"][1]["y"] == estimate["mean"][1]
    else:
        trajectory = result["plots"][0]
        assert trajectory["equal_scale"] is True
        assert trajectory["series"][0]["points"][1]["x"] == estimate["mean"][0]
        assert trajectory["series"][0]["points"][1]["y"] == estimate["mean"][1]
        assert all(not plot["series"][2]["points"] for plot in result["plots"][1:3])
        for plot in result["plots"][3:]:
            assert plot["y_label"].endswith("(m)")


def test_projection_refuses_forged_evidence_or_wrong_example(execution):
    example, bundle = execution
    changed = deepcopy(bundle)
    changed["steps"][0]["result"]["data"]["estimates"][0]["mean"][0] += 1
    with pytest.raises(ValueError):
        project(changed, example)
    other = "thermal" if example != "thermal" else "metrology"
    with pytest.raises(ValueError):
        project(bundle, other)


@pytest.mark.parametrize("example", EXAMPLES)
@pytest.mark.parametrize("edge", ["min", "max"])
def test_supported_parameter_extremes_execute_real_instrument(example, edge, providers):
    entry = next(item for item in catalog() if item["id"] == example)
    parameters = {parameter["id"]: parameter[edge] for parameter in entry["parameters"]}
    source = source_for(example, parameters)
    bundle = SensorFusionEKFWorkflow().create_session(canonical(source), providers)
    assert project(bundle, example)["verification"]["outcome"] == "passed"
