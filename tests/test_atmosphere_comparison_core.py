"""Adversarial coverage of reference declarations and exact-height comparisons."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from ciw import atmosphere_comparison as comparator
from ciw import atmosphere_comparison_contract as contract
from ciw.atmosphere_compiler import compile_atmosphere as dry_compile
from ciw.atmosphere_contract import example_request as dry_request
from ciw.atmosphere_moist_compiler import compile_atmosphere as moist_compile
from ciw.atmosphere_moist_contract import example_request as moist_request
from ciw.core.identities import evidence_id
from ciw.operations.runner import digest, seal


def _bindings(reference):
    return {
        "source_evidence_id": digest("original model evidence"),
        "source_result_id": "result-" + "1" * 32,
        "source_execution_id": "execution-" + "2" * 32,
        "source_record_digest": digest("retained model result envelope"),
        "verification_id": "verification-" + "3" * 32,
        "recomputed_report_digest": digest("fresh atmospheric verification report"),
        "reference_evidence_id": contract.make_reference_source(reference)["evidence_id"],
    }


def _inputs(moist=False):
    request = moist_request() if moist else dry_request()
    result = moist_compile(request) if moist else dry_compile(request)
    reference = contract.example_reference(request)
    policy = contract.example_policy(reference)
    return request, result, reference, policy, _bindings(reference)


def _reseal(reference):
    seal(reference)
    return reference


def _datum(reference, field="temperature_k"):
    return reference["observations"][0]["quantities"][field]


@pytest.mark.parametrize("moist", [False, True])
def test_example_preserves_distinct_evidence_and_agreement(moist):
    request, result, reference, policy, bindings = _inputs(moist)
    comparison = comparator.compare(request, result, reference, policy, bindings)
    assert comparison["qualification"] == {"action": "LOCAL", "reasons": []}
    assert comparison["agreement_status"] == "PASS"
    assert comparison["reference_digest"] == reference["record_digest"]
    assert comparison["reference_evidence_id"] not in {digest(reference), reference["record_digest"]}
    assert comparison["claims"]["physical_validation"] == "not_established"
    assert comparison["claims"]["independence_declared"] is False


def test_reference_source_is_an_artifact_declaration_without_altitude_clock():
    reference = _inputs()[2]
    source = contract.make_reference_source(reference)
    assert source["evidence_id"] == evidence_id(source)
    assert source["time_s"] == [0.0]
    assert source["channels"] == {"reference_record_declaration": {"unit": "1", "values": [1.0]}}
    assert source["metadata"]["manifest"]["role"] == "declared_reference_artifact"
    assert source["metadata"]["manifest"]["supported_operations"] == [
        "atmosphere.compare.v1", "atmosphere.compare-verify.v1"]
    assert contract.reference_from_source(source) == reference


@pytest.mark.parametrize("mutation", ["render", "channel", "run_id", "provenance", "manifest"])
def test_resealed_reference_source_cannot_change_declaration_envelope(mutation):
    source = contract.make_reference_source(_inputs()[2])
    if mutation == "render":
        source["render"] = {"coordinate_frame": source["metadata"]["coordinate_frame"]}
    elif mutation == "channel":
        source["channels"]["reference_record_declaration"]["values"] = [2.0]
    elif mutation == "run_id":
        source["run_id"] = "run-other"
    elif mutation == "provenance":
        source["metadata"]["provenance"]["source"] = "genuine sensor reading"
    else:
        source["metadata"]["manifest"]["supported_operations"] = ["arbitrary.saved.operation"]
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError):
        contract.reference_from_source(source)


@pytest.mark.parametrize("field,value", [
    ("temperature_k", 0.0), ("temperature_k", True), ("temperature_k", 1e7),
    ("pressure_pa", -1.0), ("pressure_pa", 1e10), ("density_kg_per_m3", 0.0),
    ("density_kg_per_m3", 1e7), ("water_vapour_pressure_pa", -1.0),
    ("water_vapour_pressure_pa", 1e-300), ("relative_humidity", 2.1),
    ("relative_humidity", float("nan")), ("relative_humidity", 1e-300),
    ("liquid_water_saturation_pressure_pa", float("inf")),
])
def test_reference_scalar_bounds_reject_aliases_and_unusable_extremes(field, value):
    reference = _inputs(True)[2]
    reference["context"]["humidity_convention"] = contract.PURE_LIQUID_CONVENTION
    datum = deepcopy(_datum(reference))
    datum.update(value=value, unit=contract.FIELD_UNITS[field])
    reference["observations"][0]["quantities"] = {field: datum}
    if value == value and abs(value) != float("inf"):
        seal(reference)
    with pytest.raises(ValueError):
        contract.validate_reference(reference)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://", "https://user:secret@example.com/x",
                                 "https://example.com/with space", "https://example.com:bad/x",
                                 "https://example.com/\x00x", "https://example.com/" + "x" * 2048])
def test_reference_url_is_only_a_bounded_credential_free_http_declaration(url):
    reference = _inputs()[2]
    reference["provenance"]["source_url"] = url
    seal(reference)
    with pytest.raises(ValueError):
        contract.validate_reference(reference)


@pytest.mark.parametrize("url", [None, "https://www.nist.gov/reference", "http://example.org/table?x=1"])
def test_valid_reference_url_never_fetches_network_data(url):
    reference = _inputs()[2]
    reference["provenance"]["source_url"] = url
    seal(reference)
    with patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
        assert contract.validate_reference(reference)["provenance"]["source_url"] == url


@pytest.mark.parametrize("mutation", [
    "unknown_top", "missing_provenance", "unknown_provenance", "string_independence",
    "empty_source", "unknown_context", "non_utc", "invalid_time", "boolean_origin",
    "negative_height", "boolean_index", "duplicate_index", "descending_index", "index_129",
    "empty_quantities", "unknown_quantity", "unknown_datum", "wrong_unit", "unknown_uncertainty",
    "negative_bound", "tiny_bound", "wrong_coverage", "expanded_without_coverage",
    "exact_with_bound", "rounding_synthetic", "empty_uncertainty_reference", "unknown_convention",
])
def test_reference_exact_structure_and_uncertainty_declarations(mutation):
    reference = _inputs()[2]
    datum = _datum(reference)
    if mutation == "unknown_top": reference["provider_import"] = "untrusted.module"
    elif mutation == "missing_provenance": del reference["provenance"]
    elif mutation == "unknown_provenance": reference["provenance"]["authenticated"] = True
    elif mutation == "string_independence": reference["provenance"]["independent_of_candidate"] = "yes"
    elif mutation == "empty_source": reference["provenance"]["source_ref"] = " "
    elif mutation == "unknown_context": reference["context"]["interpolation"] = True
    elif mutation == "non_utc": reference["context"]["valid_time_utc"] = "2026-10-03T10:00:00-04:00"
    elif mutation == "invalid_time": reference["context"]["valid_time_utc"] = "2026-02-30T00:00:00Z"
    elif mutation == "boolean_origin": reference["context"]["height_origin_m"] = False
    elif mutation == "negative_height": reference["observations"][0]["height_m"] = -1.0
    elif mutation == "boolean_index": reference["observations"][0]["sample_index"] = False
    elif mutation == "duplicate_index": reference["observations"].append(deepcopy(reference["observations"][0]))
    elif mutation == "descending_index":
        reference["observations"].append(deepcopy(reference["observations"][0]))
        reference["observations"][0]["sample_index"] = 1
    elif mutation == "index_129": reference["observations"][0]["sample_index"] = 129
    elif mutation == "empty_quantities": reference["observations"][0]["quantities"] = {}
    elif mutation == "unknown_quantity": reference["observations"][0]["quantities"]["wind"] = deepcopy(datum)
    elif mutation == "unknown_datum": datum["authentic"] = True
    elif mutation == "wrong_unit": datum["unit"] = "degC"
    elif mutation == "unknown_uncertainty": datum["uncertainty"]["kind"] = "standard_deviation"
    elif mutation == "negative_bound": datum["uncertainty"]["absolute_bound"] = -1.0
    elif mutation == "tiny_bound": datum["uncertainty"]["absolute_bound"] = 1e-100
    elif mutation == "wrong_coverage": datum["uncertainty"]["coverage_factor"] = 2.0
    elif mutation == "expanded_without_coverage": datum["uncertainty"]["kind"] = "declared_expanded"
    elif mutation == "exact_with_bound": datum["uncertainty"]["absolute_bound"] = 1.0
    elif mutation == "rounding_synthetic": datum["uncertainty"].update(kind="rounding_bound", absolute_bound=0.1)
    elif mutation == "empty_uncertainty_reference": datum["uncertainty"]["reference"] = ""
    else: reference["context"]["humidity_convention"] = "sensor_default"
    seal(reference)
    with pytest.raises(ValueError):
        contract.validate_reference(reference)


def _measurements(reference):
    reference["provenance"].update(kind="declared_measurements", independent_of_candidate=True)
    reference["context"]["valid_time_utc"] = "2026-10-03T12:00:00Z"
    for datum in reference["observations"][0]["quantities"].values():
        datum["instrument_ref"] = "declared instrument serial 123"
        datum["calibration_ref"] = "declared calibration certificate 456"
        datum["uncertainty"].update(kind="declared_expanded", absolute_bound=2.0,
                                    coverage_factor=2.0, reference="Declared expanded uncertainty")
    return seal(reference)


@pytest.mark.parametrize("mutation", ["no_time", "no_instrument", "zero_bound", "exact_fixture", "rounding_bound"])
def test_measurements_require_time_instrument_and_nonzero_declared_bound(mutation):
    reference = _measurements(_inputs()[2])
    if mutation == "no_time": reference["context"]["valid_time_utc"] = None
    elif mutation == "no_instrument": _datum(reference)["instrument_ref"] = None
    elif mutation == "zero_bound": _datum(reference)["uncertainty"]["absolute_bound"] = 0.0
    else:
        _datum(reference)["uncertainty"].update(kind=mutation, coverage_factor=None, absolute_bound=0.0)
    seal(reference)
    with pytest.raises(ValueError): contract.validate_reference(reference)


def test_declared_expanded_bound_is_not_multiplied_by_coverage_factor_again():
    request, _, reference, policy, _ = _inputs()
    reference = _measurements(reference)
    request["reference"]["context"].update(source_kind="declared_environment",
                                           valid_time_utc="2026-10-03T12:00:00+00:00")
    result = dry_compile(request)
    _datum(reference)["value"] += 3.0
    seal(reference)
    policy["thresholds"]["temperature_k"]["absolute_tolerance"] = 0.0
    seal(policy)
    comparison = comparator.compare(request, result, reference, policy, _bindings(reference))
    row = next(row for row in comparison["rows"] if row["field"] == "temperature_k")
    assert row["reference_bound"] == row["total_allowance"] == 2.0
    assert row["normalized_acceptance_residual"] == 1.5
    assert comparison["agreement_status"] == "FAIL"
    assert comparison["qualification"]["action"] == "LOCAL"
    assert comparison["claims"]["independence_declared"] is True
    assert comparison["claims"]["independence_established"] is False
    assert comparison["claims"]["calibration_validation"] is False


@pytest.mark.parametrize("mutation", ["unknown", "missing", "negative", "boolean", "huge", "relative", "tiny", "rule"])
def test_policy_requires_exact_field_union_and_bounded_allowances(mutation):
    reference, policy = _inputs()[2:4]
    if mutation == "unknown": policy["thresholds"]["wind"] = {"absolute_tolerance": 0.0, "relative_tolerance": 0.0}
    elif mutation == "missing": del policy["thresholds"]["pressure_pa"]
    elif mutation == "negative": policy["thresholds"]["temperature_k"]["absolute_tolerance"] = -1.0
    elif mutation == "boolean": policy["thresholds"]["temperature_k"]["absolute_tolerance"] = True
    elif mutation == "huge": policy["thresholds"]["temperature_k"]["absolute_tolerance"] = 1e7
    elif mutation == "relative": policy["thresholds"]["temperature_k"]["relative_tolerance"] = 0.051
    elif mutation == "tiny": policy["thresholds"]["temperature_k"]["relative_tolerance"] = 1e-100
    else: policy["rule"] = "statistical_z_score"
    seal(policy)
    with pytest.raises(ValueError): contract.validate_policy(reference, policy)


@pytest.mark.parametrize("mutation,code", [
    ("frame", "frame_mismatch"), ("origin", "height_origin_mismatch"),
    ("time", "time_mismatch"), ("height", "height_mismatch"),
    ("index", "sample_index_out_of_range"),
])
def test_incompatible_geometry_or_time_refuses_every_quantitative_claim(mutation, code):
    request, result, reference, policy, _ = _inputs()
    if mutation == "frame": reference["context"]["frame"] = "declared.other-frame.v1"
    elif mutation == "origin": reference["context"]["height_origin_m"] = 1.0
    elif mutation == "time": reference["context"]["valid_time_utc"] = "2026-10-03T12:00:00Z"
    elif mutation == "height": reference["observations"][0]["height_m"] = 1.0
    else: reference["observations"][0]["sample_index"] = 128
    seal(reference)
    comparison = comparator.compare(request, result, reference, policy, _bindings(reference))
    assert comparison["qualification"] == {"action": "REFUSE", "reasons": [code]}
    assert comparison["agreement_status"] == "NOT_EVALUATED"
    assert all(row["model_value"] is None and row["signed_difference"] is None for row in comparison["rows"])


def test_measurement_against_synthetic_model_context_refuses_even_matching_time():
    request, _, reference, policy, _ = _inputs()
    reference = _measurements(reference)
    request["reference"]["context"]["valid_time_utc"] = reference["context"]["valid_time_utc"]
    comparison = comparator.compare(request, dry_compile(request), reference, policy, _bindings(reference))
    assert comparison["qualification"]["reasons"] == ["measurement_context_incompatible"]
    assert comparison["qualification"]["action"] == "REFUSE"


@pytest.mark.parametrize("moist,convention", [(False, contract.PURE_LIQUID_CONVENTION),
                                             (True, "pressure_enhanced_relative_humidity")])
def test_unrepresented_quantity_expands_without_silently_coercing_humidity(moist, convention):
    request, result, reference, _, _ = _inputs(moist)
    datum = deepcopy(_datum(reference))
    datum.update(value=0.5, unit="1")
    reference["observations"][0]["quantities"]["relative_humidity"] = datum
    reference["context"]["humidity_convention"] = convention
    seal(reference)
    comparison = comparator.compare(request, result, reference, contract.example_policy(reference), _bindings(reference))
    assert comparison["qualification"]["action"] == "EXPAND"
    humidity = next(row for row in comparison["rows"] if row["field"] == "relative_humidity")
    assert humidity["status"] == "NOT_EVALUATED"
    assert humidity["model_value"] is None
    assert next(row for row in comparison["rows"] if row["field"] == "temperature_k")["status"] == "PASS"


@pytest.mark.parametrize("offset,expected", [(0.0, "PASS"), (0.5, "PASS"), (2.0, "FAIL")])
def test_disagreement_does_not_change_local_domain_qualification(offset, expected):
    request, result, reference, policy, _ = _inputs()
    _datum(reference)["value"] += offset
    seal(reference)
    comparison = comparator.compare(request, result, reference, policy, _bindings(reference))
    assert comparison["qualification"]["action"] == "LOCAL"
    assert comparison["agreement_status"] == expected


@pytest.mark.parametrize("offset,expected", [(0.0, "PASS"), (0.01, "FAIL")])
def test_zero_allowance_has_null_normalized_residual_and_exact_acceptance(offset, expected):
    request, result, reference, policy, _ = _inputs()
    _datum(reference)["value"] += offset
    seal(reference)
    policy["thresholds"]["temperature_k"]["absolute_tolerance"] = 0.0
    seal(policy)
    row = next(row for row in comparator.compare(request, result, reference, policy, _bindings(reference))["rows"]
               if row["field"] == "temperature_k")
    assert row["normalized_acceptance_residual"] is None
    assert row["status"] == expected


@pytest.mark.parametrize("binding", sorted(contract.BINDING_KEYS))
def test_report_is_bound_to_each_separate_identity(binding):
    inputs = _inputs()
    comparison = comparator.compare(*inputs)
    if binding in {"source_result_id", "source_execution_id", "verification_id"}:
        comparison[binding] = comparison[binding].split("-")[0] + "-" + "4" * 32
    else: comparison[binding] = digest("other content")
    seal(comparison)
    with pytest.raises(ValueError): comparator.validate_comparison(*inputs[:4], comparison, inputs[4])


@pytest.mark.parametrize("mutation", ["extra", "missing_row", "model", "reference", "unit", "index_alias", "claims", "none_arithmetic"])
def test_static_read_rejects_detached_values_and_false_authority(mutation):
    inputs = _inputs()
    comparison = comparator.compare(*inputs)
    row = comparison["rows"][0]
    if mutation == "extra": comparison["activate"] = "provider.module"
    elif mutation == "missing_row": comparison["rows"].pop()
    elif mutation == "model": row["model_value"] += 1.0
    elif mutation == "reference": row["reference_value"] += 1.0
    elif mutation == "unit": row["unit"] = "bar"
    elif mutation == "index_alias": row["sample_index"] = False
    elif mutation == "claims": comparison["claims"]["state_admission_performed"] = True
    else: row["signed_difference"] = None
    seal(comparison)
    with pytest.raises(ValueError): comparator.validate_comparison(*inputs[:4], comparison, inputs[4])


def test_static_read_retains_wrong_arithmetic_without_replaying_any_provider():
    inputs = _inputs()
    comparison = comparator.compare(*inputs)
    comparison["rows"][0]["signed_difference"] = 1.0
    seal(comparison)
    with patch.object(comparator, "compare", side_effect=AssertionError("comparison replay")), \
            patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("compiler replay")), \
            patch("ciw.atmosphere_verification.verify", side_effect=AssertionError("verifier replay")):
        assert comparator.validate_comparison(*inputs[:4], comparison, inputs[4]) == comparison


def test_comparison_and_reference_return_detached_data():
    inputs = _inputs()
    reference = inputs[2]
    detached = contract.validate_reference(reference)
    _datum(detached)["value"] = 100.0
    assert _datum(reference)["value"] == inputs[0]["reference"]["temperature_k"]
    comparison = comparator.compare(*inputs)
    detached = comparator.validate_comparison(*inputs[:4], comparison, inputs[4])
    detached["rows"][0]["reference_value"] = 100.0
    assert detached != comparison


def test_maximum_scalar_budget_is_exact_and_bounded():
    request = moist_request()
    request["sampling"]["height_m"] = [float(index * 10) for index in range(129)]
    result = moist_compile(request)
    reference = contract.example_reference(request)
    reference["context"]["humidity_convention"] = contract.PURE_LIQUID_CONVENTION
    template = deepcopy(_datum(reference))
    reference["observations"] = []
    for index, height in enumerate(request["sampling"]["height_m"]):
        quantities = {}
        for field, unit in contract.FIELD_UNITS.items():
            datum = deepcopy(template)
            datum.update(value=result["profile"][field][index], unit=unit)
            quantities[field] = datum
        reference["observations"].append({"sample_index": index, "height_m": height, "quantities": quantities})
    seal(reference)
    comparison = comparator.compare(request, result, reference, contract.example_policy(reference), _bindings(reference))
    assert len(comparison["rows"]) == contract.MAX_SCALARS == 774
    assert comparison["agreement_status"] == "PASS"
    reference["observations"].append(deepcopy(reference["observations"][-1]))
    seal(reference)
    with pytest.raises(ValueError): contract.validate_reference(reference)


def test_reference_evidence_identity_cannot_be_replaced_by_an_artifact_digest():
    request, result, reference, policy, bindings = _inputs()
    bindings["reference_evidence_id"] = digest(reference)
    with pytest.raises(ValueError): comparator.compare(request, result, reference, policy, bindings)
