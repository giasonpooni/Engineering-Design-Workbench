"""Independent continuum-mode, finite-volume and physical interface-work audit.

The verifier does not import the numerical solver or its matrix assembly.
Static retained-report reads do not evaluate PDEs, eigenmodes or propagation.
"""
from copy import deepcopy
import math
import numpy as np

from .control_contracts import keys,number
from .fluid_fsi_contract import (CLAIM_SCOPE,EXPANSION_OBSERVABLES,REFUSED_OBSERVABLES,REPORT_SCHEMA,TRACE_LABELS,
    FIELD_NAMES,SCALAR_NAMES,mode_parameters,trace_declarations,validate_request,validate_result)
from .fluid_fsi_contract import MAX_ELEVATION_DEPTH_FRACTION,MAX_WALL_LENGTH_FRACTION
from .fluid_fsi_reference import REFERENCE_ID,reference
from .operations.runner import check_seal,digest,seal

VERIFIER_ID="independent_continuum_mode_fv_and_conservative_wall_audit_binary64.v1"
CHECK_TOLERANCES={"finite_volume_continuity":"equations_relative","interior_momentum":"equations_relative",
 "wall_momentum":"equations_relative","wall_kinematics":"equations_relative","boundary_velocity":"equations_relative",
 "physical_boundary_traction":"equations_relative","constitutive_fields":"equations_relative",
 "work_quadrature":"equations_relative","mass_balance":"mass_relative","total_energy_balance":"energy_relative",
 "fluid_energy_balance":"energy_relative","structure_energy_balance":"energy_relative","force_conjugacy":"equations_relative",
 "work_conjugacy":"energy_relative","continuous_mode_reference":"analytic_normalized",
 "time_refinement":"time_refinement_normalized","spatial_refinement":"spatial_refinement_normalized",
 "temporal_second_order":None,"spatial_second_order":None,"small_amplitude_domain":None,"initial_mode_binding":"equations_relative"}
LIMITATIONS=[
 "Numerical qualification of a synthetic one-dimensional linear shallow-water channel coupled bidirectionally to one preloaded undamped spring-mass endwall, initialized in its fundamental continuous eigenmode.",
 "The left wall is fixed and reflective; right boundary velocity equals structural velocity. Resting hydrostatic force is balanced by preload; reported interface force and energies are perturbations.",
 "Elevation is a finite-volume cell average. Horizontal velocity is depth averaged and face located; no vertical velocity profile, 3-D Navier--Stokes flow, turbulence, wetting/drying or breaking wave is represented.",
 "The half-dual-cell liquid inertia at the wall remains in fluid kinetic energy. Physical boundary pressure uses its acceleration correction; cell-center pressure is not used as physical wall traction.",
 "Monolithic fixed implicit midpoint uses equal opposite physical interface force/work and a shared provider-owned model clock; no partitioned lag, external solver adapter or live clock synchronization is supplied.",
 "The independent reference solves the continuous coupled characteristic equation and analytically averages its field over each cell. It does not reuse finite-volume matrices or midpoint recurrence.",
 "Finite temporal and spatial refinements establish an empirical second-order comparison within this benchmark; they are not certified error bounds, a general continuum proof or experimental validation.",
 "Nonzero structural damping, material failure, nonlinear moving geometry, arbitrary initial fields, external forcing and external CFD adapters require additional qualified providers; the damper coefficient is fixed at zero.",
 "Hard continuous amplitude/wavelength/travel limits apply to the declared exact eigenmode. Retained numerical fields are separately screened; these limits are modeling assumptions, not calibrated physical accuracy guarantees.",
 "No molecular reduction, arbitrary CFD coupling, physical uncertainty calibration, certified design, canonical state mutation or state admission is performed.",
 "Content seals bind retained declarations. Static reads check report coherence without replay; a coherent forged numerical report can pass a static read, so fresh verification is required to reassess physics."]
MAX_RESIDUAL=1e150


def _norm(values,scale):
    result=float(np.max(np.abs(values))) / max(scale,1e-30)
    return min(result,MAX_RESIDUAL) if math.isfinite(result) else MAX_RESIDUAL


def _spec(request):
    return {name:0.0 if key is None else request["tolerances"][key] for name,key in CHECK_TOLERANCES.items()}


