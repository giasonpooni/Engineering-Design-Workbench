"""Bounded scalar radiometry references using SI constants and explicit units.

These are monochromatic, idealized numerical models. Brightness temperature is
not a land-surface-temperature retrieval; Beer--Lambert describes the unscattered
direct beam and does not solve atmospheric radiative transfer.
"""
import math
import sys

from .common import keys, number, output_number

# Exact defining SI constants (2019 SI).
H = 6.62607015e-34
C = 299792458.0
K = 1.380649e-23
_LOG_C1 = math.log(2.0 * H * C * C)
_LOG_C2 = math.log(H * C / K)
_LOG_MICROMETRES = math.log(1e6)
_LOG_MAX = math.log(sys.float_info.max)
_RADIANCE_UNIT = "W m^-2 sr^-1 um^-1"
_PLANCK_LIMITATIONS = [
    "Monochromatic ideal blackbody radiance, per micrometre of wavelength.",
    "No band response, emissivity, reflected radiance or atmospheric correction.",
]
_ATMOSPHERE_LIMITATIONS = [
    "Beer-Lambert attenuation of the unscattered direct beam only.",
    "Optical depth is along the reference path; air_mass scales that path.",
    "No scattering into the beam, thermal emission or atmospheric profile retrieval.",
]


def _positive(value, name):
    value = number(value)
    if value <= 0:
        raise ValueError(name + " must be positive")
    return value


