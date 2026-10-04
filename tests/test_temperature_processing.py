from copy import deepcopy
import math

import pytest

from ciw.operations.runner import digest, seal
from ciw.temperature_contract import AUTHORITY, example_request, validate_request
from ciw.temperature_processing import process_request, validate_report


def complete_budget(request):
    for item in request["budget"]:
        if item["status"] == "omitted":
            item.update(status="not_applicable", reason="Synthetic test assumption only",
                        evidence_ref=digest({"synthetic": item["category"]}))
    return request


def installed(request):
    request["installed_correction"] = {
        "source_id": "installation", "dependency_ids": ["synthetic.contact-error"],
        "evidence_ref": digest({"synthetic_installed_correction": 1}),
        "correlation_policy": "independent_of_all_other_sources", "offsets_K": [2.0, 3.0],
        "covariance_K2": [[0.25, 0.25], [0.25, 0.25]],
        **{key: request["identity"][key] for key in ("installation_id", "location_id", "material_id", "specimen_id")},
        "valid_time_s": [0.0, 10.0], "ambient_range_K": [290.0, 300.0], "heating_rate_range_K_s": [0.0, 20.0],
    }
    for item in request["budget"]:
        if item["category"] == "installation":
            item.update(status="included", source_ids=["installation"],
                        evidence_ref=digest({"synthetic_installation_budget": 1}))
    return request


def test_default_fixture_does_not_invent_evidence_or_polymer_temperature():
    request = example_request()
    report = process_request(request)
    assert report["authority"] == AUTHORITY
    assert report["polymer_temperature"]["status"] == "unavailable"
    assert report["acceptance"]["status"] == "indeterminate"
    assert report["uncertainty"]["status"] == "incomplete_declared_budget"
    assert report["raw_observations"] == request["raw_observations"]
    assert report["identities"]["raw_observations_ref"] == digest(request["raw_observations"])
    assert "not_acquisition_file_bytes" in report["identities"]["raw_commitment_scope"]
    validate_report(request, report)


def test_hand_calculated_joint_cross_covariance_is_preserved():
    request = example_request()
    request["calibration"].update(gain=2.0, coefficient_covariance=[[0.0025, 0.01], [0.01, 0.25]])
    request["joint_covariance"].update(cross_covariance_policy="declared", matrix=[
        [0.04, 0.01, 0.002, 0.005], [0.01, 0.09, 0.003, -0.004],
        [0.002, 0.003, 0.0025, 0.01], [0.005, -0.004, 0.01, 0.25]])
    report = process_request(request)
    output = report["calibrated_sensor_temperature"]
    assert [row["value_K"] for row in output["samples"]] == [292.0, 294.0]
    assert output["covariance_K2"][0] == pytest.approx([0.4605, 0.341])
    assert output["covariance_K2"][1] == pytest.approx([0.341, 0.668])
    validate_report(request, report)


def test_shared_offset_does_not_average_away_and_gain_is_shared():
    request = example_request()
    output = process_request(request)["calibrated_sensor_temperature"]
    assert output["covariance_K2"][0] == pytest.approx([0.30, 0.33])
    assert output["covariance_K2"][1] == pytest.approx([0.33, 0.42])
    mean_variance = sum(map(sum, output["covariance_K2"])) / 4
    assert mean_variance == pytest.approx(0.345)
    assert mean_variance >= request["calibration"]["coefficient_covariance"][1][1]


def test_deterministic_detached_processing_and_all_input_identities():
    request = example_request()
    first = process_request(request)
    assert process_request(request) == first
    validated = validate_request(request)
    validated["identity"]["sensor_id"] = "changed"
    assert request["identity"]["sensor_id"] != "changed"
    request["raw_observations"]["samples"][0]["value"] = 1.5
    second = process_request(request)
    assert first["raw_observations"]["samples"][0]["value"] == 1.0
    for key in ("request_ref", "raw_observations_ref"):
        assert second["identities"][key] != first["identities"][key]
    assert second["identities"]["calibration_ref"] == first["identities"]["calibration_ref"]
    assert second["record_digest"] != first["record_digest"]


