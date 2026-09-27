"""Bounded A -> B benchmark: fixed model, smooth state variation, explicit units.

Conservation is complementary to the analytic reference, never a substitute for
it. These checks establish numerical agreement for abstract model species only.
"""
from copy import deepcopy
import math
import re

from .telemetry import byte_digest, canonical

PROFILE = "reaction-a-to-b.v1"
MODEL = "closed-isothermal-a-to-b.v1"
PROVIDERS = {"catalyst", "cantera"}
SEMANTICS = {"layout": "time-major", "concentration_unit": "mol/m^3",
             "production_rate_unit": "mol/m^3/s", "time_unit": "s",
             "temperature_unit": "K", "volume_unit": "m^3",
             "frame": "homogeneous-control-volume", "clock": "declared-simulation-time"}
METHOD = "independent_python_analytic_reaction_and_rate_law"
METRICS = {"trajectory_max_abs_mol_m3", "rate_law_max_abs_mol_m3_s",
           "conservation_max_abs_mol_m3", "minimum_concentration_mol_m3"}


def validate_payload(p):
    from .native_interop_contract import keys, number, count, vector
    keys(p, {"model", "species_order", "initial_concentration_mol_m3", "rate_constant_s_inv",
             "temperature_k", "volume_m3", "time_s", "solver"})
    if p["model"] != MODEL or p["species_order"] not in (["A", "B"], ["B", "A"]):
        raise ValueError("Unsupported reaction model or species order")
    vector(p["initial_concentration_mol_m3"], 2, bound=1000)
    for x in p["initial_concentration_mol_m3"]: number(x, 0, 1000)
    number(math.fsum(p["initial_concentration_mol_m3"]), 1e-6, 1000)
    number(p["rate_constant_s_inv"], 0, 10)
    number(p["temperature_k"], 250, 500)
    number(p["volume_m3"], 1e-6, 1)
    t = vector(p["time_s"], bound=100)
    if not 2 <= len(t) <= 128 or t[0] != 0 or any(b <= a for a,b in zip(t,t[1:])):
        raise ValueError("Reaction time grid must increase from zero")
    if p["rate_constant_s_inv"] * t[-1] > 30:
        raise ValueError("Reaction exposure exceeds the qualified profile")
    keys(p["solver"], {"reltol", "abstol_mol_m3", "max_steps"})
    number(p["solver"]["reltol"], 1e-9, 1e-9)
    number(p["solver"]["abstol_mol_m3"], 1e-11, 1e-11)
    count(p["solver"]["max_steps"], 100000)
    return deepcopy(p)


def reference(p):
    """Independent exact solution evaluated in binary64; stable product growth."""
    validate_payload(p)
    order = p["species_order"]
    initial = dict(zip(order, p["initial_concentration_mol_m3"]))
    a0, b0, k = initial["A"], initial["B"], p["rate_constant_s_inv"]
    concentrations, rates = [], []
    for t in p["time_s"]:
        a = a0 * math.exp(-k*t)
        row = {"A": a, "B": b0 - a0 * math.expm1(-k*t)}
        rate = {"A": -k*a, "B": k*a}
        concentrations.append([row[name] for name in order])
        rates.append([rate[name] for name in order])
    return {"model": MODEL, "species_order": deepcopy(order), "time_s": deepcopy(p["time_s"]),
            "concentration_mol_m3": concentrations, "production_rate_mol_m3_s": rates}


def validate_output(s, data):
    """Retained structural binding checks, with no solver or reference execution."""
    from .native_interop_contract import keys, vector
    p = s["payload"]
    keys(data, {"model", "species_order", "time_s", "concentration_mol_m3",
                "production_rate_mol_m3_s", "mechanism", "solver"})
    vector(data["time_s"], len(p["time_s"]), bound=100)
    for name in ("model", "species_order", "time_s"):
        if data[name] != p[name]: raise ValueError("Reaction output model/order/grid differs")
    for name in ("concentration_mol_m3", "production_rate_mol_m3_s"):
        if type(data[name]) is not list or len(data[name]) != len(p["time_s"]):
            raise ValueError("Reaction output sample count differs")
        for row in data[name]: vector(row, 2, bound=1e8)
    mechanism = data["mechanism"]
    keys(mechanism, {"format", "bytes_hex", "sha256"})
    fmt = "catalyst-code-v1" if s["provider"] == "catalyst" else "cantera-yaml-v1"
    raw = mechanism["bytes_hex"]
    if mechanism["format"] != fmt or type(raw) is not str or not 2 <= len(raw) <= 131072 or not re.fullmatch("[a-f0-9]+", raw) or len(raw)%2:
        raise ValueError("Malformed retained reaction mechanism")
    if byte_digest(bytes.fromhex(raw)) != mechanism["sha256"]:
        raise ValueError("Reaction mechanism byte identity differs")
    bytes.fromhex(raw).decode("utf-8", "strict")
    algorithm = "Catalyst.Tsit5" if s["provider"] == "catalyst" else "Cantera.CVODES"
    if canonical(data["solver"]) != canonical({"algorithm": algorithm, "retcode": "Success", **p["solver"]}):
        raise ValueError("Reaction solver declaration differs")
    return data


def check_output(s, data):
    from .native_interop_contract import compare, POLICY, AUTHORITY
    validate_output(s, data)
    p = s["payload"]
    ref = reference(p)
    compare(ref, data)
    concentrations, rates = data["concentration_mol_m3"], data["production_rate_mol_m3_s"]
    ai = p["species_order"].index("A")
    initial_total = math.fsum(p["initial_concentration_mol_m3"])
    k = p["rate_constant_s_inv"]
    rate_error = 0.0
    for row, actual in zip(concentrations, rates):
        expected = [-k*row[ai] if name == "A" else k*row[ai] for name in p["species_order"]]
        rate_error = max(rate_error, compare(expected, actual))
    balance = max(abs(math.fsum(row)-initial_total) for row in concentrations)
    minimum = min(min(row) for row in concentrations)
    allowance = POLICY["atol"] + POLICY["rtol"] * initial_total
    if balance > allowance or minimum < -POLICY["atol"]:
        raise ValueError("Reaction conservation or numerical admissibility failed")
    metrics = {"trajectory_max_abs_mol_m3": max(abs(x-y) for a,b in zip(ref["concentration_mol_m3"], concentrations) for x,y in zip(a,b)),
               "rate_law_max_abs_mol_m3_s": rate_error,
               "conservation_max_abs_mol_m3": balance, "minimum_concentration_mol_m3": minimum}
    return {"outcome": "passed", "method": METHOD, "max_abs_discrepancy": metrics["trajectory_max_abs_mol_m3"],
            "policy": deepcopy(POLICY), "authority": deepcopy(AUTHORITY), "metrics": metrics}


def validate_metrics(metrics):
    from .native_interop_contract import keys, number
    keys(metrics, METRICS)
    for name,value in metrics.items():
        number(value, -2e-8 if name == "minimum_concentration_mol_m3" else 0, 1e8)
