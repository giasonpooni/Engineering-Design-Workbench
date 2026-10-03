"""Independent multiscale physics and finite-observable audit checks."""
from __future__ import annotations

from copy import deepcopy
import math

import numpy as np
import pytest

from ciw import fluid_scale_maps as maps
from ciw.operations.runner import digest, seal


def _parcel_snapshot():
    return seal({"schema": maps.SNAPSHOT_SCHEMA, "profile": "sph", "particle_semantics": maps.SEMANTICS["sph"],
        "source_refs": {"request_digest": digest({"request": 1}), "result_digest": digest({"result": 1}),
                        "verification_digest": digest({"verification": 1})},
        "sample": {"trace": "time_fine", "index": 1, "time": 0.1}, "unit_system": "SI",
        "units": {"length": "m", "mass": "kg", "velocity": "m/s", "time": "s", "volume": "m^3",
                  "momentum": "kg*m/s", "energy": "J", "density": "kg/m^3"},
        "frame": "source_periodic_cartesian_frame", "dimension": 1, "periodic_lengths": [1.0],
        "cross_section_area": 0.5, "particle_masses": [2.0, 2.0, 2.0, 2.0],
        "positions": [[0.1], [0.3], [0.7], [0.9]], "velocities": [[2.0], [-1.0], [3.0], [-2.0]]})


def test_instantaneous_map_preserves_extensive_mass_momentum_and_kinetic_split():
    snapshot = _parcel_snapshot()
    mapped = maps.reduce(snapshot, bins_per_axis=[2])
    first, second = mapped["cells"]
    assert first["mass"] == 4.0 and second["mass"] == 4.0
    assert first["momentum"] == [2.0] and second["momentum"] == [2.0]
    assert first["mean_velocity"] == [0.5]
    assert second["mean_velocity"] == [0.5]
    assert first["volume"] == 0.25 and first["mass_density"] == 16.0
    assert second["mass_density"] == 16.0
    assert first["particle_kinetic_energy"] == 5.0 and first["resolved_kinetic_energy"] == 0.5
    assert first["subcell_kinetic_energy"] == 4.5
    assert second["particle_kinetic_energy"] == 13.0
    assert second["resolved_kinetic_energy"] == 0.5
    assert sum(cell["mass"] for cell in mapped["cells"]) == 8.0
    assert sum(cell["momentum"][0] for cell in mapped["cells"]) == 4.0
    np.testing.assert_allclose(sum(cell["resolved_kinetic_energy"] + cell["subcell_kinetic_energy"] for cell in mapped["cells"]), 18.0, rtol=0, atol=1e-14)
    report = maps.verify(snapshot, mapped)
    assert report["status"] == "PASS" and report["qualification"]["action"] == "LOCAL"
    assert not report["claims"]["source_fresh_physics_replayed"]
    assert not report["claims"]["constitutive_model_supplied"]
    assert not report["claims"]["physical_validation_established"]
    assert "individual_particle_identity" in report["discarded_information"]
    assert "pressure_tensor" in report["discarded_information"]


def test_particle_map_periodic_wrapping_and_empty_bin_have_explicit_mean_semantics():
    original = _parcel_snapshot()
    shifted = deepcopy(original)
    for position in shifted["positions"]:
        position[0] += 2.0
    seal(shifted)
    left = maps.reduce(original, bins_per_axis=[8])
    right = maps.reduce(shifted, bins_per_axis=[8])
    assert left["cells"] == right["cells"]
    empty = [cell for cell in left["cells"] if cell["particle_count"] == 0]
    assert empty
    assert all(cell["mean_velocity"] is None and cell["mass"] == 0 for cell in empty)
    assert maps.verify(shifted, right)["status"] == "PASS"


def test_particle_map_forgetting_is_explicit_and_cannot_relabel_parcels_as_atomic_sites():
    snapshot = _parcel_snapshot()
    snapshot["particle_semantics"] = maps.SEMANTICS["molecular"]
    seal(snapshot)
    with pytest.raises(ValueError, match="remain distinct"):
        maps.reduce(snapshot, bins_per_axis=[2])


