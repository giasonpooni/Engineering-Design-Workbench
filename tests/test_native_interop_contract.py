from copy import deepcopy
import pytest

from ciw import native_interop_contract as nc
from ciw.telemetry import canonical


AFFINE = {"rows":2,"columns":3,"a_row_major":[2,1,-1,-1,3,2],"b":[5,-2],"x0":[3,4,2],"delta_x":[0.25,-0.5,0.125]}
OSCILLATOR = {"model":{"mass_kg":2,"omega_0_rad_s":2,"gamma_s_inv":0.1},
              "initial_state":{"q0_m":1,"v0_m_s":-0.25},"time_s":[0,0.125,0.25,0.375,0.5]}
QP = {"rows":2,"columns":2,"j_row_major":[2,1,-1,3],"y0":[1,-2],"target":[0,0],
      "regularization":1,"lower":[-1,-1],"upper":[1,1],"max_iterations":10000}


def test_rectangular_golden_has_offset_and_row_major_contributions():
    expected={"rows":2,"columns":3,"baseline_output":[13,11],"contributions":[0.5,-0.5,-0.125,-0.25,-1.5,0.25],
              "predicted_delta":[-0.125,-1.5],"predicted_output":[12.875,9.5],"model_output":[12.875,9.5],"residual":[0,0],"denominator":1}
    assert nc.affine_reference(AFFINE)==expected
    report=nc.check_output(nc.make_source("affine-binary64.v1","cpp",AFFINE),expected)
    assert report["max_abs_discrepancy"]==0
    assert report["authority"]["sp1_verification"]=="not_performed"


def test_exact_fixed_denominator_golden():
    p=deepcopy(AFFINE)
    for field in ("a_row_major","b","x0","delta_x"):
        p[field]=[int(256*x) for x in p[field]]
    s=nc.make_source("affine-d256.v1","julia",p)
    result=nc.affine_reference(p,True)
    assert result["denominator"]==65536
    assert result["baseline_output"]==[851968,720896]
    assert result["predicted_delta"]==[-8192,-98304]
    assert result["predicted_output"]==[843776,622592]
    assert nc.check_output(s,result)["outcome"]=="passed"
    result["predicted_output"][0]+=1
    with pytest.raises(ValueError,match="Exact"):
        nc.check_output(s,result)


def test_frozen_rectangular_holdout():
    p={"rows":3,"columns":2,"a_row_major":[1,0,0,0,-2,3],"b":[2,-1,0],"x0":[0.5,-1],"delta_x":[-0.25,0.5]}
    result=nc.affine_reference(p)
    assert result["baseline_output"]==[2.5,-1,-4]
    assert result["predicted_delta"]==[-0.25,0,2]
    assert result["model_output"]==[2.25,-1,-2]


def test_exact_shifted_state_uses_larger_bound_without_rounding():
    p={"rows":1,"columns":1,"a_row_major":[4096],"b":[4096],"x0":[4096],"delta_x":[4096]}
    s=nc.make_source("affine-d256.v1","cpp",p)
    r=nc.affine_reference(p,True)
    assert r["model_output"]==[34603008]
    assert nc.check_output(s,r)["outcome"]=="passed"


def test_si_force_energy_nonunit_mass_and_signs():
    p={"model":OSCILLATOR["model"],"time_s":[0],"q_m":[1],"v_m_s":[-0.25]}
    expected={"time_s":[0],"stiffness_n_m":8,"damping_n_s_m":0.4,"restoring_force_n":[-8],
              "damping_force_n":[0.1],"net_force_n":[-7.9],"acceleration_m_s2":[-3.95],
              "potential_energy_j":[4],"kinetic_energy_j":[0.0625],"energy_j":[4.0625]}
    assert nc.force_reference(p)==expected
    assert nc.check_output(nc.make_source("oscillator-force-energy.v1","cpp",p),expected)["outcome"]=="passed"


def test_analytic_reference_initial_state_and_equilibrium():
    r=nc.oscillator_reference(OSCILLATOR)
    assert r["q_m"][0]==1
    assert r["v_m_s"][0]==-0.25
    assert r["energy_j"][0]==4.0625
    zero=deepcopy(OSCILLATOR)
    zero["initial_state"]={"q0_m":0,"v0_m_s":0}
    assert nc.oscillator_reference(zero)["energy_j"]==[0]*5


@pytest.mark.parametrize("d,objective",[([-0.6,0.4],0.3)])
def test_coupled_qp_independent_objective_and_stationarity(d,objective):
    s=nc.make_source("design-qp.v1","julia",QP)
    assert nc.check_output(s,{"delta":d,"objective_value":objective,"lower_residual":[0,0],"upper_residual":[0,0],"gradient":[0,0]})["outcome"]=="passed"
    with pytest.raises(ValueError):
        nc.check_output(s,{"delta":[0,0],"objective_value":2.5})


def test_qp_active_and_fixed_bounds():
    p={**QP,"j_row_major":[1,0,0,1],"y0":[2,-2],"lower":[-0.5,-0.5],"upper":[0.5,0.5]}
    assert nc.check_output(nc.make_source("design-qp.v1","julia",p),{"delta":[-0.5,0.5],"objective_value":2.5,"lower_residual":[0,0],"upper_residual":[0,0],"gradient":[1,-1]})["outcome"]=="passed"
    p.update(lower=[0,0],upper=[0,0])
    assert nc.check_output(nc.make_source("design-qp.v1","julia",p),{"delta":[0,0],"objective_value":4,"lower_residual":[0,0],"upper_residual":[0,0],"gradient":[2,-2]})["outcome"]=="passed"


