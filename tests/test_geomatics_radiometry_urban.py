import copy
import json
import math

import pytest

from net_geomatics import radiometry as r
from net_geomatics import urban as u


def test_planck_thermal_infrared_reference_and_inverse():
    result = r.planck({"wavelength_um": 10.0, "temperature_k": 300.0})
    assert result["spectral_radiance_w_m2_sr_um"] == pytest.approx(9.924033330070701, rel=2e-13)
    assert result["unit"] == "W m^-2 sr^-1 um^-1"
    assert not result["underflow"]
    inverse = r.brightness_temperature({
        "wavelength_um": 10.0,
        "spectral_radiance_w_m2_sr_um": result["spectral_radiance_w_m2_sr_um"],
    })
    assert inverse["brightness_temperature_k"] == pytest.approx(300.0, rel=1e-13)
    assert any("not land surface temperature" in item for item in inverse["limitations"])


@pytest.mark.parametrize("wavelength,temperature", [(0.5, 5778), (1000, 10), (1e10, 1e10)])
def test_planck_round_trip_across_spectral_regimes(wavelength, temperature):
    radiance = r.planck({"wavelength_um": wavelength, "temperature_k": temperature})[
        "spectral_radiance_w_m2_sr_um"]
    inverse = r.brightness_temperature({
        "wavelength_um": wavelength, "spectral_radiance_w_m2_sr_um": radiance})
    assert inverse["brightness_temperature_k"] == pytest.approx(temperature, rel=2e-13)


def test_planck_extreme_wien_underflow_explicit_and_not_invertible():
    result = r.planck({"wavelength_um": 1e-100, "temperature_k": 1e-100})
    assert result["underflow"]
    assert result["spectral_radiance_w_m2_sr_um"] == 0.0
    with pytest.raises(ValueError):
        r.brightness_temperature({"wavelength_um": 10, "spectral_radiance_w_m2_sr_um": 0})


def test_planck_minimum_positive_float_does_not_divide_by_zero():
    result = r.planck({"wavelength_um": 5e-324, "temperature_k": 5e-324})
    assert result["underflow"]


def test_planck_result_overflow_rejected():
    with pytest.raises(ValueError, match="overflow"):
        r.planck({"wavelength_um": 1e-97, "temperature_k": 1e100})


@pytest.mark.parametrize("bad", [True, False, 0, -1, float("inf"), float("nan"), "300", None])
def test_radiometry_rejects_invalid_positive_physical_inputs(bad):
    with pytest.raises(ValueError):
        r.planck({"wavelength_um": 10, "temperature_k": bad})
    with pytest.raises(ValueError):
        r.brightness_temperature({"wavelength_um": 10, "spectral_radiance_w_m2_sr_um": bad})
    with pytest.raises(ValueError):
        r.transmission({"optical_depth": 0.5, "air_mass": bad})


def test_direct_beam_analytic_values_and_inverse():
    result = r.transmission({"optical_depth": math.log(2), "air_mass": 2})
    assert result["transmittance"] == pytest.approx(0.25)
    inverse = r.optical_depth({"transmittance": result["transmittance"], "air_mass": 2})
    assert inverse["optical_depth"] == pytest.approx(math.log(2))
    assert r.transmission({"optical_depth": 0, "air_mass": 2})["transmittance"] == 1
    assert r.optical_depth({"transmittance": 1, "air_mass": 2})["optical_depth"] == 0


def test_transmission_underflow_is_labeled_and_zero_inverse_rejected():
    result = r.transmission({"optical_depth": 1000, "air_mass": 1})
    assert result["transmittance"] == 0 and result["underflow"]
    with pytest.raises(ValueError):
        r.optical_depth({"transmittance": 0, "air_mass": 1})


@pytest.mark.parametrize("bad", [-1, True, float("nan"), float("inf"), "1"])
def test_transmission_invalid_optical_depth(bad):
    with pytest.raises(ValueError):
        r.transmission({"optical_depth": bad, "air_mass": 1})


@pytest.mark.parametrize("bad", [0, -0.1, 1.001, True, float("inf"), float("nan")])
def test_optical_depth_invalid_transmittance(bad):
    with pytest.raises(ValueError):
        r.optical_depth({"transmittance": bad, "air_mass": 1})


