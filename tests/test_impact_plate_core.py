"""Contract, provider and independently propagated finite-basis regressions."""
from copy import deepcopy
import math
import numpy as np
import pytest

from ciw.impact_plate_contract import (example_request, modal_parameters, nominal_contact_duration_s,
                                      validate_request, validate_result)
from ciw.impact_plate_reference import reference, reference_values, sample
from ciw.impact_plate_solver import simulate
from ciw.operations.runner import seal


@pytest.fixture(scope="module")
def plate_request():
    return example_request()


@pytest.fixture(scope="module")
def result(plate_request):
    return simulate(plate_request)


def _energy(plate_request, values, modes):
    basis = modal_parameters(plate_request["model"], modes)
    q, velocity = np.asarray(values["modal_displacement_m"]), np.asarray(values["modal_velocity_m_per_s"])
    mass = np.asarray(basis["modal_mass_kg"])[:, None]
    stiffness = np.asarray(basis["modal_stiffness_n_per_m"])[:, None]
    striker = 0.5 * plate_request["model"]["mass_kg"] * np.asarray(values["velocity_m_per_s"]) ** 2
    contact = 0.5 * plate_request["model"]["stiffness_n_per_m"] * np.maximum(values["compression_m"], 0.0) ** 2
    return striker + contact + np.sum(0.5 * (mass * velocity ** 2 + stiffness * q ** 2), axis=0)


def test_example_is_detached_and_has_three_declared_grids(plate_request, result):
    validated = validate_request(plate_request)
    validated["model"]["mass_kg"] = 2.0
    assert plate_request["model"]["mass_kg"] == 1.0
    assert validate_result(plate_request, result) == result
    assert [result[name]["modes_per_axis"] for name in ("primary", "refined", "spatial")] == [3, 3, 5]
    assert [len(result[name]["time_s"]) for name in ("primary", "refined", "spatial")] == [1537, 3073, 3073]
    assert result["refined"]["time_s"][::2] == result["primary"]["time_s"]
    assert result["spatial"]["time_s"] == result["refined"]["time_s"]


@pytest.mark.parametrize(("section", "field", "value"), [
    ("model", "mass_kg", True), ("model", "poissons_ratio", 0.5),
    ("model", "thickness_m", 0.005), ("model", "patch_width_x_m", 0.001),
    ("model", "patch_center_x_m", 0.01), ("model", "damping_n_s_per_m", 0.1),
    ("model", "gravity_during_contact_m_per_s2", 9.81), ("model", "initial_compression_m", 0.01),
    ("model", "young_modulus_pa", float("nan")), ("model", "density_kg_per_m3", 99.0),
    ("integration", "modes_per_axis", 2), ("integration", "modes_per_axis", True),
    ("integration", "spatial_refinement_increment", True), ("integration", "spatial_refinement_increment", 4),
    ("integration", "steps_per_contact", 256), ("integration", "steps_per_contact", 2049),
    ("integration", "duration_factor", 2.1), ("tolerances", "spatial_refinement_normalized", 0.2),
])
def test_invalid_physics_and_numerical_declarations_fail_before_calculation(plate_request, section, field, value):
    candidate = deepcopy(plate_request)
    candidate[section][field] = value
    with pytest.raises(ValueError):
        validate_request(candidate)


@pytest.mark.parametrize("section", [None, "model", "integration", "tolerances"])
def test_unknown_fields_are_not_ignored(plate_request, section):
    candidate = deepcopy(plate_request)
    (candidate if section is None else candidate[section])["unknown"] = 0.0
    with pytest.raises(ValueError):
        validate_request(candidate)


def test_phase_scan_resource_limit_is_refused_by_contract_without_reference_replay(plate_request, monkeypatch):
    import ciw.impact_plate_reference as independent
    candidate = deepcopy(plate_request)
    candidate["model"]["young_modulus_pa"] = 1.5e10
    candidate["integration"].update(steps_per_contact=2048, duration_factor=2.0)
    monkeypatch.setattr(independent, "reference", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("reference replay")))
    with pytest.raises(ValueError, match="phase budget"):
        validate_request(candidate)


def test_supported_and_declared_expansion_observables_remain_distinct(plate_request):
    candidate = deepcopy(plate_request)
    candidate["desired_observables"] = ["plate_modes", "fracture"]
    assert validate_request(candidate) == candidate
    candidate["desired_observables"] = ["plate_modes", "invented"]
    with pytest.raises(ValueError):
        validate_request(candidate)
    candidate["desired_observables"] = ["plate_modes", "plate_modes"]
    with pytest.raises(ValueError):
        validate_request(candidate)


def test_finite_patch_average_is_not_a_point_load_and_modal_units_are_consistent(plate_request):
    model = plate_request["model"]
    basis = modal_parameters(model, 3)
    area = model["length_x_m"] * model["length_y_m"]
    assert basis["modal_mass_kg"][0] == pytest.approx(model["density_kg_per_m3"] * model["thickness_m"] * area / 4)
    sinc = math.sin(math.pi * 0.02 / 0.4) / (math.pi * 0.02 / 0.4)
    assert basis["patch_coupling"][0] == pytest.approx(sinc * sinc)
    assert basis["patch_coupling"][0] < 1.0
    scaled = deepcopy(model)
    scaled["young_modulus_pa"] *= 4
    four = modal_parameters(scaled, 3)
    assert four["modal_mass_kg"] == basis["modal_mass_kg"]
    assert four["angular_frequency_rad_per_s"][0] == pytest.approx(2 * basis["angular_frequency_rad_per_s"][0])


