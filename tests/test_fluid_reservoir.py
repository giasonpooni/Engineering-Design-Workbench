"""Analytic, conservation, refinement and retained-data reservoir regressions."""
from copy import deepcopy
import math
from unittest.mock import patch

import numpy as np
import pytest

from ciw.fluid_reservoir_contract import example_request,validate_request,validate_result,continuous_bounds
from ciw.fluid_reservoir_solver import simulate
from ciw.fluid_reservoir_reference import reference
from ciw.fluid_reservoir_verification import verify,validate_report
from ciw.operations.runner import seal


@pytest.fixture(scope="module")
def qualified():
    request = example_request()
    result = simulate(request)
    return request,result,verify(request,result)


def test_default_is_numerically_qualified_with_second_order_refinement(qualified):
    request,result,report = qualified
    validate_report(request,result,report)
    assert report["status"]=="PASS"
    assert report["qualification"]["action"]=="LOCAL"
    assert all(3.95<ratio<4.05 for ratio in report["metrics"]["convergence_ratios"])
    assert report["metrics"]["convergence_resolved"]
    assert result["representation"]["particle_meaning"]=="none"


def test_uncoupled_undamped_matches_independent_analytic_oscillator():
    request = example_request()
    request["structure"]["enabled"] = False
    request["connector"]["resistance_pa_s_per_m3"] = 0.0
    result = simulate(request)
    report = verify(request,result)
    rho,gravity = request["fluid"]["density_kg_per_m3"],request["fluid"]["gravity_m_per_s2"]
    inertia = rho*request["connector"]["length_m"]/request["connector"]["area_m2"]
    stiffness = rho*gravity*(1/request["reservoirs"]["area1_m2"]+1/request["reservoirs"]["area2_m2"])
    omega = math.sqrt(stiffness/inertia)
    trace = result["resolutions"]["finer"]["trace"]
    expected_r = [request["initial"]["transfer_m3"]*math.cos(omega*time) for time in trace["time_s"]]
    expected_q = [-request["initial"]["transfer_m3"]*omega*math.sin(omega*time) for time in trace["time_s"]]
    assert np.max(np.abs(np.array(trace["transfer_m3"])-expected_r))<1e-9
    assert np.max(np.abs(np.array(trace["flow_m3_per_s"])-expected_q))<1e-9
    assert max(trace["structure_energy_j"])==0.0
    assert report["status"]=="PASS"
    assert max(trace["total_energy_j"])-min(trace["total_energy_j"])<1e-12
    modal = reference(request,[0.0,0.2,1.0,4.0])
    for time,state in zip(modal["time_s"],modal["state"]):
        assert state[0]==pytest.approx(request["initial"]["transfer_m3"]*math.cos(omega*time),abs=1e-15)
        assert state[1]==pytest.approx(-request["initial"]["transfer_m3"]*omega*math.sin(omega*time),abs=1e-15)


def test_piston_is_bidirectional_and_volume_sweep_is_conserved(qualified):
    request,result,report = qualified
    trace = result["resolutions"]["finer"]["trace"]
    assert max(abs(value) for value in trace["piston_displacement_m"])>1e-4
    held = np.array(trace["reservoir1_volume_m3"])+trace["reservoir2_column_volume_m3"]+np.array(trace["piston_swept_volume_m3"])
    assert np.ptp(held)<1e-15
    # Omitting swept volume would create a measurable false mass defect.
    wrong = np.array(trace["reservoir1_volume_m3"])+trace["reservoir2_column_volume_m3"]
    assert np.ptp(wrong)>1e-6
    assert max(abs(value) for value in trace["structure_interface_work_j"])>1e-5
    assert np.max(np.abs(np.array(trace["fluid_interface_work_j"])+trace["structure_interface_work_j"]))==0.0
    uncoupled = deepcopy(request)
    uncoupled["structure"]["enabled"] = False
    comparison = simulate(uncoupled)["resolutions"]["finer"]["trace"]
    assert max(abs(a-b) for a,b in zip(comparison["transfer_m3"],trace["transfer_m3"]))>1e-6
    assert report["metrics"]["residuals"]["fluid_energy_balance"]<1e-10
    assert report["metrics"]["residuals"]["structure_energy_balance"]<1e-10


def test_undamped_coupled_energy_and_damped_dissipation(qualified):
    request,result,report = qualified
    trace = result["resolutions"]["finer"]["trace"]
    assert trace["total_energy_j"][-1]<trace["total_energy_j"][0]
    lost = trace["total_energy_j"][0]-trace["total_energy_j"][-1]
    dissipated = trace["fluid_dissipation_j"][-1]+trace["structure_dissipation_j"][-1]
    assert lost==pytest.approx(dissipated,abs=1e-12)
    undamped = deepcopy(request)
    undamped["connector"]["resistance_pa_s_per_m3"] = 0.0
    undamped["structure"]["damping_n_s_per_m"] = 0.0
    candidate = simulate(undamped)
    tr = candidate["resolutions"]["finer"]["trace"]
    assert max(tr["total_energy_j"])-min(tr["total_energy_j"])<1e-12
    assert verify(undamped,candidate)["status"]=="PASS"


