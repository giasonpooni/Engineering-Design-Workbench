"""Trust-boundary and synchronization checks for the legibility instrument."""

import base64
from copy import deepcopy
import hashlib
import json

import pytest

from ciw.core.identities import canonical_json, content_identity, validate_identity
from ciw.legibility import (
    CANONICALIZATION, compile_bundle, key_fingerprint, load_json_strict,
    sign_bundle, validate_contract, verify_bundle,
)


PHOTO = b"original photograph bytes; image decoding is not an integrity assertion"
ARTIFACTS = {"photo:specimen-01": PHOTO}


@pytest.fixture
def contract():
    evidence = content_identity({"instrument": "impact.v1", "force_n": [0, 11.5, 0]})
    return {
        "schema": "ciw.legibility-contract.v1",
        "object": {"object_id": "specimen:polymer-01", "version": "3", "label": "Polymer specimen α", "kind": "impact-test-specimen"},
        "bindings": {"evidence_id": evidence, "operation_id": "impact.test.v1",
                     "execution_id": "execution-" + "1" * 32, "verification_id": None},
        "semantics": {
            "coordinate_frame": "fixture:impact-rig-01",
            "properties": [
                {"property_id": "peak-force", "value": 11.5, "unit": "N",
                 "uncertainty": {"status": "measured", "standard_uncertainty": 0.7}, "evidence_refs": [evidence]},
                {"property_id": "strain-rate", "value": 900, "unit": "s^-1",
                 "uncertainty": {"status": "unknown", "standard_uncertainty": None}, "evidence_refs": []},
            ],
            "relationships": [{"relation": "tested_in", "target_id": "rig:01", "target_version": "2"}],
            "assumptions": ["Uniform initial temperature", "Camera frame is distinct from fixture frame"],
        },
        "claims": [
            {"claim_id": "predicted", "statement": "Model predicts elastic response", "status": "simulated", "evidence_refs": ["model:01"]},
            {"claim_id": "unknown", "statement": "Fracture mechanism remains unresolved", "status": "unresolved", "evidence_refs": []},
            {"claim_id": "limit", "statement": "Peak force exceeds the declared limit", "status": "failed", "evidence_refs": [evidence]},
        ],
        "qualification": {"status": "unqualified", "calibration_refs": ["calibration:rig-01"], "verification_refs": [], "canonical_admission": False},
        "vision": {"image_artifact_id": "photo:specimen-01", "annotations": [
            {"annotation_id": "specimen-outline", "coordinate_frame": "camera:01", "bbox_xywh_normalized": [0.1, 0.2, 0.4, 0.5]},
        ]},
        "artifacts": [{"artifact_id": "photo:specimen-01", "media_type": "image/png", "sha256": "sha256:" + hashlib.sha256(PHOTO).hexdigest(), "size_bytes": len(PHOTO)}],
    }


@pytest.fixture
def key():
    module = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    return module.Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def raw_public(envelope):
    return base64.b64decode(envelope["public_key_b64"])


def test_compile_is_deterministic_independent_and_preserves_core_hashes(contract):
    before = canonical_json(contract)
    first = compile_bundle(contract)
    second = compile_bundle(deepcopy(contract), ARTIFACTS)
    assert first == second
    assert canonical_json(contract) == before
    assert first["manifest"]["source_digest"] == content_identity(contract)
    assert first["bundle_id"] == content_identity(first["manifest"])
    assert first["manifest"]["canonicalization"] == CANONICALIZATION
    assert canonical_json({"μ": 1.0}) == '{"\\u03bc":1.0}'
    first["source"]["semantics"]["properties"][0]["value"] = 99
    first["representations"]["reasoning"]["semantics"]["assumptions"].clear()
    assert canonical_json(contract) == before
    assert second["source"]["semantics"]["properties"][0]["value"] == 11.5


def test_every_projection_retains_full_scientific_semantics_and_evidence(contract):
    bundle = compile_bundle(contract)
    for view in bundle["representations"].values():
        assert view["semantics"] == contract["semantics"]
        assert view["claims"] == contract["claims"]
        assert view["qualification"] == contract["qualification"]
        assert view["evidence_bindings"] == contract["bindings"]
        assert view["artifacts"] == contract["artifacts"]
        assert view["object_id"] == contract["object"]["object_id"]
        assert view["version"] == "3"
        assert view["source_digest"] == bundle["manifest"]["source_digest"]
    assert [item["claim_id"] for item in bundle["representations"]["human"]["attention"]] == ["limit", "unknown", "predicted"]
    assert bundle["representations"]["vision"]["detector_evaluated"] is False
    assert bundle["representations"]["reasoning"]["claims_independently_validated"] is False


