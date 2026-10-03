"""Separately derived cubic-kernel Hamiltonian and high-resolution RK4 oracle.

The reference does not import any provider helpers. Sources: Price (2012),
https://arxiv.org/abs/1012.1885; Monaghan (1992),
https://doi.org/10.1146/annurev.aa.30.090192.002551.
"""
import math
import numpy as np

from .control_contracts import number
from .fluid_sph_contract import initial_state, validate_request

REFERENCE_ID = "independent_fixed_h_sph_hamiltonian_rk4_v1"
_GAUSS_ABSCISSAE = np.asarray([-0.9602898564975363, -0.7966664774136267, -0.5255324099163290,
                              -0.1834346424956498, 0.1834346424956498, 0.5255324099163290,
                              0.7966664774136267, 0.9602898564975363])
_GAUSS_WEIGHTS = 0.5 * np.asarray([0.1012285362903763, 0.2223810344533745, 0.3137066458778873,
                                 0.3626837833783620, 0.3626837833783620, 0.3137066458778873,
                                 0.2223810344533745, 0.1012285362903763])
_GAUSS_S = 0.5 * (_GAUSS_ABSCISSAE + 1.0)


def quantities(model, x, velocity, mass, h):
    length, rho0, c = model["length_m"], model["reference_density_kg_per_m3"], model["sound_speed_m_per_s"]
    raw = x[:, None] - x[None, :]
    r = raw - length * np.floor(raw / length + 0.5)
    absolute = np.abs(r)
    s = absolute / h
    w, dw = np.zeros_like(s), np.zeros_like(s)
    inner, outer = s <= 1.0, (s > 1.0) & (s < 2.0)
    w[inner] = (2.0 / 3.0 - s[inner] ** 2 + 0.5 * s[inner] ** 3) / h
    w[outer] = (2.0 - s[outer]) ** 3 / (6.0 * h)
    dw[inner] = (-2.0 * s[inner] + 1.5 * s[inner] ** 2) / (h * h)
    dw[outer] = -(2.0 - s[outer]) ** 2 / (2.0 * h * h)
    dw *= np.sign(r)
    rho = np.sum(w, axis=1) * mass / model["area_m2"]
    pressure = c * c * (rho - rho0)
    eprime = pressure / rho ** 2
    a = -mass / model["area_m2"] * np.sum((eprime[:, None] + eprime[None, :]) * dw, axis=1)
    # Integrate de/drho=p/rho^2 independently of the provider's Taylor series:
    # e=c^2*d^2*integral_0^1 s/(1+d*s)^2 ds. The 8-point Gauss rule
    # avoids platform-dependent long-double cancellation at tiny strain.
    # For |d|<=.01 its truncation is far below binary64 roundoff. Outside
    # that small domain use the non-cancelling closed primitive directly;
    # such a candidate independently fails this instrument's hard bounds.
    delta = (rho - rho0) / rho0
    integral = np.sum(_GAUSS_WEIGHTS[None, :] * _GAUSS_S[None, :] /
                      (1.0 + delta[:, None] * _GAUSS_S[None, :]) ** 2, axis=1)
    internal = c * c * delta * delta * integral
    outside = np.abs(delta) > 0.01
    ratio = rho[outside] / rho0
    internal[outside] = c * c * (np.log(ratio) + 1.0 / ratio - 1.0)
    energy = mass * float(np.sum(0.5 * velocity * velocity + internal))
    return rho, pressure, a, energy


def reference(request, times, *, particles=None, substeps=32):
    request = validate_request(request)
    n = request["integration"]["particles"] if particles is None else particles
    if type(n) is not int or n not in (request["integration"]["particles"], 2 * request["integration"]["particles"], 4 * request["integration"]["particles"]):
        raise ValueError("Reference parcels must retain one declared spatial resolution")
    if type(times) is not list or not 2 <= len(times) <= 513 or times[0] != 0.0:
        raise ValueError("Reference needs the declared ordered zero-origin time grid")
    for time in times:
        number(time)
    dt = times[1] - times[0]
    if dt <= 0.0 or times != [index * dt for index in range(len(times))] or not math.isclose(times[-1], request["integration"]["duration_s"], rel_tol=2e-14):
        raise ValueError("Reference times must be uniform and cover the declared horizon")
    if type(substeps) is not int or substeps not in (16, 32):
        raise ValueError("Reference substeps must use the declared 16/32 error comparison")
    mass = request["model"]["reference_density_kg_per_m3"] * request["model"]["area_m2"] * request["model"]["length_m"] / n
    h = 2 * request["model"]["length_m"] / n
    x, v = (np.asarray(values) for values in initial_state(request, n))
    positions, velocities = [x.tolist()], [v.tolist()]
    step = dt / substeps

    def rhs(pos, vel):
        return vel, quantities(request["model"], pos, vel, mass, h)[2]

    for index in range(1, len(times)):
        for _ in range(substeps):
            k1x, k1v = rhs(x, v)
            k2x, k2v = rhs(x + 0.5 * step * k1x, v + 0.5 * step * k1v)
            k3x, k3v = rhs(x + 0.5 * step * k2x, v + 0.5 * step * k2v)
            k4x, k4v = rhs(x + step * k3x, v + step * k3v)
            x = x + step * (k1x + 2 * k2x + 2 * k3x + k4x) / 6.0
            v = v + step * (k1v + 2 * k2v + 2 * k3v + k4v) / 6.0
        positions.append(x.tolist())
        velocities.append(v.tolist())
    return {"method": REFERENCE_ID, "unwrapped_position_m": positions, "velocity_m_per_s": velocities}


def analytic_values(request, times, n):
    """Linear continuum material-coordinate acoustic benchmark, not exact SPH."""
    model = request["model"]
    q = (np.arange(n) + 0.5) * model["length_m"] / n
    k = 2.0 * math.pi / model["length_m"]
    phase = k * (q[None, :] - model["sound_speed_m_per_s"] * np.asarray(times)[:, None])
    a = model["strain_amplitude"]
    return {"unwrapped_position_m": q[None, :] - a / k * np.sin(phase),
            "velocity_m_per_s": model["sound_speed_m_per_s"] * a * np.cos(phase),
            "density_kg_per_m3": model["reference_density_kg_per_m3"] * (1.0 + a * np.cos(phase))}
