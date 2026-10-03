from copy import deepcopy
import math

import pytest

from ciw.weather_dynamics import PROFILES, checks, compute, validate


def example(profile, **changes):
    result = deepcopy(PROFILES[profile]["example"])
    result.update(changes)
    return result


@pytest.mark.parametrize("profile", PROFILES)
def test_examples_have_complete_units_and_independent_checks(profile):
    inputs = example(profile)
    result = compute(profile, inputs)
    assert set(result) == set(PROFILES[profile]["units"])
    assert all(checks(profile, inputs, result).values())


def test_geostrophic_signs_and_analytic_values_in_both_hemispheres():
    north = compute("synoptic", example("synoptic", latitude_deg=30.0,
                    pressure_gradient_east_pa_m=0.0, pressure_gradient_north_pa_m=-0.001,
                    density_kg_m3=1.0))
    assert north["coriolis_s1"] == pytest.approx(7.292115e-5)
    assert north["geostrophic_east_m_s"] == pytest.approx(0.001 / 7.292115e-5)
    assert north["geostrophic_north_m_s"] == 0.0
    south = compute("synoptic", example("synoptic", latitude_deg=-30.0,
                    pressure_gradient_east_pa_m=0.0, pressure_gradient_north_pa_m=-0.001,
                    density_kg_m3=1.0))
    assert south["geostrophic_east_m_s"] == -north["geostrophic_east_m_s"]


def test_solid_body_rotation_and_temperature_advection():
    # u=-omega*y and v=omega*x -> curl=2*omega, div=0.
    result = compute("synoptic", example("synoptic", du_dx_s1=0.0, dv_dy_s1=0.0,
                     du_dy_s1=-0.0001, dv_dx_s1=0.0001, wind_east_m_s=10.0,
                     wind_north_m_s=5.0, temperature_gradient_east_k_m=0.001,
                     temperature_gradient_north_k_m=-0.002))
    assert result["divergence_s1"] == 0.0
    assert result["relative_vorticity_s1"] == pytest.approx(0.0002)
    assert result["temperature_advection_k_s"] == 0.0
    assert result["wind_speed_m_s"] == pytest.approx(math.sqrt(125.0))


@pytest.mark.parametrize("profile", PROFILES)
def test_each_reported_output_is_independently_checked(profile):
    inputs = example(profile)
    original = compute(profile, inputs)
    for name in original:
        changed = deepcopy(original)
        if isinstance(changed[name], list):
            changed[name][0] += 0.125
        else:
            changed[name] += max(0.125, abs(changed[name]) * 0.01)
        assert not all(checks(profile, inputs, changed).values()), name


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("bad", [True, "1", None, float("nan"), float("inf")])
def test_scalar_type_refusal(profile, bad):
    field = "latitude_deg" if profile == "synoptic" else "velocity_m_s"
    with pytest.raises(ValueError):
        validate(profile, example(profile, **{field: bad}))


@pytest.mark.parametrize("latitude", [0, 4.999, -4.999, 90, -90])
def test_geostrophic_excludes_equatorial_and_pole_singular_scope(latitude):
    with pytest.raises(ValueError):
        validate("synoptic", example("synoptic", latitude_deg=latitude))


@pytest.mark.parametrize("changes", [
    {"density_kg_m3": 0}, {"density_kg_m3": 2.1},
    {"pressure_gradient_east_pa_m": 0.02}, {"wind_north_m_s": 301},
    {"du_dy_s1": 0.02}, {"temperature_gradient_north_k_m": -0.02},
])
def test_synoptic_scope_bounds(changes):
    with pytest.raises(ValueError):
        validate("synoptic", example("synoptic", **changes))


@pytest.mark.parametrize("profile", PROFILES)
def test_missing_and_extra_fields_refused(profile):
    inputs = example(profile)
    with pytest.raises(ValueError):
        validate(profile, {**inputs, "unknown": 3})
    del inputs[next(iter(inputs))]
    with pytest.raises(ValueError):
        validate(profile, inputs)


@pytest.mark.parametrize("u", [1.0, -1.0])
def test_cfl_one_is_exact_periodic_translation(u):
    initial = [0.0, 1.0, 4.0, 2.0, 0.5]
    inputs = example("nwp_transport", initial_scalar=initial, velocity_m_s=u,
                     cell_width_m=1.0, time_step_s=1.0, steps=7)
    result = compute("nwp_transport", inputs)
    expected = [initial[(i - int(u) * 7) % len(initial)] for i in range(len(initial))]
    assert result["final_scalar"] == expected
    assert result["numerical_diffusivity_m2_s"] == 0.0
    assert all(checks("nwp_transport", inputs, result).values())


@pytest.mark.parametrize("changes", [{"velocity_m_s": 0.0}, {"steps": 0}])
def test_zero_velocity_or_zero_steps_preserves_initial_field(changes):
    inputs = example("nwp_transport", **changes)
    result = compute("nwp_transport", inputs)
    assert result["final_scalar"] == inputs["initial_scalar"]
    assert all(checks("nwp_transport", inputs, result).values())


