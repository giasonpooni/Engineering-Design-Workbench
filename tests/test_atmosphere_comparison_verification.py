from copy import deepcopy

import pytest

from ciw.atmosphere_contract import example_request as dry_request
from ciw.atmosphere_compiler import compile_atmosphere as compile_dry
from ciw.atmosphere_moist_contract import example_request as moist_request
from ciw.atmosphere_moist_compiler import compile_atmosphere as compile_moist
from ciw.atmosphere_comparison_contract import (
    FIELD_UNITS, PURE_LIQUID_CONVENTION, example_reference, example_policy,
    make_reference_source,
)
from ciw.atmosphere_comparison import compare, validate_comparison
from ciw.atmosphere_comparison_verification import (
    CHECK_NAMES, LIMITATIONS, VERIFIER_ID, validate_report, verify,
)
from ciw.operations.runner import digest, seal


def _bindings(result, reference):
    return {
        "source_evidence_id": "sha256:" + "1" * 64,
        "source_result_id": "result-" + "2" * 32,
        "source_execution_id": "execution-" + "3" * 32,
        "source_record_digest": result["record_digest"],
        "verification_id": "verification-" + "4" * 32,
        "recomputed_report_digest": "sha256:" + "5" * 64,
        "reference_evidence_id": make_reference_source(reference)["evidence_id"],
    }


def _prepare(*, moist=False, reference=None, policy=None, request=None):
    request = request or (moist_request() if moist else dry_request())
    compiler = compile_moist if request["schema"] == moist_request()["schema"] else compile_dry
    result = compiler(request)
    reference = reference or example_reference(request)
    policy = policy or example_policy(reference)
    bindings = _bindings(result, reference)
    candidate = compare(request, result, reference, policy, bindings)
    report = verify(request, result, reference, policy, candidate, bindings)
    return request, result, reference, policy, candidate, report, bindings


def _audit(data, candidate=None):
    request, result, reference, policy, original, _, bindings = data
    return verify(request, result, reference, policy, candidate or original, bindings)


def _validate(data, *, candidate=None, report=None):
    request, result, reference, policy, original, audit, bindings = data
    return validate_report(request, result, reference, policy, candidate or original, report or audit, bindings)


def _failed(report, name):
    return next(check for check in report["checks"] if check["name"] == name)["status"] == "FAIL"


@pytest.fixture(scope="module")
def qualified():
    return _prepare()


def test_default_comparison_independent_audit_preserves_separate_identities(qualified):
    request, result, reference, policy, comparison, report, bindings = qualified
    _validate(qualified)
    assert report["status"] == "PASS" and report["qualification"]["action"] == "LOCAL"
    assert report["candidate_digest"] == comparison["record_digest"]
    assert report["request_digest"] == digest(request)
    assert report["atmosphere_result_digest"] == result["record_digest"]
    assert report["reference_digest"] == reference["record_digest"]
    assert report["policy_digest"] == policy["record_digest"]
    assert all(report[field] == value for field, value in bindings.items())
    assert report["verifier"] == VERIFIER_ID
    assert len(report["checks"]) == len(CHECK_NAMES)
    assert report["metrics"] == {
        "row_count": 2, "evaluated_count": 2, "passed_count": 2, "failed_count": 0,
        "not_evaluated_count": 0, "comparison_action": "LOCAL", "agreement_status": "PASS"}
    assert report["limitations"] == LIMITATIONS
    assert any("physical validation" in value for value in LIMITATIONS)


