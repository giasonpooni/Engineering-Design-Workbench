"""Independent science checks and saved-data non-actuation boundaries."""
from copy import deepcopy
import math
from unittest.mock import patch

import pytest

from ciw.polymer_contract import AUTHORITY, example_request
from ciw.polymer_models import simulate_control
from ciw.polymer_workflow import _assess, make_source
from ciw import polymer_verification as audit
from ciw.operations.runner import check_seal, digest, seal


def _case(request=None):
    request = example_request() if request is None else request
    return request, _assess(make_source(request), {})


def _statuses(report):
    return {check["name"]: check["status"] for check in report["checks"]}


@pytest.mark.parametrize("process", ["injection_molding", "extrusion_blow_molding"])
def test_independent_audit_passes_supported_processes_without_claiming_physics(process):
    request, assessment = _case(example_request(process))
    report = audit.verify(request, assessment)
    assert report["status"] == "PASS"
    assert report["scope"] == "finite_numeric_consistency_not_physical_validation"
    assert report["request_ref"] == digest(request) and report["assessment_ref"] == digest(assessment)
    assert report["authority"] == AUTHORITY
    assert all(check["status"] == "PASS" for check in report["checks"])
    check_seal(report)


def test_independent_verifier_never_calls_scientific_providers():
    request, assessment = _case()
    with patch("ciw.polymer_metrology.assess_metrology", side_effect=AssertionError("provider metrology")), \
         patch("ciw.polymer_models.engineering_estimate", side_effect=AssertionError("provider engineering")), \
         patch("ciw.polymer_models.control_proposal", side_effect=AssertionError("provider control")), \
         patch("ciw.polymer_models.simulate_control", side_effect=AssertionError("provider simulation")):
        assert audit.verify(request, assessment)["status"] == "PASS"


def test_offline_readers_do_not_run_providers_or_independent_numeric_oracles():
    request, assessment = _case()
    simulation = simulate_control(request["control"])
    report = audit.verify(request, assessment)
    with patch("ciw.polymer_metrology.assess_metrology", side_effect=AssertionError("metrology")), \
         patch("ciw.polymer_models.engineering_estimate", side_effect=AssertionError("engineering")), \
         patch("ciw.polymer_models.control_proposal", side_effect=AssertionError("control")), \
         patch("ciw.polymer_models.simulate_control", side_effect=AssertionError("simulation")), \
         patch.object(audit, "_metrology_oracle", side_effect=AssertionError("interval oracle")), \
         patch.object(audit, "_cooling_oracle", side_effect=AssertionError("cooling oracle")), \
         patch.object(audit, "_control_oracle", side_effect=AssertionError("controller oracle")):
        audit.validate_assessment(request, assessment)
        audit.validate_simulation(request["control"], simulation)
        audit.validate_report(report)


@pytest.mark.parametrize("mutation", ["identity", "source_kind", "source_ref", "sample_value", "sample_time", "calibration_ref", "clock_ref"])
def test_exact_source_and_sample_bindings_refuse_after_rehashing(mutation):
    request, assessment = _case()
    if mutation == "identity":
        assessment["identity"]["part_id"] = "substituted-part"
    elif mutation == "source_kind":
        assessment["source_kind"] = "retained_observation"
    elif mutation == "source_ref":
        assessment["source_ref"] = digest({"substituted": True})
    elif mutation in {"sample_value", "sample_time"}:
        row = assessment["metrology"]["measurements"][0]
        row["value" if mutation == "sample_value" else "time_s"] += 0.25
    else:
        request["sensors"][0][mutation] = digest({"substituted": mutation})
        assessment["source_ref"] = digest(request)
    report = audit.verify(request, assessment)
    assert report["status"] == "FAIL"
    assert _statuses(report)["retained_contract_and_source_binding"] == "FAIL"


@pytest.mark.parametrize("section,flag", [("authority", "hardware_actuation"), ("authority", "physical_validation"),
                                         ("engineering", "plc_write"), ("control", "hardware_control"),
                                         ("metrology", "state_admission")])
def test_resealed_authority_promotions_are_rejected(section, flag):
    request, assessment = _case()
    authority = assessment["authority"] if section == "authority" else assessment[section]["authority"]
    authority[flag] = True
    assert audit.verify(request, assessment)["status"] == "FAIL"
    with pytest.raises(ValueError):
        audit.validate_assessment(request, assessment)


