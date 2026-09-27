"""Bounded data contracts and independent references for SCR native providers.

These references assess calculations, not physical measurements or authority.
They are called explicitly after execution, never during retained inspection.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re

import numpy as np

from .adapters.subprocess import _json
from .telemetry import canonical

SCHEMA = "ciw.native-interop-source.v1"
PROFILES = {
    "affine-binary64.v1": {"cpp", "julia"},
    "affine-d256.v1": {"cpp", "julia"},
    "oscillator-force-energy.v1": {"cpp"},
    "oscillator-tsit5.v1": {"julia"},
    "control-oscillator.v1": {"julia"},
    "design-qp.v1": {"julia"},
    "reaction-a-to-b.v1": {"catalyst", "cantera"},
    "scalar-square-interval.v1": {"intervals"},
}
AFFINE_SEMANTICS = {"layout": "row-major", "input_units": "dimensionless",
                    "output_units": "dimensionless", "frame": "declared-cartesian", "clock": "not-applicable"}
OSCILLATOR_SEMANTICS = {"layout": "row-major", "input_units": "SI", "output_units": "SI",
                        "frame": "one-dimensional-inertial", "clock": "declared-simulation-time"}
AUTHORITY = {"physical_validation": "not_established", "measurement_uncertainty": "not_declared",
             "state_admission": "not_performed", "hardware_actuation": "not_performed",
             "sp1_verification": "not_performed"}
POLICY = {"atol": 2e-8, "rtol": 2e-8, "qp_kkt_atol": 2e-6,
          "covariance_status": "not_applicable", "calibration": "not_applicable"}


def keys(value, required):
    if type(value) is not dict or set(value) != set(required):
        raise ValueError("Unexpected or missing native interoperability fields")


def number(value, lo, hi):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError("Native interoperability value outside finite bounds")
    return value


def count(value, hi=8, lo=1):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError("Native interoperability dimension or budget outside bounds")
    return value


def vector(value, size=None, *, exact=False, bound=1e6):
    if type(value) is not list or not 1 <= len(value) <= 4096 or (size is not None and len(value) != size):
        raise ValueError("Native interoperability vector shape differs")
    for x in value:
        if exact:
            if type(x) is not int or abs(x) > bound:
                raise ValueError("Exact profile requires bounded integer numerators")
        else:
            number(x, -bound, bound)
    return value


def semantics(profile):
    if profile == "scalar-square-interval.v1":
        from .interval_contract import SEMANTICS
        return deepcopy(SEMANTICS)
    if profile == "reaction-a-to-b.v1":
        from .reaction_contract import SEMANTICS
        return deepcopy(SEMANTICS)
    return deepcopy(AFFINE_SEMANTICS if profile.startswith("affine-") or profile == "design-qp.v1" else OSCILLATOR_SEMANTICS)


def arithmetic(profile):
    if profile == "scalar-square-interval.v1":
        return "outward-binary64"
    return "exact-d256" if profile == "affine-d256.v1" else "binary64"


def policy(profile):
    if profile == "scalar-square-interval.v1":
        from .interval_contract import CONFIGURATION
        return deepcopy(CONFIGURATION)
    return deepcopy(POLICY)


def model(value):
    keys(value, {"omega_0_rad_s", "gamma_s_inv", "mass_kg"})
    number(value["omega_0_rad_s"], math.ulp(1.0), 20)
    number(value["gamma_s_inv"], 0, value["omega_0_rad_s"] / 2)
    number(value["mass_kg"], math.ulp(1.0), 100)


def times(value, *, singleton=False, uniform=False):
    vector(value, bound=12)
    if len(value) < (1 if singleton else 2) or value[0] != 0 or any(b <= a for a, b in zip(value, value[1:])):
        raise ValueError("Require increasing simulation times beginning at zero")
    if uniform:
        dt = value[1] - value[0]
        if any(not math.isclose(x, i * dt, rel_tol=1e-12, abs_tol=1e-12) for i, x in enumerate(value)):
            raise ValueError("JuliaControl profile requires an explicitly uniform grid")


def validate_payload(profile, p):
    if profile == "scalar-square-interval.v1":
        from .interval_contract import validate_payload as validate_interval
        return validate_interval(p)
    if profile == "reaction-a-to-b.v1":
        from .reaction_contract import validate_payload as validate_reaction
        return validate_reaction(p)
    if profile.startswith("affine-"):
        keys(p, {"rows", "columns", "a_row_major", "b", "x0", "delta_x"})
        m, n = count(p["rows"]), count(p["columns"])
        exact = profile == "affine-d256.v1"
        for name, size in (("a_row_major", m*n), ("b", m), ("x0", n), ("delta_x", n)):
            vector(p[name], size, exact=exact, bound=4096 if exact else 1e6)
    elif profile == "design-qp.v1":
        keys(p, {"rows", "columns", "j_row_major", "y0", "target", "regularization", "lower", "upper", "max_iterations"})
        m, n = count(p["rows"]), count(p["columns"])
        for name, size in (("j_row_major", m*n), ("y0", m), ("target", m), ("lower", n), ("upper", n)):
            vector(p[name], size, bound=1e4)
        number(p["regularization"], 1e-6, 1e4)
        count(p["max_iterations"], 10000, 0)
        if any(lo > hi for lo, hi in zip(p["lower"], p["upper"])):
            raise ValueError("QP lower bound exceeds upper bound")
    elif profile == "oscillator-force-energy.v1":
        keys(p, {"model", "time_s", "q_m", "v_m_s"})
        model(p["model"])
        # This new C++ evaluator has a narrower declared numerical domain;
        # the existing Julia oscillator domain remains unchanged.
        if p["model"]["mass_kg"] <= 1e-12 or p["model"]["omega_0_rad_s"] <= 1e-12:
            raise ValueError("Native force profile requires mass and frequency above 1e-12")
        times(p["time_s"], singleton=True)
        vector(p["q_m"], len(p["time_s"]), bound=1000)
        vector(p["v_m_s"], len(p["time_s"]), bound=1000)
    elif profile in {"oscillator-tsit5.v1", "control-oscillator.v1"}:
        keys(p, {"model", "initial_state", "time_s"} | ({"solver"} if profile == "oscillator-tsit5.v1" else set()))
        model(p["model"])
        keys(p["initial_state"], {"q0_m", "v0_m_s"})
        number(p["initial_state"]["q0_m"], -10, 10)
        number(p["initial_state"]["v0_m_s"], -100, 100)
        times(p["time_s"], uniform=profile == "control-oscillator.v1")
        if "solver" in p:
            keys(p["solver"], {"abstol", "reltol", "maxiters"})
            number(p["solver"]["abstol"], 1e-14, 1e-3)
            number(p["solver"]["reltol"], 1e-14, 1e-3)
            count(p["solver"]["maxiters"], 10_000_000)
    else:
        raise ValueError("Unsupported native profile")
    return deepcopy(p)


def source(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= 512*1024:
        raise ValueError("Native source exceeds byte budget")
    s = _json(raw)
    keys(s, {"schema", "experiment_id", "provider", "profile", "arithmetic", "semantics", "payload", "configuration", "upstream"})
    if s["schema"] != SCHEMA or type(s["profile"]) is not str or s["profile"] not in PROFILES or type(s["provider"]) is not str or s["provider"] not in PROFILES[s["profile"]]:
        raise ValueError("Unsupported native source/provider profile")
    if type(s["experiment_id"]) is not str or not 1 <= len(s["experiment_id"]) <= 128:
        raise ValueError("Require bounded experiment identity")
    if s["arithmetic"] != arithmetic(s["profile"]) or s["semantics"] != semantics(s["profile"]) or canonical(s["configuration"]) != canonical(policy(s["profile"])):
        raise ValueError("Native arithmetic, semantics or check policy differs")
    validate_payload(s["profile"], s["payload"])
    if s["upstream"] is not None:
        keys(s["upstream"], {"bundle_digest", "result_id"})
        if s["profile"] != "oscillator-force-energy.v1" or any(not isinstance(v, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", v) for v in s["upstream"].values()):
            raise ValueError("Only force/energy may link a retained trajectory")
    if canonical(s) != raw:
        raise ValueError("Native source must retain its canonical JSON bytes")
    return deepcopy(s)


def make_source(profile, provider, payload, *, experiment_id="native-interop", upstream=None):
    s = {"schema": SCHEMA, "experiment_id": experiment_id, "provider": provider, "profile": profile,
         "arithmetic": arithmetic(profile), "semantics": semantics(profile), "payload": deepcopy(payload),
         "configuration": policy(profile), "upstream": deepcopy(upstream)}
    return source(canonical(s))


def affine_reference(p, exact=False):
    m, n = p["rows"], p["columns"]
    add = sum if exact else math.fsum
    baseline, change, predicted, direct, contributions = [], [], [], [], []
    for i in range(m):
        row = p["a_row_major"][i*n:(i+1)*n]
        base = add(a*x for a, x in zip(row, p["x0"])) + p["b"][i]*(256 if exact else 1)
        part = [a*d for a, d in zip(row, p["delta_x"])]
        delta = add(part)
        evaluated = add(a*(x+d) for a, x, d in zip(row, p["x0"], p["delta_x"])) + p["b"][i]*(256 if exact else 1)
        baseline.append(base); change.append(delta); predicted.append(base+delta); direct.append(evaluated)
        contributions.extend(part)
    return {"rows": m, "columns": n, "baseline_output": baseline, "contributions": contributions,
            "predicted_delta": change, "predicted_output": predicted, "model_output": direct,
            "residual": [x-y for x, y in zip(direct, predicted)], "denominator": 65536 if exact else 1}


def oscillator_reference(p):
    w, g, mass = (p["model"][k] for k in ("omega_0_rad_s", "gamma_s_inv", "mass_kg"))
    q0, v0 = p["initial_state"]["q0_m"], p["initial_state"]["v0_m_s"]
    wd = math.sqrt(w*w-g*g)
    q, v = [], []
    for t in p["time_s"]:
        c, s, decay = math.cos(wd*t), math.sin(wd*t), math.exp(-g*t)
        q.append(decay*(q0*c + (v0+g*q0)*s/wd))
        v.append(decay*(v0*c - (w*w*q0+g*v0)*s/wd))
    return {"time_s": p["time_s"], "q_m": q, "v_m_s": v,
            "energy_j": [mass*(vv*vv+w*w*qq*qq)/2 for qq, vv in zip(q,v)]}


def force_reference(p):
    w, g, mass = (p["model"][k] for k in ("omega_0_rad_s", "gamma_s_inv", "mass_kg"))
    k, c = mass*w*w, 2*mass*g
    restoring = [-k*q for q in p["q_m"]]
    damping = [-c*v for v in p["v_m_s"]]
    net = [a+b for a,b in zip(restoring, damping)]
    potential = [k*q*q/2 for q in p["q_m"]]
    kinetic = [mass*v*v/2 for v in p["v_m_s"]]
    return {"time_s": p["time_s"], "stiffness_n_m": k, "damping_n_s_m": c,
            "restoring_force_n": restoring, "damping_force_n": damping, "net_force_n": net,
            "acceleration_m_s2": [x/mass for x in net], "potential_energy_j": potential,
            "kinetic_energy_j": kinetic, "energy_j": [a+b for a,b in zip(potential, kinetic)]}


def compare(expected, actual, *, exact=False):
    errors = []
    def walk(a,b):
        if type(a) is dict:
            if type(b) is not dict or not a.keys() <= b.keys(): raise ValueError("Provider output missing declared fields")
            for k,v in a.items(): walk(v,b[k])
        elif type(a) is list:
            if type(b) is not list or len(a)!=len(b): raise ValueError("Provider output shape differs")
            for x,y in zip(a,b): walk(x,y)
        elif type(a) in (int,float):
            number(b,-1e20,1e20)
            if exact and (type(b) is not int or a!=b): raise ValueError("Exact affine output differs")
            if not exact and not math.isclose(a,b,rel_tol=POLICY["rtol"],abs_tol=POLICY["atol"]):
                raise ValueError("Provider differs from independent reference")
            errors.append(abs(a-b))
        elif a!=b: raise ValueError("Provider declaration differs")
    walk(expected,actual)
    return max(errors,default=0)


def validate_output(s, data):
    """Structural output checks usable offline; no model evaluation."""
    profile,p=s["profile"],s["payload"]
    if profile == "scalar-square-interval.v1":
        from .interval_contract import validate_output as validate_interval
        return validate_interval(s, data)
    if profile == "reaction-a-to-b.v1":
        from .reaction_contract import validate_output as validate_reaction
        return validate_reaction(s, data)
    if profile.startswith("affine-"):
        keys(data,{"rows","columns","baseline_output","contributions","predicted_delta","predicted_output","model_output","residual","denominator"})
        if type(data["rows"]) is not int or type(data["columns"]) is not int or (data["rows"],data["columns"])!=(p["rows"],p["columns"]):
            raise ValueError("Returned affine dimensions differ")
        exact=profile=="affine-d256.v1"
        if type(data["denominator"]) is not int or data["denominator"]!=(65536 if exact else 1): raise ValueError("Output denominator differs")
        for name in ("baseline_output","contributions","predicted_delta","predicted_output","model_output","residual"):
            vector(data[name],p["rows"]*p["columns"] if name=="contributions" else p["rows"],exact=exact,bound=1e20)
    elif profile=="oscillator-force-energy.v1":
        keys(data,{"time_s","stiffness_n_m","damping_n_s_m","restoring_force_n","damping_force_n","net_force_n","acceleration_m_s2","potential_energy_j","kinetic_energy_j","energy_j"})
        if data["time_s"]!=p["time_s"]: raise ValueError("Force time grid differs")
        for name,value in data.items():
            if name in {"stiffness_n_m","damping_n_s_m"}: number(value,0,1e20)
            else: vector(value,len(p["time_s"]),bound=1e20)
    elif profile in {"oscillator-tsit5.v1","control-oscillator.v1"}:
        extra={"schema","operation_id","request_id"} if profile=="oscillator-tsit5.v1" else {"state_order"}
        keys(data,{"time_s","q_m","v_m_s","energy_j","solver"}|extra)
        vector(data["time_s"],len(p["time_s"]),bound=12)
        if data["time_s"]!=p["time_s"]: raise ValueError("Response resampled the submitted grid")
        for name in ("q_m","v_m_s","energy_j"): vector(data[name],len(p["time_s"]),bound=1e20)
        if type(data["solver"]) is not dict or data["solver"].get("retcode")!="Success": raise ValueError("Numerical solver did not succeed")
        solver=data["solver"]
        if profile=="control-oscillator.v1":
            keys(solver,{"algorithm","method","sample_interval_s","controlsystemsbase_version","retcode"})
            number(solver["sample_interval_s"],0,12)
            if data["state_order"]!=["q","v"] or solver["algorithm"]!="ControlSystemsBase.lsim" or solver["method"]!="zoh" or solver["controlsystemsbase_version"]!="1.22.0" or solver["sample_interval_s"]!=p["time_s"][1]-p["time_s"][0]:
                raise ValueError("Control response declaration differs")
        else:
            keys(solver,{"algorithm","retcode","abstol","reltol","accepted_steps","rejected_steps"})
            if data["schema"]!="ciw.julia-oscillator-result.v1" or data["operation_id"]!="ciw.julia-oscillator.v1" or solver["algorithm"]!="Tsit5" or any(solver[k]!=p["solver"][k] for k in ("abstol","reltol")):
                raise ValueError("Tsit5 response declaration differs")
            for k in ("accepted_steps","rejected_steps"):
                if type(solver[k]) is not int or solver[k]<0: raise ValueError("Invalid solver step count")
    elif profile=="design-qp.v1":
        keys(data,{"delta","objective_value","lower_residual","upper_residual","gradient","solver"})
        for name in ("delta","lower_residual","upper_residual","gradient"): vector(data[name],p["columns"],bound=1e20)
        number(data["objective_value"],0,1e20)
        if type(data["solver"]) is not dict or data["solver"].get("termination_status")!="OPTIMAL" or data["solver"].get("primal_status")!="FEASIBLE_POINT":
            raise ValueError("QP provider did not return a feasible optimal candidate")
        solver=data["solver"]
        keys(solver,{"name","version","library_version","jump_version","termination_status","primal_status","options","solve_seconds"})
        if (solver["name"],solver["version"],solver["library_version"],solver["jump_version"])!=("HiGHS","1.25.4","v1.15.1","1.31.2"):
            raise ValueError("QP solver version differs")
        if canonical(solver["options"])!=canonical({"threads":1,"time_limit":10.0,"qp_iteration_limit":p["max_iterations"],"primal_feasibility_tolerance":1e-9,"dual_feasibility_tolerance":1e-9,"random_seed":0}):
            raise ValueError("QP solver options differ")
        number(solver["solve_seconds"],0,180)
    return data


def check_output(s, data):
    """Fresh independent reference check. Never called by retained inspection."""
    p, profile = s["payload"], s["profile"]
    if profile == "scalar-square-interval.v1":
        from .interval_contract import check_output as check_interval
        return check_interval(s, data)
    if profile == "reaction-a-to-b.v1":
        from .reaction_contract import check_output as check_reaction
        return check_reaction(s, data)
    if profile.startswith("affine-"):
        exact = profile == "affine-d256.v1"
        error = compare(affine_reference(p,exact),data,exact=exact)
        method = "independent_python_affine_integer" if exact else "independent_python_affine_binary64"
    elif profile == "oscillator-force-energy.v1":
        error = compare(force_reference(p),data)
        method = "independent_python_force_energy"
    elif profile in {"oscillator-tsit5.v1","control-oscillator.v1"}:
        error = compare(oscillator_reference(p),data)
        method = "independent_python_analytic_oscillator"
    elif profile == "design-qp.v1":
        d = np.asarray(vector(data["delta"],p["columns"],bound=1e5),dtype=float)
        j = np.asarray(p["j_row_major"],dtype=float).reshape(p["rows"],p["columns"])
        r = np.asarray(p["y0"])-np.asarray(p["target"])+j@d
        objective = float((r@r+p["regularization"]*(d@d))/2)
        compare({"objective_value":objective},data)
        lo,hi=np.asarray(p["lower"]),np.asarray(p["upper"])
        violation=float(max(0,np.max(lo-d),np.max(d-hi)))
        gradient=j.T@r+p["regularization"]*d
        compare({"lower_residual":np.maximum(lo-d,0).tolist(),"upper_residual":np.maximum(d-hi,0).tolist(),"gradient":gradient.tolist()},data)
        # Projected gradient vanishes at box-constrained optima, including
        # fixed bounds. This numerical check is not an exact certificate.
        residual=float(np.max(np.abs(d-np.clip(d-gradient,lo,hi))))
        if violation>POLICY["qp_kkt_atol"] or residual>POLICY["qp_kkt_atol"]:
            raise ValueError("QP candidate failed independent feasibility/KKT check")
        error=max(violation,residual)
        method="independent_python_objective_box_projected_gradient"
    else:
        raise ValueError("Unsupported check")
    return {"outcome":"passed","method":method,"max_abs_discrepancy":error,
            "policy":deepcopy(POLICY),"authority":deepcopy(AUTHORITY)}
