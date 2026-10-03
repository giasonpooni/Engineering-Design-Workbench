"""Bounded sounding diagnostics and paired temperature-forecast verification.

The sounding receives an already specified parcel virtual-temperature path.
It does not integrate parcel thermodynamics, locate an LFC/EL, or report CAPE
or CIN. Its positive/negative areas integrate *all* supplied height intervals.

References (equations independently implemented, no copied source):
https://www.meted.ucar.edu/tropical/textbook_2nd_edition/print_6.htm
https://www.weather.gov/source/zhu/ZHU_Training_Page/convective_parameters/Sounding_Stuff/MesoscaleParameters.html
https://www.nwrfc.noaa.gov/verification/verify_help.cgi
"""
from __future__ import annotations

import math
from typing import Any

from .control_contracts import keys, number

GRAVITY_M_S2 = 9.80665
MAX_SAMPLES = 64

PROFILES = {
    "storm_sounding": {
        "scope": "Supplied-parcel virtual-temperature buoyancy, signed height integrals, and endpoint wind shear.",
        "limitations": [
            "Parcel virtual temperatures are inputs, not a computed moist or dry parcel ascent.",
            "Buoyancy is interpolated linearly with height; zero crossings are integrated exactly within this representation.",
            "Positive and negative integrals cover the full declared layer and are not operational CAPE or CIN.",
            "Endpoint shear covers the declared layer only; it is not automatically a 0–6 km or effective storm layer.",
            "Fixed Earth gravity; no pressure perturbations, condensate loading, entrainment, or hazard forecast.",
            "A numerical closure check is not validation against observed storms.",
        ],
        "example": {
            "height_m": [0, 1000, 2000, 3000],
            "environment_virtual_temperature_k": [300, 294, 288, 282],
            "parcel_virtual_temperature_k": [299, 296, 290, 281],
            "eastward_wind_m_s": [2, 6, 10, 14],
            "northward_wind_m_s": [0, 3, 6, 9],
        },
        "units": {
            "buoyancy_m_s2": "m/s^2",
            "positive_buoyancy_integral_j_kg": "J/kg",
            "negative_buoyancy_integral_j_kg": "J/kg",
            "net_buoyancy_integral_j_kg": "J/kg",
            "bulk_shear_eastward_m_s": "m/s",
            "bulk_shear_northward_m_s": "m/s",
            "bulk_shear_m_s": "m/s",
            "layer_depth_m": "m",
        },
    },
    "forecast_verification": {
        "scope": "Equal-weight, paired temperature-forecast error and comparison with a supplied persistence forecast.",
        "limitations": [
            "Kelvin temperatures only; forecast, observation, and persistence entries must refer to the same valid times and locations.",
            "Persistence values are supplied; chronology and absence of look-ahead leakage must be established by the caller.",
            "No missing-value omission, weighting, uncertainty intervals, event verification, or operational forecast generation.",
            "MSE improvement is baseline MSE minus forecast MSE in K^2, not a normalized skill score; it remains defined at a zero-error baseline.",
            "In-sample numerical scores do not establish out-of-sample forecast skill.",
        ],
        "example": {
            "forecast_k": [280, 282, 281, 283],
            "observation_k": [281, 280, 281, 285],
            "persistence_k": [279, 281, 280, 281],
        },
        "units": {
            "bias_k": "K",
            "mae_k": "K",
            "rmse_k": "K",
            "persistence_rmse_k": "K",
            "mse_improvement_k2": "K^2",
        },
    },
}


def _profile(profile: str) -> dict:
    if type(profile) is not str or profile not in PROFILES:
        raise ValueError("Unknown weather-storm profile")
    return PROFILES[profile]


def _array(value: Any, name: str, minimum: int, low: float, high: float) -> None:
    if type(value) is not list or not minimum <= len(value) <= MAX_SAMPLES:
        raise ValueError(f"{name} requires {minimum}..{MAX_SAMPLES} samples")
    if any(not low <= number(item) <= high for item in value):
        raise ValueError(f"{name} is outside declared bounds [{low}, {high}]")


