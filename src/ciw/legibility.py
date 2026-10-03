"""Deterministic scientific representations with optional Ed25519 attribution.

The private CIW canonical profile reuses ``core.identities.canonical_json``
unchanged: sorted keys, ASCII escapes, compact separators, arbitrary JSON
integers, Python binary64 float serialization, and no nonfinite values. It is
not RFC 8785/JCS, JSON-LD canonicalization, a VC implementation, or C2PA.

An intact bundle or valid signature does not validate observations, qualify a
model, identify a person, or authorize canonical admission. Trust anchors and
the expected object/version/source are supplied by the caller.
"""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any

from .core.identities import canonical_json, content_identity, new_identity, validate_identity
from .operations.registry import valid_operation_id


CONTRACT_SCHEMA = "ciw.legibility-contract.v1"
BUNDLE_SCHEMA = "ciw.legibility-bundle.v1"
MANIFEST_SCHEMA = "ciw.legibility-manifest.v1"
SIGNATURE_SCHEMA = "ciw.legibility-signature.v1"
REPORT_SCHEMA = "ciw.legibility-verification.v1"
CANONICALIZATION = "ciw.json.sort-keys.ascii.binary64.v1"
COMPILER = "ciw.legibility.v1"
_SIGN_DOMAIN = b"CIW-LEGIBILITY-SIGNATURE-V1\x00"
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _fields(value: Any, names: set[str], path: str) -> None:
    if type(value) is not dict or set(value) != names:
        raise ValueError(f"{path} requires exactly the fields {', '.join(sorted(names))}")


