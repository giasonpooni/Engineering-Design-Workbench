"""Monolithic staggered finite-volume/midpoint compliant-wall wave provider.

Face displacement coordinates give eta=-H*D(displacement); velocity is on
faces. The right face's half-dual-cell liquid inertia belongs to fluid energy.
The physical boundary pressure is reconstructed using that face acceleration.
A symmetric modal factorization evaluates the fixed implicit-midpoint recurrence;
it is a numerical implementation of the spatially discrete equations, not a
continuous-mode reference or an external CFD adapter.
"""
from copy import deepcopy
import numpy as np

from .fluid_fsi_contract import (CLAIM_SCOPE,CLOCK,FIELD_NAMES,PROVIDER_ID,REPRESENTATION,RESULT_SCHEMA,
    SOLVER_ID,UNITS,mode_parameters,trace_declarations,validate_request,validate_result)
from .operations.runner import digest,seal


def _trace(request,cells,steps):
    model,wall=request["model"],request["structure"]
    length,depth,width,rho,g=(model[name] for name in ("length_m","depth_m","width_m","density_kg_per_m3","gravity_m_per_s2"))
    dx,dt=length/cells,request["integration"]["duration_s"]/steps
    liquid_dual_mass=rho*width*depth*dx
    masses=np.full(cells,liquid_dual_mass)
    masses[-1]=wall["mass_kg"]+liquid_dual_mass/2
    stiffness_scale=rho*g*width*depth*depth/dx
    stiffness=np.diag(np.full(cells,2*stiffness_scale))
    stiffness+=np.diag(np.full(cells-1,-stiffness_scale),1)+np.diag(np.full(cells-1,-stiffness_scale),-1)
    stiffness[-1,-1]=stiffness_scale+wall["stiffness_n_per_m"]
    root_mass=np.sqrt(masses)
    normalized=stiffness/np.outer(root_mass,root_mass)
    lambdas,vectors=np.linalg.eigh(normalized)
    if np.min(lambdas)<=0 or np.max(lambdas)/np.min(lambdas)>1e8:
        raise ValueError("FSI monolithic modal system exceeds positivity/conditioning budget")
    frequencies=np.sqrt(lambdas)
    mode=mode_parameters(request)
    faces=np.arange(cells+1)*dx
    initial=-model["amplitude_m"]/(depth*mode["wavenumber_per_m"])*np.sin(mode["wavenumber_per_m"]*faces[1:])
    modal_initial=vectors.T@(root_mass*initial)
    # theta is the exact per-step phase of the implicit midpoint recurrence.
    theta=2*np.arctan(frequencies*dt/2)
    phase=np.outer(np.arange(steps+1),theta)
    modal_position=np.cos(phase)*modal_initial
    modal_velocity=-np.sin(phase)*(modal_initial*frequencies)
    displacement=(modal_position@vectors.T)/root_mass
    velocity=(modal_velocity@vectors.T)/root_mass
    acceleration=(-(modal_position*lambdas)@vectors.T)/root_mass
    displacement=np.column_stack((np.zeros(steps+1),displacement))
    velocity=np.column_stack((np.zeros(steps+1),velocity))
    elevation=-depth*np.diff(displacement,axis=1)/dx
    x,v,a=displacement[:,-1],velocity[:,-1],acceleration[:,-1]
    boundary_eta=elevation[:,-1]-dx*a/(2*g)
    force=rho*g*width*depth*boundary_eta
    fluid_energy=.5*rho*width*dx*(g*np.sum(elevation*elevation,axis=1)+depth*(np.sum(velocity[:,1:-1]**2,axis=1)+.5*v*v))
    structure_energy=.5*(wall["mass_kg"]*v*v+wall["stiffness_n_per_m"]*x*x)
    increments=dt*.5*(force[:-1]+force[1:])*.5*(v[:-1]+v[1:])
    work=np.concatenate(([0.0],np.cumsum(increments)))
    column_volume=width*dx*np.sum(depth+elevation,axis=1)
    swept=width*depth*x
    total_volume=column_volume+swept
    return {"cells":cells,"steps":steps,"dx_m":dx,"dt_s":dt,
            "time_s":[j*dt for j in range(steps+1)],"cell_x_m":[(j+.5)*dx for j in range(cells)],"face_x_m":[j*dx for j in range(cells+1)],
            "free_surface_elevation_m":elevation.tolist(),"depth_averaged_velocity_m_per_s":velocity.tolist(),
            "volume_flux_m3_per_s":(width*depth*velocity).tolist(),"bottom_gauge_pressure_pa":(rho*g*(depth+elevation)).tolist(),
            "wall_displacement_m":x.tolist(),"wall_velocity_m_per_s":v.tolist(),"wall_acceleration_m_per_s2":a.tolist(),
            "boundary_elevation_m":boundary_eta.tolist(),"boundary_pressure_deviation_pa":(rho*g*boundary_eta).tolist(),
            "fluid_force_on_structure_n":force.tolist(),"structure_force_on_fluid_n":(-force).tolist(),
            "column_volume_m3":column_volume.tolist(),"wall_swept_volume_m3":swept.tolist(),"liquid_volume_m3":total_volume.tolist(),
            "liquid_mass_kg":(rho*total_volume).tolist(),"fluid_energy_j":fluid_energy.tolist(),"structure_energy_j":structure_energy.tolist(),
            "total_energy_j":(fluid_energy+structure_energy).tolist(),"fluid_interface_work_j":(-work).tolist(),
            "structure_interface_work_j":work.tolist(),"structure_dissipation_j":[0.0]*(steps+1),"external_work_j":[0.0]*(steps+1)}


def simulate(request):
    request=validate_request(request)
    result=seal({"schema":RESULT_SCHEMA,"request_digest":digest(request),"claim_scope":CLAIM_SCOPE,
                 "provider":PROVIDER_ID,"solver":SOLVER_ID,"units":deepcopy(UNITS),"clock":deepcopy(CLOCK),
                 "representation":deepcopy(REPRESENTATION),
                 **{name:_trace(request,cells,steps) for name,cells,steps in trace_declarations(request)}})
    return validate_result(request,result)


def csv_rows(result):
    """Flatten the retained primary field; no resampling or physics execution."""
    trace=result["primary"]
    header=["time_s","cell_index","cell_x_m","free_surface_elevation_m","bottom_gauge_pressure_pa",
            "left_face_velocity_m_per_s","right_face_velocity_m_per_s","wall_displacement_m","wall_velocity_m_per_s",
            "fluid_force_on_structure_n","liquid_volume_m3","total_energy_j","structure_interface_work_j"]
    rows=[]
    for j,time in enumerate(trace["time_s"]):
        for i,position in enumerate(trace["cell_x_m"]):
            rows.append([time,i,position,trace["free_surface_elevation_m"][j][i],trace["bottom_gauge_pressure_pa"][j][i],
                         trace["depth_averaged_velocity_m_per_s"][j][i],trace["depth_averaged_velocity_m_per_s"][j][i+1],
                         trace["wall_displacement_m"][j],trace["wall_velocity_m_per_s"][j],trace["fluid_force_on_structure_n"][j],
                         trace["liquid_volume_m3"][j],trace["total_energy_j"][j],trace["structure_interface_work_j"][j]])
    return header,rows