def _qualification(request,passed):
    obs=set(request["desired_observables"])
    unsupported=sorted(obs & (EXPANSION_OBSERVABLES|REFUSED_OBSERVABLES))
    refused=bool(obs & REFUSED_OBSERVABLES)
    action="REFUSE" if not passed or refused else "EXPAND" if unsupported else "LOCAL"
    return {"action":action,"supported_observables":sorted(obs-set(unsupported)),"unsupported_observables":unsupported,
            "reason":"Numerical checks failed or requested claims are explicitly refused." if action=="REFUSE" else
            "Requested observables require an additional qualified provider." if action=="EXPAND" else
            "Numerical checks passed within the declared continuous-mode compliant-wall benchmark."}


def _summary(result):
    t=result["spatial_fine"]
    return {"cells":t["cells"],"sample_count":len(t["time_s"]),"duration_s":t["time_s"][-1],
            "maximum_absolute_elevation_m":max(abs(v) for row in t["free_surface_elevation_m"] for v in row),
            "maximum_absolute_velocity_m_per_s":max(abs(v) for row in t["depth_averaged_velocity_m_per_s"] for v in row),
            "maximum_wall_displacement_m":max(abs(v) for v in t["wall_displacement_m"]),
            "initial_total_energy_j":t["total_energy_j"][0],"terminal_total_energy_j":t["total_energy_j"][-1],
            "terminal_structure_interface_work_j":t["structure_interface_work_j"][-1],
            "terminal_liquid_volume_m3":t["liquid_volume_m3"][-1]}


def _terminal(result):
    t=result["spatial_fine"]
    return {name:t[name][-1] for name in SCALAR_NAMES}


def _state_difference(coarse,fine,time_factor=1,space_factor=1):
    eta=np.array(fine["free_surface_elevation_m"])[::time_factor]
    u=np.array(fine["depth_averaged_velocity_m_per_s"])[::time_factor]
    if space_factor>1:
        eta=eta.reshape(len(coarse["time_s"]),coarse["cells"],space_factor).mean(axis=2)
        u=u[:,::space_factor]
    return (np.array(coarse["free_surface_elevation_m"])-eta,
            np.array(coarse["depth_averaged_velocity_m_per_s"])-u,
            np.array(coarse["wall_displacement_m"])-np.array(fine["wall_displacement_m"])[::time_factor],
            np.array(coarse["wall_velocity_m_per_s"])-np.array(fine["wall_velocity_m_per_s"])[::time_factor])