@pytest.mark.parametrize("modes", [3, 5])
def test_eigen_reference_conserves_striker_contact_and_plate_energy_through_release(plate_request, modes):
    ref = reference(plate_request, modes)
    assert ref["single_contact_supported"] is True
    assert ref["first_recontact_time_s"] is None
    assert nominal_contact_duration_s(plate_request["model"]) < ref["release_time_s"] < ref["observation_duration_s"]
    times = np.linspace(0.0, ref["observation_duration_s"], 701).tolist()
    values = reference_values(plate_request, times, modes)
    energy = _energy(plate_request, values, modes)
    assert max(abs(energy / ref["initial_energy_j"] - 1.0)) < 1e-10
    after = sample(plate_request, ref["release_time_s"] + 0.001, modes)
    assert after["force_n"] == 0.0
    assert after["compression_m"] < 0.0
    assert after["velocity_m_per_s"] == pytest.approx(-ref["restitution"] * plate_request["model"]["initial_speed_m_per_s"])


def test_reference_detects_missing_release_and_later_recontact(plate_request):
    compliant = deepcopy(plate_request)
    compliant["model"].update(length_x_m=0.3, length_y_m=0.3, patch_center_x_m=0.15, patch_center_y_m=0.15)
    ref = reference(compliant)
    assert ref["release_time_s"] is None
    assert ref["single_contact_supported"] is False
    assert ref["restitution"] is None
    recontact = deepcopy(plate_request)
    recontact["model"]["young_modulus_pa"] = 1e7
    ref = reference(recontact)
    assert 0.0 < ref["release_time_s"] < ref["first_recontact_time_s"] < ref["observation_duration_s"]
    assert ref["single_contact_supported"] is False


def test_fixed_step_temporal_refinement_reduces_independent_eigen_error(plate_request, result):
    errors = []
    for label in ("primary", "refined"):
        trace = result[label]
        values = reference_values(plate_request, trace["time_s"], 3)
        errors.append(max(abs(left - right) for left, right in zip(trace["force_n"], values["force_n"])))
    assert errors[1] < errors[0] / 2.0
    assert errors[0] / reference(plate_request)["nominal_force_n"] < 0.001


def test_modal_energy_and_contact_exchange_are_retained_in_provider(plate_request, result):
    for label in ("primary", "refined", "spatial"):
        trace = result[label]
        energy = _energy(plate_request, trace, trace["modes_per_axis"])
        assert max(abs(energy / 0.00045 - 1.0)) < 0.001
        assert max(trace["plate_contact_displacement_m"]) > 0.0001
        assert max(abs(value) for value in trace["modal_velocity_m_per_s"][0]) > 0.001
        assert all(value >= 0.0 for value in trace["force_n"])


def test_offcenter_patch_excites_even_modes_and_sine_field_vanishes_on_boundaries(plate_request):
    candidate = deepcopy(plate_request)
    candidate["model"].update(patch_center_x_m=0.08, patch_center_y_m=0.09)
    result = simulate(candidate)
    trace = result["primary"]
    even_index = trace["modes"].index([2, 1])
    assert abs(trace["patch_coupling"][even_index]) > 0.1
    assert max(abs(value) for value in trace["modal_displacement_m"][even_index]) > 1e-7
    coefficients = [row[len(row) // 2] for row in trace["modal_displacement_m"]]
    a, b = candidate["model"]["length_x_m"], candidate["model"]["length_y_m"]
    for x, y in ((0.0, 0.09), (a, 0.09), (0.08, 0.0), (0.08, b)):
        displacement = sum(q * math.sin(m * math.pi * x / a) * math.sin(n * math.pi * y / b)
                           for q, (m, n) in zip(coefficients, trace["modes"]))
        assert abs(displacement) < 1e-18


@pytest.mark.parametrize("corruption", ["wrong_basis", "boolean_mode", "wrong_mass", "boolean_mass",
                                        "array_length", "wrong_dt", "wrong_initial", "modal_length", "nonfinite"])
def test_resealed_result_structure_and_parameter_corruption_is_rejected(plate_request, result, corruption):
    candidate = deepcopy(result)
    trace = candidate["primary"]
    if corruption == "wrong_basis":
        trace["modes"][0][0] = 2
    elif corruption == "boolean_mode":
        trace["modes"][0][0] = True
    elif corruption == "wrong_mass":
        trace["modal_mass_kg"][0] *= 2
    elif corruption == "boolean_mass":
        trace["modal_mass_kg"][0] = True
    elif corruption == "array_length":
        trace["force_n"].pop()
    elif corruption == "wrong_dt":
        trace["dt_s"] *= 2
    elif corruption == "wrong_initial":
        trace["modal_displacement_m"][0][0] = 1e-6
    elif corruption == "modal_length":
        trace["modal_velocity_m_per_s"].pop()
    else:
        trace["velocity_m_per_s"][10] = float("inf")
    with pytest.raises(ValueError):
        validate_result(plate_request, seal(candidate))


def test_solver_does_not_consult_reference(plate_request, monkeypatch):
    import ciw.impact_plate_reference as independent
    monkeypatch.setattr(independent, "reference", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("reference replay")))
    monkeypatch.setattr(independent, "reference_values", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("reference replay")))
    assert simulate(plate_request)["schema"] == "ciw.impact-plate-result.v1"


@pytest.mark.parametrize("time", [-1.0, True, float("nan"), 1.0])
def test_reference_refuses_invalid_and_undeclared_times(plate_request, time):
    with pytest.raises(ValueError):
        sample(plate_request, time)


def test_reference_refuses_undeclared_basis(plate_request):
    with pytest.raises(ValueError):
        reference(plate_request, 1)
