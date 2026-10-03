"""Boundary and independent analytical checks for bounded thermofluid models."""
from copy import deepcopy
import math

import pytest

from ciw.thermofluids_models import (
    OUTPUT_UNITS, PROFILES, calculate, example_request, validate_request,
)


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_examples_have_strict_semantics_and_finite_si_outputs(profile):
    request = example_request(profile)
    assert set(request) == {"schema", "profile", "input_semantics", "parameters"}
    assert request["schema"] == "ciw.thermofluids-request.v1"
    assert request["profile"] == profile
    assert request["input_semantics"] == "synthetic"
    before = deepcopy(request)
    validate_request(request)
    result = calculate(request)
    assert request == before
    assert set(result) == {"quantities", "assumptions", "limitations"}
    assert result["assumptions"] == PROFILES[profile]["assumptions"]
    assert result["limitations"] == PROFILES[profile]["limitations"]
    assert set(result["quantities"]) == set(OUTPUT_UNITS[profile])
    for name, quantity in result["quantities"].items():
        assert set(quantity) == {"value", "unit"}
        assert type(quantity["value"]) in (int, float)
        assert math.isfinite(quantity["value"])
        assert abs(quantity["value"]) <= 1e150
        assert quantity["unit"] == OUTPUT_UNITS[profile][name]


@pytest.mark.parametrize("profile", sorted(PROFILES))
@pytest.mark.parametrize("bad", [True, False, float("inf"), float("nan"), "1.0", None])
def test_all_numeric_parameter_fields_reject_non_numbers(profile, bad):
    example = example_request(profile)
    fields = [key for key, value in example["parameters"].items()
              if type(value) in (int, float)]
    assert fields
    for key in fields:
        candidate = deepcopy(example)
        candidate["parameters"][key] = bad
        with pytest.raises(ValueError):
            validate_request(candidate)


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_each_parameter_is_required_and_unknown_fields_refused(profile):
    example = example_request(profile)
    for key in example["parameters"]:
        candidate = deepcopy(example)
        del candidate["parameters"][key]
        with pytest.raises(ValueError):
            validate_request(candidate)
    for container in (None, "parameters"):
        candidate = deepcopy(example)
        target = candidate if container is None else candidate[container]
        target["unexpected"] = 1.0
        with pytest.raises(ValueError):
            validate_request(candidate)


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_examples_and_result_metadata_are_detached(profile):
    first, second = example_request(profile), example_request(profile)
    key = next(iter(first["parameters"]))
    first["parameters"][key] = "changed"
    assert second == example_request(profile)
    result = calculate(second)
    result["assumptions"].append("changed")
    result["limitations"].append("changed")
    assert "changed" not in PROFILES[profile]["assumptions"]
    assert "changed" not in PROFILES[profile]["limitations"]


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_declared_inputs_are_supported_but_observation_claims_are_not(profile):
    request = example_request(profile)
    request["input_semantics"] = "declared"
    validate_request(request)
    for semantics in ("observed", "validated", "estimated", [], None, True):
        request["input_semantics"] = semantics
        with pytest.raises(ValueError):
            validate_request(request)


@pytest.mark.parametrize("bad", ["bogus", None, [], {}, True])
def test_unknown_profile_is_value_error(bad):
    with pytest.raises(ValueError):
        example_request(bad)
    request = example_request("convection")
    request["profile"] = bad
    with pytest.raises(ValueError):
        validate_request(request)


def values(request):
    return {key: quantity["value"] for key, quantity in calculate(request)["quantities"].items()}


@pytest.mark.parametrize("boundary,nu", [("constant-wall-temperature", 3.66),
                                        ("constant-wall-heat-flux", 48.0 / 11.0)])
def test_convection_reference_values_and_signed_local_flux(boundary, nu):
    request = example_request("convection")
    p = request["parameters"]
    p["boundary_condition"] = boundary
    result = values(request)
    assert result["reynolds"] == pytest.approx(1000.0)
    assert result["prandtl"] == pytest.approx(7.0)
    assert result["peclet"] == pytest.approx(7000.0)
    assert result["nusselt"] == pytest.approx(nu)
    assert result["heat_transfer_coefficient"] == pytest.approx(60.0 * nu)
    assert result["wall_to_bulk_heat_flux"] == pytest.approx(600.0 * nu)
    p["wall_temperature_k"], p["bulk_temperature_k"] = 310.0, 320.0
    reverse = values(request)
    assert reverse["wall_to_bulk_heat_flux"] == pytest.approx(-result["wall_to_bulk_heat_flux"])
    assert reverse["heat_transfer_coefficient"] == result["heat_transfer_coefficient"]
    p["wall_temperature_k"] = p["bulk_temperature_k"]
    assert values(request)["wall_to_bulk_heat_flux"] == 0.0