@pytest.mark.parametrize("profile", [[], {}, True])
def test_particle_map_refuses_malformed_semantic_types_cleanly(profile):
    snapshot = _parcel_snapshot()
    snapshot["profile"] = profile
    with pytest.raises(ValueError, match="typed particle snapshot"):
        maps.validate_snapshot(seal(snapshot))


def test_resealed_mass_balanced_bin_momentum_exchange_is_detected():
    snapshot = _parcel_snapshot()
    mapped = maps.reduce(snapshot, bins_per_axis=[2])
    mapped["cells"][0]["momentum"][0] += 0.125
    mapped["cells"][1]["momentum"][0] -= 0.125
    seal(mapped)
    with pytest.raises(ValueError, match="exact declared instantaneous reduction"):
        maps.verify(snapshot, mapped)


def test_tiny_atomic_si_mass_conservation_uses_physical_scales_not_one_kg_floor():
    snapshot = _parcel_snapshot()
    snapshot["particle_masses"] = [value * 1e-27 for value in snapshot["particle_masses"]]
    seal(snapshot)
    mapped = maps.reduce(snapshot, bins_per_axis=[2])
    report = maps.verify(snapshot, mapped)
    assert report["status"] == "PASS"
    assert sum(cell["mass"] for cell in mapped["cells"]) == pytest.approx(8e-27, rel=1e-15, abs=0)


@pytest.mark.parametrize("distance", [1.0, 1.2, 2.499, 2.5, 2.501])
def test_molecular_force_shift_has_correct_direction_energy_and_cutoff(distance):
    from ciw.fluid_molecular_contract import example_request
    from ciw.fluid_molecular_solver import pair_state
    model = example_request()["model"]
    cutoff = model["cutoff_reduced"]
    positions = np.array([[1.0, 1.0, 1.0], [1.0 + distance, 1.0, 1.0]])
    velocities = np.zeros((2, 3))
    state = pair_state(model, positions, velocities)
    if distance < cutoff:
        force_at_cutoff = 24 * (2 / cutoff**13 - 1 / cutoff**7)
        radial_force = 24 * (2 / distance**13 - 1 / distance**7) - force_at_cutoff
        potential = (4 * (distance**-12 - distance**-6) - 4 * (cutoff**-12 - cutoff**-6)
                     + (distance - cutoff) * force_at_cutoff)
    else:
        radial_force, potential = 0.0, 0.0
    np.testing.assert_allclose(state["forces_reduced"], [[-radial_force, 0, 0], [radial_force, 0, 0]], rtol=1e-12, atol=1e-13)
    assert state["potential_energy_reduced"] == pytest.approx(potential, rel=1e-12, abs=1e-14)
    expected_pressure = distance * radial_force / (3 * model["box_length_reduced"]**3)
    assert state["virial_pressure_reduced"] == pytest.approx(expected_pressure, rel=1e-12, abs=1e-14)
    if distance == 1.0:
        assert state["forces_reduced"][0][0] < 0  # repulsive
    if distance == 1.2:
        assert state["forces_reduced"][0][0] > 0  # attractive


def test_molecular_thermal_temperature_and_virial_pressure_are_galilean_invariant():
    from ciw.fluid_molecular_contract import example_request
    from ciw.fluid_molecular_solver import pair_state
    model = example_request()["model"]
    positions = np.array([[1.0, 1.0, 1.0], [2.2, 1.0, 1.0]])
    velocities = np.array([[0.2, -0.1, 0.0], [-0.2, 0.1, 0.0]])
    original = pair_state(model, positions, velocities)
    boosted = pair_state(model, positions, velocities + [0.5, 0.3, -0.2])
    # Two sites have three COM-removed thermal degrees of freedom.
    assert original["kinetic_temperature_reduced"] == pytest.approx(2 * 0.05 / 3, abs=1e-15)
    assert boosted["kinetic_temperature_reduced"] == pytest.approx(original["kinetic_temperature_reduced"], abs=1e-15)
    assert boosted["virial_pressure_reduced"] == pytest.approx(original["virial_pressure_reduced"], abs=1e-15)
    np.testing.assert_allclose(boosted["momentum_reduced"] - original["momentum_reduced"], [1.0, 0.6, -0.4], atol=1e-15, rtol=0)