def _audit(request,result):
    model,wall=request["model"],request["structure"]
    rho,g,w,h,l,a=(model[name] for name in ("density_kg_per_m3","gravity_m_per_s2","width_m","depth_m","length_m","amplitude_m"))
    m,k=wall["mass_kg"],wall["stiffness_n_per_m"]
    mode=mode_parameters(request)
    velocity_scale=a*math.sqrt(g/h)
    force_scale=rho*g*w*h*a
    x_scale=mode["wall_amplitude_m"]
    wall_velocity_scale=x_scale*mode["angular_frequency_per_s"]
    volume_scale=w*h*l
    residuals={name:0.0 for name in CHECK_TOLERANCES}
    reference_errors={}
    primary_reference=None
    for label in TRACE_LABELS:
        tr=result[label];dx,dt=tr["dx_m"],tr["dt_s"]
        eta=np.asarray(tr["free_surface_elevation_m"]);u=np.asarray(tr["depth_averaged_velocity_m_per_s"])
        x,v,acc,eta_b,force=(np.asarray(tr[name]) for name in ("wall_displacement_m","wall_velocity_m_per_s","wall_acceleration_m_per_s2","boundary_elevation_m","fluid_force_on_structure_n"))
        energy_scale=tr["total_energy_j"][0]
        setmax=lambda name,value:residuals.__setitem__(name,max(residuals[name],value))
        setmax("boundary_velocity",max(_norm(u[:,0],velocity_scale),_norm(u[:,-1]-v,wall_velocity_scale)))
        setmax("physical_boundary_traction",max(_norm(eta_b-(eta[:,-1]-dx*acc/(2*g)),a),_norm(force-rho*g*w*h*eta_b,force_scale)))
        setmax("wall_momentum",_norm(m*acc-force+k*x,force_scale))
        setmax("force_conjugacy",_norm(force+np.asarray(tr["structure_force_on_fluid_n"]),force_scale))
        pressure=np.asarray(tr["bottom_gauge_pressure_pa"])
        ef=.5*rho*w*dx*(g*np.sum(eta**2,axis=1)+h*(np.sum(u[:,1:-1]**2,axis=1)+.5*v*v))
        es=.5*(m*v*v+k*x*x)
        column=w*dx*np.sum(h+eta,axis=1);swept=w*h*x
        algebra=[_norm(pressure-rho*g*(h+eta),rho*g*a),_norm(np.asarray(tr["volume_flux_m3_per_s"])-w*h*u,w*h*velocity_scale),
                 _norm(np.asarray(tr["boundary_pressure_deviation_pa"])-rho*g*eta_b,rho*g*a),
                 _norm(np.asarray(tr["fluid_energy_j"])-ef,energy_scale),_norm(np.asarray(tr["structure_energy_j"])-es,energy_scale),
                 _norm(np.asarray(tr["total_energy_j"])-ef-es,energy_scale),
                 _norm(np.asarray(tr["column_volume_m3"])-column,volume_scale),_norm(np.asarray(tr["wall_swept_volume_m3"])-swept,volume_scale),
                 _norm(np.asarray(tr["liquid_volume_m3"])-column-swept,volume_scale),
                 _norm(np.asarray(tr["liquid_mass_kg"])-rho*(column+swept),rho*volume_scale)]
        setmax("constitutive_fields",max(algebra))
        setmax("mass_balance",_norm(np.asarray(tr["liquid_volume_m3"])-volume_scale,volume_scale))
        wf,ws=np.asarray(tr["fluid_interface_work_j"]),np.asarray(tr["structure_interface_work_j"])
        setmax("work_conjugacy",_norm(wf+ws,energy_scale))
        setmax("total_energy_balance",_norm(np.asarray(tr["total_energy_j"])-energy_scale,energy_scale))
        setmax("fluid_energy_balance",_norm(np.asarray(tr["fluid_energy_j"])-wf-tr["fluid_energy_j"][0],energy_scale))
        setmax("structure_energy_balance",_norm(np.asarray(tr["structure_energy_j"])-ws-tr["structure_energy_j"][0],energy_scale))
        eta_mid=(eta[1:]+eta[:-1])/2;u_mid=(u[1:]+u[:-1])/2
        setmax("finite_volume_continuity",_norm(np.diff(eta,axis=0)/dt+h*np.diff(u_mid,axis=1)/dx,a*mode["angular_frequency_per_s"]))
        setmax("interior_momentum",_norm(np.diff(u[:,1:-1],axis=0)/dt+g*np.diff(eta_mid,axis=1)/dx,velocity_scale*mode["angular_frequency_per_s"]))
        setmax("wall_kinematics",max(_norm(np.diff(x)/dt-(v[1:]+v[:-1])/2,wall_velocity_scale),
                                     _norm(np.diff(v)/dt-(acc[1:]+acc[:-1])/2,wall_velocity_scale*mode["angular_frequency_per_s"])))
        increments=dt*(force[1:]+force[:-1])/2*(v[1:]+v[:-1])/2
        setmax("work_quadrature",max(_norm(np.diff(ws)-increments,energy_scale),_norm(np.diff(wf)+increments,energy_scale),_norm([ws[0],wf[0]],energy_scale)))
        violated=bool(np.max(np.abs(eta))/h>MAX_ELEVATION_DEPTH_FRACTION*(1+1e-12) or
                      np.max(np.abs(eta_b))/h>MAX_ELEVATION_DEPTH_FRACTION*(1+1e-12) or
                      np.max(np.abs(x))>wall["maximum_displacement_m"]*(1+1e-12) or
                      np.max(np.abs(x))/l>MAX_WALL_LENGTH_FRACTION*(1+1e-12))
        setmax("small_amplitude_domain",float(violated))
        ref=reference(request,tr["time_s"],tr["cell_x_m"],tr["face_x_m"])
        if label=="primary":primary_reference=ref
        differences=[_norm(eta-np.array(ref["free_surface_elevation_m"]),a),_norm(u-np.array(ref["depth_averaged_velocity_m_per_s"]),velocity_scale),
                     _norm(x-np.array(ref["wall_displacement_m"]),x_scale),_norm(v-np.array(ref["wall_velocity_m_per_s"]),wall_velocity_scale),
                     _norm(eta_b-np.array(ref["boundary_elevation_m"]),a),_norm(force-np.array(ref["fluid_force_on_structure_n"]),force_scale)]
        reference_errors[label]=max(differences)
        setmax("initial_mode_binding",max(_norm(eta[0]-np.asarray(ref["free_surface_elevation_m"])[0],a),_norm(u[0],velocity_scale),
                                          _norm([x[0]-ref["wall_displacement_m"][0]],x_scale),_norm([v[0]],wall_velocity_scale)))
    scales=(a,velocity_scale,x_scale,wall_velocity_scale)
    pairs=(("primary","time_refined",2,1),("time_refined","time_fine",2,1),
           ("time_fine","spatial_refined",1,2),("spatial_refined","spatial_fine",1,2))
    errors=[max(_norm(array,scale) for array,scale in zip(_state_difference(result[p],result[q],tf,sf),scales)) for p,q,tf,sf in pairs]
    temporal_ratio=errors[0]/max(errors[1],1e-30);spatial_ratio=errors[2]/max(errors[3],1e-30)
    residuals["continuous_mode_reference"]=max(reference_errors.values())
    residuals["time_refinement"]=errors[1];residuals["spatial_refinement"]=errors[3]
    residuals["temporal_second_order"]=max(0.0,3.0-temporal_ratio,temporal_ratio-5.0) if errors[1]>1e-11 else 0.0
    residuals["spatial_second_order"]=max(0.0,3.0-spatial_ratio,spatial_ratio-5.0) if errors[3]>1e-11 else 0.0
    refinement={"temporal_differences":errors[:2],"spatial_differences":errors[2:],"temporal_ratio":temporal_ratio,"spatial_ratio":spatial_ratio,
                "temporal_order_resolved":errors[1]>1e-11,"spatial_order_resolved":errors[3]>1e-11}
    return residuals,primary_reference,reference_errors,refinement


