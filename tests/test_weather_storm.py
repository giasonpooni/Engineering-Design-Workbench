"""Analytic examples, numerical invariants, and hostile result/input cases."""
from copy import deepcopy
import math

import pytest

from ciw import weather_storm as storm


def example(profile):
    return deepcopy(storm.PROFILES[profile]["example"])


def sounding(z, offsets):
    return {
        "height_m": z,
        "environment_virtual_temperature_k": [300] * len(z),
        "parcel_virtual_temperature_k": [300 + offset for offset in offsets],
        "eastward_wind_m_s": [0] * (len(z) - 1) + [3],
        "northward_wind_m_s": [0] * (len(z) - 1) + [4],
    }


@pytest.mark.parametrize("profile", storm.PROFILES)
def test_examples_obey_complete_output_contract(profile):
    inputs = example(profile)
    original = deepcopy(inputs)
    values = storm.compute(profile, inputs)
    assert set(values) == set(storm.PROFILES[profile]["units"])
    assert all(storm.checks(profile, inputs, values).values())
    assert inputs == original


@pytest.mark.parametrize("offset, positive, negative", [(3, 98.0665, 0), (-3, 0, -98.0665), (0, 0, 0)])
def test_constant_buoyancy_and_three_four_five_shear(offset, positive, negative):
    inputs = sounding([100, 1100], [offset, offset])
    values = storm.compute("storm_sounding", inputs)
    assert values["buoyancy_m_s2"] == pytest.approx([0.03268883333333333 * offset] * 2)
    assert values["positive_buoyancy_integral_j_kg"] == pytest.approx(positive)
    assert values["negative_buoyancy_integral_j_kg"] == pytest.approx(negative)
    assert values["bulk_shear_m_s"] == 5
    assert values["layer_depth_m"] == 1000
    assert all(storm.checks("storm_sounding", inputs, values).values())


@pytest.mark.parametrize("offsets", [[-3, 6], [6, -3]])
def test_asymmetric_zero_crossing_integrates_triangles_exactly(offsets):
    inputs = sounding([0, 900], offsets)
    values = storm.compute("storm_sounding", inputs)
    # Zero is 300 m from the -3 K end: areas 1/2 * base * buoyancy.
    assert values["positive_buoyancy_integral_j_kg"] == pytest.approx(58.8399)
    assert values["negative_buoyancy_integral_j_kg"] == pytest.approx(-14.709975)
    assert values["net_buoyancy_integral_j_kg"] == pytest.approx(44.129925)
    assert all(storm.checks("storm_sounding", inputs, values).values())


def test_multiple_zero_crossings_and_neutral_plateau():
    inputs = sounding([0, 100, 200, 300, 400, 500], [-3, 3, 0, 0, -3, 3])
    values = storm.compute("storm_sounding", inputs)
    assert values["positive_buoyancy_integral_j_kg"] == pytest.approx(9.80665)
    assert values["negative_buoyancy_integral_j_kg"] == pytest.approx(-9.80665)
    assert values["net_buoyancy_integral_j_kg"] == pytest.approx(0)
    assert all(storm.checks("storm_sounding", inputs, values).values())


def test_forecast_reference_scores():
    inputs = {"forecast_k": [282, 278, 284], "observation_k": [280, 280, 280], "persistence_k": [281, 281, 281]}
    values = storm.compute("forecast_verification", inputs)
    assert values == pytest.approx({"bias_k": 4 / 3, "mae_k": 8 / 3, "rmse_k": math.sqrt(8),
                                    "persistence_rmse_k": 1, "mse_improvement_k2": -7})


@pytest.mark.parametrize("forecast, improvement", [([280, 280], 0), ([282, 278], -4)])
def test_zero_error_persistence_is_defined_without_skill_division(forecast, improvement):
    inputs = {"forecast_k": forecast, "observation_k": [280, 280], "persistence_k": [280, 280]}
    values = storm.compute("forecast_verification", inputs)
    assert values["persistence_rmse_k"] == 0
    assert values["mse_improvement_k2"] == improvement
    assert all(storm.checks("forecast_verification", inputs, values).values())