@pytest.mark.parametrize("mutation,failed_check", [
    ("temperature", "lumped_energy_balance"), ("time_constant", "lumped_energy_balance"),
    ("uncertainty", "cooling_uncertainty"), ("clock_bound", "cooling_uncertainty"),
    ("target_time", "cooling_target_limits"), ("pressure_bracket", "nominal_pressure_brackets"),
    ("interval", "independent_metrology_intervals"), ("wrong_control_direction", "bounded_control_proposal"),
])
def test_shape_valid_scientific_tampering_requires_fresh_numeric_failure(mutation, failed_check):
    request, assessment = _case()
    cooling = assessment["engineering"]["cooling"]
    if mutation == "temperature":
        cooling["temperature_k"] += 1
    elif mutation == "time_constant":
        cooling["time_constant_s"] *= 1.1
    elif mutation == "uncertainty":
        cooling["standard_uncertainty_k"] *= 0.5
    elif mutation == "clock_bound":
        cooling["timing_temperature_bound_k"] = 0.0
    elif mutation == "target_time":
        cooling["target"]["remaining_time_s"] += 0.5
    elif mutation == "pressure_bracket":
        row = assessment["engineering"]["cavity_arrival"][0]
        row["time_interval_s"], row["cadence_s"] = [1.0, 10.0], 9.0
    elif mutation == "interval":
        assessment["metrology"]["quantities"][0]["interval"][0] += 0.000001
    else:
        control = assessment["control"]
        control["proposed"] = control["current"]-0.5
        control["delta"] = -0.5
    audit.validate_assessment(request, assessment)
    report = audit.verify(request, assessment)
    assert report["status"] == "FAIL"
    assert _statuses(report)[failed_check] == "FAIL"


def test_rehashed_model_change_cannot_make_old_numerical_result_current():
    request, assessment = _case()
    request["model"]["cooling"]["heat_transfer_w_m2_k"]["value"] *= 1.2
    assessment["source_ref"] = digest(request)
    audit.validate_assessment(request, assessment)
    assert _statuses(audit.verify(request, assessment))["lumped_energy_balance"] == "FAIL"


def test_invented_shape_valid_abstention_is_fresh_numeric_failure_not_a_crash():
    request, assessment = _case()
    assessment["engineering"]["status"] = "ABSTAINED"
    assessment["engineering"]["cooling"] = {"status": "ABSTAINED", "reason": "MISSING_SAMPLES", "sensor_id": "part-temperature"}
    audit.validate_assessment(request, assessment)
    report = audit.verify(request, assessment)
    assert report["status"] == "FAIL"
    assert _statuses(report)["lumped_energy_balance"] == "FAIL"


@pytest.mark.parametrize("section", ["engineering", "control"])
def test_authority_flags_require_exact_booleans_even_for_numeric_zero(section):
    request, assessment = _case()
    assessment[section]["authority"]["plc_write"] = 0
    with pytest.raises(ValueError):
        audit.validate_assessment(request, assessment)


@pytest.mark.parametrize("abstention", ["missing", "stale", "out_of_domain", "biot_uncertainty", "delayed_cycle", "dwell", "unobserved_new_cycle"])
def test_correct_abstention_is_numeric_pass_with_no_physical_promotion(abstention):
    request = example_request()
    if abstention == "missing":
        request["sensors"][0]["samples"] = []
    elif abstention == "stale":
        request["sensors"][0]["samples"][-1]["time_s"] = 8.0
    elif abstention == "out_of_domain":
        request["model"]["validity"]["maximum_biot"] = 0.001
    elif abstention == "biot_uncertainty":
        nominal = 50.0*1e-6/(0.006*0.2)
        request["model"]["validity"]["maximum_biot"] = nominal*1.01
    elif abstention == "delayed_cycle":
        request["control"]["cycle_guard"]["measurement_cycle_index"] = 5
    elif abstention == "dwell":
        request["control"]["cycle_guard"]["last_adjustment_cycle_index"] = 9
    else:
        request["control"]["cycle_guard"]["last_adjustment_cycle_index"] = 6
        request["control"]["cycle_guard"]["measurement_cycle_index"] = 6
        request["control"]["cycle_guard"]["maximum_measurement_delay_cycles"] = 5
    request, assessment = _case(request)
    assert (assessment["engineering"]["status"] == "ABSTAINED" or assessment["control"]["status"] == "ABSTAINED")
    assert audit.verify(request, assessment)["status"] == "PASS"


@pytest.mark.parametrize("target,expected", [(355.0, "ALREADY_SATISFIED"), (300.0, "UNREACHABLE"),
                                            (300.1, "ABSTAINED"), (330.0, "ESTIMATED")])
def test_analytic_target_limits(target, expected):
    request = example_request()
    request["model"]["cooling"]["target_temperature_k"]["value"] = target
    request, assessment = _case(request)
    assert assessment["engineering"]["cooling"]["target"]["status"] == expected
    assert audit.verify(request, assessment)["status"] == "PASS"


def test_zero_and_long_time_energy_limits_and_equilibrium_abstention():
    request = example_request()
    request["model"]["cooling"]["forecast_horizon_s"] = 0.0
    _, assessment = _case(request)
    cooling = assessment["engineering"]["cooling"]
    assert cooling["temperature_k"] == 350.0
    assert cooling["standard_uncertainty_k"] == 0.5
    assert audit.verify(request, assessment)["status"] == "PASS"
    request["model"]["cooling"]["forecast_horizon_s"] = 120.0
    _, assessment = _case(request)
    assert assessment["engineering"]["cooling"]["temperature_k"] == pytest.approx(300.0, abs=1e-6)
    assert audit.verify(request, assessment)["status"] == "PASS"
    request["sensors"][0]["samples"][-1]["value"] = 300.0
    _, assessment = _case(request)
    assert assessment["engineering"]["cooling"]["status"] == "ABSTAINED"
    assert audit.verify(request, assessment)["status"] == "PASS"