def verify(request,result):
    request=validate_request(request);result=validate_result(request,result)
    residuals,ref,errors,refinement=_audit(request,result)
    spec=_spec(request)
    checks=[{"name":name,"value":residuals[name],"tolerance":spec[name],"status":"PASS" if residuals[name]<=spec[name] else "FAIL"} for name in sorted(spec)]
    passed=all(row["status"]=="PASS" for row in checks)
    return seal({"schema":REPORT_SCHEMA,"request_digest":digest(request),"candidate_digest":result["record_digest"],"claim_scope":CLAIM_SCOPE,
                 "verifier":VERIFIER_ID,"thresholds":deepcopy(request["tolerances"]),"status":"PASS" if passed else "FAIL","checks":checks,
                 "reference":ref,"metrics":{"residuals":residuals,"summary":_summary(result),"terminal":_terminal(result),
                                            "reference_errors":errors,"refinement":refinement,"continuous_mode":mode_parameters(request)},
                 "qualification":_qualification(request,passed),"limitations":list(LIMITATIONS)})


def validate_report(request,result,report):
    """Static strict retained data validation; never evaluate reference or PDEs."""
    request=validate_request(request);result=validate_result(request,result)
    keys(report,{"schema","request_digest","candidate_digest","claim_scope","verifier","thresholds","status","checks","reference","metrics","qualification","limitations","record_digest"})
    declarations={"schema":REPORT_SCHEMA,"request_digest":digest(request),"candidate_digest":result["record_digest"],"claim_scope":CLAIM_SCOPE,
                  "verifier":VERIFIER_ID,"thresholds":request["tolerances"],"limitations":LIMITATIONS}
    if any(report[name]!=value for name,value in declarations.items()):raise ValueError("Stored FSI report identity/declaration differs")
    keys(report["thresholds"],set(request["tolerances"]))
    for value in report["thresholds"].values():number(value)
    ref=report["reference"]
    keys(ref,{"method","wavenumber_per_m","angular_frequency_per_s","characteristic_relative_residual","time_s","cell_x_m","face_x_m",
              "free_surface_elevation_m","depth_averaged_velocity_m_per_s","wall_displacement_m","wall_velocity_m_per_s","boundary_elevation_m","fluid_force_on_structure_n"})
    primary=result["primary"]
    if ref["method"]!=REFERENCE_ID or any(ref[name]!=primary[name] for name in ("time_s","cell_x_m","face_x_m")):
        raise ValueError("Stored continuous reference grid/method differs")
    for name in ("wavenumber_per_m","angular_frequency_per_s","characteristic_relative_residual"):
        if not 0<=number(ref[name])<=1e30:raise ValueError("Stored continuous reference declaration exceeds bounds")
    for name in ("time_s","cell_x_m","face_x_m"):
        if type(ref[name]) is not list:raise ValueError("Reference coordinates require lists")
        for value in ref[name]:number(value)
    for name in ("free_surface_elevation_m","depth_averaged_velocity_m_per_s"):
        count=primary["cells"]+(name=="depth_averaged_velocity_m_per_s")
        if type(ref[name]) is not list or len(ref[name])!=len(primary["time_s"]):raise ValueError("Reference field time count differs")
        for row in ref[name]:
            if type(row) is not list or len(row)!=count:raise ValueError("Reference field space count differs")
            for value in row:
                if abs(number(value))>1e30:raise ValueError("Reference field exceeds bounds")
    for name in ("wall_displacement_m","wall_velocity_m_per_s","boundary_elevation_m","fluid_force_on_structure_n"):
        if type(ref[name]) is not list or len(ref[name])!=len(primary["time_s"]):raise ValueError("Reference scalar time count differs")
        for value in ref[name]:number(value)
    metrics=report["metrics"]
    keys(metrics,{"residuals","summary","terminal","reference_errors","refinement","continuous_mode"})
    keys(metrics["residuals"],set(CHECK_TOLERANCES))
    keys(metrics["reference_errors"],set(TRACE_LABELS))
    for group in (metrics["residuals"],metrics["reference_errors"]):
        for value in group.values():
            if not 0<=number(value)<=MAX_RESIDUAL:raise ValueError("Stored FSI errors must be bounded and nonnegative")
    if metrics["summary"]!=_summary(result) or metrics["terminal"]!=_terminal(result) or metrics["continuous_mode"]!=mode_parameters(request):
        raise ValueError("Stored FSI summaries or continuous-domain declaration differs")
    keys(metrics["summary"],set(_summary(result)));keys(metrics["terminal"],set(SCALAR_NAMES));keys(metrics["continuous_mode"],set(mode_parameters(request)))
    for name in ("cells","sample_count"):
        if type(metrics["summary"][name]) is not int:raise ValueError("Stored grid/sample counts must be integers")
    for name,value in metrics["summary"].items():
        if name not in {"cells","sample_count"}:number(value)
    for value in metrics["terminal"].values():number(value)
    for value in metrics["continuous_mode"].values():number(value)
    refinement=metrics["refinement"]
    keys(refinement,{"temporal_differences","spatial_differences","temporal_ratio","spatial_ratio","temporal_order_resolved","spatial_order_resolved"})
    for kind in ("temporal","spatial"):
        values=refinement[kind+"_differences"]
        if type(values) is not list or len(values)!=2 or any(not 0<=number(v)<=MAX_RESIDUAL for v in values):raise ValueError("Stored refinement differences must be two bounded values")
        ratio=values[0]/max(values[1],1e-30);resolved=values[1]>1e-11
        if number(refinement[kind+"_ratio"])!=ratio or type(refinement[kind+"_order_resolved"]) is not bool or refinement[kind+"_order_resolved"]!=resolved:
            raise ValueError("Stored refinement order contradicts retained differences")
        metric="time_refinement" if kind=="temporal" else "spatial_refinement"
        order=max(0.0,3.0-ratio,ratio-5.0) if resolved else 0.0
        if metrics["residuals"][metric]!=values[1] or metrics["residuals"][kind+"_second_order"]!=order:
            raise ValueError("Stored refinement residual contradicts retained differences")
    if metrics["residuals"]["continuous_mode_reference"]!=max(metrics["reference_errors"].values()):raise ValueError("Stored continuum error contradicts retained profile errors")
    spec=_spec(request)
    if type(report["checks"]) is not list or len(report["checks"])!=len(spec):raise ValueError("Stored FSI check count differs")
    names=[]
    for row in report["checks"]:
        keys(row,{"name","value","tolerance","status"});name=row["name"]
        if type(name) is not str or name not in spec or number(row["value"])!=metrics["residuals"][name] or number(row["tolerance"])!=spec[name] or row["status"]!=("PASS" if row["value"]<=row["tolerance"] else "FAIL"):
            raise ValueError("Stored FSI check contradicts metric/threshold")
        names.append(name)
    if len(set(names))!=len(names) or set(names)!=set(spec):raise ValueError("Stored FSI checks duplicate/omit names")
    passed=all(row["status"]=="PASS" for row in report["checks"])
    if report["status"]!=("PASS" if passed else "FAIL") or report["qualification"]!=_qualification(request,passed):raise ValueError("Stored FSI qualification contradicts checks")
    check_seal(report)
    return deepcopy(report)