def test_forecast_paired_translation_invariance():
    inputs = example("forecast_verification")
    shifted = {key: [x + 30 for x in value] for key, value in inputs.items()}
    assert storm.compute("forecast_verification", shifted) == storm.compute("forecast_verification", inputs)


def test_nearly_equal_large_errors_do_not_falsely_fail_mse_closure():
    inputs = {"forecast_k": [388] * 6, "observation_k": [100] * 6,
              "persistence_k": [388 - 1e-12] * 6}
    values = storm.compute("forecast_verification", inputs)
    assert values["mse_improvement_k2"] < 0
    assert all(storm.checks("forecast_verification", inputs, values).values())


@pytest.mark.parametrize("profile", storm.PROFILES)
def test_every_output_is_independently_checked(profile, monkeypatch):
    inputs = example(profile)
    values = storm.compute(profile, inputs)
    monkeypatch.setattr(storm, "compute", lambda *args: pytest.fail("Checks invoked producer"))
    assert all(storm.checks(profile, inputs, values).values())
    for name in values:
        corrupted = deepcopy(values)
        if type(corrupted[name]) is list:
            for index in range(len(corrupted[name])):
                wrong = deepcopy(values)
                wrong[name][index] += 1
                assert not all(storm.checks(profile, inputs, wrong).values()), (name, index)
        else:
            corrupted[name] += 1
            assert not all(storm.checks(profile, inputs, corrupted).values()), name


@pytest.mark.parametrize("profile", storm.PROFILES)
@pytest.mark.parametrize("bad", [None, True, "1", float("nan"), float("inf"), -float("inf")])
def test_malformed_output_is_rejected(profile, bad):
    inputs = example(profile)
    values = storm.compute(profile, inputs)
    for name in values:
        wrong = deepcopy(values)
        wrong[name] = bad
        assert not all(storm.checks(profile, inputs, wrong).values())


@pytest.mark.parametrize("profile", storm.PROFILES)
def test_output_keys_and_lengths_are_exact(profile):
    inputs = example(profile)
    values = storm.compute(profile, inputs)
    for name in values:
        wrong = deepcopy(values)
        del wrong[name]
        assert not all(storm.checks(profile, inputs, wrong).values())
    values["invented"] = 0
    assert not all(storm.checks(profile, inputs, values).values())
    if profile == "storm_sounding":
        for vector in ([], [0], [0] * 65, [False] * 4, [float("nan")] * 4):
            values = storm.compute(profile, inputs)
            values["buoyancy_m_s2"] = vector
            assert not all(storm.checks(profile, inputs, values).values())


@pytest.mark.parametrize("profile", storm.PROFILES)
@pytest.mark.parametrize("bad", [None, True, "280", (), [], [float("nan")], [float("inf")], [True], [280] * 65])
def test_strict_input_types_and_budget(profile, bad):
    for name in example(profile):
        inputs = example(profile)
        inputs[name] = bad
        with pytest.raises(ValueError):
            storm.compute(profile, inputs)


@pytest.mark.parametrize("profile", storm.PROFILES)
def test_inputs_require_exact_keys_and_equal_lengths(profile):
    inputs = example(profile)
    inputs["extra"] = 1
    with pytest.raises(ValueError):
        storm.validate(profile, inputs)
    for name in example(profile):
        inputs = example(profile)
        del inputs[name]
        with pytest.raises(ValueError):
            storm.validate(profile, inputs)
        inputs = example(profile)
        inputs[name] = inputs[name][:-1]
        with pytest.raises(ValueError):
            storm.validate(profile, inputs)


@pytest.mark.parametrize("height", [[100, 100], [100, 0], [-1, 0], [0, 50001]])
def test_invalid_heights(height):
    with pytest.raises(ValueError):
        storm.validate("storm_sounding", sounding(height, [0, 0]))


@pytest.mark.parametrize("profile", storm.PROFILES)
def test_physical_input_bounds(profile):
    for name in example(profile):
        if name == "height_m":
            continue
        for value in (-201, 401):
            inputs = example(profile)
            inputs[name][0] = value
            with pytest.raises(ValueError):
                storm.validate(profile, inputs)


@pytest.mark.parametrize("profile", [None, True, 1, [], "unknown"])
def test_unknown_profile(profile):
    with pytest.raises(ValueError):
        storm.validate(profile, {})