def test_unsigned_metadata_verification_never_claims_photo_trust_freshness_or_physics(contract):
    report = verify_bundle(compile_bundle(contract))
    assert report["content_intact"] is True
    assert report["artifact_status"] == "not_checked"
    assert report["signature_valid"] is None
    assert report["issuer_trusted"] is False
    assert report["version_current"] is None
    assert report["object_matches"] is None
    assert report["source_matches"] is None
    assert report["physical_validation_status"] == "not_assessed"
    assert report["declared_qualification"] == contract["qualification"]
    assert report["canonical_admission"] is False
    assert report["errors"] == []


def test_valid_signature_trust_freshness_and_artifact_checks_are_separate(contract, key):
    bundle = compile_bundle(contract)
    envelope = sign_bundle(bundle, key)
    trust = {envelope["key_id"]: raw_public(envelope)}
    report = verify_bundle(bundle, envelope, artifacts=ARTIFACTS, trusted_keys=trust,
                           expected_object_id="specimen:polymer-01", expected_version="3",
                           expected_source_digest=bundle["manifest"]["source_digest"])
    assert report["content_intact"] and report["signature_valid"] and report["issuer_trusted"]
    assert report["artifact_status"] == "verified"
    assert report["version_current"] and report["object_matches"] and report["source_matches"]
    assert report["physical_validation_status"] == "not_assessed"
    assert report["canonical_admission"] is False
    assert report["errors"] == []
    assert sign_bundle(bundle, bytes(range(32))) == envelope
    assert key_fingerprint(raw_public(envelope)) == envelope["key_id"]


def test_cryptographic_report_has_new_event_and_recomputable_seal(contract):
    bundle = compile_bundle(contract)
    first, second = verify_bundle(bundle), verify_bundle(bundle)
    validate_identity(first["verification_id"], "verification")
    assert first["verification_id"] != second["verification_id"]
    seal = first.pop("report_id")
    assert seal == content_identity(first)
    assert bundle["source"]["bindings"]["verification_id"] is None


def test_report_digest_binds_complete_bundle_and_is_null_after_source_or_view_tamper(contract):
    bundle = compile_bundle(contract)
    report = verify_bundle(bundle)
    assert report["verified_bundle_digest"] == content_identity(bundle)
    for target in ("source", "human", "reasoning", "vision"):
        changed = deepcopy(bundle)
        if target == "source":
            changed["source"]["object"]["label"] += " edited"
        else:
            changed["representations"][target]["semantics"]["assumptions"].clear()
        assert changed["bundle_id"] == report["bundle_id"]
        assert content_identity(changed) != report["verified_bundle_digest"]
        rejected = verify_bundle(changed)
        assert rejected["content_intact"] is False
        assert rejected["verified_bundle_digest"] is None


@pytest.mark.parametrize("target", ["source", "human", "reasoning", "vision"])
def test_source_or_view_tamper_detected_even_with_unchanged_valid_signature(contract, key, target):
    bundle = compile_bundle(contract)
    envelope = sign_bundle(bundle, key)
    changed = deepcopy(bundle)
    if target == "source":
        changed["source"]["object"]["label"] += " tampered"
    else:
        changed["representations"][target]["semantics"]["assumptions"].clear()
    report = verify_bundle(changed, envelope)
    assert report["content_intact"] is False
    assert report["signature_valid"] is True
    assert any(error["code"] == "content_mismatch" for error in report["errors"])
    with pytest.raises(ValueError, match="integrity mismatch"):
        sign_bundle(changed, key)


def test_signed_self_consistent_but_wrong_projection_is_refused(contract):
    bundle = compile_bundle(contract)
    bundle["representations"]["reasoning"]["semantics"]["properties"][0]["value"] = 0
    bundle["manifest"]["representation_digests"]["reasoning"] = content_identity(bundle["representations"]["reasoning"])
    bundle["bundle_id"] = content_identity(bundle["manifest"])
    assert verify_bundle(bundle)["content_intact"] is False


