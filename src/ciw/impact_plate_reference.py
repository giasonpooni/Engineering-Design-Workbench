"""Independent finite-basis eigen evolution with a first-release boundary.

The active-contact matrix is symmetric after mass normalization. Its sine and
cosine propagator is independent of the Verlet path. After the first release,
the striker is ballistic and plate modes evolve freely; a later recontact is
reported as outside this reference's single-contact qualification domain.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
import math
import numpy as np

from .control_contracts import number
from .impact_plate_contract import (MAX_REFERENCE_PHASE_INTERVALS, MAX_SAMPLES, STATE_FIELDS, modal_parameters,
                                    nominal_contact_duration_s, nominal_scales, validate_request)


def _bisect(function, left, right):
    fleft = function(left)
    for _ in range(70):
        middle = 0.5 * (left + right)
        fmiddle = function(middle)
        if fmiddle == 0.0 or middle == left or middle == right:
            return middle
        if (fmiddle > 0.0) == (fleft > 0.0):
            left, fleft = middle, fmiddle
        else:
            right = middle
    return 0.5 * (left + right)


@lru_cache(maxsize=16)
def _prepared(encoded_request: str, modes_per_axis: int) -> dict:
    request = json.loads(encoded_request)
    model, integration = request["model"], request["integration"]
    basis = modal_parameters(model, modes_per_axis)
    masses = np.asarray([model["mass_kg"]] + basis["modal_mass_kg"], dtype=float)
    square_root_mass = np.sqrt(masses)
    plate_omega = np.asarray(basis["angular_frequency_rad_per_s"])
    coupling = np.asarray(basis["patch_coupling"])
    contact_vector = np.concatenate(([1.0], -coupling)) / square_root_mass
    active_matrix = np.diag(np.concatenate(([0.0], plate_omega ** 2)))
    active_matrix += model["stiffness_n_per_m"] * np.outer(contact_vector, contact_vector)
    eigenvalues, eigenvectors = np.linalg.eigh(active_matrix)
    if np.any(eigenvalues <= 0.0) or not np.all(np.isfinite(eigenvalues)):
        raise ValueError("Active-contact eigen system exceeds the positive binary64 reference profile")
    omega = np.sqrt(eigenvalues)
    initial_velocity = np.zeros(len(masses))
    initial_velocity[0] = square_root_mass[0] * model["initial_speed_m_per_s"]
    amplitudes = eigenvectors.T @ initial_velocity
    delta_amplitudes = (contact_vector @ eigenvectors) * amplitudes / omega
    count = math.ceil(integration["steps_per_contact"] * integration["duration_factor"])
    horizon = count * nominal_contact_duration_s(model) / integration["steps_per_contact"]
    # The contract limits dt*omega, so this phase-aware scan is itself bounded.
    scan_count = max(256, math.ceil(horizon * float(max(omega)) * 32.0 / math.pi))
    if scan_count > MAX_REFERENCE_PHASE_INTERVALS:
        raise ValueError("Reference event scan exceeds the declared phase budget")
    scan_times = np.linspace(0.0, horizon, scan_count + 1)
    delta = delta_amplitudes @ np.sin(np.outer(omega, scan_times))

    def active_delta(time):
        return float(delta_amplitudes @ np.sin(omega * time))

    release = None
    for index in range(1, scan_count + 1):
        if delta[index] <= 0.0:
            release = _bisect(active_delta, float(scan_times[index - 1]), float(scan_times[index]))
            break
    prepared = {"request": request, "basis": basis, "masses": masses,
                "square_root_mass": square_root_mass, "coupling": coupling,
                "plate_omega": plate_omega, "omega": omega, "eigenvectors": eigenvectors,
                "amplitudes": amplitudes, "release": release, "horizon": horizon,
                "first_recontact": None, "scan_count": scan_count}
    if release is not None:
        q, velocities = _active_values(prepared, np.asarray([release]))
        prepared["release_q"], prepared["release_v"] = q[:, 0], velocities[:, 0]

        def free_delta(time):
            free_q, _ = _free_values(prepared, np.asarray([time]))
            return float(free_q[0, 0] - coupling @ free_q[1:, 0])

        # Skip the mathematically zero release sample. The first offset is
        # phase-small yet comfortably above cancellation at the event itself.
        first_offset = min((horizon - release) / 2.0, math.pi / (float(max(omega)) * 1024.0))
        if first_offset > 0.0:
            free_times = np.linspace(release + first_offset, horizon, scan_count + 1)
            free_q, _ = _free_values(prepared, free_times)
            free_gap = free_q[0, :] - coupling @ free_q[1:, :]
            if free_gap[0] >= 0.0:
                # A tangency or unresolved immediate recollision is outside
                # the strictly separating single-contact reference domain.
                prepared["first_recontact"] = float(free_times[0])
            else:
                for index in range(1, len(free_times)):
                    if free_gap[index - 1] < 0.0 and free_gap[index] >= 0.0:
                        prepared["first_recontact"] = _bisect(free_delta, float(free_times[index - 1]),
                                                                float(free_times[index]))
                        break
    return prepared


def _prepare(request: dict, modes_per_axis: int | None) -> dict:
    request = validate_request(request)
    modes_per_axis = request["integration"]["modes_per_axis"] if modes_per_axis is None else modes_per_axis
    if type(modes_per_axis) is not int or modes_per_axis not in (
        request["integration"]["modes_per_axis"], request["integration"]["modes_per_axis"] + 2):
        raise ValueError("Reference basis must be the declared primary or spatial refinement")
    return _prepared(json.dumps(request, sort_keys=True, separators=(",", ":")), modes_per_axis)


def _active_values(prepared: dict, times: np.ndarray):
    phase = np.outer(prepared["omega"], times)
    displacement = prepared["eigenvectors"] @ ((prepared["amplitudes"] / prepared["omega"])[:, None] * np.sin(phase))
    velocity = prepared["eigenvectors"] @ (prepared["amplitudes"][:, None] * np.cos(phase))
    return displacement / prepared["square_root_mass"][:, None], velocity / prepared["square_root_mass"][:, None]


def _free_values(prepared: dict, times: np.ndarray):
    elapsed = times - prepared["release"]
    q0, v0, omega = prepared["release_q"], prepared["release_v"], prepared["plate_omega"]
    phase = np.outer(omega, elapsed)
    q = np.empty((len(q0), len(times)))
    velocity = np.empty_like(q)
    q[0, :] = q0[0] + v0[0] * elapsed
    velocity[0, :] = v0[0]
    q[1:, :] = q0[1:, None] * np.cos(phase) + (v0[1:] / omega)[:, None] * np.sin(phase)
    velocity[1:, :] = -q0[1:, None] * omega[:, None] * np.sin(phase) + v0[1:, None] * np.cos(phase)
    return q, velocity


def _values(prepared: dict, times: np.ndarray) -> dict:
    q, velocities = _active_values(prepared, times)
    if prepared["release"] is not None:
        free = times >= prepared["release"]
        if np.any(free):
            q[:, free], velocities[:, free] = _free_values(prepared, times[free])
    contact_q = prepared["coupling"] @ q[1:, :]
    contact_v = prepared["coupling"] @ velocities[1:, :]
    gap = q[0, :] - contact_q
    force = prepared["request"]["model"]["stiffness_n_per_m"] * np.maximum(gap, 0.0)
    if prepared["release"] is not None:
        force[times >= prepared["release"]] = 0.0
    result = {"striker_displacement_m": q[0, :].tolist(), "compression_m": gap.tolist(),
              "velocity_m_per_s": velocities[0, :].tolist(), "force_n": force.tolist(),
              "plate_contact_displacement_m": contact_q.tolist(),
              "plate_contact_velocity_m_per_s": contact_v.tolist(),
              "modal_displacement_m": q[1:, :].tolist(), "modal_velocity_m_per_s": velocities[1:, :].tolist()}
    # Preserve declared initial data exactly, avoiding eigen cancellation at t=0.
    for index in np.flatnonzero(times == 0.0):
        for field in STATE_FIELDS:
            result[field][index] = (prepared["request"]["model"]["initial_speed_m_per_s"]
                                    if field == "velocity_m_per_s" else 0.0)
        for field in ("modal_displacement_m", "modal_velocity_m_per_s"):
            for row in result[field]:
                row[index] = 0.0
    return result


def reference(request: dict, modes_per_axis: int | None = None) -> dict:
    prepared = _prepare(request, modes_per_axis)
    release = prepared["release"]
    times = np.linspace(0.0, prepared["horizon"], prepared["scan_count"] + 1)
    if release is not None:
        times = np.sort(np.concatenate((times, [release])))
    values = _values(prepared, times)
    model, basis = prepared["request"]["model"], prepared["basis"]
    release_speed = None if release is None else float(prepared["release_v"][0])
    return {**nominal_scales(model),
            "nominal_contact_duration_s": nominal_contact_duration_s(model),
            "observation_duration_s": prepared["horizon"], "contact_duration_s": release,
            "release_time_s": release, "first_recontact_time_s": prepared["first_recontact"],
            "single_contact_supported": release is not None and prepared["first_recontact"] is None,
            "maximum_compression_m": max(values["compression_m"]),
            "peak_force_n": max(values["force_n"]),
            "maximum_plate_contact_displacement_m": max(abs(value) for value in values["plate_contact_displacement_m"]),
            "maximum_plate_l1_displacement_m": float(np.max(np.sum(np.abs(values["modal_displacement_m"]), axis=0))),
            "striker_impulse_n_s": None if release is None else model["mass_kg"] * (model["initial_speed_m_per_s"] - release_speed),
            "restitution": None if release is None else -release_speed / model["initial_speed_m_per_s"],
            **{field: deepcopy(basis[field]) for field in ("modes", "modal_mass_kg", "modal_stiffness_n_per_m", "patch_coupling")}}


def reference_values(request: dict, times: list, modes_per_axis: int | None = None) -> dict:
    if type(times) is not list or not 1 <= len(times) <= MAX_SAMPLES:
        raise ValueError("Require a bounded nonempty list of reference times")
    for time in times:
        if number(time) < 0.0:
            raise ValueError("Reference times must be finite and nonnegative")
    prepared = _prepare(request, modes_per_axis)
    if max(times) > prepared["horizon"] * (1.0 + 2e-14):
        raise ValueError("Reference times exceed the declared single-contact observation window")
    return _values(prepared, np.asarray(times, dtype=float))


def sample(request: dict, time_s: float, modes_per_axis: int | None = None) -> dict:
    values = reference_values(request, [time_s], modes_per_axis)
    return {field: ([row[0] for row in series] if field.startswith("modal_") else series[0])
            for field, series in values.items()}