@pytest.fixture(scope="module")
def molecular_qualified():
    from ciw.fluid_molecular_contract import example_request
    from ciw.fluid_molecular_solver import simulate
    from ciw.fluid_molecular_verification import verify
    request = example_request()
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "PASS" and report["qualification"]["action"] == "LOCAL"
    return request, result, report


def test_molecular_reduction_retains_reduced_units_and_exact_instantaneous_momentum(molecular_qualified):
    request, result, report = molecular_qualified
    snapshot = maps.molecular_snapshot(request, result, report, sample_index=5)
    mapped = maps.reduce(snapshot, bins_per_axis=[2, 2, 2])
    assert snapshot["unit_system"] == mapped["unit_system"] == "reduced_lj"
    assert mapped["particle_semantics"] == "structureless_atomistic_interaction_site"
    assert sum(cell["mass"] for cell in mapped["cells"]) == 8.0
    np.testing.assert_allclose(np.sum([cell["momentum"] for cell in mapped["cells"]], axis=0),
                               result["time_fine"]["momentum_reduced"][5], atol=1e-15, rtol=0)
    assert sum(cell["particle_kinetic_energy"] for cell in mapped["cells"]) == pytest.approx(
        result["time_fine"]["kinetic_energy_reduced"][5], rel=1e-15, abs=0)
    assert maps.verify(snapshot, mapped)["status"] == "PASS"


def test_molecular_optional_si_scales_are_explicit_and_remain_uncalibrated():
    from ciw.fluid_molecular_contract import example_request
    from ciw.fluid_molecular_solver import simulate
    from ciw.fluid_molecular_verification import verify
    request = example_request()
    request["si_scaling"] = {"sigma_m": 3.4e-10, "epsilon_j": 1.65e-21, "site_mass_kg": 6.63e-26,
                             "parameter_status": "declared_unvalidated_scales"}
    result = simulate(request)
    report = verify(request, result)
    snapshot = maps.molecular_snapshot(request, result, report, sample_index=4)
    velocity_scale = math.sqrt(1.65e-21 / 6.63e-26)
    assert snapshot["unit_system"] == "SI"
    np.testing.assert_allclose(snapshot["positions"], np.array(result["time_fine"]["positions_reduced"][4]) * 3.4e-10, rtol=1e-15, atol=0)
    np.testing.assert_allclose(snapshot["velocities"], np.array(result["time_fine"]["velocities_reduced"][4]) * velocity_scale, rtol=1e-15, atol=0)
    assert snapshot["sample"]["time"] == pytest.approx(result["time_fine"]["time_reduced"][4] * 3.4e-10 / velocity_scale, rel=1e-15, abs=0)
    mapped = maps.reduce(snapshot, bins_per_axis=[2, 2, 2])
    assert math.fsum(cell["mass"] for cell in mapped["cells"]) == pytest.approx(8 * 6.63e-26, rel=1e-15, abs=0)
    assert not mapped["claims"]["si_parameter_calibration_established"]
    assert maps.verify(snapshot, mapped)["status"] == "PASS"