def test_fresh_audit_does_not_call_comparator(qualified, monkeypatch):
    import ciw.atmosphere_comparison as comparator
    import ciw.atmosphere_compiler as dry_compiler
    import ciw.atmosphere_moist_compiler as moist_compiler
    import ciw.atmosphere_verification as dry_auditor
    import ciw.atmosphere_moist_verification as moist_auditor
    def forbidden(*args, **kwargs):
        raise AssertionError("Independent verifier invoked a physical provider or comparator")
    monkeypatch.setattr(comparator, "compare", forbidden)
    monkeypatch.setattr(comparator, "_domain", forbidden)
    monkeypatch.setattr(dry_compiler, "compile_atmosphere", forbidden)
    monkeypatch.setattr(moist_compiler, "compile_atmosphere", forbidden)
    monkeypatch.setattr(dry_auditor, "verify", forbidden)
    monkeypatch.setattr(moist_auditor, "verify", forbidden)
    assert _audit(qualified)["status"] == "PASS"


def test_static_report_reader_does_not_replay_arithmetic(qualified, monkeypatch):
    import ciw.atmosphere_comparison as comparator
    import ciw.atmosphere_comparison_verification as auditor
    def forbidden(*args, **kwargs):
        raise AssertionError("Static reader repeated comparison arithmetic")
    monkeypatch.setattr(comparator, "compare", forbidden)
    for name in ("verify", "_reconstruct", "_errors"):
        monkeypatch.setattr(auditor, name, forbidden)
    _validate(qualified)


def _disagreement():
    request = dry_request()
    reference = example_reference(request)
    reference["observations"][0]["quantities"]["temperature_k"]["value"] += 2.0
    seal(reference)
    return _prepare(request=request, reference=reference)


def test_scientific_disagreement_is_an_independently_verified_local_comparison():
    data = _disagreement()
    comparison, report = data[4:6]
    assert comparison["agreement_status"] == "FAIL"
    assert comparison["qualification"]["action"] == "LOCAL"
    assert report["status"] == "PASS" and report["qualification"]["action"] == "LOCAL"
    assert report["metrics"]["failed_count"] == 1
    _validate(data)


@pytest.mark.parametrize("field,check", [
    ("signed_difference", "signed_difference"),
    ("absolute_difference", "absolute_difference"),
    ("engineering_allowance", "engineering_allowance"),
    ("total_allowance", "total_allowance"),
    ("normalized_acceptance_residual", "normalized_acceptance_residual"),
])
def test_resealed_arithmetic_forgery_is_detected_by_fresh_independent_audit(field, check):
    data = _disagreement()
    candidate = deepcopy(data[4])
    row = next(row for row in candidate["rows"] if row["field"] == "temperature_k")
    row[field] = row[field] * -1.0 if field == "signed_difference" else row[field] + 0.25
    seal(candidate)
    validate_comparison(*data[:4], candidate, data[6])
    report = _audit(data, candidate)
    assert _failed(report, check)
    assert report["status"] == "FAIL" and report["qualification"]["action"] == "REFUSE"
    _validate(data, candidate=candidate, report=report)


def test_coherently_resealed_forgery_can_be_inspected_but_requires_fresh_verification():
    data = _disagreement()
    candidate, report = deepcopy(data[4]), deepcopy(data[5])
    row = next(row for row in candidate["rows"] if row["field"] == "temperature_k")
    row["signed_difference"] *= -1.0
    seal(candidate)
    report["candidate_digest"] = candidate["record_digest"]
    seal(report)
    _validate(data, candidate=candidate, report=report)
    assert _audit(data, candidate)["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["schema", "verifier", "candidate_digest", "request_digest",
    "atmosphere_result_digest", "reference_digest", "policy_digest", "source_evidence_id",
    "source_result_id", "source_execution_id", "source_record_digest", "verification_id",
    "recomputed_report_digest", "reference_evidence_id", "limitations", "metrics"])
def test_retained_report_rejects_stale_identity_or_summary(qualified, mutation):
    report = deepcopy(qualified[5])
    if mutation == "limitations":
        report[mutation] = []
    elif mutation == "metrics":
        report[mutation]["row_count"] += 1
    else:
        report[mutation] = "changed"
    seal(report)
    with pytest.raises(ValueError):
        _validate(qualified, report=report)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "negative", "boolean", "fraction",
    "tolerance", "status", "aggregate", "qualification", "extra"])
