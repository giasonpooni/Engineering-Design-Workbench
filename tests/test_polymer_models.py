"""Analytical, domain, freshness, and toy-control regression checks.

These establish numerical reference behavior only, not physical qualification.
"""
from copy import deepcopy
import json
import math

import pytest

from ciw.polymer_contract import example_request, validate_request
from ciw.polymer_metrology import assess_metrology
from ciw.polymer_models import (control_proposal, engineering_estimate, example_control,
                               example_model, simulate_control, validate_control, validate_model)


def request():
    return validate_request(example_request())


def sensor(req, name):
    return next(s for s in req["sensors"] if s["sensor_id"] == name)


def test_cooling_matches_closed_form_and_target_time():
    req = request()
    result = engineering_estimate(req)
    cooling = result["cooling"]
    tau = 950.0 * 2000.0 * 1e-6 / (50.0 * 0.006)
    assert cooling["status"] == "ESTIMATED"
    assert cooling["time_constant_s"] == pytest.approx(tau)
    assert cooling["temperature_k"] == pytest.approx(300.0 + 50.0 * math.exp(-5.0 / tau))
    assert cooling["target"]["remaining_time_s"] == pytest.approx(tau * math.log(50.0 / 30.0))
    assert cooling["biot_number"] == pytest.approx(50.0 * 1e-6 / (0.006 * 0.2))
    assert cooling["standard_uncertainty_k"] > 0
    assert cooling["timing_temperature_bound_k"] > 0
    assert cooling["biot_standard_uncertainty"] > 0
    assert all(value is False for value in result["authority"].values())
    assert result["semantics"] == "reference_estimate"
    json.dumps(result, allow_nan=False)


def test_first_order_uncertainty_matches_independent_finite_difference():
    req = request()
    req["clock"]["max_skew_s"] = 0.0
    params = req["model"]["cooling"]
    nominal = engineering_estimate(req)["cooling"]
    contributions = []
    for name in ("density_kg_m3", "heat_capacity_j_kg_k", "volume_m3", "area_m2", "heat_transfer_w_m2_k"):
        original = params[name]["value"]
        eps = original * 1e-5
        params[name]["value"] = original + eps
        plus = engineering_estimate(req)["cooling"]["temperature_k"]
        params[name]["value"] = original - eps
        minus = engineering_estimate(req)["cooling"]["temperature_k"]
        params[name]["value"] = original
        contributions.append((plus-minus) / (2*eps) * params[name]["standard_uncertainty"])
    for name in ("part-temperature", "cooling-water"):
        sample = sensor(req, name)["samples"][-1]
        original, eps = sample["value"], 1e-3
        sample["value"] = original + eps
        plus = engineering_estimate(req)["cooling"]["temperature_k"]
        sample["value"] = original - eps
        minus = engineering_estimate(req)["cooling"]["temperature_k"]
        sample["value"] = original
        contributions.append((plus-minus) / (2*eps) * sample["standard_uncertainty"])
    assert nominal["standard_uncertainty_k"] == pytest.approx(math.hypot(*contributions), rel=1e-7)


def test_zero_horizon_no_decay_and_zero_supplied_uncertainty():
    req = request()
    req["clock"]["max_skew_s"] = 0.0
    req["model"]["cooling"]["forecast_horizon_s"] = 0.0
    for name in ("part-temperature", "cooling-water"):
        sensor(req, name)["samples"][-1]["standard_uncertainty"] = 0.0
    for name, param in req["model"]["cooling"].items():
        if type(param) is dict:
            param["standard_uncertainty"] = 0.0
    cooling = engineering_estimate(req)["cooling"]
    assert cooling["temperature_k"] == 350.0
    assert cooling["standard_uncertainty_k"] == 0.0
    assert cooling["timing_temperature_bound_k"] == 0.0


@pytest.mark.parametrize("change", ["biot", "temperature", "elapsed", "heating"])
def test_out_of_domain_cooling_abstains(change):
    req = request()
    if change == "biot":
        req["model"]["cooling"]["heat_transfer_w_m2_k"]["value"] = 1000.0
    elif change == "temperature":
        sensor(req, "part-temperature")["samples"][-1]["value"] = 600.0
    elif change == "elapsed":
        req["model"]["cooling"]["forecast_horizon_s"] = 121.0
    else:
        sensor(req, "part-temperature")["samples"][-1]["value"] = 280.0
    assert engineering_estimate(req)["cooling"]["status"] == "ABSTAINED"


def test_unreachable_and_near_singular_target_times_do_not_invent_solution():
    req = request()
    req["model"]["cooling"]["target_temperature_k"]["value"] = 300.0
    assert engineering_estimate(req)["cooling"]["target"]["status"] == "UNREACHABLE"
    req["model"]["cooling"]["target_temperature_k"]["value"] = 300.000001
    assert engineering_estimate(req)["cooling"]["target"]["status"] == "ABSTAINED"