def test_extra_covariance_counted_once_despite_multiple_budget_allocations():
    request = example_request()
    request["contributions"] = [{"source_id": "drift", "dependency_ids": ["synthetic.drift"],
        "evidence_ref": digest({"synthetic_drift": 1}), "correlation_policy": "independent_of_all_other_sources",
        "covariance_K2": [[0.2, 0.1], [0.1, 0.3]]}]
    for item in request["budget"]:
        if item["category"] in {"drift", "environment"}:
            item.update(status="included", source_ids=["drift"], evidence_ref=digest({"synthetic_drift": 1}))
    output = process_request(request)["calibrated_sensor_temperature"]
    assert output["covariance_K2"][0] == pytest.approx([0.5, 0.43])
    assert output["covariance_K2"][1] == pytest.approx([0.43, 0.72])


@pytest.mark.parametrize("field,value", [("gain", True), ("offset_K", math.nan), ("gain", math.inf), ("offset_K", 1e13)])
def test_non_numeric_nonfinite_and_outsize_scalars_refused(field, value):
    request = example_request()
    request["calibration"][field] = value
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize("mode", ["asymmetric", "negative_variance", "not_psd", "wrong_order", "coefficient_block", "unknown", "zero_policy"])
def test_bad_covariance_refused(mode):
    request = example_request()
    joint = request["joint_covariance"]
    if mode == "asymmetric":
        joint["matrix"][0][1] = 0.00001
    elif mode == "negative_variance":
        joint["matrix"][0][0] = -1.0
    elif mode == "not_psd":
        joint["cross_covariance_policy"] = "declared"
        joint["matrix"][0][1] = joint["matrix"][1][0] = 0.001
    elif mode == "wrong_order":
        joint["order"][0], joint["order"][1] = joint["order"][1], joint["order"][0]
    elif mode == "coefficient_block":
        joint["matrix"][2][2] = 0.05
    elif mode == "unknown":
        joint["cross_covariance_policy"] = "unknown"
    else:
        joint["matrix"][0][1] = joint["matrix"][1][0] = 0.00001
    with pytest.raises(ValueError):
        process_request(request)


@pytest.mark.parametrize("mode", ["duplicate_source", "overlapping_dependency", "unknown_correlation"])
def test_double_counting_or_unsupported_correction_correlation_refused(mode):
    request = installed(example_request())
    correction = request["installed_correction"]
    if mode == "duplicate_source":
        correction["source_id"] = "joint"
    elif mode == "overlapping_dependency":
        correction["dependency_ids"] = [request["joint_covariance"]["dependency_ids"][0]]
    else:
        correction["correlation_policy"] = "unknown"
    with pytest.raises(ValueError):
        process_request(request)


@pytest.mark.parametrize("status,value,flag", [("missing", None, "acquisition_missing"), ("saturated", 1.0, "acquisition_saturated"), ("invalid", None, "acquisition_invalid")])
def test_invalid_observations_retained_and_not_dropped(status, value, flag):
    request = complete_budget(example_request())
    request["raw_observations"]["samples"][0].update(status=status, value=value)
    report = process_request(request)
    assert report["raw_observations"] == request["raw_observations"]
    output = report["calibrated_sensor_temperature"]
    assert len(output["samples"]) == 2
    assert output["samples"][0]["value_K"] is None
    assert flag in output["samples"][0]["flags"]
    assert output["covariance_K2"][0] == [None, None]
    assert output["covariance_K2"][1][0] is None
    assert output["samples"][1]["value_K"] == 310.0
    assert report["acceptance"]["status"] == "indeterminate"
    validate_report(request, report)


@pytest.mark.parametrize("mode,flag", [("stale", "stale_observation"), ("range", "raw_outside_calibration"),
    ("ambient", "ambient_outside_calibration"), ("ramp", "heating_rate_outside_calibration"),
    ("identity", "calibration_sensor_id_mismatch"), ("time", "time_outside_calibration")])
