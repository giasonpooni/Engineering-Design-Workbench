"""Exact independent interval contract tests; synthetic outputs qualify no engine."""
from copy import deepcopy
from fractions import Fraction
import math
import struct

import pytest

from ciw import interval_contract as ic, native_interop_contract as nc
from ciw.telemetry import canonical


def ratio(numerator, denominator=1):
    return {"numerator": numerator, "denominator": denominator}


def payload(*, x=(3, 1), lower=(-1, 2), upper=(1, 2), limit=(1, 4)):
    return {"model": "scalar-square.v1", "x": ratio(*x),
            "variation_lower": ratio(*lower), "variation_upper": ratio(*upper),
            "error_limit": ratio(*limit)}


def bits(value):
    return struct.pack(">d", value).hex()


def declared_output(lower=-0.25, upper=0.0):
    """Hand-declared binary64 bounds, deliberately independent of ic.reference."""
    requirement = ("holds_throughout" if upper <= 0 else
                   "fails_throughout" if lower > 0 else "inconclusive")
    return {"model": "scalar-square.v1", "expression": "u^2-error_limit",
            "enclosure": {"lower_hex": bits(lower), "upper_hex": bits(upper),
                          "decoration": "com", "guaranteed": True},
            "requirement": requirement, "configuration": deepcopy(ic.CONFIGURATION)}


def source(p=None):
    return nc.make_source(ic.PROFILE, "intervals", payload() if p is None else p)


def forbidden(*args, **kwargs):
    raise AssertionError("Retained structural inspection invoked an exact oracle")


def test_source_roundtrip_preserves_exact_configuration():
    s = source()
    assert nc.source(canonical(s)) == s
    assert s["arithmetic"] == "outward-binary64"
    assert s["semantics"] == ic.SEMANTICS
    assert s["configuration"] == ic.CONFIGURATION
    assert s["payload"] == payload()
    check = nc.check_output(s, declared_output())
    assert check == {"outcome": "passed", "method": ic.METHOD,
                     "max_abs_discrepancy": 0, "policy": ic.CONFIGURATION,
                     "authority": nc.AUTHORITY}


@pytest.mark.parametrize("p,expected", [
    (payload(), (Fraction(-1, 4), Fraction(0))),
    (payload(lower=(1, 1), upper=(2, 1), limit=(0, 1)), (Fraction(1), Fraction(4))),
    (payload(lower=(-1, 1), upper=(1, 1), limit=(1, 2)), (Fraction(-1, 2), Fraction(1, 2))),
    (payload(lower=(-2, 1), upper=(-1, 1), limit=(1, 2)), (Fraction(1, 2), Fraction(7, 2))),
    (payload(lower=(1, 10), upper=(1, 10), limit=(1, 100)), (Fraction(0), Fraction(0))),
    (payload(lower=(0, 1), upper=(0, 1), limit=(0, 1)), (Fraction(0), Fraction(0))),
    (payload(x=(100, 1), lower=(-200, 1), upper=(0, 1), limit=(40000, 1)), (Fraction(-40000), Fraction(0))),
    (payload(x=(-100, 1), lower=(0, 1), upper=(200, 1), limit=(40000, 1)), (Fraction(-40000), Fraction(0))),
])
def test_reference_has_exact_independent_extrema(p, expected):
    assert ic.validate_payload(p) == p
    actual = ic.reference(p)
    assert actual == expected
    assert all(type(value) is Fraction for value in actual)


def test_square_remainder_is_independent_of_baseline_x():
    assert ic.reference(payload(x=(-99, 1))) == ic.reference(payload(x=(99, 1)))


@pytest.mark.parametrize("bad", [
    True, 0.1, "1/10", None, [], {},
    ratio(True), ratio(1, True), ratio(1, 0), ratio(1, -1),
    ratio(2, 4), ratio(0, 2), ratio(1000001), ratio(-1000001),
    ratio(1, 1000001), ratio(1.0), ratio(1, 2.0),
    {"numerator": 1, "denominator": 2, "extra": 0},
])
def test_rational_encoding_rejects_coercion_noncanonical_and_unbounded_values(bad):
    p = payload(); p["variation_lower"] = bad
    with pytest.raises(ValueError):
        ic.validate_payload(p)