def test_pipe_reference_pressure_shear_energy_and_darcy_convention():
    request = example_request("pipe-flow")
    result = values(request)
    assert result["reynolds"] == pytest.approx(1000.0)
    assert result["darcy_friction_factor"] == pytest.approx(0.064)
    assert result["pressure_drop"] == pytest.approx(64.0)
    assert result["wall_shear_stress"] == pytest.approx(0.08)
    assert result["centerline_velocity"] == pytest.approx(0.2)
    assert result["volume_flow_rate"] == pytest.approx(math.pi / 400000)
    p = request["parameters"]
    radius = p["diameter_m"] / 2.0
    # Independent momentum balance: pressure force equals integrated wall shear.
    assert result["pressure_drop"] * math.pi * radius**2 == pytest.approx(
        result["wall_shear_stress"] * 2 * math.pi * radius * p["length_m"])
    assert result["hydraulic_pumping_power"] == pytest.approx(
        result["pressure_drop"] * result["volume_flow_rate"])
    assert result["mass_flow_rate"] == pytest.approx(
        p["density_kg_m3"] * result["volume_flow_rate"])
    # Doubling the developed measurement length changes loss, not velocity or flow.
    p["length_m"] *= 2.0
    longer = values(request)
    assert longer["pressure_drop"] == pytest.approx(2 * result["pressure_drop"])
    assert longer["hydraulic_pumping_power"] == pytest.approx(2 * result["hydraulic_pumping_power"])
    assert longer["volume_flow_rate"] == result["volume_flow_rate"]
    assert longer["wall_shear_stress"] == result["wall_shear_stress"]


@pytest.mark.parametrize("profile", ["convection", "pipe-flow"])
@pytest.mark.parametrize("velocity", [0.0, 0.00001, 0.2000001, 1.0])
def test_laminar_reference_refuses_outside_reynolds_scope(profile, velocity):
    request = example_request(profile)
    request["parameters"]["mean_velocity_m_s"] = velocity
    with pytest.raises(ValueError):
        calculate(request)


@pytest.mark.parametrize("profile,key", [
    ("convection", "axial_distance_from_inlet_m"),
    ("convection", "heated_distance_to_section_m"),
    ("pipe-flow", "upstream_development_length_m"),
])
def test_development_distance_is_not_confused_with_measurement_length(profile, key):
    request = example_request(profile)
    request["parameters"][key] = 0.01
    if profile == "pipe-flow":
        request["parameters"]["length_m"] = 10000.0
    with pytest.raises(ValueError, match="development"):
        calculate(request)


@pytest.mark.parametrize("field,value", [
    ("conductivity_w_m_k", 100.0),  # Pr below allowed domain.
    ("conductivity_w_m_k", 0.0001),  # Pr above allowed domain.
    ("mean_velocity_m_s", 0.001),  # Re allowed, axial diffusion screen fails.
    ("heated_distance_to_section_m", 11.0),
    ("boundary_condition", "turbulent"),
    ("boundary_condition", []),
])
def test_convection_refuses_unqualified_regimes(field, value):
    request = example_request("convection")
    request["parameters"][field] = value
    with pytest.raises(ValueError):
        calculate(request)