def test_outside_applicability_suppresses_acceptance(mode, flag):
    request = complete_budget(example_request())
    if mode == "stale":
        request["raw_observations"]["samples"][0]["received_time_s"] = 0.6
    elif mode == "range":
        request["raw_observations"]["samples"][0]["value"] = 6.0
    elif mode == "ambient":
        request["conditions"]["ambient_temperature_K"] = 310.0
    elif mode == "ramp":
        request["conditions"]["maximum_heating_rate_K_s"] = 21.0
    elif mode == "identity":
        request["calibration"]["sensor_id"] = "different.sensor"
    else:
        request["calibration"]["valid_time_s"] = [0.5, 100.0]
    report = process_request(request)
    assert flag in report["calibrated_sensor_temperature"]["samples"][0]["flags"]
    assert report["acceptance"]["status"] == "indeterminate"
    validate_report(request, report)


def test_missing_budget_category_suppresses_acceptance():
    request = complete_budget(example_request())
    request["budget"] = [row for row in request["budget"] if row["category"] != "drift"]
    report = process_request(request)
    assert report["uncertainty"]["missing_or_omitted_categories"] == ["drift"]
    assert report["acceptance"]["status"] == "indeterminate"


@pytest.mark.parametrize("lower,upper,expected", [(300.0, 310.0, "conditional_pass"),
    (301.0, 310.0, "conditional_fail"), (290.0, 299.0, "conditional_fail")])
def test_closed_acceptance_boundaries_zero_uncertainty(lower, upper, expected):
    request = complete_budget(example_request())
    request["joint_covariance"]["matrix"] = [[0.0] * 4 for _ in range(4)]
    request["calibration"]["coefficient_covariance"] = [[0.0, 0.0], [0.0, 0.0]]
    request["acceptance"].update(lower=lower, upper=upper)
    report = process_request(request)
    assert report["acceptance"]["status"] == expected
    assert report["authority"]["physical_qualification"] == "not_established"


def test_uncertainty_interval_overlap_is_indeterminate():
    request = complete_budget(example_request())
    request["acceptance"].update(lower=300.0, upper=312.0)
    report = process_request(request)
    assert report["acceptance"]["status"] == "indeterminate"
    assert report["acceptance"]["sample_results"][0]["expanded_interval_K"][0] < 300.0
    validate_report(request, report)


def test_sub_ulp_positive_uncertainty_cannot_collapse_at_boundary():
    request = complete_budget(example_request())
    request["joint_covariance"]["matrix"] = [[0.0] * 4 for _ in range(4)]
    request["joint_covariance"]["matrix"][3][3] = 1e-40
    request["calibration"]["coefficient_covariance"] = [[0.0, 0.0], [0.0, 1e-40]]
    request["acceptance"].update(lower=300.0, upper=311.0)
    report = process_request(request)
    row = report["acceptance"]["sample_results"][0]
    assert row["expanded_interval_K"] == [math.nextafter(300.0, -math.inf), math.nextafter(300.0, math.inf)]
    assert row["status"] == report["acceptance"]["status"] == "indeterminate"
    validate_report(request, report)


def test_installed_correction_keeps_sensor_and_estimate_separate():
    request = complete_budget(installed(example_request()))
    request["acceptance"]["quantity"] = "polymer_temperature"
    report = process_request(request)
    sensor, polymer = report["calibrated_sensor_temperature"], report["polymer_temperature"]
    assert [row["value_K"] for row in sensor["samples"]] == [300.0, 310.0]
    assert [row["value_K"] for row in polymer["samples"]] == [302.0, 313.0]
    assert polymer["covariance_K2"][0] == pytest.approx([0.55, 0.58])
    assert polymer["covariance_K2"][1] == pytest.approx([0.58, 0.67])
    assert report["raw_observations"]["samples"][0]["value"] == 1.0
    assert report["authority"]["model_inference"] == "not_run"
    validate_report(request, report)


def test_wrong_installed_correction_cannot_admit_polymer_temperature():
    request = complete_budget(installed(example_request()))
    request["installed_correction"]["installation_id"] = "different.installation"
    request["acceptance"]["quantity"] = "polymer_temperature"
    report = process_request(request)
    assert all(sample["value_K"] is None for sample in report["polymer_temperature"]["samples"])
    assert report["calibrated_sensor_temperature"]["samples"][0]["value_K"] == 300.0
    assert report["acceptance"]["status"] == "indeterminate"
    validate_report(request, report)