def validate(profile: str, inputs: dict) -> None:
    spec = _profile(profile)
    keys(inputs, set(spec["example"]))
    if profile == "storm_sounding":
        _array(inputs["height_m"], "height_m", 2, 0, 50000)
        for field in ("environment_virtual_temperature_k", "parcel_virtual_temperature_k"):
            _array(inputs[field], field, 2, 100, 400)
        for field in ("eastward_wind_m_s", "northward_wind_m_s"):
            _array(inputs[field], field, 2, -200, 200)
        if any(b <= a for a, b in zip(inputs["height_m"], inputs["height_m"][1:])):
            raise ValueError("Sounding heights must be strictly increasing")
    else:
        for field in inputs:
            _array(inputs[field], field, 1, 100, 400)
    if len({len(value) for value in inputs.values()}) != 1:
        raise ValueError("All profile arrays must have equal lengths")


def compute(profile: str, inputs: dict) -> dict:
    validate(profile, inputs)
    if profile == "forecast_verification":
        count = len(inputs["forecast_k"])
        errors = [f - o for f, o in zip(inputs["forecast_k"], inputs["observation_k"])]
        baseline_errors = [p - o for p, o in zip(inputs["persistence_k"], inputs["observation_k"])]
        squared_error_sum = math.fsum(error * error for error in errors)
        baseline_squared_error_sum = math.fsum(error * error for error in baseline_errors)
        mse = squared_error_sum / count
        baseline_mse = baseline_squared_error_sum / count
        return {
            "bias_k": math.fsum(errors) / count,
            "mae_k": math.fsum(abs(error) for error in errors) / count,
            "rmse_k": math.sqrt(mse),
            "persistence_rmse_k": math.sqrt(baseline_mse),
            # Difference of squares avoids cancellation of large near-equal MSEs.
            "mse_improvement_k2": math.fsum((baseline - error) * (baseline + error)
                for baseline, error in zip(baseline_errors, errors)) / count,
        }

    z = inputs["height_m"]
    buoyancy = [GRAVITY_M_S2 * (parcel - env) / env for parcel, env in zip(
        inputs["parcel_virtual_temperature_k"], inputs["environment_virtual_temperature_k"])]
    positive, negative = [], []
    for z0, z1, b0, b1 in zip(z, z[1:], buoyancy, buoyancy[1:]):
        depth = z1 - z0
        if b0 >= 0 and b1 >= 0:
            positive.append(0.5 * depth * (b0 + b1))
        elif b0 <= 0 and b1 <= 0:
            negative.append(0.5 * depth * (b0 + b1))
        else:
            fraction = abs(b0) / (abs(b0) + abs(b1))
            first = 0.5 * depth * fraction * b0
            second = 0.5 * depth * (1 - fraction) * b1
            positive.append(max(first, second))
            negative.append(min(first, second))
    pos, neg = math.fsum(positive), math.fsum(negative)
    du = inputs["eastward_wind_m_s"][-1] - inputs["eastward_wind_m_s"][0]
    dv = inputs["northward_wind_m_s"][-1] - inputs["northward_wind_m_s"][0]
    return {
        "buoyancy_m_s2": buoyancy,
        "positive_buoyancy_integral_j_kg": pos,
        "negative_buoyancy_integral_j_kg": neg,
        "net_buoyancy_integral_j_kg": pos + neg,
        "bulk_shear_eastward_m_s": du,
        "bulk_shear_northward_m_s": dv,
        "bulk_shear_m_s": math.hypot(du, dv),
        "layer_depth_m": z[-1] - z[0],
    }


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)


