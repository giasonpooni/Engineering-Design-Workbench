"""Resolved fluid/structure benchmark checks and adversarial retained-data tests."""
from copy import deepcopy
import json
import math
from unittest.mock import patch

import numpy as np
import pytest

from ciw.fluid_fsi_contract import example_request,validate_request,validate_result,mode_parameters,preservation_scope,length_scale_m,time_scale_s
from ciw.fluid_fsi_solver import simulate,csv_rows
from ciw.fluid_fsi_reference import reference
from ciw.fluid_fsi_verification import verify,validate_report
from ciw.operations.runner import seal


@pytest.fixture(scope="module")
def qualified():
    request=example_request();result=simulate(request);report=verify(request,result)
    return request,result,report


def test_default_qualifies_and_stays_under_four_mib(qualified):
    request,result,report=qualified
    validate_report(request,result,report)
    assert report["status"]=="PASS"
    assert report["qualification"]["action"]=="LOCAL"
    assert len(json.dumps(result).encode())<4*1024*1024
    assert len(json.dumps(result,indent=2).encode())<4*1024*1024
    assert report["metrics"]["refinement"]["temporal_ratio"]==pytest.approx(4.0,rel=.02)
    assert report["metrics"]["refinement"]["spatial_ratio"]==pytest.approx(4.0,rel=.03)
    assert report["metrics"]["reference_errors"]["spatial_fine"]<1e-5


def test_force_reconstruction_has_halfcell_inertia_and_true_interface_sign(qualified):
    request,result,_=qualified
    model,wall=request["model"],request["structure"]
    tr=result["primary"]
    rho,g,w,h=(model[name] for name in ("density_kg_per_m3","gravity_m_per_s2","width_m","depth_m"))
    half_mass=.5*rho*w*h*tr["dx_m"]
    last_eta=np.asarray(tr["free_surface_elevation_m"])[:,-1]
    acc=np.array(tr["wall_acceleration_m_per_s2"])
    actual_force=np.array(tr["fluid_force_on_structure_n"])
    pressure_based=rho*g*w*h*last_eta-half_mass*acc
    mechanical=wall["mass_kg"]*acc+wall["stiffness_n_per_m"]*np.array(tr["wall_displacement_m"])
    assert np.max(np.abs(actual_force-pressure_based))<1e-14
    assert np.max(np.abs(actual_force-mechanical))<1e-13
    assert np.max(np.abs(actual_force-rho*g*w*h*last_eta))>1e-4
    assert np.array_equal(actual_force,-np.array(tr["structure_force_on_fluid_n"]))


def test_mass_includes_signed_swept_wall_volume(qualified):
    request,result,_=qualified
    model=request["model"];tr=result["spatial_fine"]
    dx=tr["dx_m"]
    column=model["width_m"]*dx*np.sum(model["depth_m"]+np.array(tr["free_surface_elevation_m"]),axis=1)
    swept=model["width_m"]*model["depth_m"]*np.array(tr["wall_displacement_m"])
    assert np.ptp(column)>1e-5
    assert np.ptp(column+swept)<2e-15
    assert np.max(np.abs(column+swept-model["width_m"]*model["depth_m"]*model["length_m"]))<1e-15
    assert np.allclose(tr["liquid_mass_kg"],model["density_kg_per_m3"]*(column+swept),rtol=0,atol=1e-12)