def test_polymer_acceptance_unavailable_without_correction():
    request = complete_budget(example_request())
    request["acceptance"]["quantity"] = "polymer_temperature"
    assert process_request(request)["acceptance"]["status"] == "indeterminate"


@pytest.mark.parametrize("mode", ["sample_bound", "duplicate_time", "duplicate_id", "boolean_time", "clock_mismatch", "missing_value", "extra_field", "wrong_unit"])
def test_structure_and_bounds(mode):
    request = example_request()
    samples = request["raw_observations"]["samples"]
    if mode == "sample_bound":
        request["raw_observations"]["samples"] = [deepcopy(samples[0]) for _ in range(65)]
    elif mode == "duplicate_time":
        samples[1]["time_s"] = 0.0
    elif mode == "duplicate_id":
        samples[1]["sample_id"] = samples[0]["sample_id"]
    elif mode == "boolean_time":
        samples[0]["time_s"] = False
    elif mode == "clock_mismatch":
        request["clock"]["id"] = "unaligned.clock"
    elif mode == "missing_value":
        samples[0]["value"] = None
    elif mode == "extra_field":
        request["physical_qualification"] = "established"
    else:
        request["raw_observations"]["unit"] = "degC"
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize("change", ["unsealed_value", "authority", "identity", "flags", "applicability", "polymer_unit", "uncertainty"])
def test_report_seals_bindings_and_structure_checked_without_dispatch(monkeypatch, change):
    request = example_request()
    report = process_request(request)
    def forbidden(*args, **kwargs):
        raise AssertionError("Structural validation must not dispatch processing")
    monkeypatch.setattr("ciw.temperature_processing.process_request", forbidden)
    validate_report(request, report)
    changed = deepcopy(report)
    if change == "unsealed_value":
        changed["calibrated_sensor_temperature"]["samples"][0]["value_K"] = 999.0
    elif change == "authority":
        changed["authority"]["physical_qualification"] = "established"
    elif change == "identity":
        changed["identities"]["raw_observations_ref"] = digest({"different": 1})
    elif change == "flags":
        changed["calibrated_sensor_temperature"]["samples"][0]["flags"] = ["invented"]
    elif change == "applicability":
        changed["applicability"]["calibration_status"] = "physical_qualification_passed"
    elif change == "polymer_unit":
        changed["polymer_temperature"]["unit"] = "degC"
    else:
        changed["calibrated_sensor_temperature"]["samples"][0]["standard_uncertainty_K"] = 0.0
    if change != "unsealed_value":
        seal(changed)
    with pytest.raises(ValueError):
        validate_report(request, changed)


def test_propagated_covariance_may_exceed_input_entry_bound():
    request = example_request()
    request["joint_covariance"]["matrix"][2][2] = 1e24
    request["calibration"]["coefficient_covariance"][0][0] = 1e24
    report = process_request(request)
    assert report["calibrated_sensor_temperature"]["covariance_K2"][1][1] >= 4e24
    validate_report(request, report)


def test_maximum_64_sample_profile_retains_all_covariance_axes():
    request = example_request()
    request["clock"]["end_s"] = 63.0
    request["raw_observations"]["samples"] = [
        {"sample_id": f"s{i}", "time_s": float(i), "received_time_s": float(i) + 0.1,
         "value": 1.0 + i / 64, "status": "ok"} for i in range(64)]
    request["joint_covariance"]["order"] = [f"raw:s{i}" for i in range(64)] + ["gain", "offset_K"]
    request["joint_covariance"]["matrix"] = [[0.0] * 66 for _ in range(66)]
    for i in range(64):
        request["joint_covariance"]["matrix"][i][i] = 0.0001
    request["joint_covariance"]["matrix"][64][64] = 0.04
    request["joint_covariance"]["matrix"][65][65] = 0.25
    report = process_request(request)
    assert len(report["calibrated_sensor_temperature"]["samples"]) == 64
    assert len(report["calibrated_sensor_temperature"]["covariance_K2"]) == 64
    assert report["calibrated_sensor_temperature"]["samples"][-1]["status"] == "computed_from_declarations"
    validate_report(request, report)
