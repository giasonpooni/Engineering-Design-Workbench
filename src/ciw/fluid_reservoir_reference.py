"""Independent mass-normalized modal exponential reference, NumPy only.

This independently assembles the generalized mass/stiffness/damping system.
It neither imports the midpoint solver nor reproduces its recurrence. Critical
or numerically non-diagonalizable damping configurations are explicitly refused
when the eigenbasis is ill-conditioned. This reference is a numerical check of
the declared linear model, not physical validation or an exact-arithmetic proof.
"""
from __future__ import annotations

import numpy as np

from .control_contracts import number
from .fluid_reservoir_contract import validate_request

REFERENCE_ID = "independent_mass_normalized_eigen_exponential_binary64.v1"
MAX_REFERENCE_SAMPLES = 4097
MAX_EIGENBASIS_CONDITION = 1e8


def reference(request: dict, times: list) -> dict:
    request = validate_request(request)
    if type(times) is not list or not 1 <= len(times) <= MAX_REFERENCE_SAMPLES:
        raise ValueError("Require 1..4097 reference times")
    checked = [number(t) for t in times]
    if any(t<0 or t>request["clock"]["duration_s"] for t in checked) or any(b<a for a,b in zip(checked,checked[1:])):
        raise ValueError("Reference times must be ordered inside the model clock")
    density = request["fluid"]["density_kg_per_m3"]
    gravity = 9.80665  # Independently declared physical constant, not solver helper.
    area1, area2 = request["reservoirs"]["area1_m2"], request["reservoirs"]["area2_m2"]
    hydraulic_mass = density*request["connector"]["length_m"]/request["connector"]["area_m2"]
    coupled = request["structure"]["enabled"]
    area = request["structure"]["piston_area_m2"] if coupled else 0.0
    masses = np.array([hydraulic_mass,request["structure"]["mass_kg"]] if coupled else [hydraulic_mass])
    root_mass = np.sqrt(masses)
    stiffness = np.array([[density*gravity*(1/area1+1/area2)]])
    dampings = np.array([request["connector"]["resistance_pa_s_per_m3"]])
    positions = [request["initial"]["transfer_m3"]]
    speeds = [request["initial"]["flow_m3_per_s"]]
    if coupled:
        stiffness = np.array([[density*gravity*(1/area1+1/area2),-density*gravity*area/area2],
                              [-density*gravity*area/area2,request["structure"]["stiffness_n_per_m"]+density*gravity*area*area/area2]])
        dampings = np.append(dampings,request["structure"]["damping_n_s_per_m"])
        positions.append(request["initial"]["piston_displacement_m"])
        speeds.append(request["initial"]["piston_velocity_m_per_s"])
    dimension = len(masses)
    normalized_stiffness = stiffness/np.outer(root_mass,root_mass)
    normalized_damping = np.diag(dampings/masses)
    generator = np.block([[np.zeros((dimension,dimension)),np.eye(dimension)],
                          [-normalized_stiffness,-normalized_damping]])
    eigenvalues,eigenvectors = np.linalg.eig(generator)
    condition = float(np.linalg.cond(eigenvectors))
    if not np.isfinite(condition) or condition > MAX_EIGENBASIS_CONDITION:
        raise ValueError("Independent modal reference refuses an ill-conditioned or defective eigenbasis")
    initial = np.concatenate((np.asarray(positions)*root_mass,np.asarray(speeds)*root_mass))
    coefficients = np.linalg.solve(eigenvectors,initial.astype(complex))
    rows = []
    for time in checked:
        state_complex = eigenvectors@(np.exp(eigenvalues*time)*coefficients)
        if float(np.max(np.abs(state_complex.imag))) > 1e-10*max(1.0,float(np.max(np.abs(state_complex.real)))):
            raise ValueError("Independent modal reference exceeds its real-state residue budget")
        state = state_complex.real
        position = state[:dimension]/root_mass
        velocity = state[dimension:]/root_mass
        rows.append([float(position[0]),float(velocity[0]),float(position[1]) if coupled else 0.0,float(velocity[1]) if coupled else 0.0])
    return {"method": REFERENCE_ID, "eigenbasis_condition": condition,
            "time_s": list(checked), "state_order": ["transfer_m3","flow_m3_per_s","piston_displacement_m","piston_velocity_m_per_s"],
            "state": rows}