def test_halfcell_fluid_energy_and_work_accounting(qualified):
    request,result,_=qualified
    tr=result["spatial_fine"];model=request["model"];wall=request["structure"]
    u=np.array(tr["depth_averaged_velocity_m_per_s"]);eta=np.array(tr["free_surface_elevation_m"])
    fluid=.5*model["density_kg_per_m3"]*model["width_m"]*tr["dx_m"]*(model["gravity_m_per_s2"]*np.sum(eta**2,axis=1)+model["depth_m"]*(np.sum(u[:,1:-1]**2,axis=1)+.5*u[:,-1]**2))
    structure=.5*(wall["mass_kg"]*np.array(tr["wall_velocity_m_per_s"])**2+wall["stiffness_n_per_m"]*np.array(tr["wall_displacement_m"])**2)
    assert np.max(np.abs(fluid-tr["fluid_energy_j"]))<1e-18
    assert np.max(np.abs(structure-tr["structure_energy_j"]))<1e-18
    force=np.array(tr["fluid_force_on_structure_n"]);v=np.array(tr["wall_velocity_m_per_s"])
    work=np.concatenate(([0.],np.cumsum(tr["dt_s"]*(force[1:]+force[:-1])/2*(v[1:]+v[:-1])/2)))
    assert np.max(np.abs(work-tr["structure_interface_work_j"]))<1e-18
    assert np.max(np.abs(fluid-fluid[0]+work))<1e-15
    assert np.max(np.abs(structure-structure[0]-work))<1e-15
    assert np.ptp(fluid+structure)<1e-15


def test_continuous_mode_mass_boundary_momentum_and_cell_averages(qualified):
    request,result,_=qualified
    tr=result["primary"]
    ref=reference(request,tr["time_s"],tr["cell_x_m"],tr["face_x_m"])
    model,wall=request["model"],request["structure"]
    k,omega=ref["wavenumber_per_m"],ref["angular_frequency_per_s"]
    x=np.array(ref["wall_displacement_m"])
    force=np.array(ref["fluid_force_on_structure_n"])
    assert np.max(np.abs(force-(wall["stiffness_n_per_m"]-wall["mass_kg"]*omega*omega)*x))<1e-14
    eta=np.array(ref["free_surface_elevation_m"])
    assert np.max(np.abs(model["width_m"]*tr["dx_m"]*np.sum(eta,axis=1)+model["width_m"]*model["depth_m"]*x))<1e-18
    assert np.max(np.abs(np.array(ref["depth_averaged_velocity_m_per_s"])[:,-1]-ref["wall_velocity_m_per_s"]))<1e-18
    center_samples=model["amplitude_m"]*np.cos(k*np.array(tr["cell_x_m"]))
    assert np.max(np.abs(center_samples-eta[0]))>1e-9
    factor=math.sin(k*tr["dx_m"]/2)/(k*tr["dx_m"]/2)
    assert np.max(np.abs(center_samples*factor-eta[0]))<1e-18


def test_owned_clock_boundaries_and_spatial_variation(qualified):
    _,result,_=qualified
    tr=result["spatial_fine"]
    u=np.asarray(tr["depth_averaged_velocity_m_per_s"])
    assert np.array_equal(u[:,0],np.zeros(len(tr["time_s"])))
    assert np.array_equal(u[:,-1],np.asarray(tr["wall_velocity_m_per_s"]))
    assert np.ptp(tr["free_surface_elevation_m"][0])>1e-5
    assert result["clock"]["externally_synchronized"] is False
    assert result["representation"]["particle_meaning"]=="none"


@pytest.mark.parametrize("mutate",[
    lambda r:r["structure"].update(damping_n_s_per_m=0.1),
    lambda r:r["structure"].update(equilibrium_preload="absent"),
    lambda r:r["structure"].update(maximum_displacement_m=1e-4),
    lambda r:r["model"].update(amplitude_m=0.002),
    lambda r:r["model"].update(depth_m=10.0),
    lambda r:r["model"].update(particle_semantics="SPH"),
    lambda r:r["model"].update(boundary="periodic"),
    lambda r:r["model"].update(gravity_m_per_s2=float("nan")),
    lambda r:r["integration"].update(steps=True),
    lambda r:r["integration"].update(cells=64),
    lambda r:r["integration"].update(method="explicit_euler"),
    lambda r:r["clock"].update(externally_synchronized=0),
    lambda r:r.update(extra="unrequested"),
])
def test_hard_domain_refusal(mutate):
    request=example_request();mutate(request)
    with pytest.raises(ValueError):validate_request(request)


def test_expansion_and_explicit_refusal_are_retained():
    request=example_request();request["desired_observables"].append("external_cfd_adapter")
    report=verify(request,simulate(request))
    assert report["status"]=="PASS" and report["qualification"]["action"]=="EXPAND"
    request["desired_observables"].append("certified_design")
    report=verify(request,simulate(request))
    assert report["status"]=="PASS" and report["qualification"]["action"]=="REFUSE"


