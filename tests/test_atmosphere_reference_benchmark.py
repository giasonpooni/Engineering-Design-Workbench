from copy import deepcopy
import json
from pathlib import Path

import pytest

from ciw.atmosphere_comparison import compare
from ciw.atmosphere_comparison_contract import (
    make_reference_source, validate_policy, validate_reference,
)
from ciw.atmosphere_comparison_verification import verify as verify_comparison
from ciw.atmosphere_moist_compiler import compile_atmosphere
from ciw.atmosphere_moist_contract import validate_request
from ciw.atmosphere_moist_verification import verify as verify_atmosphere
from ciw.atmosphere_reference_benchmark import (
    DISPLAY_ROUNDING_BOUND_PA, QUANTITY, SOURCE_REF, SOURCE_URL, cases, example,
)
from ciw.atmosphere_workflow import make_source
from ciw.operations.runner import check_seal, digest, seal


PUBLISHED_POINTS = (
    ("nistir5078-20c", 293.15, 2339.3),
    ("nistir5078-25c", 298.15, 3169.9),
    ("nistir5078-30c", 303.15, 4247.0),
    ("nistir5078-35c", 308.15, 5629.0),
)
EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "atmosphere-reference"


def _bindings(item, result, report):
    return {
        "source_evidence_id": make_source(item["request"])["evidence_id"],
        "source_result_id": "result-" + "1" * 32,
        "source_execution_id": "execution-" + "2" * 32,
        "source_record_digest": digest({"fixture_result": result}),
        "verification_id": "verification-" + "3" * 32,
        "recomputed_report_digest": report["record_digest"],
        "reference_evidence_id": make_reference_source(item["reference"])["evidence_id"],
    }


def test_cases_retain_the_four_published_iapws_table_points():
    supplied = cases()
    assert len(supplied) == 4
    for item, (name, temperature, pressure) in zip(supplied, PUBLISHED_POINTS):
        assert set(item) == {"name", "request", "reference", "policy"}
        assert item["name"] == name
        assert item["request"]["reference"]["temperature_k"] == temperature
        reference = validate_reference(item["reference"])
        assert reference["observations"][0]["quantities"][QUANTITY]["value"] == pressure
        assert reference["provenance"] == {
            "kind": "published_reference", "source_ref": SOURCE_REF,
            "source_url": SOURCE_URL, "independent_of_candidate": True,
        }


def test_reference_fixture_construction_does_not_activate_scientific_providers(monkeypatch):
    import ciw.atmosphere_moist_compiler as compiler
    import ciw.atmosphere_moist_verification as verification

    def forbidden(*args, **kwargs):
        raise AssertionError("Reference construction activated an atmospheric provider")

    monkeypatch.setattr(compiler, "compile_atmosphere", forbidden)
    monkeypatch.setattr(compiler, "mixture_properties", forbidden)
    monkeypatch.setattr(verification, "verify", forbidden)
    assert [item["reference"]["observations"][0]["quantities"][QUANTITY]["value"]
            for item in cases()] == [2339.3, 3169.9, 4247.0, 5629.0]


def test_case_calls_return_detached_declarations_and_seals():
    baseline = cases()
    changed = cases()
    changed[0]["request"]["reference"]["temperature_k"] = 999.0
    changed[0]["reference"]["observations"][0]["quantities"][QUANTITY]["value"] = 1.0
    changed[0]["policy"]["thresholds"][QUANTITY]["relative_tolerance"] = 0.001
    assert cases() == baseline
    assert example() == baseline[1]
    for item in baseline:
        validate_request(item["request"])
        validate_reference(item["reference"])
        validate_policy(item["reference"], item["policy"])
        check_seal(item["reference"])
        check_seal(item["policy"])


