"""Bounded scalar-square remainder enclosure with an exact rational reference.

The enclosure describes the declared polynomial over a closed interval. It is
neither a confidence interval nor validation of a physical model or its bounds.
"""
from copy import deepcopy
from fractions import Fraction
import math
import re
import struct

from .telemetry import canonical

PROFILE = "scalar-square-interval.v1"
MODEL = "scalar-square.v1"
METHOD = "independent_python_rational_enclosure"
SEMANTICS = {"layout": "scalar", "input_unit": "1", "output_unit": "1",
             "frame": "dimensionless-cartesian", "clock": "not_applicable"}
CONFIGURATION = {"input_encoding": "reduced-rational", "endpoint_encoding": "ieee754-binary64-hex",
                 "rounding": "correct", "power": "slow", "decoration": "com", "guaranteed": True,
                 "covariance_status": "not_applicable", "calibration_status": "not_applicable"}


def rational(value):
    from .native_interop_contract import keys
    keys(value, {"numerator", "denominator"})
    n, d = value["numerator"], value["denominator"]
    if type(n) is not int or type(d) is not int or abs(n) > 1_000_000 or not 1 <= d <= 1_000_000:
        raise ValueError("Require bounded exact rational integers")
    if math.gcd(n, d) != 1:
        raise ValueError("Require a reduced rational, including zero as 0/1")
    return Fraction(n, d)


def validate_payload(p):
    from .native_interop_contract import keys
    keys(p, {"model", "x", "variation_lower", "variation_upper", "error_limit"})
    if p["model"] != MODEL:
        raise ValueError("Unsupported interval model")
    x, lo, hi, limit = (rational(p[name]) for name in ("x", "variation_lower", "variation_upper", "error_limit"))
    if not (-100 <= x <= 100 and -200 <= lo <= hi <= 200 and
            -100 <= x + lo <= x + hi <= 100 and 0 <= limit <= 40000):
        raise ValueError("Interval input exceeds the declared scalar-square domain")
    return deepcopy(p)


def reference(p):
    """Exact extrema, independent of the worker's interval implementation."""
    validate_payload(p)
    lo, hi, limit = (rational(p[name]) for name in ("variation_lower", "variation_upper", "error_limit"))
    lower = Fraction(0) if lo <= 0 <= hi else min(lo * lo, hi * hi)
    return lower - limit, max(lo * lo, hi * hi) - limit


def endpoint(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{16}", value):
        raise ValueError("Require exact binary64 endpoint bits")
    result = struct.unpack(">d", bytes.fromhex(value))[0]
    if not math.isfinite(result):
        raise ValueError("Interval endpoint is not finite")
    return result


def conclusion(lo, hi):
    return "holds_throughout" if hi <= 0 else "fails_throughout" if lo > 0 else "inconclusive"


def validate_output(s, data):
    """Inspect declarations and sign classification without executing an oracle."""
    from .native_interop_contract import keys
    keys(data, {"model", "expression", "enclosure", "requirement", "configuration"})
    if data["model"] != s["payload"]["model"] or data["expression"] != "u^2-error_limit":
        raise ValueError("Interval mathematical claim differs")
    if canonical(data["configuration"]) != canonical(CONFIGURATION):
        raise ValueError("Interval construction or rounding policy differs")
    e = data["enclosure"]
    keys(e, {"lower_hex", "upper_hex", "decoration", "guaranteed"})
    if e["decoration"] != "com" or e["guaranteed"] is not True:
        raise ValueError("Interval must be common and guaranteed")
    lo, hi = endpoint(e["lower_hex"]), endpoint(e["upper_hex"])
    if lo > hi or data["requirement"] != conclusion(lo, hi):
        raise ValueError("Interval ordering or requirement classification differs")
    return data


def check_output(s, data):
    from .native_interop_contract import AUTHORITY
    validate_output(s, data)
    actual_lo, actual_hi = (Fraction.from_float(endpoint(data["enclosure"][key])) for key in ("lower_hex", "upper_hex"))
    exact_lo, exact_hi = reference(s["payload"])
    if actual_lo > exact_lo or actual_hi < exact_hi:
        raise ValueError("Provider interval fails exact rational containment")
    # Shared envelope scalar is zero for no containment violation. It does not
    # claim equality of the exact range and the rounded enclosure endpoints.
    return {"outcome": "passed", "method": METHOD, "max_abs_discrepancy": 0,
            "policy": deepcopy(CONFIGURATION), "authority": deepcopy(AUTHORITY)}
