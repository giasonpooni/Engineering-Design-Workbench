"""Bounded local synoptic diagnostics and a teaching advection primitive.

Coordinates are local Cartesian east (x), north (y), up (z). Synoptic
derivatives are supplied at constant geometric height, not inferred from a
map or pressure-coordinate field. Numerical agreement does not validate a
forecast or the geostrophic approximation for a particular atmosphere.

References:
* NOAA GFDL, Relation between flow and mass fields, sections 5.1--5.2:
  https://www.gfdl.noaa.gov/wp-content/uploads/files/user_files/stg/ch_5.pdf
* MITgcm, Linear advection schemes, first-order upwind:
  https://mitgcm.readthedocs.io/en/latest/algorithm/adv-schemes.html
* MIT 12.950, problem set 1, periodic advection and convergence:
  https://ocw.mit.edu/courses/12-950-atmospheric-and-oceanic-modeling-spring-2004/faff2f0b33c6834028a1b1d65785931f_ps1.pdf
"""
from __future__ import annotations

import math
from typing import Any

from .control_contracts import keys, number

EARTH_ROTATION_RAD_S = 7.292115e-5

PROFILES = {
    "synoptic": {
        "scope": "Local ENU f-plane geostrophic balance, wind-gradient diagnostics and temperature advection",
        "limitations": [
            "All gradients are local Cartesian derivatives at constant geometric height; x is east and y is north.",
            "Geostrophic wind assumes steady, frictionless balance on an f-plane; supplied wind need not be balanced.",
            "The profile excludes abs(latitude) below 5 degrees and exact poles; this cutoff is a numerical scope guard, not a validity proof.",
            "No curvature, beta effect, vertical motion, fronts, convection, storm evolution or forecast is modeled.",
            "Divergence and vorticity use the supplied wind-gradient tensor, not derivatives of the computed geostrophic wind.",
        ],
        "example": {
            "latitude_deg": 45.0,
            "density_kg_m3": 1.2,
            "pressure_gradient_east_pa_m": 0.001,
            "pressure_gradient_north_pa_m": -0.002,
            "wind_east_m_s": 15.0,
            "wind_north_m_s": 5.0,
            "du_dx_s1": 1e-5,
            "du_dy_s1": -2e-5,
            "dv_dx_s1": 3e-5,
            "dv_dy_s1": -1e-5,
            "temperature_gradient_east_k_m": 1e-5,
            "temperature_gradient_north_k_m": -2e-5,
        },
        "units": {
            "coriolis_s1": "s^-1",
            "geostrophic_east_m_s": "m s^-1",
            "geostrophic_north_m_s": "m s^-1",
            "ageostrophic_east_m_s": "m s^-1",
            "ageostrophic_north_m_s": "m s^-1",
            "wind_speed_m_s": "m s^-1",
            "divergence_s1": "s^-1",
            "relative_vorticity_s1": "s^-1",
            "absolute_vorticity_s1": "s^-1",
            "temperature_advection_k_s": "K s^-1",
        },
    },
    "nwp_transport": {
        "scope": "One-dimensional periodic constant-velocity passive-tracer transport using first-order upwind",
        "limitations": [
            "Teaching numerical primitive, not a numerical weather prediction model or operational forecast.",
            "Uniform periodic grid, constant prescribed velocity, dimensionless nonnegative cell-average scalar; no sources or sinks.",
            "3..128 cells and 0..500 explicit steps; abs(velocity)*dt/dx must be at most one.",
            "Tracer integrals have units of metres for a dimensionless tracer; they are not physical atmospheric masses.",
            "First-order numerical diffusion smears resolved features; the reported coefficient is the leading modified-equation coefficient, not physical diffusivity.",
            "No atmospheric momentum, thermodynamics, data assimilation, moisture, terrain or boundary forcing is included.",
        ],
        "example": {
            "initial_scalar": [0.0, 0.0, 0.25, 0.75, 1.0, 0.75, 0.25, 0.0],
            "velocity_m_s": 10.0,
            "cell_width_m": 1000.0,
            "time_step_s": 50.0,
            "steps": 8,
        },
        "units": {
            "final_scalar": "1",
            "courant_number": "1",
            "elapsed_time_s": "s",
            "domain_length_m": "m",
            "tracer_integral_initial_m": "m",
            "tracer_integral_final_m": "m",
            "initial_min": "1",
            "initial_max": "1",
            "final_min": "1",
            "final_max": "1",
            "total_variation_initial": "1",
            "total_variation_final": "1",
            "numerical_diffusivity_m2_s": "m^2 s^-1",
        },
    },
}


def _bounded(value: Any, low: float, high: float, name: str) -> float:
    result = number(value)
    if not low <= result <= high:
        raise ValueError(f"{name} outside supported [{low}, {high}] range")
    return result


def _profile(profile: str) -> dict:
    if type(profile) is not str or profile not in PROFILES:
        raise ValueError("Unknown weather dynamics profile")
    return PROFILES[profile]