def test_retained_report_rejects_inconsistent_checks(qualified, mutation):
    report = deepcopy(qualified[5])
    row = report["checks"][0]
    if mutation == "missing":
        report["checks"].pop()
    elif mutation == "duplicate":
        report["checks"][-1] = deepcopy(row)
    elif mutation in {"negative", "boolean", "fraction"}:
        row["value"] = {"negative": -1, "boolean": False, "fraction": 0.0}[mutation]
    elif mutation == "tolerance":
        row["tolerance"] = 1
    elif mutation == "status":
        row["status"] = "FAIL"
    elif mutation == "aggregate":
        report["status"] = "FAIL"
    elif mutation == "qualification":
        report["qualification"]["action"] = "EXPAND"
    else:
        row["unexpected"] = True
    seal(report)
    with pytest.raises(ValueError):
        _validate(qualified, report=report)


def test_comparison_audit_does_not_mutate_inputs(qualified):
    before = digest(list(qualified))
    _audit(qualified)
    _validate(qualified)
    assert digest(list(qualified)) == before


def _quantity(value, field, *, bound=0.0):
    return {
        "value": value, "unit": FIELD_UNITS[field],
        "uncertainty": {
            "kind": "exact_fixture" if bound == 0.0 else "declared_absolute_bound",
            "absolute_bound": bound, "coverage_factor": None,
            "reference": "Synthetic bounded comparison fixture; no calibration claim."},
        "instrument_ref": None, "calibration_ref": None,
    }


@pytest.mark.parametrize("difference,status", [(0.0, "PASS"), (1.0, "FAIL")])
def test_zero_allowance_has_explicit_null_normalization(difference, status):
    request = dry_request()
    reference = example_reference(request)
    reference["observations"][0]["quantities"] = {
        "temperature_k": _quantity(request["reference"]["temperature_k"] + difference, "temperature_k")}
    seal(reference)
    policy = example_policy(reference)
    policy["thresholds"]["temperature_k"]["absolute_tolerance"] = 0.0
    seal(policy)
    data = _prepare(request=request, reference=reference, policy=policy)
    row = data[4]["rows"][0]
    assert row["status"] == status and row["total_allowance"] == 0.0
    assert row["normalized_acceptance_residual"] is None
    assert data[5]["status"] == "PASS"
    _validate(data)


@pytest.mark.parametrize("bound,agreement", [(1.0, "PASS"), (0.999, "FAIL")])
def test_declared_uncertainty_is_additive_and_exact_boundary_is_inclusive(bound, agreement):
    request = dry_request()
    reference = example_reference(request)
    target = request["reference"]["temperature_k"] + 2.0
    reference["observations"][0]["quantities"] = {
        "temperature_k": _quantity(target, "temperature_k", bound=bound)}
    seal(reference)
    data = _prepare(request=request, reference=reference)
    row = data[4]["rows"][0]
    assert row["engineering_allowance"] == 1.0
    assert row["reference_bound"] == bound
    assert row["total_allowance"] == 1.0 + bound
    assert row["normalized_acceptance_residual"] == 2.0 / (1.0 + bound)
    assert data[4]["agreement_status"] == agreement and data[5]["status"] == "PASS"


def test_relative_allowance_uses_magnitude_of_declared_reference():
    request = dry_request()
    reference = example_reference(request)
    reference["observations"][0]["quantities"] = {"pressure_pa": _quantity(100000.0, "pressure_pa", bound=5.0)}
    seal(reference)
    policy = example_policy(reference)
    policy["thresholds"]["pressure_pa"] = {"absolute_tolerance": 2.0, "relative_tolerance": 0.01}
    seal(policy)
    data = _prepare(request=request, reference=reference, policy=policy)
    row = data[4]["rows"][0]
    assert row["engineering_allowance"] == 1002.0 and row["total_allowance"] == 1007.0
    assert row["signed_difference"] == 1325.0 and data[5]["status"] == "PASS"