@pytest.mark.parametrize("field,value",[("rows",0),("rows",9),("rows",True),("columns",2),("a_row_major",[]),
                                     ("delta_x",[0,float("nan"),0]),("x0",[1,2,1e7])])
def test_source_rejects_malformed_shapes_and_values(field,value):
    p=deepcopy(AFFINE);p[field]=value
    with pytest.raises(ValueError): nc.make_source("affine-binary64.v1","cpp",p)


@pytest.mark.parametrize("field,value",[("provider","rust"),("arithmetic","exact-d256"),("semantics",{}),
                                     ("configuration",{}),("upstream",{"path":"run.exe"}),("experiment_id","")])
def test_source_refuses_authority_and_semantic_substitution(field,value):
    s=nc.make_source("affine-binary64.v1","cpp",AFFINE);s[field]=value
    with pytest.raises(ValueError): nc.source(canonical(s))


def test_data_only_unknown_fields_and_input_mutation():
    s=nc.make_source("affine-binary64.v1","cpp",AFFINE)
    original=canonical(s)
    parsed=nc.source(original)
    parsed["payload"]["b"][0]=9
    assert canonical(s)==original
    s["executable"]="arbitrary"
    with pytest.raises(ValueError): nc.source(canonical(s))


def test_control_refuses_irregular_grid_but_tsit5_preserves_it():
    p=deepcopy(OSCILLATOR);p["time_s"]=[0,0.1,0.3]
    with pytest.raises(ValueError,match="uniform"):
        nc.make_source("control-oscillator.v1","julia",p)
    p["solver"]={"abstol":1e-10,"reltol":1e-10,"maxiters":100000}
    assert nc.make_source("oscillator-tsit5.v1","julia",p)["payload"]["time_s"]==[0,0.1,0.3]


@pytest.mark.parametrize("change",[{"lower":[2,0]},{"regularization":0},{"max_iterations":True},{"target":[float("inf"),0]}])
def test_qp_bad_bounds_and_configuration_refuse(change):
    with pytest.raises(ValueError): nc.make_source("design-qp.v1","julia",{**QP,**change})


def test_exact_cannot_accept_float_numerators_or_bool_outputs():
    p={"rows":1,"columns":1,"a_row_major":[256],"b":[0],"x0":[256],"delta_x":[0]}
    s=nc.make_source("affine-d256.v1","cpp",p)
    p["x0"]=[256.0]
    with pytest.raises(ValueError): nc.make_source("affine-d256.v1","cpp",p)
    r=nc.affine_reference(s["payload"],True);r["residual"]=[False]
    with pytest.raises(ValueError): nc.check_output(s,r)

@pytest.mark.parametrize("field",["mass_kg","omega_0_rad_s"])
def test_force_profile_declares_its_native_lower_domain(field):
    model={"mass_kg":2,"omega_0_rad_s":2,"gamma_s_inv":0}
    model[field]=1e-13
    p={"model":model,"time_s":[0],"q_m":[1],"v_m_s":[0]}
    with pytest.raises(ValueError,match="above 1e-12"):
        nc.make_source("oscillator-force-energy.v1","cpp",p)

@pytest.mark.parametrize("profile",["oscillator-tsit5.v1","control-oscillator.v1"])
def test_output_time_grid_cannot_alias_booleans_to_seconds(profile):
    p={**OSCILLATOR,"time_s":[0,1]}
    if profile=="oscillator-tsit5.v1":
        p["solver"]={"abstol":1e-10,"reltol":1e-10,"maxiters":100000}
    source=nc.make_source(profile,"julia",p)
    data={**nc.oscillator_reference(p),"solver":{"retcode":"Success"}}
    if profile=="control-oscillator.v1":
        data["state_order"]=["q","v"]
        data["solver"].update(algorithm="ControlSystemsBase.lsim",method="zoh",
                              sample_interval_s=1,controlsystemsbase_version="1.22.0")
    else:
        data.update(schema="ciw.julia-oscillator-result.v1",operation_id="ciw.julia-oscillator.v1",request_id="grid-check")
        data["solver"].update(algorithm="Tsit5",abstol=1e-10,reltol=1e-10,accepted_steps=1,rejected_steps=0)
    nc.validate_output(source,data)
    data["time_s"]=[False,True]
    with pytest.raises(ValueError,match="finite bounds"):
        nc.validate_output(source,data)


def test_solver_metadata_does_not_alias_booleans_to_numbers():
    p={**OSCILLATOR,"time_s":[0,1,2]}
    s=nc.make_source("control-oscillator.v1","julia",p)
    data={**nc.oscillator_reference(p),"state_order":["q","v"],"solver":{
        "algorithm":"ControlSystemsBase.lsim","method":"zoh","sample_interval_s":True,
        "controlsystemsbase_version":"1.22.0","retcode":"Success"}}
    with pytest.raises(ValueError):nc.validate_output(s,data)
    s=nc.make_source("design-qp.v1","julia",QP)
    data={"delta":[-0.6,0.4],"objective_value":0.3,"lower_residual":[0,0],"upper_residual":[0,0],"gradient":[0,0],
        "solver":{"name":"HiGHS","version":"1.25.4","library_version":"v1.15.1","jump_version":"1.31.2",
          "termination_status":"OPTIMAL","primal_status":"FEASIBLE_POINT","solve_seconds":0,
          "options":{"threads":True,"time_limit":10.0,"qp_iteration_limit":QP["max_iterations"],
                     "primal_feasibility_tolerance":1e-9,"dual_feasibility_tolerance":1e-9,"random_seed":0}}}
    with pytest.raises(ValueError,match="options"):nc.validate_output(s,data)