@pytest.mark.parametrize("arrangement", ["counterflow", "parallel-flow"])
def test_exchanger_equal_capacity_limit_energy_balance_and_zero_ua(arrangement):
    request = example_request("heat-exchanger")
    p = request["parameters"]
    p["arrangement"] = arrangement
    result = values(request)
    expected_epsilon = 0.2 if arrangement == "counterflow" else (1.0 - math.exp(-0.5)) / 2.0
    assert result["capacity_ratio"] == 1.0
    assert result["ntu"] == 0.25
    assert result["effectiveness"] == pytest.approx(expected_epsilon)
    duty = result["heat_duty"]
    assert duty == pytest.approx(200000.0 * expected_epsilon)
    assert duty == pytest.approx(result["hot_capacity_rate"] * (350 - result["hot_outlet_temperature"]))
    assert duty == pytest.approx(result["cold_capacity_rate"] * (result["cold_outlet_temperature"] - 300))
    assert 300 <= result["hot_outlet_temperature"] <= 350
    assert 300 <= result["cold_outlet_temperature"] <= 350
    p["ua_w_k"] = 0.0
    inactive = values(request)
    assert inactive["heat_duty"] == 0.0
    assert inactive["effectiveness"] == 0.0
    assert inactive["hot_outlet_temperature"] == 350.0
    assert inactive["cold_outlet_temperature"] == 300.0


def test_counterflow_near_equal_capacity_is_continuous_and_matches_decimal_reference():
    from decimal import Decimal, localcontext
    request = example_request("heat-exchanger")
    request["parameters"]["cold_heat_capacity_j_kg_k"] = 4000.0 * (1 - 1e-12)
    result = values(request)
    with localcontext() as context:
        context.prec = 60
        ch = Decimal(4000)
        cc = Decimal.from_float(request["parameters"]["cold_heat_capacity_j_kg_k"])
        cr, ntu = cc / ch, Decimal(1000) / cc
        exponent = (-ntu * (1 - cr)).exp()
        epsilon = (1 - exponent) / (1 - cr * exponent)
    assert result["effectiveness"] == pytest.approx(float(epsilon), rel=2e-15)
    assert result["effectiveness"] == pytest.approx(0.2, abs=1e-12)


@pytest.mark.parametrize("arrangement", ["counterflow", "parallel-flow"])
def test_exchanger_unequal_capacities_high_ntu_limits_and_equal_inlet(arrangement):
    request = example_request("heat-exchanger")
    p = request["parameters"]
    p["arrangement"] = arrangement
    p["cold_mass_flow_kg_s"] = 0.5
    p["ua_w_k"] = 1e8
    result = values(request)
    expected = 1.0 if arrangement == "counterflow" else 2.0 / 3.0
    assert result["capacity_ratio"] == 0.5
    assert result["effectiveness"] == pytest.approx(expected)
    assert result["heat_duty"] <= 100000.0
    p["hot_inlet_temperature_k"] = 300.0
    isothermal = values(request)
    assert isothermal["heat_duty"] == 0.0
    assert isothermal["hot_outlet_temperature"] == isothermal["cold_outlet_temperature"] == 300.0


@pytest.mark.parametrize("field,value", [
    ("hot_inlet_temperature_k", 299.0), ("hot_mass_flow_kg_s", 0.0),
    ("cold_heat_capacity_j_kg_k", -1.0), ("ua_w_k", -1.0),
    ("ua_w_k", 1e12), ("arrangement", "crossflow"), ("arrangement", []),
])
def test_exchanger_invalid_and_unsupported_cases_fail(field, value):
    request = example_request("heat-exchanger")
    request["parameters"][field] = value
    with pytest.raises(ValueError):
        calculate(request)


def test_radiation_blackbody_graybody_reversal_area_and_equilibrium():
    request = example_request("radiation")
    p = request["parameters"]
    p.update(surface_1_temperature_k=400.0, surface_2_temperature_k=300.0,
             emissivity_1=1.0, emissivity_2=1.0, area_m2=2.0)
    black = values(request)
    expected_flux = 5.670374419e-8 * (400.0**4 - 300.0**4)
    assert black["net_heat_flux"] == pytest.approx(expected_flux)
    assert black["net_heat_rate"] == pytest.approx(2 * expected_flux)
    assert black["effective_emissivity"] == 1.0
    p.update(emissivity_1=0.5, emissivity_2=0.5)
    gray = values(request)
    assert gray["effective_emissivity"] == pytest.approx(1 / 3)
    assert gray["net_heat_flux"] == pytest.approx(expected_flux / 3)
    p.update(surface_1_temperature_k=300.0, surface_2_temperature_k=400.0)
    assert values(request)["net_heat_rate"] == pytest.approx(-gray["net_heat_rate"])
    p["surface_2_temperature_k"] = 300.0
    equilibrium = values(request)
    assert equilibrium["net_heat_flux"] == 0.0
    assert equilibrium["radiative_heat_transfer_coefficient"] == pytest.approx(
        (1 / 3) * 4 * 5.670374419e-8 * 300**3)