@pytest.mark.parametrize("mismatch,code", [
    ("frame", "frame_mismatch"), ("origin", "height_origin_mismatch"),
    ("time", "time_mismatch"), ("index", "sample_index_out_of_range"),
    ("height", "height_mismatch"),
])
def test_correct_alignment_refusal_is_numerically_verifiable(mismatch, code):
    request = dry_request()
    reference = example_reference(request)
    if mismatch == "frame":
        reference["context"]["frame"] = "receiver.other_frame.v1"
    elif mismatch == "origin":
        reference["context"]["height_origin_m"] = 1.0
    elif mismatch == "time":
        reference["context"]["valid_time_utc"] = "2026-10-03T15:00:00Z"
    elif mismatch == "index":
        reference["observations"][0]["sample_index"] = 128
    else:
        reference["observations"][0]["height_m"] = 1.0
    seal(reference)
    data = _prepare(request=request, reference=reference)
    candidate, report = data[4:6]
    assert candidate["qualification"]["action"] == "REFUSE"
    assert candidate["qualification"]["reasons"] == [code]
    assert all(row["status"] == "NOT_EVALUATED" for row in candidate["rows"])
    assert report["status"] == "PASS" and report["qualification"]["action"] == "REFUSE"
    _validate(data)


def test_equivalent_utc_spelling_does_not_refuse_exact_context():
    request = dry_request()
    request["reference"]["context"]["valid_time_utc"] = "2026-10-03T15:00:00Z"
    reference = example_reference(request)
    reference["context"]["valid_time_utc"] = "2026-10-03T15:00:00+00:00"
    seal(reference)
    data = _prepare(request=request, reference=reference)
    assert data[4]["qualification"]["action"] == "LOCAL" and data[5]["status"] == "PASS"


@pytest.mark.parametrize("declared_environment,action", [(True, "LOCAL"), (False, "REFUSE")])
def test_measurement_declaration_requires_matching_declared_environment_context(declared_environment, action):
    request = dry_request()
    request["reference"]["context"]["valid_time_utc"] = "2026-10-03T15:00:00Z"
    if declared_environment:
        request["reference"]["context"]["source_kind"] = "declared_environment"
    reference = example_reference(request)
    reference["provenance"]["kind"] = "declared_measurements"
    for datum in reference["observations"][0]["quantities"].values():
        datum["uncertainty"].update(kind="declared_absolute_bound", absolute_bound=1.0)
        datum["instrument_ref"] = "test.sensor.declaration"
    seal(reference)
    data = _prepare(request=request, reference=reference)
    assert data[4]["qualification"]["action"] == action and data[5]["status"] == "PASS"
    assert data[4]["claims"]["measurement_authenticity_established"] is False
    assert data[4]["claims"]["physical_validation"] == "not_established"


@pytest.mark.parametrize("field", ["water_vapour_pressure_pa", "relative_humidity", "liquid_water_saturation_pressure_pa"])
def test_dry_missing_water_quantities_are_honest_verified_expansion(field):
    request = dry_request()
    reference = example_reference(request)
    reference["context"]["humidity_convention"] = PURE_LIQUID_CONVENTION
    reference["observations"][0]["quantities"][field] = _quantity(
        0.5 if field == "relative_humidity" else 1000.0, field)
    seal(reference)
    data = _prepare(request=request, reference=reference)
    assert data[4]["qualification"]["action"] == "EXPAND"
    unsupported = next(row for row in data[4]["rows"] if row["field"] == field)
    assert unsupported["status"] == "NOT_EVALUATED" and unsupported["model_value"] is None
    assert data[5]["status"] == "PASS" and data[5]["qualification"]["action"] == "EXPAND"
    _validate(data)