def test_biot_uncertainty_crossing_guard_abstains_even_when_nominal_inside():
    req = request()
    req["model"]["cooling"]["heat_transfer_w_m2_k"].update(value=110.0, standard_uncertainty=20.0)
    cooling = engineering_estimate(req)["cooling"]
    assert cooling["biot_number"] < 0.1
    assert cooling["biot_number"] + 2.0 * cooling["biot_standard_uncertainty"] > 0.1
    assert cooling["status"] == "ABSTAINED"


def test_independence_cannot_be_silently_inferred():
    model = example_model()
    del model["uncertainty_profile"]
    with pytest.raises(ValueError):
        validate_model(model)
    model = example_model()
    model["uncertainty_profile"] = "unknown_dependence"
    with pytest.raises(ValueError):
        validate_model(model)


def test_missing_and_stale_temperature_abstain_and_sample_age_is_propagated():
    req = request()
    sensor(req, "part-temperature")["samples"][-1]["time_s"] = 9.5
    cooling = engineering_estimate(req)["cooling"]
    assert cooling["elapsed_s"] == 5.5
    assert cooling["temperature_k"] < 300.0 + 50.0 * math.exp(-5.0 / cooling["time_constant_s"])
    sensor(req, "part-temperature")["samples"][-1]["time_s"] = 8.0
    assert engineering_estimate(req)["cooling"]["status"] == "ABSTAINED"
    sensor(req, "part-temperature")["samples"] = []
    assert engineering_estimate(req)["cooling"]["status"] == "ABSTAINED"


def test_pressure_crossing_retains_sampling_bracket_and_no_spatial_claim():
    result = engineering_estimate(request())["cavity_arrival"][0]
    assert result["status"] == "BRACKETED"
    assert result["time_interval_s"] == [0.0, 1.0]
    assert result["spatial_extrapolation"] is False
    assert result["endpoint_standard_uncertainties_pa"] == [10000.0, 10000.0]
    assert "melt-front" in result["uncertainty_statement"]
    assert "time_s" not in result


def test_pressure_left_censoring_missing_and_stale_are_explicit():
    req = request()
    row = sensor(req, "cavity-1")
    row["samples"][0]["value"] = 2e6
    assert engineering_estimate(req)["cavity_arrival"][0]["reason"] == "LEFT_CENSORED_THRESHOLD_ALREADY_EXCEEDED"
    row["samples"] = []
    assert engineering_estimate(req)["cavity_arrival"][0]["status"] == "ABSTAINED"
    req = request()
    sensor(req, "cavity-1")["samples"].pop()
    assert engineering_estimate(req)["cavity_arrival"][0]["status"] == "ABSTAINED"


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -float("inf"), "950", -1.0, 0.0])
def test_model_numeric_contract_rejects_ambiguous_or_nonphysical_values(value):
    model = example_model()
    model["cooling"]["density_kg_m3"]["value"] = value
    with pytest.raises(ValueError):
        validate_model(model)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), 0.0, 1e-20])
def test_control_rejects_invalid_gain(value):
    control = example_control()
    control["response"]["local_gain_per_parameter"] = value
    with pytest.raises(ValueError):
        validate_control(control)


def test_model_and_control_are_detached_strict_and_process_bound():
    model = example_model()
    copy = validate_model(model)
    model["cooling"]["density_kg_m3"]["value"] = 1.0
    assert copy["cooling"]["density_kg_m3"]["value"] == 950.0
    model = example_model()
    model["process"] = "extrusion_blow_molding"
    with pytest.raises(ValueError):
        validate_model(model)
    model["cavity_arrival"]["pressure_sensor_ids"] = []
    validate_model(model)
    control = example_control()
    control["process"] = "extrusion_blow_molding"
    control["parameter"].update(name="holding_pressure_pa", unit="Pa")
    with pytest.raises(ValueError):
        validate_control(control)
    control = example_control()
    control["plc_endpoint"] = "unsafe-authority-extension"
    with pytest.raises(ValueError):
        validate_control(control)
    req = request()
    req["model"]["process"] = "extrusion_blow_molding"
    req["model"]["cavity_arrival"]["pressure_sensor_ids"] = []
    with pytest.raises(ValueError):
        engineering_estimate(req)


def test_bounded_proposal_uses_declared_gain_and_retains_measurement_sources():
    req = request()
    metrology = assess_metrology(req)
    result = control_proposal(req, metrology)
    assert result["status"] == "PROPOSED"
    assert result["proposed"] == pytest.approx(11.0)
    assert abs(result["delta"]) <= req["control"]["parameter"]["maximum_step"]
    assert req["control"]["response"]["gain_source_ref"] in result["source_refs"]
    assert all(value is False for value in result["authority"].values())
    assert req["control"]["parameter"]["current"] == 10.0
    req["control"]["parameter"]["current"] = 30.0
    result = control_proposal(req, metrology)
    assert result["status"] == "BOUND_LIMITED"
    assert result["delta"] == 0.0