@pytest.mark.parametrize("field", ["bundle_id", "source_digest", "representation_digest", "canonicalization", "compiler"])
def test_manifest_or_hash_tamper_is_detected(contract, key, field):
    bundle = compile_bundle(contract)
    envelope = sign_bundle(bundle, key)
    changed = deepcopy(bundle)
    if field == "bundle_id":
        changed[field] = "sha256:" + "0" * 64
    elif field == "representation_digest":
        changed["manifest"]["representation_digests"]["human"] = "sha256:" + "0" * 64
    elif field == "source_digest":
        changed["manifest"][field] = "sha256:" + "0" * 64
    else:
        changed["manifest"][field] = "unknown.v1"
    report = verify_bundle(changed, envelope)
    assert report["content_intact"] is False
    assert report["signature_valid"] is False


@pytest.mark.parametrize("artifacts", [{}, {"photo:specimen-01": b"altered"}, {"other": PHOTO}, {"photo:specimen-01": PHOTO + b"x"}])
def test_artifact_bytes_must_match_all_declared_identity_length_and_hash(contract, artifacts):
    with pytest.raises(ValueError):
        compile_bundle(contract, artifacts)
    report = verify_bundle(compile_bundle(contract), artifacts=artifacts)
    assert report["content_intact"] is True
    assert report["artifact_status"] == "failed"
    assert any(error["code"] == "artifact_mismatch" for error in report["errors"])


def test_stale_version_wrong_object_and_source_fail_without_invalidating_signature(contract, key):
    bundle = compile_bundle(contract)
    report = verify_bundle(bundle, sign_bundle(bundle, key), expected_object_id="specimen:other", expected_version="4",
                           expected_source_digest="sha256:" + "0" * 64)
    assert report["content_intact"] is True and report["signature_valid"] is True
    assert report["version_current"] is False and report["object_matches"] is False and report["source_matches"] is False
    assert {error["code"] for error in report["errors"]} == {"object_mismatch", "stale_version", "source_digest_mismatch"}


def test_embedded_or_replaced_key_is_never_a_trust_anchor(contract, key):
    bundle = compile_bundle(contract)
    envelope = sign_bundle(bundle, key)
    assert verify_bundle(bundle, envelope)["signature_valid"] is True
    assert verify_bundle(bundle, envelope)["issuer_trusted"] is False
    trust = {envelope["key_id"]: raw_public(envelope)}
    other_envelope = sign_bundle(bundle, b"x" * 32)
    report = verify_bundle(bundle, other_envelope, trusted_keys=trust)
    assert report["signature_valid"] is True
    assert report["issuer_trusted"] is False
    assert any(error["code"] == "issuer_untrusted" for error in report["errors"])
    with pytest.raises(ValueError, match="Trusted key identity"):
        verify_bundle(bundle, envelope, trusted_keys={envelope["key_id"]: b"x" * 32})


@pytest.mark.parametrize("field,value", [
    ("algorithm", "none"), ("algorithm", "RSA"), ("canonicalization", "RFC8785"),
    ("key_id", "ed25519:sha256:" + "0" * 64), ("public_key_b64", "bad"),
    ("signature_b64", base64.b64encode(b"x" * 64).decode()), ("schema", "unknown.v1"),
])
def test_signature_key_algorithm_profile_and_encoding_substitution_fail(contract, key, field, value):
    bundle = compile_bundle(contract)
    envelope = sign_bundle(bundle, key)
    envelope[field] = value
    report = verify_bundle(bundle, envelope)
    assert report["content_intact"] is True
    assert report["signature_valid"] is False
    assert report["issuer_trusted"] is False


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"nested":{"x":1,"x":1}}', '{"x":NaN}', '[Infinity]', '[-Infinity]', '{"x":1e400}',
                                   '"\\ud800"', '{"\\udfff": 0}'])
def test_strict_json_refuses_duplicate_keys_and_nonfinite_numbers(text):
    with pytest.raises(ValueError):
        load_json_strict(text)


def test_strict_json_and_export_reimport_preserve_identity(contract):
    bundle = compile_bundle(contract)
    recovered = load_json_strict(json.dumps(bundle, ensure_ascii=False, indent=2))
    assert recovered == bundle
    assert verify_bundle(recovered, artifacts=ARTIFACTS)["content_intact"] is True
    assert load_json_strict(canonical_json(contract).encode()) == contract
    assert load_json_strict('"\\ud83d\\ude00"') == "😀"