def test_sph_reduction_uses_computational_parcel_mass_and_cross_section():
    from ciw.fluid_sph_contract import example_request
    from ciw.fluid_sph_solver import simulate
    from ciw.fluid_sph_verification import verify
    request = example_request()
    result = simulate(request)
    report = verify(request, result)
    assert report["status"] == "PASS" and report["qualification"]["action"] == "LOCAL"
    snapshot = maps.sph_snapshot(request, result, report, sample_index=5)
    mapped = maps.reduce(snapshot, bins_per_axis=[8])
    model = request["model"]
    expected_mass = model["reference_density_kg_per_m3"] * model["area_m2"] * model["length_m"]
    assert math.fsum(cell["mass"] for cell in mapped["cells"]) == pytest.approx(expected_mass, rel=1e-15, abs=0)
    assert math.fsum(cell["volume"] for cell in mapped["cells"]) == pytest.approx(model["area_m2"] * model["length_m"], rel=1e-15, abs=0)
    assert mapped["particle_semantics"] == "equal_mass_sph_continuum_parcel"
    assert maps.verify(snapshot, mapped)["status"] == "PASS"


def _fsi_mode(request):
    """Independent continuum eigenvalue from fluid momentum and wall balance."""
    model, wall = request["model"], request["structure"]
    length, width, depth, rho, gravity = (model[key] for key in ("length_m", "width_m", "depth_m", "density_kg_per_m3", "gravity_m_per_s2"))
    mu = wall["mass_kg"] / (rho * width * depth * length)
    kappa = wall["stiffness_n_per_m"] * length / (rho * gravity * width * depth**2)
    low, high = 1e-12, math.pi
    for _ in range(90):
        middle = (low + high) / 2
        # m*x''+k_s*x=rho*g*W*H*eta(L), u(L)=x',
        # eta=A*cos(k*z)*cos(omega*t), omega²=g*H*k².
        residual = (mu * middle**2 - kappa) * math.sin(middle) - middle * math.cos(middle)
        if residual > 0:
            high = middle
        else:
            low = middle
    k = (low + high) / (2 * length)
    return k, math.sqrt(gravity * depth) * k


@pytest.fixture(scope="module")
def fsi():
    from ciw.fluid_fsi_contract import example_request
    from ciw.fluid_fsi_solver import simulate
    request = example_request()
    return request, simulate(request)


def test_fsi_half_dual_cell_inertia_and_boundary_traction_have_correct_physics(fsi):
    request, result = fsi
    model, wall = request["model"], request["structure"]
    width, depth, density, gravity = (model[key] for key in ("width_m", "depth_m", "density_kg_per_m3", "gravity_m_per_s2"))
    for label in ("primary", "time_fine", "spatial_fine"):
        trace = result[label]
        eta = np.array(trace["free_surface_elevation_m"])
        velocity = np.array(trace["depth_averaged_velocity_m_per_s"])
        x, v, acceleration = (np.array(trace[key]) for key in ("wall_displacement_m", "wall_velocity_m_per_s", "wall_acceleration_m_per_s2"))
        dx = trace["dx_m"]
        assert np.all(velocity[:, 0] == 0)
        np.testing.assert_allclose(velocity[:, -1], v, rtol=0, atol=1e-15)
        boundary_eta = eta[:, -1] - dx * acceleration / (2 * gravity)
        physical_force = density * gravity * width * depth * boundary_eta
        np.testing.assert_allclose(trace["boundary_elevation_m"], boundary_eta, rtol=0, atol=1e-15)
        np.testing.assert_allclose(trace["fluid_force_on_structure_n"], physical_force, rtol=0, atol=1e-13)
        np.testing.assert_allclose(trace["structure_force_on_fluid_n"], -physical_force, rtol=0, atol=1e-13)
        np.testing.assert_allclose(wall["mass_kg"] * acceleration + wall["stiffness_n_per_m"] * x,
                                   physical_force, rtol=0, atol=1e-11)
        half_dual_mass = density * width * depth * dx / 2
        np.testing.assert_allclose((wall["mass_kg"] + half_dual_mass) * acceleration + wall["stiffness_n_per_m"] * x,
                                   density * gravity * width * depth * eta[:, -1], rtol=0, atol=1e-11)
        reconstructed_fluid_energy = 0.5 * density * width * dx * (
            gravity * np.sum(eta**2, axis=1) + depth * np.sum(velocity[:, 1:-1]**2, axis=1)) + 0.5 * half_dual_mass * v**2
        np.testing.assert_allclose(trace["fluid_energy_j"], reconstructed_fluid_energy, rtol=1e-13, atol=1e-16)
        volume = width * dx * np.sum(depth + eta, axis=1) + width * depth * x
        np.testing.assert_allclose(volume, width * depth * model["length_m"], rtol=0, atol=2e-14)
        np.testing.assert_allclose(trace["liquid_mass_kg"], density * volume, rtol=0, atol=2e-10)
        work = np.r_[0, np.cumsum(trace["dt_s"] * 0.5 * (physical_force[1:] + physical_force[:-1]) * 0.5 * (v[1:] + v[:-1]))]
        np.testing.assert_allclose(trace["structure_interface_work_j"], work, rtol=0, atol=1e-15)
        np.testing.assert_allclose(trace["fluid_interface_work_j"], -work, rtol=0, atol=1e-15)
        structure_energy = 0.5 * (wall["mass_kg"] * v**2 + wall["stiffness_n_per_m"] * x**2)
        np.testing.assert_allclose(structure_energy - structure_energy[0], work, rtol=0, atol=2e-14)
        np.testing.assert_allclose(reconstructed_fluid_energy - reconstructed_fluid_energy[0], -work, rtol=0, atol=2e-14)


