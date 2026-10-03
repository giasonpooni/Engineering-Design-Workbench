from ciw.computational_objects import (
    make_object, select, context_package, perturbation_request, compare_observations, validate_object
)
import pytest

def specimen():
    return make_object(
        object_id="rk4.integrator-step.v1", kind="state-transition", label="RK4 integration step",
        operation_id="oscillator.integrate.v1",
        source={"repository":"giasonpooni/Notations-Engineering-Terminal","revision":"abc123",
                "path":"src/ciw/example.py","span":[10,40],"language":"python","sha256":"sha256:"+"0"*64},
        mathematics={"domain":"(x_n, dt, theta)","codomain":"x_(n+1)",
                     "expression":"x_(n+1) = Phi_dt(x_n, theta)","units":{},
                     "assumptions":["finite timestep"]},
        invariants=["state dimension is preserved"], evidence=["artifact:reference-trajectory"],
        experiments=["experiment:oscillator-convergence"])

def test_object_is_descriptive_and_selection_is_bounded():
    obj=specimen()
    assert validate_object(obj)["authority"]["may_execute"] is False
    selection=select(obj,views=["source","algebra","composition"],edit_paths=["src/ciw/example.py"])
    assert selection["edit_envelope"]["requires_human_or_executor_authorization"] is True
    package=context_package(obj,selection)
    assert package["object"]["object_id"] == obj["object_id"]
    assert package["instructions"]["verification_requires_separate_identity"] is True

def test_selection_rejects_unrelated_edit_surface_and_stale_object():
    obj=specimen()
    with pytest.raises(ValueError):
        select(obj,edit_paths=["src/ciw/unrelated.py"])
    selection=select(obj)
    changed={**obj,"label":"changed"}
    with pytest.raises(ValueError):
        context_package(changed,selection)

def test_perturbation_is_a_request_not_execution():
    req=perturbation_request(specimen(),dimension="parameter",change={"dt":{"from":0.01,"to":0.005}})
    assert req["execute"] is False
    assert "invariants" in req["required_observations"]

def test_comparison_reports_numbers_without_claiming_verification():
    result=compare_observations(specimen(),{"x":[1.0,2.0]},{"x":[1.0,2.5]},
                                metrics=["output","residual","invariant"])
    assert result["numerical_summary"]["max_abs"] == 0.5
    assert result["verification_status"] == "not_verified"
    assert result["invariants_assessed"] is False

def test_invalid_authority_is_refused():
    obj=specimen()
    obj["authority"]["may_execute"]=True
    with pytest.raises(ValueError):
        validate_object(obj)
