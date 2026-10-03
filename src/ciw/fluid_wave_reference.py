"""Independent analytic continuum reference for a right-travelling linear wave.

This evaluates eta(x,t)=sum A_m*cos(k_m*(x-c*t-x0)) and u=c*eta/H.
It does not import the provider, discrete spatial operator, or numerical clock.
"""
from __future__ import annotations

import math
import numpy as np

from .control_contracts import number
from .fluid_wave_contract import HARMONICS, validate_request

REFERENCE_ID = "analytic_continuum_right_travelling_three_mode_wave"


def reference(request: dict, times: list, *, cells: int | None = None) -> dict:
    request = validate_request(request)
    model = request["model"]
    if type(times) is not list or not 1 <= len(times) <= 1025:
        raise ValueError("Reference times must be a bounded ordered list")
    horizon = request["integration"]["duration_s"]
    for index, time in enumerate(times):
        if not 0.0 <= number(time) <= horizon * (1.0 + 2e-14):
            raise ValueError("Reference time exceeds declared model horizon")
        if index and time <= times[index - 1]:
            raise ValueError("Reference times must be strictly ordered")
    if cells is None:
        cells = request["integration"]["cells"]
    if type(cells) is not int or cells not in tuple(request["integration"]["cells"] * factor for factor in (1, 2, 4)):
        raise ValueError("Reference grid must be one declared spatial resolution")
    dx = model["length_m"] / cells
    cell_x = np.asarray([(index + 0.5) * dx for index in range(cells)])
    face_x = np.asarray([index * dx for index in range(cells)])
    c = math.sqrt(model["gravity_m_per_s2"] * model["depth_m"])
    elapsed = np.asarray(times, dtype=float)[:, None]

    def elevation(x):
        values = np.zeros((len(times), cells))
        for harmonic, weight in HARMONICS:
            values += model["amplitude_m"] * weight * np.cos(2.0 * math.pi * harmonic / model["length_m"] *
                (x[None, :] - c * elapsed - model["pulse_center_m"]))
        return values

    eta = elevation(cell_x)
    u = c / model["depth_m"] * elevation(face_x)
    energy = (0.5 * model["density_kg_per_m3"] * model["width_m"] * model["length_m"]
              * model["gravity_m_per_s2"] * model["amplitude_m"] ** 2
              * sum(weight * weight for _, weight in HARMONICS))
    return {"method": REFERENCE_ID, "wave_speed_m_per_s": c, "time_s": list(times),
            "cell_x_m": cell_x.tolist(), "face_x_m": face_x.tolist(),
            "free_surface_elevation_m": eta.tolist(), "depth_averaged_velocity_m_per_s": u.tolist(),
            "volume_flux_m3_per_s": (model["width_m"] * model["depth_m"] * u).tolist(),
            "bottom_gauge_pressure_pa": (model["density_kg_per_m3"] * model["gravity_m_per_s2"] * (model["depth_m"] + eta)).tolist(),
            "liquid_volume_m3": model["width_m"] * model["length_m"] * model["depth_m"],
            "mechanical_energy_j": energy}