def test_fsi_continuum_reference_is_cell_averaged_and_has_correct_normal_mode(fsi):
    request, result = fsi
    model = request["model"]
    k, omega = _fsi_mode(request)
    trace = result["spatial_fine"]
    times = np.array(trace["time_s"])
    amplitude, depth = model["amplitude_m"], model["depth_m"]
    centers, faces = np.array(trace["cell_x_m"]), np.array(trace["face_x_m"])
    cell_average_factor = np.sinc(k * trace["dx_m"] / (2 * math.pi))
    eta = amplitude * cell_average_factor * np.cos(k * centers)[None, :] * np.cos(omega * times)[:, None]
    velocity = amplitude * math.sqrt(model["gravity_m_per_s2"] * depth) / depth * np.sin(k * faces)[None, :] * np.sin(omega * times)[:, None]
    wall_x = -amplitude * math.sin(k * model["length_m"]) / (depth * k) * np.cos(omega * times)
    assert np.max(np.abs(np.array(trace["free_surface_elevation_m"]) - eta)) / amplitude < 0.002
    assert np.max(np.abs(np.array(trace["depth_averaged_velocity_m_per_s"]) - velocity)) / (amplitude * omega / (depth * k)) < 0.002
    assert np.max(np.abs(np.array(trace["wall_displacement_m"]) - wall_x)) / np.max(np.abs(wall_x)) < 0.002
    # At maximum displacement every face is at rest. Cell values are exact
    # averages of the continuous initial mode, including the partial last cell.
    np.testing.assert_allclose(trace["free_surface_elevation_m"][0], eta[0], rtol=0, atol=2e-17)