@pytest.mark.parametrize("expected", [[], {}, 1, float("nan"), "\ud800"])
def test_invalid_caller_expectations_are_refused_before_report_serialization(contract, expected):
    with pytest.raises(ValueError):
        verify_bundle(compile_bundle(contract), expected_version=expected)


@pytest.mark.parametrize("path", [(), ("object",), ("bindings",), ("semantics",),
                                  ("semantics", "properties", 0), ("semantics", "properties", 0, "uncertainty"),
                                  ("semantics", "relationships", 0), ("claims", 0), ("qualification",),
                                  ("vision",), ("vision", "annotations", 0), ("artifacts", 0)])
def test_unknown_fields_refused_at_every_schema_layer(contract, path):
    value = contract
    for part in path:
        value = value[part]
    value["undeclared_authority"] = True
    with pytest.raises(ValueError, match="requires exactly"):
        validate_contract(contract)


@pytest.mark.parametrize("field", ["unit", "uncertainty", "evidence_refs"])
def test_property_semantics_cannot_be_omitted(contract, field):
    del contract["semantics"]["properties"][0][field]
    with pytest.raises(ValueError):
        validate_contract(contract)


@pytest.mark.parametrize("path,value", [
    (("semantics", "properties", 0, "value"), float("nan")),
    (("semantics", "properties", 0, "uncertainty", "standard_uncertainty"), -1),
    (("semantics", "properties", 0, "uncertainty", "standard_uncertainty"), True),
    (("semantics", "properties", 0, "uncertainty", "standard_uncertainty"), None),
    (("semantics", "properties", 1, "uncertainty", "standard_uncertainty"), 0),
    (("semantics", "coordinate_frame"), ""),
    (("qualification", "canonical_admission"), True),
    (("qualification", "canonical_admission"), 0),
    (("vision", "image_artifact_id"), None),
    (("vision", "image_artifact_id"), "not-an-artifact"),
    (("vision", "annotations", 0, "coordinate_frame"), ""),
    (("vision", "annotations", 0, "bbox_xywh_normalized"), [0, 0, 0, 1]),
    (("vision", "annotations", 0, "bbox_xywh_normalized"), [0.8, 0, 0.4, 1]),
    (("vision", "annotations", 0, "bbox_xywh_normalized"), [False, 0, 1, 1]),
    (("artifacts", 0, "size_bytes"), True),
    (("bindings", "evidence_id"), "execution-" + "1" * 32),
    (("bindings", "operation_id"), "impact.test"),
    (("bindings", "execution_id"), "verification-" + "1" * 32),
    (("bindings", "verification_id"), "execution-" + "1" * 32),
])
def test_invalid_scientific_semantics_identity_types_and_admission_refused(contract, path, value):
    target = contract
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_contract(contract)


@pytest.mark.parametrize("path", [("claims",), ("semantics", "properties"), ("vision", "annotations"), ("artifacts",)])
def test_duplicate_ids_refused(contract, path):
    items = contract
    for part in path:
        items = items[part]
    items.append(deepcopy(items[0]))
    with pytest.raises(ValueError, match="duplicate"):
        validate_contract(contract)


def test_claimed_experimental_qualification_is_retained_without_automatic_authority(contract, key):
    contract["qualification"]["status"] = "experimental"
    contract["bindings"]["verification_id"] = "verification-" + "2" * 32
    bundle = compile_bundle(contract)
    report = verify_bundle(bundle, sign_bundle(bundle, key), artifacts=ARTIFACTS)
    assert report["declared_qualification"]["status"] == "experimental"
    assert report["physical_validation_status"] == "not_assessed"
    assert report["canonical_admission"] is False
    assert bundle["source"]["bindings"]["verification_id"] == "verification-" + "2" * 32


@pytest.mark.parametrize("bundle", [None, [], {}, {"manifest": {}}, {"bundle_id": "unknown", "source": None}])
def test_malformed_bundle_returns_failed_sealed_report(bundle):
    report = verify_bundle(bundle)
    assert report["content_intact"] is False
    assert report["physical_validation_status"] == "not_assessed"
    assert report["declared_qualification"] is None
    assert report["verified_bundle_digest"] is None
    assert report["errors"]
    seal = report.pop("report_id")
    assert content_identity(report) == seal