def test_continuous_domain_uses_energy_bound_not_just_initial_heads():
    request = example_request()
    request["initial"]["flow_m3_per_s"] = 0.1
    # Initial heads still satisfy the declared small-displacement domain.
    assert abs(request["initial"]["transfer_m3"]/request["reservoirs"]["area1_m2"])<0.05
    with pytest.raises(ValueError,match="continuous small-head"):
        validate_request(request)
    default = continuous_bounds(example_request())
    assert default["head1_m"]<0.05
    assert default["piston_displacement_m"]<0.1


@pytest.mark.parametrize("mutate",[
    lambda r:r["clock"].update(coarse_step_count=True),
    lambda r:r["clock"].update(kind="wall_clock"),
    lambda r:r["clock"].update(coarse_step_count=8),
    lambda r:r["source"].update(kind="measured"),
    lambda r:r["fluid"].update(density_kg_per_m3=float("nan")),
    lambda r:r["fluid"].update(gravity_m_per_s2=True),
    lambda r:r["connector"].update(resistance_pa_s_per_m3=-1),
    lambda r:r["forcing"].update(external_force_n=1),
    lambda r:r["structure"].update(enabled=1),
    lambda r:r["initial"].update(transfer_m3=0.0),
    lambda r:r.update(extra="unrequested"),
    lambda r:r["desired_observables"].append("mass_balance"),
])
def test_request_refuses_invalid_or_unqualified_declarations(mutate):
    request = example_request()
    mutate(request)
    with pytest.raises(ValueError):
        validate_request(request)


def test_expand_for_requested_higher_physics(qualified):
    request,_,_ = qualified
    request = deepcopy(request)
    request["desired_observables"].extend(["turbulence","molecular_transport"])
    report = verify(request,simulate(request))
    assert report["status"]=="PASS"
    assert report["qualification"]["action"]=="EXPAND"
    assert report["qualification"]["unsupported_observables"]==["molecular_transport","turbulence"]


def test_result_and_report_are_detached_and_sealed(qualified):
    request,result,report = qualified
    detached = validate_result(request,result)
    detached["resolutions"]["coarse"]["trace"]["transfer_m3"][1] += 0.001
    assert detached["resolutions"]["coarse"]["trace"]["transfer_m3"][1]!=result["resolutions"]["coarse"]["trace"]["transfer_m3"][1]
    with pytest.raises(ValueError,match="integrity"):
        validate_result(request,detached)
    declaration = validate_request(request)
    declaration["initial"]["transfer_m3"] = -0.002
    assert request["initial"]["transfer_m3"]==-0.001


def test_resealed_candidate_tampering_is_detected_by_fresh_verification(qualified):
    request,result,_ = qualified
    forged = deepcopy(result)
    forged["resolutions"]["finer"]["trace"]["piston_displacement_m"][30] += 1e-4
    seal(forged)
    validate_result(request,forged)
    report = verify(request,forged)
    assert report["status"]=="FAIL"
    assert report["qualification"]["action"]=="REFUSE"
    assert report["metrics"]["residuals"]["constitutive"]>request["tolerances"]["equations_relative"]


def test_resealed_units_clock_and_report_forgery_are_rejected(qualified):
    request,result,report = qualified
    forged = deepcopy(result)
    forged["units"]["flow_m3_per_s"] = "litre/s"
    seal(forged)
    with pytest.raises(ValueError):
        validate_result(request,forged)
    forged = deepcopy(result)
    forged["resolutions"]["coarse"]["trace"]["time_s"][1] = True
    seal(forged)
    with pytest.raises(ValueError):
        validate_result(request,forged)
    altered = deepcopy(report)
    altered["checks"][0]["value"] += 1e-6
    seal(altered)
    with pytest.raises(ValueError):
        validate_report(request,result,altered)


def test_static_read_does_not_repeat_solver_reference_or_verifier(qualified):
    request,result,report = qualified
    with patch("ciw.fluid_reservoir_solver.simulate",side_effect=AssertionError("solver replay")), \
         patch("ciw.fluid_reservoir_verification.verify",side_effect=AssertionError("verifier replay")), \
         patch("ciw.fluid_reservoir_verification.reference",side_effect=AssertionError("reference replay")):
        validate_result(request,result)
        validate_report(request,result,report)


def test_reference_rejects_clock_escape_and_unbounded_samples():
    request = example_request()
    for times in ([4.1],[1.0,0.0],[True],[0.0]*4098):
        with pytest.raises(ValueError):
            reference(request,times)


def test_reference_explicitly_refuses_defective_critical_damping():
    request = example_request()
    request["structure"]["enabled"] = False
    rho = request["fluid"]["density_kg_per_m3"]
    inertia = rho*request["connector"]["length_m"]/request["connector"]["area_m2"]
    stiffness = rho*9.80665*(1/request["reservoirs"]["area1_m2"]+1/request["reservoirs"]["area2_m2"])
    request["connector"]["resistance_pa_s_per_m3"] = 2*math.sqrt(inertia*stiffness)
    with pytest.raises(ValueError,match="ill-conditioned or defective"):
        reference(request,[0.0,1.0])