@pytest.mark.parametrize("field,value", [
    ("surface_1_temperature_k", 0.0), ("surface_2_temperature_k", -273.15),
    ("emissivity_1", 0.0), ("emissivity_2", 1.01), ("area_m2", 0.0),
])
def test_radiation_refuses_non_absolute_or_invalid_inputs(field, value):
    request = example_request("radiation")
    request["parameters"][field] = value
    with pytest.raises(ValueError):
        calculate(request)


def test_radiation_tiny_temperature_difference_retains_sign_and_nonzero_flux():
    request = example_request("radiation")
    p = request["parameters"]
    p.update(surface_1_temperature_k=300.0, surface_2_temperature_k=math.nextafter(300.0, 0.0))
    result = values(request)
    assert result["net_heat_flux"] > 0.0
    assert result["net_heat_flux"] == result["radiative_heat_transfer_coefficient"] * (
        p["surface_1_temperature_k"] - p["surface_2_temperature_k"])


@pytest.mark.parametrize("quality", [0.0, 0.1, 0.5, 1.0])
def test_homogeneous_mixture_mass_volume_and_enthalpy_endpoints(quality):
    request = example_request("two-phase")
    p = request["parameters"]
    p.update(quality_in=quality, quality_out=quality)
    result = values(request)
    assert result["heat_duty"] == 0.0
    alpha = result["outlet_void_fraction"]
    rho = result["outlet_mixture_density"]
    assert 0 <= alpha <= 1
    assert p["vapor_density_kg_m3"] * (1 - 1e-14) <= rho <= p["liquid_density_kg_m3"] * (1 + 1e-14)
    # Unit mixture volume: constituent masses recover the prescribed mass quality.
    vapor_mass = alpha * p["vapor_density_kg_m3"]
    liquid_mass = (1 - alpha) * p["liquid_density_kg_m3"]
    assert vapor_mass + liquid_mass == pytest.approx(rho)
    assert vapor_mass / (vapor_mass + liquid_mass) == pytest.approx(quality)
    assert result["outlet_specific_enthalpy"] == pytest.approx(
        p["liquid_enthalpy_j_kg"] + quality * result["latent_enthalpy"])
    if quality == 0:
        assert alpha == 0.0
        assert rho == pytest.approx(p["liquid_density_kg_m3"])
    if quality == 1:
        assert alpha == 1.0
        assert rho == pytest.approx(p["vapor_density_kg_m3"])


def test_two_phase_latent_duty_condensation_and_enthalpy_reference_invariance():
    request = example_request("two-phase")
    p = request["parameters"]
    result = values(request)
    assert result["latent_enthalpy"] == 2257000.0
    assert result["heat_duty"] == pytest.approx(45140.0)
    assert result["heat_duty"] == pytest.approx(p["mass_flow_kg_s"] * (
        result["outlet_specific_enthalpy"] - result["inlet_specific_enthalpy"]))
    p["quality_in"], p["quality_out"] = p["quality_out"], p["quality_in"]
    assert values(request)["heat_duty"] == pytest.approx(-result["heat_duty"])
    p["liquid_enthalpy_j_kg"] -= 1e6
    p["vapor_enthalpy_j_kg"] -= 1e6
    shifted = values(request)
    assert shifted["heat_duty"] == pytest.approx(-result["heat_duty"])
    assert shifted["latent_enthalpy"] == result["latent_enthalpy"]


@pytest.mark.parametrize("field,value", [
    ("quality_in", -0.01), ("quality_out", 1.01),
    ("liquid_density_kg_m3", 0.598), ("vapor_density_kg_m3", 1000.0),
    ("liquid_enthalpy_j_kg", 2676000.0), ("vapor_enthalpy_j_kg", 418999.0),
    ("mass_flow_kg_s", 0.0), ("saturation_pressure_pa", 0.0),
])
def test_two_phase_refuses_noncoexisting_order_or_out_of_saturation_interval(field, value):
    request = example_request("two-phase")
    request["parameters"][field] = value
    with pytest.raises(ValueError):
        calculate(request)