@pytest.mark.parametrize("quantity", ["eta", "velocity", "boundary_force"])
def test_fsi_second_order_spatial_trend_comes_from_independent_continuum_fields(fsi, quantity):
    request, result = fsi
    model = request["model"]
    k, omega = _fsi_mode(request)
    amplitude, depth = model["amplitude_m"], model["depth_m"]
    errors = []
    # These three traces have the same retained time step. The exact continuum
    # mode advances under implicit midpoint with rotation angle
    # 2*atan(omega*dt/2) per step. Removing that known temporal phase isolates
    # spatial error, rather than mistaking a fixed temporal floor for poor
    # spatial convergence. No provider references or claimed orders are used.
    for label in ("time_fine", "spatial_refined", "spatial_fine"):
        trace = result[label]
        times = np.array(trace["time_s"])
        phase = (2*math.atan(omega*trace["dt_s"]/2)/trace["dt_s"])*times
        if quantity == "eta":
            expected = amplitude*np.sinc(k*trace["dx_m"]/(2*math.pi))*np.cos(k*np.array(trace["cell_x_m"]))[None,:]*np.cos(phase)[:,None]
            candidate = np.array(trace["free_surface_elevation_m"])
        elif quantity == "velocity":
            expected = amplitude*math.sqrt(model["gravity_m_per_s2"]*depth)/depth*np.sin(k*np.array(trace["face_x_m"]))[None,:]*np.sin(phase)[:,None]
            candidate = np.array(trace["depth_averaged_velocity_m_per_s"])
        else:
            expected = model["density_kg_per_m3"]*model["gravity_m_per_s2"]*model["width_m"]*depth*amplitude*math.cos(k*model["length_m"])*np.cos(phase)
            candidate = np.array(trace["fluid_force_on_structure_n"])
        errors.append(float(np.sqrt(np.mean((candidate-expected)**2))))
    orders = [math.log(left/right,2) for left,right in zip(errors,errors[1:])]
    assert all(1.85 < order < 2.15 for order in orders), (quantity, errors, orders)


@pytest.mark.parametrize("df", [1, 2, 4])
@pytest.mark.parametrize("statistic", [0.001, 0.1, 1.0, 4.0, 25.0, 100.0])
def test_chi_square_survival_against_independent_closed_forms(df, statistic):
    # NIST chi-square distribution is Gamma(df/2, scale2):
    # https://www.itl.nist.gov/div898/handbook/eda/section3/eda3666.htm
    from ciw.fluid_experiment_statistics import chi_square_survival
    z = statistic / 2
    expected = (math.erfc(math.sqrt(z)) if df == 1 else math.exp(-z)
                if df == 2 else math.exp(-z) * (1 + z))
    assert chi_square_survival(statistic, df) == pytest.approx(expected, rel=2e-13, abs=0)


@pytest.mark.parametrize("alpha", [1e-6, 0.05, 0.25])
def test_two_degree_chi_square_critical_value_is_exact_exponential_quantile(alpha):
    from ciw.fluid_experiment_statistics import critical_value
    assert critical_value(alpha, 2) == pytest.approx(-2 * math.log(alpha), rel=1e-13, abs=0)


def _statistical_inputs():
    from ciw.fluid_experiment_contract import template
    metadata = template()["metadata"]
    metadata["clock"]["offset_standard_uncertainty_s"] = 0.1
    rows = [{"sample_id": "s" + str(index), "time_s": time, "role": "holdout", "values": [value + 1e-4]}
            for index, (time, value) in enumerate(zip([0.5, 1.5, 2.5], [1.0, 0.5, -0.5]))]
    trace = {"time_s": [0.0, 1.0, 2.0, 3.0], "head1_m": [0.0, 2.0, -1.0, 0.0]}
    # Pure statistical inputs avoid Session fixtures and make the projection
    # operator's known slopes [2,-3,1] independently inspectable.
    source = {"evidence_id": "evidence-independent-statistical-test"}
    model = {"record_digest": digest({"statistical_model": 1}),
             "candidate": {"result_id": "result-independent-statistical-test", "execution_id": "execution-independent-statistical-test",
                 "data": {"resolutions": {"finer": {"trace": trace}}}},
             "fresh_verification": {"verification_id": "verification-independent-statistical-test"}}
    return source, metadata, rows, model