def test_conservative_interval_union_retains_disagreement_without_precision_gain():
    request = example_request()
    additional = deepcopy(request["sensors"][3])
    additional["sensor_id"] = "second-dimension"
    additional["samples"][-1]["value"] = 0.0200
    request["sensors"].append(additional)
    _, assessment = _case(request)
    assert assessment["metrology"]["quantities"][0]["interval"] == pytest.approx([0.01998, 0.02022])
    assert assessment["metrology"]["status"] == "INDETERMINATE"
    assert assessment["control"]["status"] == "ABSTAINED"
    assert audit.verify(request, assessment)["status"] == "PASS"


@pytest.mark.parametrize("fault,reason", [
    ("condition", "RESPONSE_MEASUREMENT_CONDITION_MISMATCH"),
    ("overlap", "UNQUALIFIED_RESPONSE_METROLOGY"),
    ("missing_specification", "MISSING_OR_AMBIGUOUS_RESPONSE_SPECIFICATION"),
])
def test_independent_audit_checks_response_specific_abstention_despite_other_failure(fault, reason):
    request = example_request()
    if fault == "condition":
        request["tolerances"][0]["condition"] = "conditioned"
    elif fault == "overlap":
        next(s for s in request["sensors"] if s["sensor_id"] == "dimension-1")["samples"][-1]["value"] = 0.0201
    else:
        request["tolerances"] = []
    request["tolerances"].append({"quantity": "wall_thickness", "unit": "m", "lower": 0.0012,
                                  "upper": 0.0013, "coverage_factor": 2.0, "condition": "ejection",
                                  "specification_ref": digest({"unrelated_wall_specification": 1})})
    request, assessment = _case(request)
    assert assessment["metrology"]["status"] == "NONCONFORMING"
    assert assessment["control"]["status"] == "ABSTAINED"
    assert assessment["control"]["reason"] == reason
    with patch("ciw.polymer_models.control_proposal", side_effect=AssertionError("provider control")):
        assert audit.verify(request, assessment)["status"] == "PASS"
    forged = deepcopy(assessment)
    forged["control"] = _case()[1]["control"]
    with pytest.raises(ValueError):
        audit.validate_assessment(request, forged)
    assert audit.verify(request, forged)["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["authority", "index", "bounds", "rate", "plant", "interlock", "omit", "final", "dwell_move"])
def test_simulation_reader_rejects_tampered_bounds_state_interlocks_and_dwell(mutation):
    control = example_request()["control"]
    simulation = simulate_control(control)
    if mutation == "authority":
        simulation["authority"]["plc_write"] = True
    elif mutation == "index":
        simulation["cycles"][0]["cycle_index"] = 0
    elif mutation == "bounds":
        simulation["cycles"][0]["parameter_after"] = 40.0
    elif mutation == "rate":
        simulation["cycles"][0]["delta"] = 2.0
    elif mutation == "plant":
        simulation["cycles"][0]["quantity_after"] += 0.0001
    elif mutation == "interlock":
        control["toy_plant"]["interlock_ok"][0] = False
    elif mutation == "omit":
        simulation["cycles"].pop()
    elif mutation == "final":
        simulation["final_quantity"] += 0.01
    else:
        row = simulation["cycles"][1]
        assert row["status"] == "DWELLING"
        row["status"] = "PROPOSED"
        row["parameter_after"] = row["parameter_before"]+0.5
        row["delta"] = 0.5
        row["quantity_after"] = row["quantity_before"]+control["toy_plant"]["actual_gain_per_parameter"]*0.5
    with pytest.raises(ValueError):
        audit.validate_simulation(control, simulation)


def test_simulation_halts_and_reader_refuses_additional_rows_after_dropout():
    control = example_request()["control"]
    control["toy_plant"]["interlock_ok"][2] = False
    simulation = simulate_control(control)
    assert simulation["status"] == "HALTED" and len(simulation["cycles"]) == 3
    audit.validate_simulation(control, simulation)
    simulation["cycles"].append(deepcopy(simulation["cycles"][-1]))
    simulation["cycles"][-1]["cycle"] += 1
    simulation["cycles"][-1]["cycle_index"] += 1
    with pytest.raises(ValueError):
        audit.validate_simulation(control, simulation)


@pytest.mark.parametrize("mutation", ["status", "authority", "scope", "checks", "seal"])
def test_report_resealing_cannot_promote_authority_or_contradict_check_status(mutation):
    request, assessment = _case()
    report = audit.verify(request, assessment)
    if mutation == "status":
        report["checks"][1]["status"] = "FAIL"
    elif mutation == "authority":
        report["authority"]["physical_validation"] = "established"
    elif mutation == "scope":
        report["scope"] = "structural_acceptance"
    elif mutation == "checks":
        report["checks"].pop()
    else:
        report["record_digest"] = digest({"other": True})
    if mutation != "seal":
        seal(report)
    with pytest.raises(ValueError):
        audit.validate_report(report)
