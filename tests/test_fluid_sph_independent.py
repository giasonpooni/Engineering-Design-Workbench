"""SPH checks derived from the declared mechanics, independently of providers.

The density sum, spline, Hamiltonian and Runge--Kutta evolution below do not
import provider/reference force, kernel, energy or verification helpers.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext
import math

import numpy as np
import pytest

from ciw.operations.runner import seal


def _spline(distance: np.ndarray, smoothing_length: float) -> np.ndarray:
    """Normalized one-dimensional cubic spline from its piecewise polynomial."""
    q = np.abs(np.asarray(distance, dtype=float)) / smoothing_length
    f = np.where(q < 1.0, 1.0 - 1.5 * q**2 + 0.75 * q**3,
                 np.where(q < 2.0, 0.25 * (2.0 - q)**3, 0.0))
    return 2.0 / (3.0 * smoothing_length) * f


def _spline_derivative(distance: np.ndarray, smoothing_length: float) -> np.ndarray:
    q = np.abs(np.asarray(distance, dtype=float)) / smoothing_length
    f_prime = np.where(q < 1.0, -3.0 * q + 2.25 * q**2,
                       np.where(q < 2.0, -0.75 * (2.0 - q)**2, 0.0))
    return 2.0 / (3.0 * smoothing_length**2) * f_prime * np.sign(distance)


def _closed_energy(density: np.ndarray, velocities: np.ndarray, mass: float,
                   rest_density: float, sound_speed: float) -> float:
    """Closed EOS primitive, with portable precision for its cancellation."""
    if np.finfo(np.longdouble).eps < 1e-18:
        ratio = density.astype(np.longdouble) / np.longdouble(rest_density)
        internal = np.longdouble(sound_speed**2) * (np.log(ratio) + 1.0 / ratio - 1.0)
        return float(np.longdouble(mass) * np.sum(
            0.5 * velocities.astype(np.longdouble)**2 + internal))
    # On platforms where longdouble aliases binary64, its cancelled O(delta²)
    # primitive loses the precision required by the small-strain checks.
    # Decimal evaluates the logarithm and reciprocal directly, independently
    # of the provider series and the reference's energy integration.
    with localcontext() as context:
        context.prec = 50
        reference_density = Decimal.from_float(float(rest_density))
        speed = Decimal.from_float(float(sound_speed))
        total = Decimal(0)
        for rho, velocity in zip(density, velocities):
            ratio = Decimal.from_float(float(rho)) / reference_density
            speed_at_parcel = Decimal.from_float(float(velocity))
            total += (speed_at_parcel**2 / 2
                      + speed**2 * (ratio.ln() + 1 / ratio - 1))
        return float(Decimal.from_float(float(mass)) * total)


def _mechanics(positions: np.ndarray, velocities: np.ndarray, *, length: float,
               smoothing_length: float, mass: float, area: float,
               rest_density: float, sound_speed: float, include_energy: bool = True) -> dict:
    positions = np.asarray(positions, dtype=float)
    velocities = np.asarray(velocities, dtype=float)
    separation = positions[:, None] - positions[None, :]
    separation -= length * np.floor(separation / length + 0.5)
    density = mass / area * np.sum(_spline(separation, smoothing_length), axis=1)
    pressure = sound_speed**2 * (density - rest_density)
    work_coefficient = pressure / density**2
    acceleration = -mass / area * np.sum(
        (work_coefficient[:, None] + work_coefficient[None, :])
        * _spline_derivative(separation, smoothing_length), axis=1)
    return {"density": density, "pressure": pressure, "acceleration": acceleration,
            "energy": _closed_energy(density, velocities, mass, rest_density, sound_speed)
            if include_energy else None,
            "momentum": float(mass * np.sum(velocities))}


def _rk4(positions: np.ndarray, velocities: np.ndarray, duration: float, steps: int,
         parameters: dict) -> tuple[np.ndarray, np.ndarray]:
    """Independent continuous-time SPH ODE integration, never Verlet stepping."""
    x, velocity = np.array(positions, dtype=float), np.array(velocities, dtype=float)
    dt = duration / steps

    def acceleration(at: np.ndarray) -> np.ndarray:
        return _mechanics(at, np.zeros_like(at), include_energy=False, **parameters)["acceleration"]

    for _ in range(steps):
        first_x, first_v = velocity, acceleration(x)
        second_x = velocity + 0.5 * dt * first_v
        second_v = acceleration(x + 0.5 * dt * first_x)
        third_x = velocity + 0.5 * dt * second_v
        third_v = acceleration(x + 0.5 * dt * second_x)
        fourth_x = velocity + dt * third_v
        fourth_v = acceleration(x + dt * third_x)
        x += dt / 6.0 * (first_x + 2.0 * second_x + 2.0 * third_x + fourth_x)
        velocity += dt / 6.0 * (first_v + 2.0 * second_v + 2.0 * third_v + fourth_v)
    return x, velocity


def _parameters(request: dict, trace: dict) -> dict:
    model = request["model"]
    return {"length": model["length_m"], "area": model["area_m2"],
            "rest_density": model["reference_density_kg_per_m3"],
            "sound_speed": model["sound_speed_m_per_s"],
            "mass": trace["parcel_mass_kg"], "smoothing_length": trace["smoothing_length_m"]}


def _initial(request: dict, count: int) -> tuple[np.ndarray, np.ndarray]:
    model = request["model"]
    material = (np.arange(count) + 0.5) * model["length_m"] / count
    wave_number = 2.0 * math.pi / model["length_m"]
    strain = model["strain_amplitude"]
    return (material - strain / wave_number * np.sin(wave_number * material),
            model["sound_speed_m_per_s"] * strain * np.cos(wave_number * material))


@pytest.fixture(scope="module")
def sph():
    from ciw.fluid_sph_contract import example_request
    from ciw.fluid_sph_solver import simulate
    request = example_request()
    return request, simulate(request)


def test_provider_spline_has_unit_integral_and_periodic_uniform_density(sph):
    from ciw.fluid_sph_solver import evaluate, kernel_and_gradient
    request, _ = sph
    length = request["model"]["length_m"]
    count = request["integration"]["particles"]
    h = 2.0 * length / count
    # Four-point Gauss quadrature integrates each cubic piece exactly.
    nodes, weights = np.polynomial.legendre.leggauss(4)
    integral = 0.0
    for left, right in ((-2.0, -1.0), (-1.0, 0.0), (0.0, 1.0), (1.0, 2.0)):
        positions = h * (0.5 * (right + left) + 0.5 * (right - left) * nodes)
        observed, derivative = kernel_and_gradient(positions, h)
        np.testing.assert_allclose(observed, _spline(positions, h), rtol=2e-15, atol=2e-15 / h)
        np.testing.assert_allclose(derivative, _spline_derivative(positions, h), rtol=2e-15, atol=2e-15 / h**2)
        integral += h * 0.5 * (right - left) * float(weights @ observed)
    assert integral == pytest.approx(1.0, abs=3e-15)
    endpoints = h * np.array([-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0])
    observed, derivative = kernel_and_gradient(endpoints, h)
    np.testing.assert_allclose(observed, _spline(endpoints, h), rtol=0.0, atol=2e-15 / h)
    np.testing.assert_allclose(derivative, _spline_derivative(endpoints, h), rtol=0.0, atol=2e-15 / h**2)
    assert observed[0] == observed[-1] == derivative[0] == derivative[-1] == 0.0
    material = (np.arange(count) + 0.5) * length / count
    mass = request["model"]["reference_density_kg_per_m3"] * request["model"]["area_m2"] * length / count
    density, pressure, acceleration, energy, momentum = evaluate(
        request["model"], material, np.zeros(count), mass, h)
    np.testing.assert_allclose(density, request["model"]["reference_density_kg_per_m3"], rtol=0.0, atol=5e-12)
    np.testing.assert_allclose(pressure, 0.0, rtol=0.0, atol=5e-10)
    np.testing.assert_allclose(acceleration, 0.0, rtol=0.0, atol=5e-12)
    assert abs(energy) < 1e-23 and momentum == 0.0


def test_provider_force_is_independent_hamiltonian_gradient_and_zero_total_force(sph):
    from ciw.fluid_sph_solver import evaluate
    request, result = sph
    trace = result["resolutions"]["primary"]
    parameters = _parameters(request, trace)
    count, length = trace["particles"], parameters["length"]
    dx = length / count
    material = (np.arange(count) + 0.5) * dx
    # Nonuniform spacing exercises inner and outer spline pieces and parcel
    # pairs on both sides of the periodic boundary.
    positions = material + dx * (0.02 * np.sin(6.0 * math.pi * material / length)
                                 + 0.01 * np.cos(14.0 * math.pi * material / length))
    velocity = 0.003 * np.sin(2.0 * math.pi * material / length)
    mechanics = _mechanics(positions, velocity, **parameters)
    density, pressure, acceleration, energy, momentum = evaluate(
        request["model"], positions, velocity, parameters["mass"], parameters["smoothing_length"])
    np.testing.assert_allclose(density, mechanics["density"], rtol=2e-15, atol=3e-12)
    np.testing.assert_allclose(pressure, mechanics["pressure"], rtol=0.0, atol=3e-10)
    np.testing.assert_allclose(acceleration, mechanics["acceleration"], rtol=3e-12, atol=3e-11)
    assert energy == pytest.approx(mechanics["energy"], rel=2e-12, abs=1e-14)
    assert momentum == pytest.approx(mechanics["momentum"], abs=1e-17)
    gradient = np.empty(count)
    epsilon = dx * 1e-5
    for particle in range(count):
        plus, minus = positions.copy(), positions.copy()
        plus[particle] += epsilon
        minus[particle] -= epsilon
        gradient[particle] = (_mechanics(plus, velocity, **parameters)["energy"]
                              - _mechanics(minus, velocity, **parameters)["energy"]) / (2.0 * epsilon)
    np.testing.assert_allclose(parameters["mass"] * acceleration, -gradient,
                               rtol=2e-6, atol=2e-8 * np.max(np.abs(gradient)))
    assert abs(float(parameters["mass"] * np.sum(acceleration))) < 2e-13 * float(np.sum(np.abs(parameters["mass"] * acceleration)))


@pytest.mark.parametrize("strain", [1e-5, 1e-4, 5e-4])
@pytest.mark.parametrize("count", [32, 256])
def test_small_density_internal_energy_matches_independent_closed_primitive(sph, strain, count):
    from ciw.fluid_sph_reference import quantities
    from ciw.fluid_sph_solver import evaluate
    original, _ = sph
    request = deepcopy(original)
    request["model"]["strain_amplitude"] = strain
    model = request["model"]
    length, area, rho0, speed = (model[field] for field in (
        "length_m", "area_m2", "reference_density_kg_per_m3", "sound_speed_m_per_s"))
    parameters = {"length": length, "area": area, "rest_density": rho0,
                  "sound_speed": speed, "mass": rho0 * area * length / count,
                  "smoothing_length": 2.0 * length / count}
    positions, _ = _initial(request, count)
    velocity = np.zeros(count)
    expected = _mechanics(positions, velocity, **parameters)["energy"]
    provider_energy = evaluate(model, positions, velocity,
                               parameters["mass"], parameters["smoothing_length"])[3]
    reference_energy = quantities(model, positions, velocity,
                                  parameters["mass"], parameters["smoothing_length"])[3]
    energy_scale = rho0 * area * length * speed**2 * strain**2
    assert expected > 0.0
    assert abs(provider_energy - expected) / energy_scale < 1e-8
    assert abs(reference_energy - expected) / energy_scale < 1e-8


def test_small_density_energy_is_portable_when_longdouble_has_binary64_precision(sph, monkeypatch):
    from ciw import fluid_sph_reference
    from ciw.fluid_sph_solver import evaluate
    original, _ = sph
    request = deepcopy(original)
    request["model"]["strain_amplitude"] = 1e-5
    count = 256
    model = request["model"]
    parameters = {"length": model["length_m"], "area": model["area_m2"],
                  "rest_density": model["reference_density_kg_per_m3"],
                  "sound_speed": model["sound_speed_m_per_s"],
                  "mass": model["reference_density_kg_per_m3"] * model["area_m2"] * model["length_m"] / count,
                  "smoothing_length": 2.0 * model["length_m"] / count}
    positions, _ = _initial(request, count)
    velocity = np.zeros(count)
    # The reference and this test share NumPy; scope the platform emulation so
    # no following test inherits the reduced precision.
    with monkeypatch.context() as patch:
        patch.setattr(fluid_sph_reference.np, "longdouble", np.float64)
        assert np.finfo(np.longdouble).eps >= 1e-18
        expected = _mechanics(positions, velocity, **parameters)["energy"]
        reference_energy = fluid_sph_reference.quantities(
            model, positions, velocity, parameters["mass"], parameters["smoothing_length"])[3]
        provider_energy = evaluate(model, positions, velocity,
                                   parameters["mass"], parameters["smoothing_length"])[3]
    energy_scale = (parameters["rest_density"] * parameters["area"] * parameters["length"]
                    * parameters["sound_speed"]**2 * model["strain_amplitude"]**2)
    assert expected > 0.0
    assert abs(reference_energy - expected) / energy_scale < 1e-8
    assert abs(provider_energy - expected) / energy_scale < 1e-8


def test_every_emitted_state_and_verlet_transition_matches_independent_mechanics(sph):
    request, result = sph
    for trace in result["resolutions"].values():
        parameters = _parameters(request, trace)
        assert parameters["smoothing_length"] == 2.0 * parameters["length"] / trace["particles"]
        assert parameters["mass"] == parameters["rest_density"] * parameters["area"] * parameters["length"] / trace["particles"]
        positions = np.array(trace["unwrapped_position_m"])
        velocity = np.array(trace["velocity_m_per_s"])
        expected_x, expected_v = _initial(request, trace["particles"])
        np.testing.assert_allclose(positions[0], expected_x, rtol=0.0, atol=2e-16)
        np.testing.assert_allclose(velocity[0], expected_v, rtol=0.0, atol=2e-18)
        acceleration, energy = [], []
        for index, (x, v) in enumerate(zip(positions, velocity)):
            observed = _mechanics(x, v, **parameters)
            acceleration.append(observed["acceleration"])
            energy.append(observed["energy"])
            np.testing.assert_allclose(trace["density_kg_per_m3"][index], observed["density"], rtol=0.0, atol=5e-11)
            np.testing.assert_allclose(trace["pressure_pa"][index], observed["pressure"], rtol=0.0, atol=5e-9)
            assert trace["total_energy_j"][index] == pytest.approx(observed["energy"], rel=1e-8, abs=2e-14)
            assert trace["total_momentum_kg_m_per_s"][index] == pytest.approx(observed["momentum"], abs=2e-17)
        acceleration = np.array(acceleration)
        dt = trace["dt_s"]
        np.testing.assert_allclose(positions[1:], positions[:-1] + dt * velocity[:-1] + 0.5 * dt**2 * acceleration[:-1],
                                   rtol=0.0, atol=3e-16)
        np.testing.assert_allclose(velocity[1:], velocity[:-1] + 0.5 * dt * (acceleration[:-1] + acceleration[1:]),
                                   rtol=0.0, atol=2e-13)
        momentum_scale = parameters["mass"] * trace["particles"] * request["model"]["sound_speed_m_per_s"] * request["model"]["strain_amplitude"]
        assert np.ptp(trace["total_momentum_kg_m_per_s"]) < 2e-14 * momentum_scale
        assert np.max(np.abs(np.array(energy) / energy[0] - 1.0)) < 2e-5


@pytest.mark.parametrize("length,area,density,speed", [
    (0.1, 1e-4, 500.0, 2000.0),
    (100.0, 10.0, 2000.0, 1.0),
])
def test_declared_dimensional_scaling_preserves_the_dimensionless_sph_trajectory(sph, length, area, density, speed):
    from ciw.fluid_sph_solver import simulate
    request, base_result = sph
    scaled_request = deepcopy(request)
    scaled_request["model"].update(length_m=length, area_m2=area,
                                 reference_density_kg_per_m3=density, sound_speed_m_per_s=speed)
    scaled_request["integration"]["duration_s"] = 0.125 * length / speed
    scaled_result = simulate(scaled_request)
    base_model = request["model"]
    for label, base in base_result["resolutions"].items():
        scaled = scaled_result["resolutions"][label]
        for field, base_scale, scaled_scale in (
            ("unwrapped_position_m", base_model["length_m"], length),
            ("velocity_m_per_s", base_model["sound_speed_m_per_s"], speed),
            ("density_kg_per_m3", base_model["reference_density_kg_per_m3"], density),
            ("pressure_pa", base_model["reference_density_kg_per_m3"] * base_model["sound_speed_m_per_s"]**2,
             density * speed**2),
            ("total_energy_j", base_model["reference_density_kg_per_m3"] * base_model["area_m2"]
             * base_model["length_m"] * base_model["sound_speed_m_per_s"]**2,
             density * area * length * speed**2),
        ):
            np.testing.assert_allclose(np.array(scaled[field]) / scaled_scale,
                                       np.array(base[field]) / base_scale, rtol=1e-10, atol=1e-13)


def test_verlet_temporal_order_against_independent_converged_rk4(sph):
    request, result = sph
    trace = result["resolutions"]["primary"]
    parameters = _parameters(request, trace)
    x0, v0 = _initial(request, trace["particles"])
    duration = request["integration"]["duration_s"]
    exact_x, exact_v = _rk4(x0, v0, duration, 1024, parameters)
    check_x, check_v = _rk4(x0, v0, duration, 512, parameters)
    position_scale = request["model"]["strain_amplitude"] * parameters["length"] / (2.0 * math.pi)
    velocity_scale = request["model"]["strain_amplitude"] * request["model"]["sound_speed_m_per_s"]

    def error(x, velocity):
        return float(np.sqrt(np.mean(((x - exact_x) / position_scale)**2
                                     + ((velocity - exact_v) / velocity_scale)**2)))

    assert error(check_x, check_v) < 2e-9
    errors = [error(np.array(result["resolutions"][label]["unwrapped_position_m"][-1]),
                    np.array(result["resolutions"][label]["velocity_m_per_s"][-1]))
              for label in ("primary", "time_refined", "time_fine")]
    assert all(value > 100.0 * error(check_x, check_v) for value in errors)
    orders = [math.log2(first / second) for first, second in zip(errors[:-1], errors[1:])]
    assert all(1.97 < order < 2.03 for order in orders)


def test_reference_owns_its_physics_and_matches_separate_rk4(sph, monkeypatch):
    from ciw.fluid_sph_reference import reference
    from ciw import fluid_sph_solver
    request, result = sph
    trace = result["resolutions"]["primary"]

    def forbidden(*args, **kwargs):
        raise AssertionError("Independent reference reused provider physics")

    monkeypatch.setattr(fluid_sph_solver, "evaluate", forbidden)
    monkeypatch.setattr(fluid_sph_solver, "kernel_and_gradient", forbidden)
    independent = reference(request, trace["time_s"])
    parameters = _parameters(request, trace)
    x0, v0 = _initial(request, trace["particles"])
    x, velocity = _rk4(x0, v0, request["integration"]["duration_s"], 1024, parameters)
    np.testing.assert_allclose(independent["unwrapped_position_m"][-1], x, rtol=0.0, atol=5e-15)
    np.testing.assert_allclose(independent["velocity_m_per_s"][-1], velocity, rtol=0.0, atol=5e-13)


def test_coherent_resealed_wrong_force_trajectory_fails_fresh_verification(sph):
    from ciw.fluid_sph_contract import validate_result
    from ciw.fluid_sph_verification import validate_report, verify
    request, result = sph
    candidate = deepcopy(result)
    for trace in candidate["resolutions"].values():
        parameters = _parameters(request, trace)
        # Keep the declared initial state exactly, then evolve with a different
        # stiffness. Derived density, pressure, energy and momentum stay fully
        # coherent with each forged state and the genuine declared EOS.
        x = np.array(trace["unwrapped_position_m"][0])
        velocity = np.array(trace["velocity_m_per_s"][0])
        dt = trace["dt_s"]
        acceleration = 0.5 * _mechanics(x, velocity, include_energy=False, **parameters)["acceleration"]
        for index in range(1, trace["steps"] + 1):
            x = x + dt * velocity + 0.5 * dt**2 * acceleration
            next_acceleration = 0.5 * _mechanics(x, velocity, include_energy=False, **parameters)["acceleration"]
            velocity = velocity + 0.5 * dt * (acceleration + next_acceleration)
            acceleration = next_acceleration
            derived = _mechanics(x, velocity, **parameters)
            trace["unwrapped_position_m"][index] = x.tolist()
            trace["velocity_m_per_s"][index] = velocity.tolist()
            trace["density_kg_per_m3"][index] = derived["density"].tolist()
            trace["pressure_pa"][index] = derived["pressure"].tolist()
            trace["total_energy_j"][index] = derived["energy"]
            trace["total_momentum_kg_m_per_s"][index] = derived["momentum"]
    candidate = seal(candidate)
    validate_result(request, candidate)
    report = verify(request, candidate)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    assert any(check["status"] == "FAIL" and "reference" in check["name"] for check in report["checks"])
    validate_report(request, candidate, report)
