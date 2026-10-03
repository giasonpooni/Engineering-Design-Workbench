"""Fixed implicit-midpoint liquid exchange with bidirectional piston coupling.

Coordinates are transferred liquid volume r, outward piston displacement x,
volumetric flow Q and piston speed v.  h1=-r/A1 and h2=(r-a*x)/A2.
I*Qdot=rho*g*(h1-h2)-R*Q; m*vdot=a*rho*g*h2-k*x-c*v.
The same midpoint traction/velocity product is used on both sides of the
interface. No adaptive clock, forcing, particle dynamics or solver admission.
"""
from __future__ import annotations

from copy import deepcopy
import numpy as np

from .fluid_reservoir_contract import (
    CLAIM_SCOPE, GRAVITY, METHOD_ID, PROVIDER_ID, REPRESENTATION,
    RESOLUTION_FACTORS, RESULT_SCHEMA, STATE_FIELDS, UNITS,
    validate_request, validate_result,
)
from .operations.runner import digest, seal


def _resolution(request, factor):
    f, rs, co, st, ini = (request[name] for name in ("fluid", "reservoirs", "connector", "structure", "initial"))
    rho, a1, a2 = f["density_kg_per_m3"], rs["area1_m2"], rs["area2_m2"]
    area = st["piston_area_m2"] if st["enabled"] else 0.0
    inertance = rho*co["length_m"]/co["area_m2"]
    resistance = co["resistance_pa_s_per_m3"]
    m, k, c = st["mass_kg"], st["stiffness_n_per_m"], st["damping_n_s_per_m"]
    # State ordering is (r,x,Q,v). Disabled structural degrees stay zero.
    matrix = np.zeros((4,4), dtype=float)
    matrix[0,2] = 1.0
    matrix[2,0] = -rho*GRAVITY*(1/a1+1/a2)/inertance
    matrix[2,1] = rho*GRAVITY*area/a2/inertance
    matrix[2,2] = -resistance/inertance
    if st["enabled"]:
        matrix[1,3] = 1.0
        matrix[3,0] = area*rho*GRAVITY/a2/m
        matrix[3,1] = -(k+area*area*rho*GRAVITY/a2)/m
        matrix[3,3] = -c/m
    count = request["clock"]["coarse_step_count"]*factor
    dt = request["clock"]["duration_s"]/count
    left, right = np.eye(4)-0.5*dt*matrix, np.eye(4)+0.5*dt*matrix
    if np.linalg.cond(left) > 1e8:
        raise ValueError("Implicit midpoint system exceeds its numerical conditioning budget")
    advance = np.linalg.solve(left,right)
    state = np.array([ini["transfer_m3"], ini["piston_displacement_m"], ini["flow_m3_per_s"], ini["piston_velocity_m_per_s"]],dtype=float)
    trace = {name: [] for name in STATE_FIELDS}
    fluid_dissipation = structure_dissipation = interface_work = 0.0
    volume1_base = a1*rs["equilibrium_depth1_m"]
    volume2_base = a2*rs["equilibrium_depth2_m"]
    slug_volume = co["length_m"]*co["area_m2"]
    for index in range(count+1):
        r,x,q,v = (float(value) for value in state)
        h1,h2 = -r/a1,(r-area*x)/a2
        p1,p2 = rho*GRAVITY*h1,rho*GRAVITY*h2
        ef = 0.5*inertance*q*q+0.5*rho*GRAVITY*(a1*h1*h1+a2*h2*h2)
        es = 0.5*(m*v*v+k*x*x) if st["enabled"] else 0.0
        volume1,volume2_column,swept = volume1_base-r,volume2_base+r-area*x,area*x
        total_volume = volume1+volume2_column+swept+slug_volume
        sample = {
            "time_s": index*dt, "transfer_m3": r, "flow_m3_per_s": q,
            "connector_velocity_m_per_s": q/co["area_m2"],
            "piston_displacement_m": x, "piston_velocity_m_per_s": v,
            "head1_m": h1, "head2_m": h2, "pressure1_deviation_pa": p1,
            "pressure2_deviation_pa": p2, "pressure_difference_pa": p1-p2,
            "interface_force_n": area*p2, "reservoir1_volume_m3": volume1,
            "reservoir2_column_volume_m3": volume2_column,
            "piston_swept_volume_m3": swept, "total_liquid_volume_m3": total_volume,
            "total_liquid_mass_kg": rho*total_volume, "fluid_energy_j": ef,
            "structure_energy_j": es, "total_energy_j": ef+es,
            "fluid_dissipation_j": fluid_dissipation,
            "structure_dissipation_j": structure_dissipation,
            "external_work_j": 0.0, "fluid_interface_work_j": -interface_work,
            "structure_interface_work_j": interface_work,
        }
        for name,value in sample.items():
            trace[name].append(float(value))
        if index < count:
            updated = advance@state
            midpoint = 0.5*(state+updated)
            rm,xm,qm,vm = (float(value) for value in midpoint)
            midpoint_pressure2 = rho*GRAVITY*(rm-area*xm)/a2
            fluid_dissipation += dt*resistance*qm*qm
            structure_dissipation += dt*c*vm*vm if st["enabled"] else 0.0
            interface_work += dt*area*midpoint_pressure2*vm
            state = updated
    return {"dt_s": dt, "step_count": count, "trace": trace}


def simulate(request: dict) -> dict:
    request = validate_request(request)
    result = seal({"schema": RESULT_SCHEMA, "request_digest": digest(request),
                   "claim_scope": CLAIM_SCOPE, "provider": PROVIDER_ID, "method": METHOD_ID,
                   "clock": deepcopy(request["clock"]), "representation": deepcopy(REPRESENTATION),
                   "units": deepcopy(UNITS),
                   "resolutions": {label: _resolution(request,factor) for label,factor in RESOLUTION_FACTORS.items()}})
    return validate_result(request,result)