def test_shared_clock_offset_induces_global_covariance_and_correct_mahalanobis_statistic():
    from ciw.fluid_experiment_statistics import compute
    source, metadata, rows, model = _statistical_inputs()
    value = compute(source, metadata, rows, model)
    slopes = np.array([2.0, -3.0, 1.0])
    expected_clock = np.outer(slopes, slopes) * 0.01
    np.testing.assert_allclose(value["prediction_slopes"], slopes, rtol=0, atol=0)
    np.testing.assert_allclose(value["covariance"]["clock_common_offset"], expected_clock, rtol=1e-15, atol=0)
    assert value["covariance"]["clock_common_offset"][0][1] < 0
    # Residual[1,1,1]*1e-4 is orthogonal to common-clock slope[2,-3,1].
    # Sherman-Morrison therefore gives q=||r||² / 1e-8 =3 exactly.
    assert value["statistics"]["chi_square"] == pytest.approx(3.0, rel=2e-9, abs=0)
    z = 1.5
    expected_survival = math.erfc(math.sqrt(z)) + 2 * math.sqrt(z / math.pi) * math.exp(-z)
    assert value["statistics"]["upper_tail_probability"] == pytest.approx(expected_survival, rel=2e-9, abs=0)
    assert value["statistics"]["degrees_of_freedom"] == 3
    assert value["outcome"] == "EMPIRICALLY_COMPATIBLE"
    assert value["support"]["conditional_measured_support"] is False
    assert value["support"]["authority"]["physical_validation"] == "not_established"
    metadata["provenance"]["source_kind"] = "declared_measured"
    measured = compute(source, metadata, rows, model, independent=True)
    assert measured["support"]["conditional_measured_support"] is True
    assert measured["support"]["authority"]["physical_validation"] == "not_established"


@pytest.mark.parametrize("unknown", ["measurement", "parameter_prediction", "model_discrepancy", "numerical_interpolation", "clock"])
def test_unknown_uncertainty_blocks_conditional_measured_support(unknown):
    from ciw.fluid_experiment_statistics import compute
    source, metadata, rows, model = _statistical_inputs()
    metadata["provenance"]["source_kind"] = "declared_measured"
    if unknown == "clock":
        metadata["clock"]["offset_standard_uncertainty_s"] = None
    else:
        metadata["uncertainty"][unknown]["matrix"] = None
    value = compute(source, metadata, rows, model)
    assert value["outcome"] == "INCONCLUSIVE"
    assert value["statistics"]["chi_square"] is None
    assert value["covariance"]["total"] is None
    assert value["support"]["conditional_measured_support"] is False


def test_covariance_psd_guard_is_independent_of_mixed_channel_unit_scales():
    from ciw.fluid_experiment_statistics import validate_covariances
    _, metadata, _, _ = _statistical_inputs()
    metadata["uncertainty"]["measurement"]["matrix"] = [[1e-16, 2e-8, 0.0], [2e-8, 1.0, 0.0], [0.0, 0.0, 1e-8]]
    with pytest.raises(ValueError, match="not positive semidefinite"):
        validate_covariances(metadata)