@pytest.mark.parametrize("fault", ["indeterminate", "stale", "missing", "ambiguous", "uncertain", "out_of_domain"])
def test_control_abstains_when_quality_does_not_qualify_local_trial(fault):
    req = request()
    report = assess_metrology(req)
    dim = next(r for r in report["measurements"] if r["quantity"] == "part_dimension")
    if fault == "indeterminate":
        report["status"] = "INDETERMINATE"
    elif fault == "stale":
        dim["status"] = "STALE"
    elif fault == "missing":
        report["measurements"].remove(dim)
    elif fault == "ambiguous":
        report["measurements"].append(deepcopy(dim))
    elif fault == "uncertain":
        dim["standard_uncertainty"] = 0.001
    else:
        dim["value"] = 0.04
    assert control_proposal(req, report)["status"] == "ABSTAINED"


@pytest.mark.parametrize("guard_change,reason", [
    ({"measurement_cycle_index": 6}, "MEASUREMENT_CYCLE_TOO_OLD"),
    ({"last_adjustment_cycle_index": 9}, "MINIMUM_CYCLE_DWELL_NOT_ELAPSED"),
    ({"last_adjustment_cycle_index": 7, "measurement_cycle_index": 7}, "NO_MEASUREMENT_AFTER_PRIOR_ADJUSTMENT"),
])
def test_cycle_guard_prevents_repeated_action_on_delayed_or_uneffected_measurement(guard_change, reason):
    req = request()
    req["control"]["cycle_guard"].update(guard_change)
    report = control_proposal(req, assess_metrology(req))
    assert report["status"] == "ABSTAINED"
    assert report["reason"] == reason


@pytest.mark.parametrize("field,value", [
    ("current_cycle_index", True), ("measurement_cycle_index", 10.0),
    ("last_adjustment_cycle_index", True), ("minimum_dwell_cycles", 0),
    ("maximum_measurement_delay_cycles", -1), ("measurement_cycle_index", 11),
])
def test_cycle_guard_requires_exact_bounded_integer_attribution(field, value):
    control = example_control()
    control["cycle_guard"][field] = value
    with pytest.raises(ValueError):
        validate_control(control)


def test_simulated_loop_converges_with_rate_and_parameter_limits():
    control = example_control()
    report = simulate_control(control)
    assert report == simulate_control(control)
    assert report["status"] == "COMPLETED"
    assert abs(report["final_quantity"]-report["target"]) <= control["response"]["tolerance"]
    errors = []
    for row in report["cycles"]:
        assert abs(row["delta"]) <= control["parameter"]["maximum_step"]
        assert control["parameter"]["minimum"] <= row["parameter_after"] <= control["parameter"]["maximum"]
        errors.append(abs(row["quantity_after"]-report["target"]))
    assert errors == sorted(errors, reverse=True)
    assert report["semantics"] == "synthetic_toy_cycle_response"
    actions = [r["cycle_index"] for r in report["cycles"] if r["delta"] != 0]
    assert all(after - before >= control["cycle_guard"]["minimum_dwell_cycles"]
               for before, after in zip(actions, actions[1:]))
    assert any(r["status"] == "DWELLING" for r in report["cycles"])


def test_interlock_dropout_halts_before_change_and_never_resumes():
    control = example_control()
    control["toy_plant"]["interlock_ok"][2] = False
    report = simulate_control(control)
    assert report["status"] == "HALTED"
    assert len(report["cycles"]) == 3
    assert report["cycles"][-1]["cycle"] == 2
    assert report["cycles"][-1]["parameter"] == report["cycles"][-2]["parameter_after"]
    assert report["final_quantity"] == report["cycles"][-2]["quantity_after"]


def test_divergent_toy_gain_leaves_domain_and_halts():
    control = example_control()
    control["toy_plant"]["actual_gain_per_parameter"] = 0.1
    report = simulate_control(control)
    assert report["status"] == "HALTED"
    assert report["cycles"][-1]["reason"] == "TOY_PLANT_OUTSIDE_RESPONSE_DOMAIN"
    assert len(report["cycles"]) == 1


def test_interlock_and_cycle_count_reject_non_boolean_or_boolean_integer():
    control = example_control()
    control["toy_plant"]["interlock_ok"][0] = 1
    with pytest.raises(ValueError):
        validate_control(control)
    control = example_control()
    control["toy_plant"]["cycles"] = True
    with pytest.raises(ValueError):
        validate_control(control)


@pytest.mark.parametrize("process", [None, [], {}, True, "unknown"])
def test_process_membership_refuses_bad_types_without_type_error(process):
    model, control = example_model(), example_control()
    model["process"] = control["process"] = process
    with pytest.raises(ValueError):
        validate_model(model)
    with pytest.raises(ValueError):
        validate_control(control)