def test_resealed_spatial_boundary_force_and_mass_tampers_fail_fresh_audit(qualified):
    request,result,_=qualified
    for field,delta,index in (("fluid_force_on_structure_n",.001,4),("wall_displacement_m",.0001,8),("liquid_volume_m3",.001,10)):
        forged=deepcopy(result);forged["primary"][field][index]+=delta;seal(forged)
        validate_result(request,forged)
        report=verify(request,forged)
        assert report["status"]=="FAIL" and report["qualification"]["action"]=="REFUSE"
    forged=deepcopy(result);forged["primary"]["free_surface_elevation_m"][5][7]+=.00001;seal(forged)
    assert verify(request,forged)["status"]=="FAIL"


def test_retained_physical_domain_has_only_roundoff_allowance(qualified):
    request,result,_=qualified
    forged=deepcopy(result)
    forged["primary"]["free_surface_elevation_m"][1][1]=.0105*request["model"]["depth_m"]
    seal(forged)
    assert verify(request,forged)["metrics"]["residuals"]["small_amplitude_domain"]==1.0
    request=deepcopy(request)
    request["structure"]["maximum_displacement_m"]=0.04
    forged=simulate(request)
    forged["primary"]["wall_displacement_m"][1]=.00105*request["model"]["length_m"]
    seal(forged)
    assert verify(request,forged)["metrics"]["residuals"]["small_amplitude_domain"]==1.0


def test_static_report_does_not_replay_physics_and_rejects_incoherent_forgery(qualified):
    request,result,report=qualified
    with patch("ciw.fluid_fsi_solver.simulate",side_effect=AssertionError("solver replay")),patch("ciw.fluid_fsi_verification.verify",side_effect=AssertionError("audit replay")),patch("ciw.fluid_fsi_verification.reference",side_effect=AssertionError("reference replay")):
        detached=validate_report(request,result,report)
        assert detached==report and detached is not report
    forged=deepcopy(report);forged["metrics"]["refinement"]["spatial_ratio"]=True;seal(forged)
    with pytest.raises(ValueError):validate_report(request,result,forged)
    forged=deepcopy(report);forged["checks"][0]["value"]+=1e-3;seal(forged)
    with pytest.raises(ValueError):validate_report(request,result,forged)


def test_sealed_detached_data_and_units(qualified):
    request,result,_=qualified
    detached=validate_result(request,result);detached["primary"]["wall_velocity_m_per_s"][0]=1.0
    assert result["primary"]["wall_velocity_m_per_s"][0]==0.0
    with pytest.raises(ValueError,match="integrity"):validate_result(request,detached)
    forged=deepcopy(result);forged["units"]["fluid_force_on_structure_n"]="Pa";seal(forged)
    with pytest.raises(ValueError):validate_result(request,forged)
    forged=deepcopy(result);forged["primary"]["depth_averaged_velocity_m_per_s"][0][0]=True;seal(forged)
    with pytest.raises(ValueError):validate_result(request,forged)


def test_csv_scope_and_reference_bounds(qualified):
    request,result,_=qualified
    header,rows=csv_rows(result)
    assert len(rows)==result["primary"]["cells"]*(result["primary"]["steps"]+1)
    assert all(len(row)==len(header) for row in rows)
    assert length_scale_m(request)==20.0
    assert time_scale_s(request)==request["integration"]["duration_s"]
    assert set(preservation_scope(request))=={"representation","particle_meaning","spatial_detail","vertical_detail","clock","receiver_coupling","physical_validity","molecular_scope"}
    tr=result["primary"]
    with pytest.raises(ValueError):reference(request,[True],tr["cell_x_m"],tr["face_x_m"])
    with pytest.raises(ValueError):reference(request,[1000.0],tr["cell_x_m"],tr["face_x_m"])
    with pytest.raises(ValueError):reference(request,[0.0],tr["cell_x_m"],tr["face_x_m"][:-1])