def test_optical_depth_overflow_rejected():
    with pytest.raises(ValueError, match="overflow"):
        r.optical_depth({"transmittance": 1e-200, "air_mass": 5e-324})


def test_urban_aggregate_uses_sum_of_denominators():
    result = u.indicators(copy.deepcopy(u.EXAMPLES["geomatics.urban.indicators.v1"]))
    assert result["areas"][0]["population_density_per_km2"] == 500
    assert result["areas"][0]["event_rate"] == 25
    assert result["totals"]["population_density_per_km2"] == 600
    assert result["totals"]["event_rate"] == 20
    assert result["totals"]["population"] == 1500


def test_urban_zero_denominators_are_undefined():
    result = u.indicators({"rows": [
        {"area_id": "zero", "population": 0, "area_km2": 0, "event_count": 0}], "rate_per": 1000})
    assert result["areas"][0]["event_rate"] is None
    assert result["areas"][0]["population_density_per_km2"] is None
    assert result["totals"]["event_rate_status"] == "undefined_zero_population"
    assert result["totals"]["density_status"] == "undefined_zero_area"


def test_urban_nonzero_events_with_zero_population_remain_undefined():
    result = u.indicators({"rows": [
        {"area_id": "zero", "population": 0, "area_km2": 5, "event_count": 10}], "rate_per": 1000})
    assert result["totals"]["event_rate"] is None
    assert result["totals"]["population_density_per_km2"] == 0


def test_accessibility_is_population_weighted_and_cutoff_inclusive():
    result = u.accessibility({"rows": [
        {"area_id": "a", "population": 100, "travel_times_min": [10, 20]},
        {"area_id": "b", "population": 300, "travel_times_min": [30, None]},
        {"area_id": "c", "population": 600, "travel_times_min": [None, None]},
    ], "cutoff_min": 10})
    assert result["served_fraction"] == 0.1
    assert result["reachable_population"] == 400
    assert result["mean_nearest_time_reachable_min"] == 25
    assert result["areas"][2]["nearest_time_min"] is None
    assert not result["areas"][2]["served"]


def test_accessibility_empty_population_and_unreachable_mean():
    result = u.accessibility({"rows": [
        {"area_id": "a", "population": 0, "travel_times_min": [None]},
    ], "cutoff_min": 0})
    assert result["served_fraction"] is None
    assert result["served_fraction_status"] == "undefined_zero_population"
    assert result["mean_nearest_time_reachable_min"] is None


def test_accessibility_zero_time_and_cutoff_are_valid():
    result = u.accessibility({"rows": [
        {"area_id": "a", "population": 2, "travel_times_min": [0]},
    ], "cutoff_min": 0})
    assert result["served_fraction"] == 1
    assert result["mean_nearest_time_reachable_min"] == 0


@pytest.mark.parametrize("field,bad", [("population", True), ("population", -1),
    ("population", 1.2), ("population", 2**53), ("area_km2", -1), ("event_count", 0.5),
    ("event_count", float("nan")), ("area_km2", float("inf"))])
def test_urban_invalid_numeric_fields(field, bad):
    params = copy.deepcopy(u.EXAMPLES["geomatics.urban.indicators.v1"])
    params["rows"][0][field] = bad
    with pytest.raises(ValueError):
        u.indicators(params)


@pytest.mark.parametrize("bad", [True, -1, float("nan"), float("inf"), "10"])
def test_accessibility_invalid_times(bad):
    params = copy.deepcopy(u.EXAMPLES["geomatics.urban.accessibility.v1"])
    params["rows"][0]["travel_times_min"][0] = bad
    with pytest.raises(ValueError):
        u.accessibility(params)


@pytest.mark.parametrize("operation", list(u.OPERATIONS))
def test_urban_unique_areas_and_nonempty_rows(operation):
    params = copy.deepcopy(u.EXAMPLES[operation])
    params["rows"][1]["area_id"] = params["rows"][0]["area_id"]
    with pytest.raises(ValueError, match="Duplicate"):
        u.OPERATIONS[operation](params)
    params["rows"] = []
    with pytest.raises(ValueError):
        u.OPERATIONS[operation](params)