def validate(profile: str, inputs: dict) -> None:
    """Reject unknown fields, bools, nonfinite values and unsupported domains."""
    definition = _profile(profile)
    keys(inputs, set(definition["example"]))
    if profile == "synoptic":
        latitude = _bounded(inputs["latitude_deg"], -89.999, 89.999, "latitude_deg")
        if abs(latitude) < 5.0:
            raise ValueError("Geostrophic profile requires abs(latitude_deg) >= 5")
        _bounded(inputs["density_kg_m3"], 0.1, 2.0, "density_kg_m3")
        for name in ("pressure_gradient_east_pa_m", "pressure_gradient_north_pa_m"):
            _bounded(inputs[name], -0.01, 0.01, name)
        for name in ("wind_east_m_s", "wind_north_m_s"):
            _bounded(inputs[name], -300.0, 300.0, name)
        for name in ("du_dx_s1", "du_dy_s1", "dv_dx_s1", "dv_dy_s1"):
            _bounded(inputs[name], -0.01, 0.01, name)
        for name in ("temperature_gradient_east_k_m", "temperature_gradient_north_k_m"):
            _bounded(inputs[name], -0.01, 0.01, name)
    else:
        scalar = inputs["initial_scalar"]
        if type(scalar) is not list or not 3 <= len(scalar) <= 128:
            raise ValueError("Require 3..128 passive-tracer cell averages")
        for item in scalar:
            _bounded(item, 0.0, 1e6, "initial_scalar item")
        velocity = _bounded(inputs["velocity_m_s"], -1000.0, 1000.0, "velocity_m_s")
        dx = _bounded(inputs["cell_width_m"], 0.001, 1e6, "cell_width_m")
        dt = _bounded(inputs["time_step_s"], 1e-6, 1e6, "time_step_s")
        if type(inputs["steps"]) is not int or not 0 <= inputs["steps"] <= 500:
            raise ValueError("Require integer steps in 0..500")
        if abs(velocity) * dt / dx > 1.0:
            raise ValueError("Upwind stability requires abs(velocity)*dt/dx <= 1")


def _variation(values: list[float]) -> float:
    return math.fsum(abs(value - values[index - 1]) for index, value in enumerate(values))


def compute(profile: str, inputs: dict) -> dict:
    validate(profile, inputs)
    if profile == "synoptic":
        f = 2.0 * EARTH_ROTATION_RAD_S * math.sin(math.radians(inputs["latitude_deg"]))
        rho = inputs["density_kg_m3"]
        ug = -inputs["pressure_gradient_north_pa_m"] / (rho * f)
        vg = inputs["pressure_gradient_east_pa_m"] / (rho * f)
        u, v = inputs["wind_east_m_s"], inputs["wind_north_m_s"]
        zeta = inputs["dv_dx_s1"] - inputs["du_dy_s1"]
        return {
            "coriolis_s1": f,
            "geostrophic_east_m_s": ug,
            "geostrophic_north_m_s": vg,
            "ageostrophic_east_m_s": float(u - ug),
            "ageostrophic_north_m_s": float(v - vg),
            "wind_speed_m_s": math.hypot(u, v),
            "divergence_s1": float(inputs["du_dx_s1"] + inputs["dv_dy_s1"]),
            "relative_vorticity_s1": float(zeta),
            "absolute_vorticity_s1": float(zeta + f),
            "temperature_advection_k_s": float(-u * inputs["temperature_gradient_east_k_m"]
                                                  - v * inputs["temperature_gradient_north_k_m"]),
        }
    initial = [float(item) for item in inputs["initial_scalar"]]
    current = initial.copy()
    u, dx, dt = (float(inputs[name]) for name in ("velocity_m_s", "cell_width_m", "time_step_s"))
    courant = abs(u) * dt / dx
    upwind_offset = -1 if u >= 0 else 1
    for _ in range(inputs["steps"]):
        current = [(1.0 - courant) * value + courant * current[(index + upwind_offset) % len(current)]
                   for index, value in enumerate(current)]
    return {
        "final_scalar": current,
        "courant_number": courant,
        "elapsed_time_s": float(inputs["steps"] * dt),
        "domain_length_m": float(len(initial) * dx),
        "tracer_integral_initial_m": math.fsum(initial) * dx,
        "tracer_integral_final_m": math.fsum(current) * dx,
        "initial_min": min(initial),
        "initial_max": max(initial),
        "final_min": min(current),
        "final_max": max(current),
        "total_variation_initial": _variation(initial),
        "total_variation_final": _variation(current),
        "numerical_diffusivity_m2_s": 0.5 * abs(u) * dx * (1.0 - courant),
    }


def _close(left: float, right: float, *, absolute: float = 1e-12) -> bool:
    return math.isclose(left, right, rel_tol=2e-11, abs_tol=absolute)