def _text(value: Any, path: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{path} must be a nonempty string")
    return value


def _number(value: Any, path: str) -> int | float:
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        raise ValueError(f"{path} must be a finite number")
    return value


def _strings(value: Any, path: str) -> None:
    if type(value) is not list:
        raise ValueError(f"{path} must be an array")
    for index, item in enumerate(value):
        _text(item, f"{path}[{index}]")
    if len(value) != len(set(value)):
        raise ValueError(f"{path} contains duplicate references")


def _items(value: Any, path: str) -> list:
    if type(value) is not list:
        raise ValueError(f"{path} must be an array")
    return value


def _json_value(value: Any, path: str = "JSON", ancestors: set[int] | None = None) -> None:
    """Refuse Python-only objects, cycles, and nonfinite JSON numbers."""
    if type(value) is str:
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError(f"{path} contains a lone Unicode surrogate")
        return
    if value is None or type(value) in (bool, int):
        return
    if type(value) is float:
        _number(value, path)
        return
    if type(value) not in (dict, list):
        raise ValueError(f"{path} must contain only JSON values")
    ancestors = set() if ancestors is None else ancestors
    if id(value) in ancestors:
        raise ValueError(f"{path} contains a cycle")
    ancestors.add(id(value))
    try:
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError(f"{path} object keys must be strings")
                _json_value(key, f"{path} key", ancestors)
                _json_value(item, f"{path}.{key}", ancestors)
        else:
            for index, item in enumerate(value):
                _json_value(item, f"{path}[{index}]", ancestors)
    finally:
        ancestors.remove(id(value))


def load_json_strict(text: str | bytes) -> Any:
    """Parse JSON, rejecting duplicate object keys and all nonfinite numbers."""
    def pairs(items: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value: str) -> None:
        raise ValueError(f"Nonfinite JSON number: {value}")

    if type(text) not in (str, bytes):
        raise ValueError("JSON input must be text or bytes")
    value = json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
    _json_value(value)
    return value


def _hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise ValueError(f"{path} must be a lowercase SHA-256 content identity")
    return value


def _unique(items: list[dict], field: str, path: str) -> None:
    identifiers = [item[field] for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{path} contains duplicate {field} values")


def validate_contract(contract: dict) -> dict:
    """Validate the closed v1 schema and return an independent JSON deep copy."""
    _json_value(contract)
    _fields(contract, {"schema", "object", "bindings", "semantics", "claims", "qualification", "vision", "artifacts"}, "contract")
    if contract["schema"] != CONTRACT_SCHEMA:
        raise ValueError("Unsupported legibility contract schema")
    obj = contract["object"]
    _fields(obj, {"object_id", "version", "label", "kind"}, "object")
    for field in obj:
        _text(obj[field], f"object.{field}")
    bindings = contract["bindings"]
    _fields(bindings, {"evidence_id", "operation_id", "execution_id", "verification_id"}, "bindings")
    _hash(bindings["evidence_id"], "bindings.evidence_id")
    if not valid_operation_id(bindings["operation_id"]):
        raise ValueError("bindings.operation_id must be a versioned CIW operation identity")
    validate_identity(bindings["execution_id"], "execution")
    if bindings["verification_id"] is not None:
        validate_identity(bindings["verification_id"], "verification")
    semantics = contract["semantics"]
    _fields(semantics, {"coordinate_frame", "properties", "relationships", "assumptions"}, "semantics")
    _text(semantics["coordinate_frame"], "semantics.coordinate_frame")
    properties = _items(semantics["properties"], "semantics.properties")
    for prop in properties:
        _fields(prop, {"property_id", "value", "unit", "uncertainty", "evidence_refs"}, "property")
        _text(prop["property_id"], "property.property_id")
        _text(prop["unit"], "property.unit")
        uncertainty = prop["uncertainty"]
        _fields(uncertainty, {"status", "standard_uncertainty"}, "property.uncertainty")
        if uncertainty["status"] not in ("unknown", "declared", "measured"):
            raise ValueError("Unsupported uncertainty status")
        amount = uncertainty["standard_uncertainty"]
        if uncertainty["status"] == "unknown":
            if amount is not None:
                raise ValueError("Unknown uncertainty must retain a null standard_uncertainty")
        elif amount is None or _number(amount, "standard_uncertainty") < 0:
            raise ValueError("Declared or measured standard_uncertainty must be nonnegative")
        _strings(prop["evidence_refs"], "property.evidence_refs")
    _unique(properties, "property_id", "semantics.properties")
    relationships = _items(semantics["relationships"], "semantics.relationships")
    for relation in relationships:
        _fields(relation, {"relation", "target_id", "target_version"}, "relationship")
        for field in relation:
            _text(relation[field], f"relationship.{field}")
    _strings(semantics["assumptions"], "semantics.assumptions")
    claims = _items(contract["claims"], "claims")
    for claim in claims:
        _fields(claim, {"claim_id", "statement", "status", "evidence_refs"}, "claim")
        _text(claim["claim_id"], "claim.claim_id")
        _text(claim["statement"], "claim.statement")
        if claim["status"] not in ("measured", "simulated", "assumed", "unresolved", "failed"):
            raise ValueError("Unsupported claim status")
        _strings(claim["evidence_refs"], "claim.evidence_refs")
    _unique(claims, "claim_id", "claims")
    qualification = contract["qualification"]
    _fields(qualification, {"status", "calibration_refs", "verification_refs", "canonical_admission"}, "qualification")
    if qualification["status"] not in ("unqualified", "numerical_only", "experimental"):
        raise ValueError("Unsupported declared qualification status")
    if qualification["canonical_admission"] is not False:
        raise ValueError("Legibility compilation cannot grant canonical admission")
    _strings(qualification["calibration_refs"], "qualification.calibration_refs")
    _strings(qualification["verification_refs"], "qualification.verification_refs")
    artifacts = _items(contract["artifacts"], "artifacts")
    for artifact in artifacts:
        _fields(artifact, {"artifact_id", "media_type", "sha256", "size_bytes"}, "artifact")
        _text(artifact["artifact_id"], "artifact.artifact_id")
        _text(artifact["media_type"], "artifact.media_type")
        _hash(artifact["sha256"], "artifact.sha256")
        if type(artifact["size_bytes"]) is not int or artifact["size_bytes"] < 0:
            raise ValueError("artifact.size_bytes must be a nonnegative integer")
    _unique(artifacts, "artifact_id", "artifacts")
    vision = contract["vision"]
    _fields(vision, {"image_artifact_id", "annotations"}, "vision")
    image = vision["image_artifact_id"]
    if image is not None:
        _text(image, "vision.image_artifact_id")
        image_record = next((item for item in artifacts if item["artifact_id"] == image), None)
        if image_record is None or not image_record["media_type"].startswith("image/"):
            raise ValueError("vision.image_artifact_id must bind a declared image artifact")
    annotations = _items(vision["annotations"], "vision.annotations")
    if annotations and image is None:
        raise ValueError("Vision annotations require an image artifact binding")
    for annotation in annotations:
        _fields(annotation, {"annotation_id", "coordinate_frame", "bbox_xywh_normalized"}, "annotation")
        _text(annotation["annotation_id"], "annotation.annotation_id")
        _text(annotation["coordinate_frame"], "annotation.coordinate_frame")
        box = annotation["bbox_xywh_normalized"]
        if type(box) is not list or len(box) != 4:
            raise ValueError("annotation.bbox_xywh_normalized must contain four numbers")
        x, y, width, height = [_number(value, "normalized bbox") for value in box]
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
            raise ValueError("Normalized bbox must have positive area and lie inside the image")
    _unique(annotations, "annotation_id", "vision.annotations")
    return deepcopy(contract)


def _check_artifacts(contract: dict, artifacts: dict[str, bytes]) -> None:
    if type(artifacts) is not dict or set(artifacts) != {item["artifact_id"] for item in contract["artifacts"]}:
        raise ValueError("Artifact bytes must match the complete declared artifact ID set")
    for item in contract["artifacts"]:
        data = artifacts[item["artifact_id"]]
        if type(data) is not bytes:
            raise ValueError("Artifact content must be bytes")
        if len(data) != item["size_bytes"] or "sha256:" + hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Artifact integrity mismatch: {item['artifact_id']}")


def compile_bundle(contract: dict, artifacts: dict[str, bytes] | None = None) -> dict:
    """Compile synchronized, deterministic views; optional bytes validate metadata.

    Omitting bytes is supported and never claims the artifact bytes were checked.
    The complete scientific uncertainty, assumptions, references, and declared
    qualification remain available in every projection.
    """
    source = validate_contract(contract)
    if artifacts is not None:
        _check_artifacts(source, artifacts)
    source_digest = content_identity(source)
    identity = {"object_id": source["object"]["object_id"], "version": source["object"]["version"], "source_digest": source_digest}
    shared = {**identity, "label": source["object"]["label"], "kind": source["object"]["kind"],
              "semantics": source["semantics"], "claims": source["claims"],
              "qualification": source["qualification"], "evidence_bindings": source["bindings"],
              "artifacts": source["artifacts"]}
    priority = {"failed": 0, "unresolved": 1, "assumed": 2, "simulated": 3, "measured": 4}
    representations = {
        "human": {**deepcopy(shared), "attention": sorted(deepcopy(source["claims"]), key=lambda claim: priority[claim["status"]])},
        "reasoning": {**deepcopy(shared), "claims_independently_validated": False},
        "vision": {**deepcopy(shared), **deepcopy(source["vision"]), "annotation_units": "normalized_image_xywh", "detector_evaluated": False},
    }
    manifest = {"schema": MANIFEST_SCHEMA, "canonicalization": CANONICALIZATION, "compiler": COMPILER,
                **identity, "bindings": deepcopy(source["bindings"]), "artifacts": deepcopy(source["artifacts"]),
                "representation_digests": {name: content_identity(view) for name, view in representations.items()}}
    return {"schema": BUNDLE_SCHEMA, "source": source, "representations": representations,
            "manifest": manifest, "bundle_id": content_identity(manifest)}


def _validate_bundle(bundle: dict) -> dict:
    _json_value(bundle)
    _fields(bundle, {"schema", "source", "representations", "manifest", "bundle_id"}, "bundle")
    if bundle["schema"] != BUNDLE_SCHEMA:
        raise ValueError("Unsupported legibility bundle schema")
    expected = compile_bundle(bundle["source"])
    if canonical_json(bundle) != canonical_json(expected):
        raise ValueError("Bundle integrity mismatch: source, representations, manifest, or bundle identity changed")
    return expected


def _crypto():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
        from cryptography.hazmat.primitives import serialization
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise RuntimeError("Ed25519 support requires the optional .[legibility] dependency") from exc
    return Ed25519PrivateKey, Ed25519PublicKey, serialization, InvalidSignature


def key_fingerprint(public_key: bytes) -> str:
    """Return a key fingerprint, which conveys no issuer trust by itself."""
    if type(public_key) is not bytes or len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain exactly 32 raw bytes")
    return "ed25519:sha256:" + hashlib.sha256(public_key).hexdigest()


def _b64decode(value: Any, size: int, path: str) -> bytes:
    _text(value, path)
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid canonical Base64: {path}") from exc
    if len(result) != size or base64.b64encode(result).decode("ascii") != value:
        raise ValueError(f"Invalid canonical Base64 length or spelling: {path}")
    return result


def _signed_bytes(bundle: dict, envelope: dict) -> bytes:
    payload = {"schema": "ciw.legibility-signed-payload.v1", "algorithm": envelope["algorithm"],
               "canonicalization": envelope["canonicalization"], "key_id": envelope["key_id"],
               "public_key_b64": envelope["public_key_b64"], "bundle_id": bundle["bundle_id"],
               "manifest": bundle["manifest"]}
    return _SIGN_DOMAIN + canonical_json(payload).encode("utf-8")


def sign_bundle(bundle: dict, private_key: Any) -> dict:
    """Sign an intact bundle using an Ed25519 key object or 32-byte raw key."""
    _validate_bundle(bundle)
    private_type, _, serialization, _ = _crypto()
    if type(private_key) is bytes:
        if len(private_key) != 32:
            raise ValueError("Ed25519 private key must contain exactly 32 raw bytes")
        private_key = private_type.from_private_bytes(private_key)
    if not isinstance(private_key, private_type):
        raise ValueError("Signing requires an Ed25519 private key")
    public_key = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    envelope = {"schema": SIGNATURE_SCHEMA, "algorithm": "Ed25519", "canonicalization": CANONICALIZATION,
                "key_id": key_fingerprint(public_key), "public_key_b64": base64.b64encode(public_key).decode("ascii")}
    envelope["signature_b64"] = base64.b64encode(private_key.sign(_signed_bytes(bundle, envelope))).decode("ascii")
    return envelope


def verify_bundle(bundle: dict, envelope: dict | None = None, *, artifacts: dict[str, bytes] | None = None,
                  trusted_keys: dict[str, bytes] | None = None, expected_object_id: str | None = None,
                  expected_version: str | None = None, expected_source_digest: str | None = None) -> dict:
    """Return sealed, separated checks; malformed or tampered data fails closed.

    Signature verification uses the supplied bundle's signed manifest; source
    and projections are checked independently by recompilation. Caller-provided
    freshness expectations are required for any freshness conclusion. This is
    a consistency/attribution report, never a physical validation report.
    """
    for field, value in (("expected_object_id", expected_object_id), ("expected_version", expected_version),
                         ("expected_source_digest", expected_source_digest)):
        if value is not None:
            _text(value, field)
            _json_value(value, field)
    if trusted_keys is not None:
        if type(trusted_keys) is not dict:
            raise ValueError("Trusted keys must be a caller-supplied key-ID to raw-bytes mapping")
        for key_id, raw_key in trusted_keys.items():
            _text(key_id, "trusted key identity")
            if key_fingerprint(raw_key) != key_id:
                raise ValueError("Trusted key identity must match the supplied raw public key")
    errors = []

    def error(code: str, exc: Exception | str) -> None:
        errors.append({"code": code, "message": str(exc)})

    checked = None
    try:
        checked = _validate_bundle(bundle)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
        error("content_mismatch", exc)
    content_intact = checked is not None
    artifact_status = "not_checked"
    if artifacts is not None:
        try:
            if checked is None:
                raise ValueError("Artifact bytes cannot be bound to an invalid bundle")
            _check_artifacts(checked["source"], artifacts)
            artifact_status = "verified"
        except (ValueError, TypeError, KeyError) as exc:
            artifact_status = "failed"
            error("artifact_mismatch", exc)
    signature_valid = None if envelope is None else False
    issuer_trusted = False
    signing_key_id = None
    if envelope is not None:
        try:
            _json_value(envelope)
            _fields(envelope, {"schema", "algorithm", "canonicalization", "key_id", "public_key_b64", "signature_b64"}, "signature")
            if envelope["schema"] != SIGNATURE_SCHEMA or envelope["algorithm"] != "Ed25519":
                raise ValueError("Unsupported signature schema or algorithm")
            if envelope["canonicalization"] != CANONICALIZATION:
                raise ValueError("Unsupported signature canonicalization profile")
            public_key = _b64decode(envelope["public_key_b64"], 32, "public_key_b64")
            signature = _b64decode(envelope["signature_b64"], 64, "signature_b64")
            signing_key_id = key_fingerprint(public_key)
            if envelope["key_id"] != signing_key_id:
                raise ValueError("Signing key fingerprint mismatch")
            if type(bundle) is not dict or type(bundle.get("manifest")) is not dict:
                raise ValueError("No signed manifest available")
            if bundle["manifest"].get("canonicalization") != CANONICALIZATION:
                raise ValueError("Unsupported signed manifest canonicalization profile")
            _, public_type, _, invalid_signature = _crypto()
            try:
                public_type.from_public_bytes(public_key).verify(signature, _signed_bytes(bundle, envelope))
            except invalid_signature as exc:
                raise ValueError("Ed25519 signature does not verify") from exc
            signature_valid = True
            if trusted_keys is not None:
                trusted_key = trusted_keys.get(signing_key_id)
                issuer_trusted = type(trusted_key) is bytes and trusted_key == public_key
                if not issuer_trusted:
                    error("issuer_untrusted", "Signing key is absent from the caller's trusted keys")
        except (ValueError, TypeError, KeyError, RuntimeError, RecursionError, OverflowError) as exc:
            error("signature_invalid", exc)
    obj = checked["source"]["object"] if checked else None
    manifest = checked["manifest"] if checked else None

    def expectation(expected: Any, actual: Any, code: str) -> bool | None:
        if expected is None:
            return None
        result = checked is not None and type(expected) is str and expected == actual
        if not result:
            error(code, "Caller expectation does not match the verified source")
        return result

    object_matches = expectation(expected_object_id, obj["object_id"] if obj else None, "object_mismatch")
    version_current = expectation(expected_version, obj["version"] if obj else None, "stale_version")
    source_matches = expectation(expected_source_digest, manifest["source_digest"] if manifest else None, "source_digest_mismatch")
    report = {"schema": REPORT_SCHEMA, "verification_id": new_identity("verification"),
              "bundle_id": bundle.get("bundle_id") if type(bundle) is dict and type(bundle.get("bundle_id")) is str and _HASH.fullmatch(bundle["bundle_id"]) else None,
              "verified_bundle_digest": content_identity(checked) if checked else None,
              "content_intact": content_intact, "artifact_status": artifact_status,
              "signature_valid": signature_valid, "issuer_trusted": issuer_trusted, "signing_key_id": signing_key_id,
              "object_matches": object_matches, "version_current": version_current, "source_matches": source_matches,
              "expected": {"object_id": expected_object_id, "version": expected_version, "source_digest": expected_source_digest},
              "physical_validation_status": "not_assessed",
              "declared_qualification": deepcopy(checked["source"]["qualification"]) if checked else None,
              "canonical_admission": False, "errors": errors}
    report["report_id"] = content_identity(report)
    return report
