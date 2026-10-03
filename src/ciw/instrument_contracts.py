"""Ingest portable Notation Systems instrument manifests as unbound providers.

The manifest and verification files are descriptive/evidentiary data. They can
advertise an operation and semantic lowering, but they cannot load code, select
a binary, bind an Operation, admit state, or authorize execution.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from .adapters.protocol import InstrumentManifest
from .control_contracts import detached, keys, text
from .control_plane import CapabilityRegistry, Port
from .core.identities import content_identity
from .operations.registry import valid_operation_id
from .semantic_capabilities import EngineLowering, SemanticMorphism, SemanticRegistry

MAX_DOCUMENT = 1024 * 1024
MATURITY = {"EXPERIMENT", "REFERENCE", "INSTRUMENT", "RELEASE"}


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("Duplicate JSON key in instrument document")
        value[key] = item
    return value


def load_document(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Instrument document must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT + 1)
    if not 0 < len(raw) <= MAX_DOCUMENT:
        raise ValueError("Instrument document exceeds 1 MiB")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if type(value) is not dict:
        raise ValueError("Instrument document must be a JSON object")
    return detached(value)


def _bounded_strings(values, maximum, label):
    if type(values) is not list or len(values) > maximum:
        raise ValueError(f"{label} must be a bounded list")
    result = []
    for value in values:
        result.append(text(value))
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def validate_manifest(value: dict) -> dict:
    keys(value, {"schema", "identity", "operation", "provider", "implementation",
                 "model", "inputs", "outputs", "verification",
                 "representations", "limits"})
    if value["schema"] != "notations.instrument.v1":
        raise ValueError("Unsupported portable instrument schema")

    identity = value["identity"]
    keys(identity, {"name", "slug", "version", "maturity", "brand", "positioning"})
    for name in ("name", "slug", "version", "brand", "positioning"):
        text(identity[name])
    if identity["maturity"] not in MATURITY:
        raise ValueError("Unknown instrument maturity")

    operation = value["operation"]
    keys(operation, {"id", "semantic_capability", "purpose",
                     "deterministic_given_inputs", "kind", "effects"})
    if not valid_operation_id(operation["id"]):
        raise ValueError("Instrument operation ID is invalid")
    text(operation["semantic_capability"])
    text(operation["purpose"])
    if type(operation["deterministic_given_inputs"]) is not bool:
        raise ValueError("determinism declaration must be boolean")
    if operation["kind"] not in {"compute", "representation"}:
        raise ValueError("Unsupported semantic operation kind")
    effects = _bounded_strings(operation["effects"], 16, "effects")

    provider = value["provider"]
    keys(provider, {"id", "runtime_family", "execution_profile", "execution_mode",
                    "resources", "priority", "ports"})
    for name in ("id", "runtime_family", "execution_profile", "execution_mode"):
        text(provider[name])
    resources = _bounded_strings(provider["resources"], 16, "resources")
    if type(provider["priority"]) is not int or not 0 <= provider["priority"] <= 10000:
        raise ValueError("provider priority must be an integer in 0..10000")
    ports = provider["ports"]
    keys(ports, {"inputs", "outputs"})
    if type(ports["inputs"]) is not dict or type(ports["outputs"]) is not dict or not ports["outputs"]:
        raise ValueError("portable provider requires typed input/output maps")
    typed_inputs = {}
    typed_outputs = {}
    for name, port in ports["inputs"].items():
        text(name)
        typed_inputs[name] = Port.from_dict(port).to_dict()
    for name, port in ports["outputs"].items():
        text(name)
        typed_outputs[name] = Port.from_dict(port).to_dict()

    # Validate semantic/runtime routing using the same objects used by the
    # semantic plane. This is still only data; no concrete binding occurs.
    SemanticMorphism(
        operation["semantic_capability"], operation["kind"],
        typed_inputs, typed_outputs, tuple(effects), operation["purpose"],
    ).to_dict()
    EngineLowering(
        operation["semantic_capability"], operation["id"], provider["id"],
        provider["runtime_family"], provider["execution_profile"],
        provider["execution_mode"], tuple(resources), provider["priority"],
    ).to_dict()

    implementation = value["implementation"]
    if type(implementation) is not dict:
        raise ValueError("implementation must be an object")
    for required in ("language", "runtime", "network_required", "hardware_required"):
        if required not in implementation:
            raise ValueError("implementation is missing required runtime metadata")
    text(implementation["language"])
    text(implementation["runtime"])
    if type(implementation["network_required"]) is not bool or type(implementation["hardware_required"]) is not bool:
        raise ValueError("implementation network/hardware facts must be boolean")
    detached(implementation)

    for name in ("model", "inputs", "outputs", "verification", "representations"):
        if type(value[name]) is not dict:
            raise ValueError(f"{name} must be an object")
        detached(value[name])
    _bounded_strings(value["limits"], 64, "limits")
    return detached(value)


def validate_verification(value: dict, instrument: dict) -> dict:
    if type(value) is not dict or value.get("schema") != "notations.verification.v1":
        raise ValueError("Unsupported verification report")
    required = {"instrument", "operation_id", "source_revision", "claims", "not_claimed"}
    if not required <= set(value):
        raise ValueError("Verification report is missing core identity/evidence fields")
    if content_identity(value["instrument"]) != content_identity(instrument["identity"]):
        raise ValueError("Verification report names a different instrument identity")
    if value["operation_id"] != instrument["operation"]["id"]:
        raise ValueError("Verification report operation differs from manifest")
    text(value["source_revision"])
    if value["source_revision"] == "unavailable":
        raise ValueError("Verified instrument requires an explicit source revision")
    _bounded_strings(value["claims"], 128, "verification claims")
    _bounded_strings(value["not_claimed"], 128, "verification exclusions")
    if "junit" in value:
        junit = value["junit"]
        keys(junit, {"tests", "failures", "errors", "skipped"})
        for name in ("tests", "failures", "errors", "skipped"):
            if type(junit[name]) is not int or junit[name] < 0:
                raise ValueError("JUnit verification counts must be nonnegative integers")
        if junit["tests"] < 1 or any(junit[name] for name in ("failures", "errors", "skipped")):
            raise ValueError("Verification JUnit must contain successful unskipped tests")
    detached(value)
    return detached(value)


def advertise_instrument(manifest: dict, verification: dict,
                         concrete: CapabilityRegistry,
                         semantic: SemanticRegistry) -> dict:
    """Advertise one verified external instrument without binding executable code."""
    manifest = validate_manifest(manifest)
    verification = validate_verification(verification, manifest)
    identity = manifest["identity"]
    operation = manifest["operation"]
    provider = manifest["provider"]
    ports = provider["ports"]

    runtime = {
        "provider": provider["id"],
        "version": identity["version"],
        "manifest_sha256": content_identity(manifest),
        "verification_sha256": content_identity(verification),
        "source_revision": verification["source_revision"],
        "execution_authority": "not_bound",
    }
    ciw_manifest = InstrumentManifest(
        instrument_id=provider["id"],
        version=identity["version"],
        role="operation_provider",
        inputs=tuple(port["schema"] for port in ports["inputs"].values()),
        outputs=tuple(port["schema"] for port in ports["outputs"].values()),
        units={},
        frames=(),
        sampling={"mode": "portable_instrument_contract"},
        normalization={"state": "provider_owned"},
        supported_operations=(operation["id"],),
        determinism={"declared_given_inputs": operation["deterministic_given_inputs"]},
        tolerance_policy={"policy": "verification_report_external"},
        calibration_requirements={"status": "instrument_specific"},
    )
    concrete.advertise(
        ciw_manifest,
        runtime=runtime,
        capabilities={operation["id"]: [operation["semantic_capability"]]},
        inputs={operation["id"]: deepcopy(ports["inputs"])},
        outputs={operation["id"]: {
            name: {"type": deepcopy(port), "path": []}
            for name, port in ports["outputs"].items()
        }},
    )

    semantic.declare(SemanticMorphism(
        operation["semantic_capability"], operation["kind"],
        deepcopy(ports["inputs"]), deepcopy(ports["outputs"]),
        tuple(operation["effects"]), operation["purpose"],
    ))
    semantic.implement(EngineLowering(
        operation["semantic_capability"], operation["id"], provider["id"],
        provider["runtime_family"], provider["execution_profile"],
        provider["execution_mode"], tuple(provider["resources"]), provider["priority"],
    ))
    return {
        "schema": "ciw.portable-instrument-ingest.v1",
        "instrument": deepcopy(identity),
        "provider_id": provider["id"],
        "operation_id": operation["id"],
        "semantic_capability": operation["semantic_capability"],
        "manifest_sha256": runtime["manifest_sha256"],
        "verification_sha256": runtime["verification_sha256"],
        "source_revision": verification["source_revision"],
        "verification_status": "checked",
        "provider_status": "advertised_unbound",
        "authorizes_execution": False,
        "authorizes_state_admission": False,
        "authorizes_release": False,
    }


def ingest_files(manifest_path: Path, verification_path: Path) -> dict:
    concrete = CapabilityRegistry()
    semantic = SemanticRegistry(concrete)
    descriptor = advertise_instrument(
        load_document(manifest_path), load_document(verification_path),
        concrete, semantic)
    return {
        "schema": "ciw.portable-instrument-view.v1",
        "descriptor": descriptor,
        "provider_catalog": concrete.catalog(),
        "semantic_catalog": semantic.catalog(),
    }