@pytest.mark.parametrize("u", [-3.0, 3.0])
def test_top_hat_conservation_positivity_and_total_variation_at_maximum_steps(u):
    inputs = example("nwp_transport", initial_scalar=[0.0] * 32 + [1.0] * 64 + [0.0] * 32,
                     velocity_m_s=u, cell_width_m=1.0, time_step_s=0.1, steps=500)
    result = compute("nwp_transport", inputs)
    assert result["tracer_integral_final_m"] == pytest.approx(64.0, rel=1e-12)
    assert 0 <= min(result["final_scalar"]) <= max(result["final_scalar"]) <= 1
    assert result["total_variation_final"] <= 2.0
    assert all(checks("nwp_transport", inputs, result).values())


def test_smooth_periodic_solution_converges_at_first_order():
    errors = []
    # One physical period, CFL=1/2, refine dx and dt together.
    for count in (16, 32, 64, 128):
        initial = [1.0 + 0.5 * math.sin(2 * math.pi * (i + 0.5) / count) for i in range(count)]
        inputs = example("nwp_transport", initial_scalar=initial, velocity_m_s=1.0,
                         cell_width_m=1.0 / count, time_step_s=0.5 / count, steps=2 * count)
        result = compute("nwp_transport", inputs)
        errors.append(math.sqrt(math.fsum((a - b) ** 2 for a, b in zip(initial, result["final_scalar"])) / count))
    assert all(1.65 < coarse / fine < 2.05 for coarse, fine in zip(errors, errors[1:]))


def test_nontrivial_fourier_mode_matches_discrete_amplification_factor():
    import cmath

    count, steps, c = 32, 13, 0.25
    phase = 2 * math.pi / count
    initial = [1 + 0.5 * math.cos(phase * j) for j in range(count)]
    inputs = example("nwp_transport", initial_scalar=initial, velocity_m_s=-1.0,
                     cell_width_m=1.0, time_step_s=c, steps=steps)
    result = compute("nwp_transport", inputs)
    amplification = (1 - c + c * cmath.exp(1j * phase)) ** steps
    expected = [1 + 0.5 * (amplification * cmath.exp(1j * phase * j)).real for j in range(count)]
    assert result["final_scalar"] == pytest.approx(expected, abs=1e-14)


def test_mass_preserving_permutation_tampering_is_detected():
    inputs = example("nwp_transport")
    result = compute("nwp_transport", inputs)
    # A cyclic permutation preserves extrema, TV and integral, but not the solution.
    result["final_scalar"] = result["final_scalar"][1:] + result["final_scalar"][:1]
    report = checks("nwp_transport", inputs, result)
    assert report["conservation"] and report["reported_extrema"] and report["reported_variation"]
    assert not report["discrete_binomial_reference"]


def test_near_cfl_one_diffusion_check_handles_dimensional_cancellation():
    velocity, dx = 43.967819424986374, 18206.10294422286
    inputs = example("nwp_transport", velocity_m_s=velocity, cell_width_m=dx,
                     time_step_s=0.999999999999 * dx / velocity, steps=20)
    result = compute("nwp_transport", inputs)
    assert result["numerical_diffusivity_m2_s"] < 1e-6
    assert all(checks("nwp_transport", inputs, result).values())


@pytest.mark.parametrize("changes", [
    {"initial_scalar": [0, 1]}, {"initial_scalar": [0] * 129},
    {"initial_scalar": [0, True, 1]}, {"initial_scalar": [-1, 0, 1]},
    {"initial_scalar": (0, 1, 2)}, {"initial_scalar": [0, 1, float("nan")]},
    {"velocity_m_s": 1001}, {"time_step_s": 0}, {"cell_width_m": 0},
    {"steps": 1.0}, {"steps": True}, {"steps": -1}, {"steps": 501},
    {"velocity_m_s": 20.0000001},
])
def test_transport_refuses_unsupported_inputs(changes):
    with pytest.raises(ValueError):
        validate("nwp_transport", example("nwp_transport", **changes))


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("corruption", ["missing", "extra", "bool", "nan"])
def test_checker_refuses_malformed_outputs(profile, corruption):
    inputs = example(profile)
    result = compute(profile, inputs)
    scalar_key = next(name for name in result if name != "final_scalar")
    if corruption == "missing":
        del result[scalar_key]
    elif corruption == "extra":
        result["unregistered"] = 1.0
    elif corruption == "bool":
        result[scalar_key] = True
    else:
        result[scalar_key] = float("nan")
    assert checks(profile, inputs, result) == {"output_contract": False}


@pytest.mark.parametrize("profile", ["unknown", None, [], True])
def test_unknown_profile_is_value_error(profile):
    with pytest.raises(ValueError):
        validate(profile, {})
