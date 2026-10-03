"""Independent numerical audit of the linear reservoir/piston candidate.

Fresh verification checks finite midpoint residuals, swept-volume conservation,
passive energy balances, work-conjugate exchange, and a separately assembled
modal exponential. Static report validation never runs the provider or reference.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .control_contracts import keys, number
from .fluid_reservoir_contract import (
    CLAIM_SCOPE, EXPANSION_OBSERVABLES, REPORT_SCHEMA, RESOLUTION_FACTORS,
    continuous_bounds, validate_request, validate_result,
)
from .fluid_reservoir_reference import REFERENCE_ID, MAX_EIGENBASIS_CONDITION, reference
from .operations.runner import check_seal, digest, seal

VERIFIER_ID = "independent_reservoir_balance_and_modal_audit_binary64.v1"
MAX_RESIDUAL = 1e150
STATE_ORDER = ["transfer_m3","flow_m3_per_s","piston_displacement_m","piston_velocity_m_per_s"]
CHECK_TOLERANCES = {
    "initial_state": "equations_relative", "constitutive": "equations_relative",
    "kinematics": "equations_relative", "hydraulic_momentum": "equations_relative",
    "structural_momentum": "equations_relative", "midpoint_work_quadrature": "equations_relative",
    "mass_balance": "balance_relative", "fluid_energy_balance": "balance_relative",
    "structure_energy_balance": "balance_relative", "total_energy_balance": "balance_relative",
    "interface_work_conjugacy": "balance_relative", "modal_reference": "reference_relative",
    "temporal_refinement": "refinement_relative", "temporal_second_order": None,
    "retained_domain": None, "clock_budget": None,
}
LIMITATIONS = [
    "Numerical qualification of a synthetic, unforced, linear incompressible two-reservoir lumped continuum model with an optional preloaded compliant piston only.",
    "Reservoir heads and pressures are deviations from equilibrium; equilibrium free surfaces share a common horizontal datum, and piston preload balances equilibrium hydrostatic pressure. Hydrostatic column inertia is neglected; connector slug inertia is retained.",
    "Hydraulic resistance is a declared constant linear constitutive coefficient; no viscosity, Reynolds-number transition, turbulence or nonlinear drag law is inferred.",
    "No molecule, SPH parcel or suspended grain is represented; no spatial velocity field, propagating surface gravity wave, acoustic wave, wetting/drying or breaking wave is qualified.",
    "Initial energy and nonnegative damping bound the entire exact passive linear trajectory within the declared small-head, piston-travel and velocity domain; this domain is a model declaration, not an experimentally established regime.",
    "A fixed midpoint clock and three finite resolutions provide an empirical second-order check; neither eigen-reference agreement nor refinement is an exact-arithmetic proof or certified continuum-error bound.",
    "An ill-conditioned or defective modal eigenbasis is refused by the independent reference; critical damping is not universally covered.",
    "Energy and interface work include perturbation energies and connector liquid volume; baseline hydrostatic preload energy is outside the perturbation model.",
    "No experimental validation, material failure prediction, uncertainty calibration, live boundary provider, actuator control or canonical state admission is performed.",
    "Content seals bind retained bytes and declarations. A coherent forged report can pass a static read; a fresh numerical verification is required to reassess its physics.",
]


def _residual(value):
    return min(abs(value),MAX_RESIDUAL) if math.isfinite(value) else MAX_RESIDUAL


def _error(observed,expected,scale):
    return _residual((observed-expected)/max(scale,1e-30))


def _spec(request):
    return {name: 0.0 if key is None else request["tolerances"][key] for name,key in CHECK_TOLERANCES.items()}


def _summary(result):
    trace = result["resolutions"]["finer"]["trace"]
    return {"sample_count": len(trace["time_s"]), "duration_s": trace["time_s"][-1],
            "maximum_head1_m": max(abs(v) for v in trace["head1_m"]),
            "maximum_head2_m": max(abs(v) for v in trace["head2_m"]),
            "maximum_piston_displacement_m": max(abs(v) for v in trace["piston_displacement_m"]),
            "maximum_connector_velocity_m_per_s": max(abs(v) for v in trace["connector_velocity_m_per_s"]),
            "initial_total_energy_j": trace["total_energy_j"][0],
            "terminal_total_energy_j": trace["total_energy_j"][-1],
            "terminal_total_dissipation_j": trace["fluid_dissipation_j"][-1]+trace["structure_dissipation_j"][-1],
            "terminal_structure_interface_work_j": trace["structure_interface_work_j"][-1]}


def _terminal(result):
    return {name: values[-1] for name,values in result["resolutions"]["finer"]["trace"].items()}


def _qualification(request,passed):
    unsupported = sorted(set(request["desired_observables"]) & EXPANSION_OBSERVABLES)
    supported = sorted(set(request["desired_observables"])-set(unsupported))
    return {"action": "REFUSE" if not passed else "EXPAND" if unsupported else "LOCAL",
            "supported_observables": supported, "unsupported_observables": unsupported,
            "reason": "Numerical checks failed for the declared reservoir model." if not passed else
                "Requested observables require an additional qualified provider." if unsupported else
                "Numerical checks passed within the declared linear reservoir/piston model."}


def _audit(request,result):
    f,rs,co,st,ini = (request[name] for name in ("fluid","reservoirs","connector","structure","initial"))
    rho_g = f["density_kg_per_m3"]*9.80665
    a1,a2 = rs["area1_m2"],rs["area2_m2"]
    area = st["piston_area_m2"] if st["enabled"] else 0.0
    inertia = f["density_kg_per_m3"]*co["length_m"]/co["area_m2"]
    resistance,m,k,c = co["resistance_pa_s_per_m3"],st["mass_kg"],st["stiffness_n_per_m"],st["damping_n_s_per_m"]
    bounds = continuous_bounds(request)
    energy_scale = bounds["initial_energy_j"]
    state_scales = [max(bounds[name],1e-12) for name in STATE_ORDER]
    pressure_scale = max(rho_g*(bounds["head1_m"]+bounds["head2_m"]),1e-12)
    force_scale = max(area*rho_g*bounds["head2_m"],k*bounds["piston_displacement_m"],c*bounds["piston_velocity_m_per_s"],1e-12)
    volume_base = a1*rs["equilibrium_depth1_m"]+a2*rs["equilibrium_depth2_m"]+co["length_m"]*co["area_m2"]
    mass_base = f["density_kg_per_m3"]*volume_base
    errors = {name: 0.0 for name in CHECK_TOLERANCES}
    for label in RESOLUTION_FACTORS:
        row = result["resolutions"][label]
        tr,dt = row["trace"],row["dt_s"]
        ef0,es0 = tr["fluid_energy_j"][0],tr["structure_energy_j"][0]
        for name,scale in zip(STATE_ORDER,state_scales):
            errors["initial_state"] = max(errors["initial_state"],_error(tr[name][0],ini[name],scale))
        for index in range(len(tr["time_s"])):
            r,q,x,v = (tr[name][index] for name in STATE_ORDER)
            h1,h2 = -r/a1,(r-area*x)/a2
            p1,p2 = rho_g*h1,rho_g*h2
            v1,v2,sw = a1*rs["equilibrium_depth1_m"]-r,a2*rs["equilibrium_depth2_m"]+r-area*x,area*x
            total_volume = v1+v2+sw+co["length_m"]*co["area_m2"]
            ef = .5*inertia*q*q+.5*rho_g*(a1*h1*h1+a2*h2*h2)
            es = .5*(m*v*v+k*x*x) if st["enabled"] else 0.0
            expected = {
                "head1_m": (h1,max(bounds["head1_m"],1e-12)), "head2_m": (h2,max(bounds["head2_m"],1e-12)),
                "pressure1_deviation_pa": (p1,pressure_scale), "pressure2_deviation_pa": (p2,pressure_scale),
                "pressure_difference_pa": (p1-p2,pressure_scale), "interface_force_n": (area*p2,force_scale),
                "connector_velocity_m_per_s": (q/co["area_m2"],max(bounds["flow_m3_per_s"]/co["area_m2"],1e-12)),
                "reservoir1_volume_m3": (v1,volume_base), "reservoir2_column_volume_m3": (v2,volume_base),
                "piston_swept_volume_m3": (sw,volume_base), "total_liquid_volume_m3": (total_volume,volume_base),
                "total_liquid_mass_kg": (f["density_kg_per_m3"]*total_volume,mass_base),
                "fluid_energy_j": (ef,energy_scale), "structure_energy_j": (es,energy_scale),
                "total_energy_j": (ef+es,energy_scale),
            }
            errors["constitutive"] = max(errors["constitutive"],max(_error(tr[name][index],value,scale) for name,(value,scale) in expected.items()))
            errors["mass_balance"] = max(errors["mass_balance"],_error(tr["total_liquid_mass_kg"][index],mass_base,mass_base))
            df,ds = tr["fluid_dissipation_j"][index],tr["structure_dissipation_j"][index]
            wf,ws = tr["fluid_interface_work_j"][index],tr["structure_interface_work_j"][index]
            errors["fluid_energy_balance"] = max(errors["fluid_energy_balance"],_error(tr["fluid_energy_j"][index]+df-wf,ef0,energy_scale))
            errors["structure_energy_balance"] = max(errors["structure_energy_balance"],_error(tr["structure_energy_j"][index]+ds-ws,es0,energy_scale))
            errors["total_energy_balance"] = max(errors["total_energy_balance"],_error(tr["total_energy_j"][index]+df+ds,energy_scale,energy_scale))
            errors["interface_work_conjugacy"] = max(errors["interface_work_conjugacy"],_error(wf+ws,0.0,energy_scale))
            # Algebraic inequalities here are a candidate-domain screen; the
            # request separately retains the continuous passive-energy bound.
            violated = (abs(h1)>0.1*rs["equilibrium_depth1_m"]*(1+1e-12) or
                        abs(h2)>0.1*rs["equilibrium_depth2_m"]*(1+1e-12) or
                        abs(x)>st["maximum_displacement_m"]*(1+1e-12) or
                        abs(q/co["area_m2"])>10*(1+1e-12) or abs(v)>10*(1+1e-12))
            errors["retained_domain"] = max(errors["retained_domain"],float(violated))
            if index:
                rm,qm,xm,vm = ((tr[name][index]+tr[name][index-1])/2 for name in STATE_ORDER)
                delta_r,delta_q,delta_x,delta_v = ((tr[name][index]-tr[name][index-1])/dt for name in STATE_ORDER)
                errors["kinematics"] = max(errors["kinematics"],_error(delta_r,qm,state_scales[1]),_error(delta_x,vm,state_scales[3]))
                expected_q_force = rho_g*(-rm/a1-(rm-area*xm)/a2)-resistance*qm
                errors["hydraulic_momentum"] = max(errors["hydraulic_momentum"],_error(inertia*delta_q,expected_q_force,pressure_scale))
                expected_v_force = area*rho_g*(rm-area*xm)/a2-k*xm-c*vm if st["enabled"] else 0.0
                errors["structural_momentum"] = max(errors["structural_momentum"],_error(m*delta_v,expected_v_force,force_scale))
                work_increment = dt*area*rho_g*(rm-area*xm)/a2*vm
                quadratures = [(tr["fluid_dissipation_j"][index]-tr["fluid_dissipation_j"][index-1],dt*resistance*qm*qm),
                               (tr["structure_dissipation_j"][index]-tr["structure_dissipation_j"][index-1],dt*c*vm*vm if st["enabled"] else 0.0),
                               (tr["structure_interface_work_j"][index]-tr["structure_interface_work_j"][index-1],work_increment),
                               (tr["fluid_interface_work_j"][index]-tr["fluid_interface_work_j"][index-1],-work_increment)]
                errors["midpoint_work_quadrature"] = max(errors["midpoint_work_quadrature"],max(_error(a,b,energy_scale) for a,b in quadratures))
        errors["clock_budget"] = max(errors["clock_budget"],float(row["step_count"]>4096))
    times = result["resolutions"]["coarse"]["trace"]["time_s"]
    independent = reference(request,times)
    level_errors = {}
    for label,factor in RESOLUTION_FACTORS.items():
        trace = result["resolutions"][label]["trace"]
        level_errors[label] = max(_error(trace[name][index*factor],expected[j],state_scales[j])
                                  for index,expected in enumerate(independent["state"])
                                  for j,name in enumerate(STATE_ORDER))
    fine,finer = result["resolutions"]["fine"]["trace"],result["resolutions"]["finer"]["trace"]
    errors["modal_reference"] = level_errors["finer"]
    errors["temporal_refinement"] = max(_error(fine[name][2*index],finer[name][4*index],state_scales[j])
                                      for index in range(len(times)) for j,name in enumerate(STATE_ORDER))
    # Below this floor, binary64 error cannot establish an observed order.
    resolved = level_errors["finer"]>1e-10
    ratios = [level_errors["coarse"]/max(level_errors["fine"],1e-30),
              level_errors["fine"]/max(level_errors["finer"],1e-30)]
    errors["temporal_second_order"] = max([0.0]+[max(0.0,3.2-ratio,ratio-4.8) for ratio in ratios]) if resolved else 0.0
    return errors,independent,level_errors,ratios,resolved,bounds


def verify(request: dict,result: dict) -> dict:
    request,result = validate_request(request),validate_result(request,result)
    residuals,independent,level_errors,ratios,resolved,bounds = _audit(request,result)
    spec = _spec(request)
    checks = [{"name":name,"value":residuals[name],"tolerance":spec[name],
               "status":"PASS" if residuals[name]<=spec[name] else "FAIL"} for name in sorted(spec)]
    passed = all(row["status"]=="PASS" for row in checks)
    return seal({"schema":REPORT_SCHEMA,"request_digest":digest(request),"candidate_digest":result["record_digest"],
                 "claim_scope":CLAIM_SCOPE,"verifier":VERIFIER_ID,"thresholds":deepcopy(request["tolerances"]),
                 "status":"PASS" if passed else "FAIL","checks":checks,"reference":independent,
                 "metrics":{"residuals":residuals,"summary":_summary(result),"terminal":_terminal(result),
                            "resolution_errors":level_errors,"convergence_ratios":ratios,
                            "convergence_resolved":resolved,"continuous_bounds":bounds},
                 "qualification":_qualification(request,passed),"limitations":list(LIMITATIONS)})


def validate_report(request: dict,result: dict,report: dict) -> None:
    """Validate retained types/bindings/check coherence without physics replay."""
    request,result = validate_request(request),validate_result(request,result)
    keys(report,{"schema","request_digest","candidate_digest","claim_scope","verifier","thresholds","status",
                 "checks","reference","metrics","qualification","limitations","record_digest"})
    declarations = {"schema":REPORT_SCHEMA,"request_digest":digest(request),"candidate_digest":result["record_digest"],
                    "claim_scope":CLAIM_SCOPE,"verifier":VERIFIER_ID,"thresholds":request["tolerances"],"limitations":LIMITATIONS}
    for name,expected in declarations.items():
        if report[name]!=expected:
            raise ValueError("Stored reservoir verification identity differs: "+name)
    keys(report["thresholds"],set(request["tolerances"]))
    for value in report["thresholds"].values():
        number(value)
    ref = report["reference"]
    keys(ref,{"method","eigenbasis_condition","time_s","state_order","state"})
    if ref["method"]!=REFERENCE_ID or ref["time_s"]!=result["resolutions"]["coarse"]["trace"]["time_s"] or ref["state_order"]!=STATE_ORDER:
        raise ValueError("Stored modal reference declaration differs")
    if not 1.0<=number(ref["eigenbasis_condition"])<=MAX_EIGENBASIS_CONDITION:
        raise ValueError("Stored modal conditioning exceeds its declared bound")
    if type(ref["time_s"]) is not list:
        raise ValueError("Stored reference times must be a list")
    for value in ref["time_s"]:
        number(value)
    if type(ref["state"]) is not list or len(ref["state"])!=len(ref["time_s"]):
        raise ValueError("Stored reference state count differs")
    for row in ref["state"]:
        if type(row) is not list or len(row)!=4:
            raise ValueError("Stored modal states require four declared coordinates")
        for value in row:
            if abs(number(value))>1e12:
                raise ValueError("Stored modal state exceeds its finite bound")
    metrics = report["metrics"]
    keys(metrics,{"residuals","summary","terminal","resolution_errors","convergence_ratios","convergence_resolved","continuous_bounds"})
    keys(metrics["residuals"],set(CHECK_TOLERANCES))
    for value in metrics["residuals"].values():
        if not 0<=number(value)<=MAX_RESIDUAL:
            raise ValueError("Stored residual must be finite and nonnegative")
    if metrics["summary"]!=_summary(result) or metrics["terminal"]!=_terminal(result) or metrics["continuous_bounds"]!=continuous_bounds(request):
        raise ValueError("Stored reservoir summary, terminal or continuous-domain declaration differs")
    keys(metrics["summary"],set(_summary(result)))
    if type(metrics["summary"]["sample_count"]) is not int:
        raise ValueError("Stored sample count must be an integer")
    for name,value in metrics["summary"].items():
        if name!="sample_count":
            number(value)
    keys(metrics["terminal"],set(_terminal(result)))
    for value in metrics["terminal"].values():
        number(value)
    keys(metrics["continuous_bounds"],set(continuous_bounds(request)))
    for value in metrics["continuous_bounds"].values():
        number(value)
    keys(metrics["resolution_errors"],set(RESOLUTION_FACTORS))
    for value in metrics["resolution_errors"].values():
        if not 0<=number(value)<=MAX_RESIDUAL:
            raise ValueError("Stored resolution error must be nonnegative")
    ratios = metrics["convergence_ratios"]
    if type(ratios) is not list or len(ratios)!=2 or any(not 0<=number(v)<=MAX_RESIDUAL for v in ratios):
        raise ValueError("Stored convergence ratios must be two nonnegative values")
    if type(metrics["convergence_resolved"]) is not bool:
        raise ValueError("Stored convergence resolution flag must be a boolean")
    errors = metrics["resolution_errors"]
    expected_ratios = [errors["coarse"]/max(errors["fine"],1e-30),errors["fine"]/max(errors["finer"],1e-30)]
    resolved = errors["finer"]>1e-10
    order = max([0.0]+[max(0.0,3.2-r, r-4.8) for r in expected_ratios]) if resolved else 0.0
    if ratios!=expected_ratios or metrics["convergence_resolved"]!=resolved or metrics["residuals"]["modal_reference"]!=errors["finer"] or metrics["residuals"]["temporal_second_order"]!=order:
        raise ValueError("Stored reference/order checks contradict retained resolution errors")
    spec = _spec(request)
    if type(report["checks"]) is not list or len(report["checks"])!=len(spec):
        raise ValueError("Stored report check count differs")
    names = []
    for row in report["checks"]:
        keys(row,{"name","value","tolerance","status"})
        name = row["name"]
        if type(name) is not str or name not in spec or number(row["value"])!=metrics["residuals"][name] or number(row["tolerance"])!=spec[name] or row["status"]!=("PASS" if row["value"]<=row["tolerance"] else "FAIL"):
            raise ValueError("Stored reservoir check contradicts its metric or tolerance")
        names.append(name)
    if len(set(names))!=len(names) or set(names)!=set(spec):
        raise ValueError("Stored report duplicates or omits a check")
    passed = all(row["status"]=="PASS" for row in report["checks"])
    if report["status"]!=("PASS" if passed else "FAIL") or report["qualification"]!=_qualification(request,passed):
        raise ValueError("Stored reservoir qualification contradicts retained checks")
    check_seal(report)