def test_pressure_enhanced_humidity_blocks_only_humidity_comparison():
    request = moist_request()
    reference = example_reference(request)
    reference["context"]["humidity_convention"] = "pressure_enhanced_relative_humidity"
    reference["observations"][0]["quantities"]["relative_humidity"] = _quantity(0.4, "relative_humidity")
    seal(reference)
    data = _prepare(request=request, reference=reference)
    assert data[4]["qualification"]["reasons"] == ["humidity_convention_incompatible"]
    assert data[4]["agreement_status"] == "NOT_EVALUATED"
    assert data[5]["metrics"]["evaluated_count"] == 2
    assert data[5]["metrics"]["not_evaluated_count"] == 1 and data[5]["status"] == "PASS"


def test_wrong_agreement_and_row_decisions_are_detected_even_with_consistent_summary():
    data = _disagreement()
    candidate = deepcopy(data[4])
    next(row for row in candidate["rows"] if row["field"] == "temperature_k")["status"] = "PASS"
    candidate["agreement_status"] = "PASS"
    seal(candidate)
    validate_comparison(*data[:4], candidate, data[6])
    report = _audit(data, candidate)
    assert _failed(report, "row_status") and _failed(report, "agreement_status")
    assert report["status"] == "FAIL"


def test_fabricated_context_refusal_is_detected_as_incorrect_decision(qualified):
    candidate = deepcopy(qualified[4])
    for row in candidate["rows"]:
        for field in ("model_value", "signed_difference", "absolute_difference", "engineering_allowance",
                      "total_allowance", "normalized_acceptance_residual"):
            row[field] = None
        row["status"] = "NOT_EVALUATED"
    candidate["diagnostics"] = [{"code": "frame_mismatch", "sample_index": None, "field": None,
        "message": "Reference and model coordinate frames differ; no coordinate transformation is performed."}]
    candidate["qualification"] = {"action": "REFUSE", "reasons": ["frame_mismatch"]}
    candidate["agreement_status"] = "NOT_EVALUATED"
    seal(candidate)
    validate_comparison(*qualified[:4], candidate, qualified[6])
    report = _audit(qualified, candidate)
    assert _failed(report, "diagnostics") and _failed(report, "qualification")
    assert _failed(report, "model_alignment") and report["status"] == "FAIL"


def test_maximum_bounded_scalar_coverage_is_audited_without_provider_execution():
    request = moist_request()
    request["sampling"]["height_m"] = [float(index) for index in range(129)]
    result = compile_moist(request)
    reference = example_reference(request)
    reference["context"]["humidity_convention"] = PURE_LIQUID_CONVENTION
    reference["observations"] = [
        {"sample_index": index, "height_m": height,
         "quantities": {field: _quantity(result["profile"][field][index], field)
                        for field in FIELD_UNITS}}
        for index, height in enumerate(request["sampling"]["height_m"])]
    seal(reference)
    data = _prepare(request=request, reference=reference)
    assert data[5]["metrics"]["row_count"] == 774
    assert data[5]["metrics"]["passed_count"] == 774 and data[5]["status"] == "PASS"
    _validate(data)


@pytest.mark.parametrize("mutation", ["reference_source", "reference_metadata", "policy", "claims", "activation"])
def test_fresh_audit_rejects_unbound_reference_policy_and_authority(qualified, mutation):
    request, result, reference, policy, candidate, _, bindings = deepcopy(qualified)
    if mutation == "reference_source":
        bindings["reference_evidence_id"] = "sha256:" + "9" * 64
    elif mutation == "reference_metadata":
        reference["provenance"]["source_ref"] = "different.reference"
        seal(reference)
    elif mutation == "policy":
        policy["thresholds"]["temperature_k"]["absolute_tolerance"] *= 2
        seal(policy)
    elif mutation == "claims":
        candidate["claims"]["physical_validation"] = "established"
        seal(candidate)
    else:
        candidate["operation_id"] = "saved.module.import.v1"
        seal(candidate)
    with pytest.raises(ValueError):
        verify(request, result, reference, policy, candidate, bindings)