@pytest.mark.parametrize("p", [
    payload(x=(101, 1)), payload(x=(-101, 1)),
    payload(lower=(1, 1), upper=(0, 1)),
    payload(lower=(-201, 1)), payload(upper=(201, 1)),
    payload(x=(100, 1)), payload(x=(-100, 1)),
    payload(limit=(-1, 1)), payload(limit=(40001, 1)),
])
def test_domain_refusals(p):
    with pytest.raises(ValueError):
        ic.validate_payload(p)


@pytest.mark.parametrize("mutation", ["model", "extra", "missing"])
def test_payload_shape_is_closed(mutation):
    p = payload()
    if mutation == "model": p["model"] = "scalar-cube.v1"
    elif mutation == "extra": p["expression"] = "eval(code)"
    else: del p["x"]
    with pytest.raises(ValueError): ic.validate_payload(p)


@pytest.mark.parametrize("p,lo,hi,label", [
    (payload(), -0.25, 0.0, "holds_throughout"),
    (payload(lower=(1, 1), upper=(2, 1), limit=(0, 1)), 1.0, 4.0, "fails_throughout"),
    (payload(lower=(-1, 1), upper=(1, 1), limit=(1, 2)), -0.5, 0.5, "inconclusive"),
    (payload(lower=(0, 1), upper=(0, 1), limit=(0, 1)), -0.0, 0.0, "holds_throughout"),
    (payload(lower=(1, 10), upper=(1, 10), limit=(1, 100)), -1e-17, 1e-17, "inconclusive"),
])
def test_exact_containment_and_tristate_boundaries(p, lo, hi, label):
    data = declared_output(lo, hi)
    assert data["requirement"] == label
    assert ic.check_output(source(p), data)["outcome"] == "passed"


@pytest.mark.parametrize("side", ["lower", "upper"])
def test_one_ulp_inward_bound_is_rejected_without_tolerance(side):
    lo, hi = -0.25, 0.0
    if side == "lower": lo = math.nextafter(lo, math.inf)
    else: hi = math.nextafter(hi, -math.inf)
    data = declared_output(lo, hi)
    # It is a well-formed interval. Only fresh exact containment must reject it.
    assert ic.validate_output(source(), data) == data
    with pytest.raises(ValueError): ic.check_output(source(), data)


def test_wider_enclosure_is_valid_without_claiming_endpoint_equality():
    data = declared_output(-1.0, 1.0)
    assert ic.check_output(source(), data)["max_abs_discrepancy"] == 0
    assert data["requirement"] == "inconclusive"


@pytest.mark.parametrize("lo,hi,label", [(-1.0, 0.0, "inconclusive"),
    (0.0, 1.0, "fails_throughout"), (math.ulp(0.0), 1.0, "holds_throughout")])
def test_requirement_must_follow_retained_endpoint_signs(lo, hi, label):
    data = declared_output(lo, hi); data["requirement"] = label
    with pytest.raises(ValueError): ic.validate_output(source(), data)


@pytest.mark.parametrize("field,value", [
    ("lower_hex", "0000"), ("lower_hex", "BFD0000000000000"),
    ("lower_hex", "0x0000000000000000"), ("lower_hex", 0),
    ("lower_hex", bits(float("nan"))), ("lower_hex", bits(float("-inf"))),
    ("upper_hex", bits(float("inf"))), ("lower_hex", bits(1.0)),
    ("decoration", "dac"), ("decoration", "ill"),
    ("guaranteed", False), ("guaranteed", 1),
])
def test_malformed_degraded_or_nonfinite_enclosure_is_refused(field, value):
    data = declared_output(); data["enclosure"][field] = value
    with pytest.raises(ValueError): ic.validate_output(source(), data)


@pytest.mark.parametrize("field,value", [
    ("rounding", "fast"), ("power", "fast"), ("decoration", "dac"),
    ("guaranteed", 1), ("input_encoding", "binary64"),
    ("covariance_status", "known"), ("calibration_status", "validated"),
])
def test_configuration_cannot_be_reinterpreted(field, value):
    s = source(); s["configuration"][field] = value
    with pytest.raises(ValueError): nc.source(canonical(s))
    data = declared_output(); data["configuration"][field] = value
    with pytest.raises(ValueError): ic.validate_output(source(), data)


def test_offline_structural_inspection_never_recomputes_reference(monkeypatch):
    s = source(); data = declared_output(-0.1, 0.0)
    monkeypatch.setattr(ic, "reference", forbidden)
    monkeypatch.setattr(ic, "check_output", forbidden)
    # A well-formed but inward bound is retained structurally, never rechecked here.
    assert nc.validate_output(s, data) == data