def test_generic_interface_reproduces_three_dimensional_rigid_motion_and_rank_one_load_noise():
    from ciw import fluid_coupling as coupling
    request = coupling.example_request()
    nodes = np.array([[0., 0., 0.], [2., 0., 0.], [0., 3., 0.], [0., 0., 4.]])
    p = np.array([[.25, .25, .25, .25], [-.1, .5, .3, .3]])
    faces = np.array([[.5, .75, 1.], [1., .9, 1.2]])
    origin = np.array([11., -7., 4.])
    area = np.array([2., 3.])
    traction = np.array([[1., 2., -3.], [-2., 5., 1.]])
    b, omega = np.array([.3, -.7, .2]), np.array([.1, .2, -.4])
    a, theta = np.array([.01, -.02, .04]), np.array([.001, -.003, .002])
    request["geometry"].update(structural_nodes_m=nodes.tolist(), fluid_face_centroids_m=faces.tolist(),
        moment_origin_m=origin.tolist(), fluid_face_areas_m2=area.tolist())
    request["mapping"]["face_motion_from_structure"] = p.tolist()
    request["fluid"]["traction_pa"] = traction.tolist()
    request["structure"]["velocities_m_per_s"] = (b + np.cross(omega, nodes-origin)).tolist()
    request["structure"]["displacements_m"] = (a + np.cross(theta, nodes-origin)).tolist()
    # One shared scalar load perturbation has exactly rank-one covariance.
    # Its mapped standard-deviation vector follows each nodal load response;
    # this tests component ordering without reconstructing a Kronecker matrix.
    perturbation = np.array([[1., 2., 3.], [-1., .5, 4.]])
    request["uncertainty"]["traction_covariance_pa2"] = np.outer(perturbation.ravel(), perturbation.ravel()).tolist()
    result = coupling.transfer(request)
    assert coupling.verify(request, result)["status"] == "PASS"
    data = result["data"]
    np.testing.assert_allclose(data["mapped_face_velocities_m_per_s"], b+np.cross(omega, faces-origin), rtol=1e-14, atol=1e-14)
    force = np.array([-4., 19., -3.])
    moment = np.cross(faces[0]-origin, [2., 4., -6.]) + np.cross(faces[1]-origin, [-6., 15., 3.])
    assert data["structural_power_w"] == pytest.approx(force@b+moment@omega, rel=1e-14, abs=0)
    assert data["fluid_reaction_power_w"] == pytest.approx(-(force@b+moment@omega), rel=1e-14, abs=0)
    assert data["structural_virtual_work_j"] == pytest.approx(force@a+moment@theta, rel=1e-14, abs=0)
    q = np.array([[sum(p[i,j]*area[i]*perturbation[i,d] for i in range(2)) for d in range(3)] for j in range(4)]).ravel()
    np.testing.assert_allclose(result["uncertainty"]["structural_force_covariance_n2"], np.outer(q,q), rtol=1e-14, atol=1e-14)


def test_generic_interface_rejects_indefinite_covariance_despite_small_raw_negative_eigenvalue():
    from ciw import fluid_coupling as coupling
    request = coupling.example_request()
    covariance = np.eye(6)
    covariance[0,0] = 1e-16
    covariance[0,1] = covariance[1,0] = 2e-8
    request["uncertainty"]["traction_covariance_pa2"] = covariance.tolist()
    # Correlation [[1,2],[2,1]] has eigenvalue -1: this cannot be load noise,
    # even though its raw SI covariance has only a tiny negative eigenvalue.
    with pytest.raises(ValueError, match="positive semidefinite"):
        coupling.validate_request(request)


def test_generic_interface_zeroing_tiny_but_nonzero_loads_and_motion_cannot_qualify():
    from ciw import fluid_coupling as coupling
    request = coupling.example_request()
    request["fluid"]["traction_pa"] = [[value*1e-14 for value in row] for row in request["fluid"]["traction_pa"]]
    for field in ("displacements_m", "velocities_m_per_s"):
        request["structure"][field] = [[value*1e-14 for value in row] for row in request["structure"][field]]
    candidate = coupling.transfer(request)
    for field in coupling.VECTOR_FIELDS:
        candidate["data"][field] = [[0.,0.,0.] for _ in candidate["data"][field]]
    for field in coupling.SCALAR_FIELDS:
        candidate["data"][field] = 0.
    report = coupling.verify(request, seal(candidate))
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"


def test_generic_interface_geometry_eligibility_cannot_depend_on_arbitrary_moment_origin():
    from ciw import fluid_coupling as coupling
    request = coupling.example_request()
    for field in ("structural_nodes_m", "fluid_face_centroids_m"):
        request["geometry"][field] = [[value*1e-14 for value in row] for row in request["geometry"][field]]
    request["geometry"]["fluid_face_centroids_m"][0][0] += 1e-14
    for origin in ([0.,0.,0.], [100.,0.,0.]):
        request["geometry"]["moment_origin_m"] = origin
        with pytest.raises(ValueError, match="coordinate reproduction"):
            coupling.validate_request(request)