def checks(profile: str, inputs: dict, values: dict) -> dict[str, bool]:
    """Verify identities and a separately expressed exact discrete solution.

    The transport reference uses the binomial expansion of the shift operator,
    not the production time-step loop. This verifies the stated discretization;
    continuum accuracy is assessed separately by analytic convergence tests.
    """
    validate(profile, inputs)
    try:
        keys(values, set(PROFILES[profile]["units"]))
        for name, value in values.items():
            if name == "final_scalar":
                if type(value) is not list or len(value) != len(inputs["initial_scalar"]):
                    raise ValueError("Wrong scalar field shape")
                for item in value:
                    number(item)
            else:
                number(value)
    except (ValueError, TypeError):
        return {"output_contract": False}
    if profile == "synoptic":
        f = 2.0 * EARTH_ROTATION_RAD_S * math.sin(inputs["latitude_deg"] * math.pi / 180.0)
        rho = inputs["density_kg_m3"]
        ug, vg = values["geostrophic_east_m_s"], values["geostrophic_north_m_s"]
        u, v = inputs["wind_east_m_s"], inputs["wind_north_m_s"]
        return {
            "output_contract": True,
            "coriolis_from_latitude": _close(values["coriolis_s1"], f, absolute=1e-15),
            "east_momentum_balance": _close(rho * f * vg, inputs["pressure_gradient_east_pa_m"], absolute=1e-15),
            "north_momentum_balance": _close(-rho * f * ug, inputs["pressure_gradient_north_pa_m"], absolute=1e-15),
            "wind_decomposition": _close(ug + values["ageostrophic_east_m_s"], u)
                                  and _close(vg + values["ageostrophic_north_m_s"], v),
            "wind_speed": values["wind_speed_m_s"] >= 0
                          and _close(values["wind_speed_m_s"] ** 2, u * u + v * v),
            "gradient_trace": _close(values["divergence_s1"] - inputs["du_dx_s1"], inputs["dv_dy_s1"], absolute=1e-15),
            "gradient_curl": _close(values["relative_vorticity_s1"] + inputs["du_dy_s1"], inputs["dv_dx_s1"], absolute=1e-15),
            "absolute_vorticity": _close(values["absolute_vorticity_s1"] - values["relative_vorticity_s1"], f, absolute=1e-15),
            "temperature_advection": _close(values["temperature_advection_k_s"],
                                             -math.fsum((u * inputs["temperature_gradient_east_k_m"],
                                                         v * inputs["temperature_gradient_north_k_m"])), absolute=1e-15),
        }
    initial = inputs["initial_scalar"]
    final = values["final_scalar"]
    n, count = inputs["steps"], len(initial)
    u, dx, dt = (float(inputs[name]) for name in ("velocity_m_s", "cell_width_m", "time_step_s"))
    c = abs(u) * dt / dx
    direction = 1 if u >= 0 else -1
    # At c=0 or c=1 Python's 0**0=1 gives the correct degenerate binomial law.
    weights = [math.comb(n, k) * c ** k * (1.0 - c) ** (n - k) for k in range(n + 1)]
    reference = [math.fsum(weight * initial[(index - direction * k) % count]
                           for k, weight in enumerate(weights)) for index in range(count)]
    initial_integral, final_integral = dx * math.fsum(initial), dx * math.fsum(final)
    tv_initial = math.fsum(abs(initial[(j + 1) % count] - initial[j]) for j in range(count))
    tv_final = math.fsum(abs(final[(j + 1) % count] - final[j]) for j in range(count))
    scale = max(1.0, max(initial))
    return {
        "output_contract": True,
        "courant_number": _close(values["courant_number"], c),
        "domain_and_time": _close(values["elapsed_time_s"], n * dt)
                           and _close(values["domain_length_m"], count * dx),
        "discrete_binomial_reference": all(_close(actual, expected, absolute=1e-12 * scale)
                                             for actual, expected in zip(final, reference)),
        "reported_integrals": _close(values["tracer_integral_initial_m"], initial_integral)
                              and _close(values["tracer_integral_final_m"], final_integral),
        "conservation": _close(initial_integral, final_integral),
        "reported_extrema": _close(values["initial_min"], min(initial))
                            and _close(values["initial_max"], max(initial))
                            and _close(values["final_min"], min(final))
                            and _close(values["final_max"], max(final)),
        "maximum_principle": min(final) >= min(initial) - 1e-12 * scale
                             and max(final) <= max(initial) + 1e-12 * scale,
        "reported_variation": _close(values["total_variation_initial"], tv_initial)
                              and _close(values["total_variation_final"], tv_final),
        "variation_diminishing": tv_final <= tv_initial + 1e-11 * scale,
        # Compare the dimensional identity before subtracting nearly equal terms
        # at CFL~1; subtraction would make a sound zero-diffusion result fail.
        "modified_equation_diffusivity": values["numerical_diffusivity_m2_s"] >= 0.0
                                          and _close(2.0 * values["numerical_diffusivity_m2_s"] + u * u * dt,
                                                     abs(u) * dx),
    }