def _positive_exp(value, name):
    if value > _LOG_MAX:
        raise ValueError(name + " overflows floating-point range")
    result = math.exp(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(name + " is outside positive floating-point range")
    output_number(result)
    return result


def planck(params):
    """B_lambda(T), with output per um rather than per metre."""
    keys(params, {"wavelength_um", "temperature_k"})
    wavelength = _positive(params["wavelength_um"], "wavelength_um")
    temperature = _positive(params["temperature_k"], "temperature_k")
    log_wavelength_m = math.log(wavelength) - _LOG_MICROMETRES
    log_x = _LOG_C2 - log_wavelength_m - math.log(temperature)
    log_prefactor = _LOG_C1 - 5.0 * log_wavelength_m - _LOG_MICROMETRES
    # Evaluate in log space so intermediate lambda**5 and exp(x) cannot overflow.
    if log_x > _LOG_MAX:
        radiance = 0.0
    else:
        if log_x < -36.0:
            log_denominator = log_x  # expm1(x) / x differs below machine precision
        else:
            x = math.exp(log_x)
            log_denominator = (x + math.log1p(-math.exp(-x))
                               if x > 50.0 else math.log(math.expm1(x)))
        log_radiance = log_prefactor - log_denominator
        if log_radiance > _LOG_MAX:
            raise ValueError("Spectral radiance overflows floating-point range")
        radiance = math.exp(log_radiance)
    output_number(radiance)
    return {
        "wavelength_um": wavelength,
        "temperature_k": temperature,
        "spectral_radiance_w_m2_sr_um": radiance,
        "unit": _RADIANCE_UNIT,
        "underflow": radiance == 0.0,
        "limitations": list(_PLANCK_LIMITATIONS),
    }


def brightness_temperature(params):
    """Invert monochromatic Planck radiance; zero radiance is not invertible here."""
    keys(params, {"wavelength_um", "spectral_radiance_w_m2_sr_um"})
    wavelength = _positive(params["wavelength_um"], "wavelength_um")
    radiance = _positive(params["spectral_radiance_w_m2_sr_um"], "spectral_radiance")
    log_wavelength_m = math.log(wavelength) - _LOG_MICROMETRES
    log_prefactor = _LOG_C1 - 5.0 * log_wavelength_m - _LOG_MICROMETRES
    log_ratio = log_prefactor - math.log(radiance)
    if log_ratio < -36.0:
        log_denominator = log_ratio
    else:
        denominator = (log_ratio + math.log1p(math.exp(-log_ratio))
                       if log_ratio > 50.0 else math.log1p(math.exp(log_ratio)))
        log_denominator = math.log(denominator)
    temperature = _positive_exp(
        _LOG_C2 - log_wavelength_m - log_denominator, "Brightness temperature")
    return {
        "wavelength_um": wavelength,
        "spectral_radiance_w_m2_sr_um": radiance,
        "brightness_temperature_k": temperature,
        "radiance_unit": _RADIANCE_UNIT,
        "limitations": list(_PLANCK_LIMITATIONS) + [
            "Brightness temperature is an equivalent blackbody temperature, not land surface temperature.",
        ],
    }


def transmission(params):
    keys(params, {"optical_depth", "air_mass"})
    depth = number(params["optical_depth"])
    if depth < 0:
        raise ValueError("optical_depth must be nonnegative")
    air_mass = _positive(params["air_mass"], "air_mass")
    transmittance = math.exp(-depth * air_mass)
    return {
        "optical_depth": depth,
        "air_mass": air_mass,
        "transmittance": transmittance,
        "underflow": transmittance == 0.0,
        "limitations": list(_ATMOSPHERE_LIMITATIONS),
    }


def optical_depth(params):
    keys(params, {"transmittance", "air_mass"})
    transmittance = _positive(params["transmittance"], "transmittance")
    if transmittance > 1:
        raise ValueError("transmittance must be in (0, 1]")
    air_mass = _positive(params["air_mass"], "air_mass")
    depth = -math.log(transmittance) / air_mass
    if not math.isfinite(depth):
        raise ValueError("Optical depth overflows floating-point range")
    output_number(depth)
    return {
        "transmittance": transmittance,
        "air_mass": air_mass,
        "optical_depth": 0.0 if depth == 0 else depth,
        "limitations": list(_ATMOSPHERE_LIMITATIONS) + [
            "Zero transmittance is rejected: it cannot identify a finite optical depth.",
        ],
    }


OPERATIONS = {
    "geomatics.radiometry.planck.v1": planck,
    "geomatics.radiometry.brightness-temperature.v1": brightness_temperature,
    "geomatics.atmosphere.transmission.v1": transmission,
    "geomatics.atmosphere.optical-depth.v1": optical_depth,
}
EXAMPLES = {
    "geomatics.radiometry.planck.v1": {"wavelength_um": 10.0, "temperature_k": 300.0},
    "geomatics.radiometry.brightness-temperature.v1": {
        "wavelength_um": 10.0, "spectral_radiance_w_m2_sr_um": 9.924033330070701},
    "geomatics.atmosphere.transmission.v1": {"optical_depth": 0.2, "air_mass": 2.0},
    "geomatics.atmosphere.optical-depth.v1": {"transmittance": 0.5, "air_mass": 2.0},
}
DESCRIPTIONS = {
    "geomatics.radiometry.planck.v1": "Monochromatic blackbody spectral radiance per micrometre",
    "geomatics.radiometry.brightness-temperature.v1": "Equivalent blackbody brightness temperature; not LST",
    "geomatics.atmosphere.transmission.v1": "Direct-beam Beer-Lambert transmittance",
    "geomatics.atmosphere.optical-depth.v1": "Reference-path optical depth from nonzero direct-beam transmittance",
}


def _output_number(value, name, *, positive=False):
    if output_number(value) < 0 or (positive and value == 0):
        raise ValueError("Invalid retained " + name)


def _echo(params, output, names):
    for name in names:
        if type(output[name]) not in (int, float) or output[name] != params[name]:
            raise ValueError("Retained parameter mismatch: " + name)


def _underflow(output, name):
    _output_number(output[name], name)
    if type(output["underflow"]) is not bool or output["underflow"] != (output[name] == 0):
        raise ValueError("Invalid retained underflow status")


def validate_planck(params, output):
    keys(params, {"wavelength_um", "temperature_k"})
    keys(output, {"wavelength_um", "temperature_k", "spectral_radiance_w_m2_sr_um", "unit", "underflow", "limitations"})
    _positive(params["wavelength_um"], "wavelength_um")
    _positive(params["temperature_k"], "temperature_k")
    _echo(params, output, ("wavelength_um", "temperature_k"))
    _underflow(output, "spectral_radiance_w_m2_sr_um")
    if output["unit"] != _RADIANCE_UNIT or output["limitations"] != _PLANCK_LIMITATIONS:
        raise ValueError("Invalid retained Planck units or limitations")


def validate_brightness_temperature(params, output):
    keys(params, {"wavelength_um", "spectral_radiance_w_m2_sr_um"})
    keys(output, {"wavelength_um", "spectral_radiance_w_m2_sr_um", "brightness_temperature_k", "radiance_unit", "limitations"})
    _positive(params["wavelength_um"], "wavelength_um")
    _positive(params["spectral_radiance_w_m2_sr_um"], "spectral_radiance")
    _echo(params, output, ("wavelength_um", "spectral_radiance_w_m2_sr_um"))
    _output_number(output["brightness_temperature_k"], "brightness_temperature_k", positive=True)
    expected = _PLANCK_LIMITATIONS + [
        "Brightness temperature is an equivalent blackbody temperature, not land surface temperature."]
    if output["radiance_unit"] != _RADIANCE_UNIT or output["limitations"] != expected:
        raise ValueError("Invalid retained brightness-temperature units or limitations")


def validate_transmission(params, output):
    keys(params, {"optical_depth", "air_mass"})
    keys(output, {"optical_depth", "air_mass", "transmittance", "underflow", "limitations"})
    if number(params["optical_depth"]) < 0:
        raise ValueError("optical_depth must be nonnegative")
    _positive(params["air_mass"], "air_mass")
    _echo(params, output, ("optical_depth", "air_mass"))
    _underflow(output, "transmittance")
    if output["transmittance"] > 1 or output["limitations"] != _ATMOSPHERE_LIMITATIONS:
        raise ValueError("Invalid retained transmittance range or limitations")


def validate_optical_depth(params, output):
    keys(params, {"transmittance", "air_mass"})
    keys(output, {"transmittance", "air_mass", "optical_depth", "limitations"})
    if _positive(params["transmittance"], "transmittance") > 1:
        raise ValueError("transmittance must be in (0, 1]")
    _positive(params["air_mass"], "air_mass")
    _echo(params, output, ("transmittance", "air_mass"))
    _output_number(output["optical_depth"], "optical_depth")
    expected = _ATMOSPHERE_LIMITATIONS + [
        "Zero transmittance is rejected: it cannot identify a finite optical depth."]
    if output["limitations"] != expected:
        raise ValueError("Invalid retained optical-depth limitations")


OUTPUT_VALIDATORS = {
    "geomatics.radiometry.planck.v1": validate_planck,
    "geomatics.radiometry.brightness-temperature.v1": validate_brightness_temperature,
    "geomatics.atmosphere.transmission.v1": validate_transmission,
    "geomatics.atmosphere.optical-depth.v1": validate_optical_depth,
}