def checks(profile: str, inputs: dict, values: dict) -> dict[str, bool]:
    """Check independent algebraic identities; never invoke the producer.

    Invalid inputs raise ValueError. Malformed candidate results fail closed.
    Every declared output is bound to the input or an independently checked
    output. Tolerances only cover floating-point closure, not measurement error.
    """
    validate(profile, inputs)
    try:
        keys(values, set(PROFILES[profile]["units"]))
        for name, value in values.items():
            if name == "buoyancy_m_s2":
                if type(value) is not list or len(value) != len(inputs["height_m"]):
                    raise ValueError("Buoyancy output length differs from sounding")
                for entry in value:
                    number(entry)
            else:
                number(value)
    except (ValueError, TypeError, OverflowError):
        return {"output_contract": False}

    if profile == "forecast_verification":
        n = len(inputs["observation_k"])
        pairs = list(zip(inputs["forecast_k"], inputs["observation_k"], inputs["persistence_k"]))
        forecast_sse = math.fsum((f - o) ** 2 for f, o, _ in pairs)
        baseline_sse = math.fsum((p - o) ** 2 for _, o, p in pairs)
        return {
            "output_contract": True,
            "bias_identity": _close(n * values["bias_k"], math.fsum(f - o for f, o, _ in pairs)),
            "absolute_error_identity": values["mae_k"] >= 0 and _close(
                n * values["mae_k"], math.fsum(abs(f - o) for f, o, _ in pairs)),
            "forecast_squared_error_identity": values["rmse_k"] >= 0 and _close(
                n * values["rmse_k"] ** 2, forecast_sse),
            "persistence_squared_error_identity": values["persistence_rmse_k"] >= 0 and _close(
                n * values["persistence_rmse_k"] ** 2, baseline_sse),
            "mse_improvement_identity": _close(n * values["mse_improvement_k2"],
                math.fsum((p - f) * (p + f - 2 * o) for f, o, p in pairs)),
            "error_inequalities": abs(values["bias_k"]) <= values["mae_k"] + 1e-10
                and values["mae_k"] <= values["rmse_k"] + 1e-10,
        }

    b, z = values["buoyancy_m_s2"], inputs["height_m"]
    signed_parts, absolute_parts = [], []
    for a, c, z0, z1 in zip(b, b[1:], z, z[1:]):
        depth = z1 - z0
        signed_parts.append(depth * (a + c) / 2)
        if a * c < 0:
            # Integral |B| for a linear sign-changing segment: two triangles.
            absolute_parts.append(depth * (a * a + c * c) / (2 * (abs(a) + abs(c))))
        else:
            absolute_parts.append(depth * (abs(a) + abs(c)) / 2)
    signed_area, absolute_area = math.fsum(signed_parts), math.fsum(absolute_parts)
    pos, neg = values["positive_buoyancy_integral_j_kg"], values["negative_buoyancy_integral_j_kg"]
    return {
        "output_contract": True,
        "buoyancy_identity": all(_close(accel * env, GRAVITY_M_S2 * (parcel - env))
            for accel, env, parcel in zip(b, inputs["environment_virtual_temperature_k"], inputs["parcel_virtual_temperature_k"])),
        "integral_signs": pos >= 0 and neg <= 0,
        "signed_area_identity": _close(pos + neg, signed_area),
        "absolute_area_identity": _close(pos - neg, absolute_area),
        "net_area_identity": _close(values["net_buoyancy_integral_j_kg"], signed_area),
        "eastward_shear_identity": _close(values["bulk_shear_eastward_m_s"], inputs["eastward_wind_m_s"][-1] - inputs["eastward_wind_m_s"][0]),
        "northward_shear_identity": _close(values["bulk_shear_northward_m_s"], inputs["northward_wind_m_s"][-1] - inputs["northward_wind_m_s"][0]),
        "shear_norm_identity": values["bulk_shear_m_s"] >= 0 and _close(values["bulk_shear_m_s"] ** 2,
            values["bulk_shear_eastward_m_s"] ** 2 + values["bulk_shear_northward_m_s"] ** 2),
        "layer_depth_identity": _close(values["layer_depth_m"], z[-1] - z[0]),
    }