@pytest.mark.parametrize("index", range(4))
def test_benchmark_compares_an_isothermal_zero_water_diagnostic_at_the_origin(index):
    item = cases()[index]
    request, reference = item["request"], item["reference"]
    assert request["profile"]["lapse_rate_k_per_m"] == 0.0
    assert request["profile"]["water_mixing_ratio_kg_per_kg_dry_air"] == 0.0
    assert request["sampling"]["height_m"] == [0.0, 100.0]
    assert reference["context"] == {
        "frame": "atmosphere.local_enu.v1", "height_origin_m": 0.0,
        "valid_time_utc": None, "humidity_convention": "not_applicable",
    }
    observation = reference["observations"][0]
    assert observation["sample_index"] == 0
    assert observation["height_m"] == 0.0
    assert set(observation["quantities"]) == {QUANTITY}
    datum = observation["quantities"][QUANTITY]
    assert datum["unit"] == "Pa"
    assert datum["instrument_ref"] is None
    assert datum["calibration_ref"] is None
    assert datum["uncertainty"]["kind"] == "rounding_bound"
    assert datum["uncertainty"]["coverage_factor"] is None
    assert datum["uncertainty"]["absolute_bound"] == DISPLAY_ROUNDING_BOUND_PA == 0.05


@pytest.mark.parametrize("index", range(4))
def test_published_reference_exposes_model_discrepancy_within_declared_allowance(index):
    item = cases()[index]
    result = compile_atmosphere(item["request"])
    model_report = verify_atmosphere(item["request"], result)
    assert model_report["status"] == "PASS"
    assert model_report["qualification"]["action"] == "LOCAL"
    assert result["profile"]["relative_humidity"] == [0.0, 0.0]
    bindings = _bindings(item, result, model_report)
    compared = compare(item["request"], result, item["reference"], item["policy"], bindings)
    assert compared["agreement_status"] == "PASS"
    row = compared["rows"][0]
    assert row["status"] == "PASS"
    assert row["signed_difference"] < 0.0
    relative_difference = row["absolute_difference"] / row["reference_value"]
    assert 0.0028 < relative_difference < 0.0032
    assert row["engineering_allowance"] == 0.004 * row["reference_value"]
    assert row["reference_bound"] == 0.05
    assert row["total_allowance"] == row["engineering_allowance"] + 0.05
    assert 0.70 < row["normalized_acceptance_residual"] < 0.80
    assert compared["claims"]["independence_declared"] is True
    assert compared["claims"]["independence_established"] is False
    assert compared["claims"]["calibration_validation"] is False
    assert compared["claims"]["physical_validation"] == "not_established"
    independent = verify_comparison(item["request"], result, item["reference"],
                                    item["policy"], compared, bindings)
    assert independent["status"] == "PASS"


@pytest.mark.parametrize("index", range(4))
def test_tighter_engineering_policy_fails_reference_agreement_and_passes_arithmetic_audit(index):
    item = cases()[index]
    policy = deepcopy(item["policy"])
    policy["thresholds"][QUANTITY]["relative_tolerance"] = 0.001
    seal(policy)
    result = compile_atmosphere(item["request"])
    model_report = verify_atmosphere(item["request"], result)
    bindings = _bindings(item, result, model_report)
    compared = compare(item["request"], result, item["reference"], policy, bindings)
    assert compared["agreement_status"] == "FAIL"
    assert compared["rows"][0]["status"] == "FAIL"
    assert compared["rows"][0]["normalized_acceptance_residual"] > 2.8
    assert model_report["status"] == "PASS"
    independent = verify_comparison(item["request"], result, item["reference"],
                                    policy, compared, bindings)
    assert independent["status"] == "PASS"
    assert independent["metrics"]["agreement_status"] == "FAIL"


@pytest.mark.parametrize("field", ["reference", "policy"])
def test_shipped_25_degree_reference_files_match_the_fixed_case(field):
    stored = json.loads((EXAMPLES / (field + ".json")).read_text(encoding="utf-8"))
    assert stored == example()[field]
    check_seal(stored)
