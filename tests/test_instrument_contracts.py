from copy import deepcopy
import json

import pytest

from ciw.control_plane import CapabilityRegistry
from ciw.instrument_contracts import advertise_instrument, ingest_files, validate_manifest, validate_verification
from ciw.operations.registry import Operation
from ciw.semantic_capabilities import SemanticRegistry


def manifest():
    return {
        "schema": "notations.instrument.v1",
        "identity": {
            "name": "FixtureSync", "slug": "fixturesync", "version": "0.1.0",
            "maturity": "INSTRUMENT", "brand": "Notation Systems",
            "positioning": "Frontier Tooling and Instrumentation for Digital Futures",
        },
        "operation": {
            "id": "fixture.time-sync.v1", "semantic_capability": "time.sync.v1",
            "purpose": "Fixture portable instrument.", "deterministic_given_inputs": True,
            "kind": "compute", "effects": ["read:timestamp", "write:derived-time"],
        },
        "provider": {
            "id": "org.notationsystems.fixturesync", "runtime_family": "python",
            "execution_profile": "scientific", "execution_mode": "headless",
            "resources": ["cpu"], "priority": 100,
            "ports": {
                "inputs": {"request": {"schema": "fixture.request.v1", "unit": None, "frame": None}},
                "outputs": {"result": {"schema": "fixture.result.v1", "unit": None, "frame": None}},
            },
        },
        "implementation": {
            "language": "Python", "runtime": "CPython 3.12",
            "distribution": "fixture", "module": "fixture", "command": "fixture",
            "network_required": False, "hardware_required": False,
        },
        "model": {"family": "fixture"},
        "inputs": {"request": "fixture request"},
        "outputs": {"result": "fixture result"},
        "verification": {"report_schema": "notations.verification.v1"},
        "representations": {"problem": "problem.md"},
        "limits": ["fixture only"],
    }


def verification():
    return {
        "schema": "notations.verification.v1",
        "instrument": deepcopy(manifest()["identity"]),
        "operation_id": "fixture.time-sync.v1",
        "source_revision": "abc123",
        "junit": {"tests": 12, "failures": 0, "errors": 0, "skipped": 0},
        "claims": ["fixture contracts passed"],
        "not_claimed": ["physical validation"],
    }


def test_portable_manifest_advertises_but_does_not_bind():
    concrete = CapabilityRegistry()
    semantic = SemanticRegistry(concrete)
    descriptor = advertise_instrument(manifest(), verification(), concrete, semantic)
    assert descriptor["provider_status"] == "advertised_unbound"
    catalog = concrete.catalog()
    row = catalog["operations"]["fixture.time-sync.v1"]
    assert row["bound"] is False
    assert row["runtime"]["verification_sha256"].startswith("sha256:")
    assert semantic.catalog()["lowerings"]["time.sync.v1"][0]["bound"] is False
    with pytest.raises(ValueError, match="No explicitly bound"):
        semantic.resolve("time.sync.v1", required_resources=["cpu"])


def test_explicit_trusted_binding_is_still_required_before_resolution():
    concrete = CapabilityRegistry()
    semantic = SemanticRegistry(concrete)
    advertise_instrument(manifest(), verification(), concrete, semantic)
    expected = concrete.contract("fixture.time-sync.v1")["runtime"]
    concrete.bind(Operation(
        "fixture.time-sync.v1", "analysis",
        lambda run, parameters: {"schema": "fixture.result.v1"},
        lambda: deepcopy(expected)))
    resolved = semantic.resolve("time.sync.v1", required_resources=["cpu"])
    assert resolved["engine_id"] == "org.notationsystems.fixturesync"
    assert resolved["agent_selected_engine"] is False


@pytest.mark.parametrize("fault", ["identity", "operation", "failed", "skipped", "unavailable"])
def test_verification_cannot_self_upgrade_or_drift(fault):
    m = manifest()
    v = verification()
    if fault == "identity":
        v["instrument"]["version"] = "9.9.9"
    elif fault == "operation":
        v["operation_id"] = "other.v1"
    elif fault == "failed":
        v["junit"]["failures"] = 1
    elif fault == "skipped":
        v["junit"]["skipped"] = 1
    else:
        v["source_revision"] = "unavailable"
    with pytest.raises(ValueError):
        validate_verification(v, m)


@pytest.mark.parametrize("fault", ["operation", "profile", "mode", "port", "maturity", "authority"])
def test_invalid_manifest_refuses(fault):
    value = manifest()
    if fault == "operation":
        value["operation"]["id"] = "not-versioned"
    elif fault == "profile":
        value["provider"]["execution_profile"] = "magic"
    elif fault == "mode":
        value["provider"]["execution_mode"] = "daemon"
    elif fault == "port":
        value["provider"]["ports"]["inputs"]["request"]["schema"] = ""
    elif fault == "maturity":
        value["identity"]["maturity"] = "BEST"
    else:
        value["provider"]["release_authority"] = True
    with pytest.raises(ValueError):
        validate_manifest(value)


def test_file_ingest_is_data_only(tmp_path):
    manifest_path = tmp_path / "instrument.json"
    verification_path = tmp_path / "verification.json"
    manifest_path.write_text(json.dumps(manifest()))
    verification_path.write_text(json.dumps(verification()))
    view = ingest_files(manifest_path, verification_path)
    assert view["descriptor"]["authorizes_execution"] is False
    assert view["descriptor"]["authorizes_state_admission"] is False
    assert view["descriptor"]["authorizes_release"] is False
    assert view["provider_catalog"]["operations"]["fixture.time-sync.v1"]["bound"] is False


def test_duplicate_json_key_refuses(tmp_path):
    manifest_path = tmp_path / "instrument.json"
    verification_path = tmp_path / "verification.json"
    manifest_path.write_text('{"schema":"notations.instrument.v1","schema":"duplicate"}')
    verification_path.write_text(json.dumps(verification()))
    with pytest.raises(ValueError, match="Duplicate"):
        ingest_files(manifest_path, verification_path)