def test_accessibility_rejects_ragged_or_empty_matrix():
    params = copy.deepcopy(u.EXAMPLES["geomatics.urban.accessibility.v1"])
    params["rows"][0]["travel_times_min"] = [1]
    with pytest.raises(ValueError, match="rectangular"):
        u.accessibility(params)
    params["rows"][0]["travel_times_min"] = []
    with pytest.raises(ValueError):
        u.accessibility(params)


@pytest.mark.parametrize("module", [r, u])
def test_examples_are_immutable_deterministic_json_and_reject_extra_fields(module):
    for operation, example in module.EXAMPLES.items():
        params = copy.deepcopy(example)
        result = module.OPERATIONS[operation](params)
        assert params == example
        assert result == module.OPERATIONS[operation](params)
        json.dumps(result, allow_nan=False)
        params["unexpected"] = True
        with pytest.raises(ValueError):
            module.OPERATIONS[operation](params)


@pytest.mark.parametrize("module", [r, u])
def test_output_validators_accept_examples_and_reject_empty_or_missing_output(module):
    for operation, params in module.EXAMPLES.items():
        result = module.OPERATIONS[operation](params)
        module.OUTPUT_VALIDATORS[operation](params, result)
        for malformed in ({}, {"result": result}, None, []):
            with pytest.raises(ValueError):
                module.OUTPUT_VALIDATORS[operation](params, malformed)
        altered = copy.deepcopy(result)
        altered.pop("limitations")
        with pytest.raises(ValueError):
            module.OUTPUT_VALIDATORS[operation](params, altered)


@pytest.mark.parametrize("operation,field", [
    ("geomatics.radiometry.planck.v1", "spectral_radiance_w_m2_sr_um"),
    ("geomatics.radiometry.brightness-temperature.v1", "brightness_temperature_k"),
    ("geomatics.atmosphere.transmission.v1", "transmittance"),
    ("geomatics.atmosphere.optical-depth.v1", "optical_depth"),
])
@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), -1, 1e151, None, []])
def test_radiometry_retained_scalar_contract(operation, field, bad):
    params = r.EXAMPLES[operation]
    result = r.OPERATIONS[operation](params)
    result[field] = bad
    with pytest.raises(ValueError):
        r.OUTPUT_VALIDATORS[operation](params, result)


@pytest.mark.parametrize("operation", list(u.OPERATIONS))
def test_urban_retained_rows_and_identities_must_match_parameters(operation):
    params = u.EXAMPLES[operation]
    original = u.OPERATIONS[operation](params)
    for replacement in ([], {}, [original["areas"][0]]):
        result = copy.deepcopy(original)
        result["areas"] = replacement
        with pytest.raises(ValueError):
            u.OUTPUT_VALIDATORS[operation](params, result)
    result = copy.deepcopy(original)
    result["areas"][0]["area_id"] = "different"
    with pytest.raises(ValueError):
        u.OUTPUT_VALIDATORS[operation](params, result)
    result = copy.deepcopy(original)
    result["areas"][0]["population"] = True
    with pytest.raises(ValueError):
        u.OUTPUT_VALIDATORS[operation](params, result)


def test_zero_denominator_status_and_null_values_validated_without_execution():
    params = {"rows": [{"area_id": "zero", "population": 0, "area_km2": 0, "event_count": 0}], "rate_per": 1000}
    output = u.indicators(params)
    u.validate_indicators(params, output)
    output["areas"][0]["event_rate"] = 0
    with pytest.raises(ValueError):
        u.validate_indicators(params, output)


def test_retained_underflow_flag_and_unit_are_validated():
    params = r.EXAMPLES["geomatics.radiometry.planck.v1"]
    output = r.planck(params)
    output["underflow"] = True
    with pytest.raises(ValueError):
        r.validate_planck(params, output)
    output = r.planck(params)
    output["unit"] = "W m^-2 sr^-1 m^-1"
    with pytest.raises(ValueError):
        r.validate_planck(params, output)


def test_accessibility_retained_nearest_value_and_summary_shape():
    params = u.EXAMPLES["geomatics.urban.accessibility.v1"]
    output = u.accessibility(params)
    output["areas"][0]["nearest_time_min"] = 12
    with pytest.raises(ValueError):
        u.validate_accessibility(params, output)
    output = u.accessibility(params)
    output["served_fraction"] = 2
    with pytest.raises(ValueError):
        u.validate_accessibility(params, output)
