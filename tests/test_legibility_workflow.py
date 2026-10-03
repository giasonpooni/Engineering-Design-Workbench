"""End-to-end retention and adversarial inspection of legibility bundles."""

from copy import deepcopy
from html.parser import HTMLParser
import json

import pytest

from ciw.cli import main as ciw_main
from ciw.core.identities import content_identity
from ciw.instruments import make_demo_run
from ciw.legibility import compile_bundle, verify_bundle
from ciw.legibility_view import render_html
from ciw.legibility_workflow import OPERATION, compile_in_session, demo_source
from ciw.session import Session, read_json, write_json


OBJECT_ID = "notations:specimen:demo-coupon-001"


def request(session, kind, payload=None):
    return session.handle({"protocol_version": 1, "request_id": "legibility-workflow-test",
                           "type": kind, "payload": {} if payload is None else payload})


def response(session, kind, payload=None):
    reply = request(session, kind, payload)
    assert reply["type"] == "response", reply
    return reply["payload"]


def inspect(directory, capsys, *options):
    status = ciw_main(["legibility", "verify", str(directory), *map(str, options)])
    captured = capsys.readouterr()
    return status, json.loads(captured.out) if captured.out.strip() else None, captured.err


@pytest.fixture
def source(tmp_path):
    return demo_source(tmp_path / "source")


@pytest.fixture
def published(tmp_path, capsys):
    pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    directory = tmp_path / "published"
    assert ciw_main(["legibility", "demo", "--output-dir", str(directory)]) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["directory"] == str(directory)
    return directory


def test_signed_demo_cli_verifies_explicit_trust_freshness_and_all_exports(published, capsys):
    status, report, error = inspect(
        published, capsys, "--trust", published / "demo-trust.json",
        "--expected-object-id", OBJECT_ID, "--expected-version", "1",
    )
    assert status == 0 and not error
    assert report["content_intact"] is True
    assert report["signature_valid"] is True
    assert report["issuer_trusted"] is True
    assert report["object_matches"] is True
    assert report["version_current"] is True
    assert report["source_matches"] is None
    assert report["artifact_status"] == "verified"
    assert report["export_status"] == "verified"
    assert report["physical_validation_status"] == "not_assessed"
    assert report["canonical_admission"] is False
    assert report["errors"] == []
    bundle = read_json(published / "bundle.json")
    for name, view in bundle["representations"].items():
        assert read_json(published / (name + ".json")) == view
    assert read_json(published / "contract.json") == bundle["source"]
    binding = read_json(published / "compilation-binding.json")
    assert binding["source_bindings"] == bundle["source"]["bindings"]
    assert binding["compilation_operation_id"] == OPERATION
    assert binding["compilation_execution_id"] != binding["source_bindings"]["execution_id"]
    assert binding["canonical_admission"] is False


def test_demo_inspection_does_not_implicitly_trust_demo_key_or_assess_freshness(published, capsys):
    status, report, error = inspect(published, capsys)
    assert status == 0 and not error
    assert report["content_intact"] is True and report["signature_valid"] is True
    assert report["issuer_trusted"] is False
    assert report["version_current"] is None
    assert report["object_matches"] is None
    assert report["source_matches"] is None
    assert report["physical_validation_status"] == "not_assessed"
    assert report["canonical_admission"] is False


def test_cli_refuses_tampered_artifact_despite_valid_signature(published, capsys):
    artifact_map = read_json(published / "artifact-map.json")
    path = published / artifact_map["specimen-diagram"]
    path.write_bytes(path.read_bytes() + b"\n<!-- altered -->")
    status, report, _ = inspect(published, capsys, "--trust", published / "demo-trust.json")
    assert status == 2
    assert report["content_intact"] is True
    assert report["signature_valid"] is True
    assert report["artifact_status"] == "failed"
    assert any(item["code"] == "artifact_mismatch" for item in report["errors"])


def test_cli_refuses_tampered_standalone_reasoning_export(published, capsys):
    path = published / "reasoning.json"
    export = read_json(path)
    export["semantics"]["assumptions"].clear()
    write_json(path, export)
    status, report, _ = inspect(published, capsys, "--trust", published / "demo-trust.json")
    assert status == 2
    assert report["content_intact"] is True
    assert report["signature_valid"] is True
    assert report["artifact_status"] == "verified"
    assert report["export_status"] == "failed"
    assert any("export" in item["code"] for item in report["errors"])


def test_cli_refuses_stale_version_even_when_envelope_remains_valid(published, capsys):
    status, report, _ = inspect(
        published, capsys, "--trust", published / "demo-trust.json",
        "--expected-object-id", OBJECT_ID, "--expected-version", "2",
    )
    assert status == 2
    assert report["content_intact"] is True
    assert report["signature_valid"] is True
    assert report["issuer_trusted"] is True
    assert report["object_matches"] is True
    assert report["version_current"] is False
    assert any(item["code"] == "stale_version" for item in report["errors"])


def test_cli_refuses_artifact_map_path_outside_bundle(published, capsys):
    mapping = read_json(published / "artifact-map.json")
    mapping["specimen-diagram"] = "../outside.svg"
    write_json(published / "artifact-map.json", mapping)
    status, report, error = inspect(published, capsys)
    assert status == 2 and report is None
    assert "escapes the bundle directory" in error


def test_compile_session_restore_keeps_occurrences_without_scientific_replay(source, tmp_path, monkeypatch):
    run, contract, artifacts = source
    session = Session(run, tmp_path / "session")
    compiled = response(session, "operation.execute", {"operation_id": OPERATION,
                        "parameters": {"contract": contract}})
    assert compiled["status"] == "completed"
    result = compiled["result"]
    assert result["operation_id"] == OPERATION
    assert result["verification_id"] is None
    assert result["verification_status"] == "not_verified"
    assert result["execution_id"] != contract["bindings"]["execution_id"]
    assert result["data"] == compile_bundle(contract, artifacts)
    retained = deepcopy(session.results)
    retained_executions = deepcopy(session.executions)
    path = session.save_workspace(tmp_path / "workspace.json")

    def no_execution(*args, **kwargs):
        raise AssertionError("Restoring retained results must not dispatch scientific operations")

    from ciw.operations.registry import OperationRegistry
    import ciw.adapters.registry as adapters
    monkeypatch.setattr(OperationRegistry, "get", no_execution)
    monkeypatch.setattr(adapters, "default_registry", no_execution)
    restored = Session.from_workspace(path, tmp_path / "restored")
    assert restored.results == retained
    assert restored.executions == retained_executions
    assert restored.run == run
    report = verify_bundle(restored.results[result["result_id"]]["data"], artifacts=artifacts)
    assert report["content_intact"] is True
    assert report["verification_id"] != result["execution_id"]
    # Envelope verification is a separate occurrence and never edits protocol v1 results.
    assert restored.results[result["result_id"]]["verification_id"] is None


def test_legacy_result_verification_identity_stays_null_after_legibility_inspection(source, tmp_path, monkeypatch):
    session = Session(make_demo_run(), tmp_path / "legacy")
    legacy = response(session, "analysis.stats")
    assert legacy["verification_id"] is None
    assert legacy["verification_status"] == "not_verified"
    original = deepcopy(session.results)
    _, contract, artifacts = source
    report = verify_bundle(compile_bundle(contract), artifacts=artifacts)
    assert report["content_intact"] is True
    assert report["verification_id"] is not None
    assert session.results == original
    path = session.save_workspace(tmp_path / "legacy-workspace.json")

    def no_execution(*args, **kwargs):
        raise AssertionError("Restoring legacy results must not dispatch scientific operations")

    import ciw.adapters.registry as adapters
    monkeypatch.setattr(adapters, "default_registry", no_execution)
    restored = Session.from_workspace(path, tmp_path / "legacy-restored")
    assert restored.results == original
    assert restored.results[legacy["result_id"]]["verification_id"] is None


@pytest.mark.parametrize("mismatch", ["evidence", "frame"])
def test_compile_refuses_source_evidence_or_frame_mismatch(source, tmp_path, mismatch):
    run, contract, _ = source
    changed = deepcopy(contract)
    if mismatch == "evidence":
        changed["bindings"]["evidence_id"] = content_identity({"other": "evidence"})
    else:
        changed["semantics"]["coordinate_frame"] = "other.coordinate.frame.v1"
    destination = tmp_path / "refused"
    with pytest.raises(ValueError, match="evidence|frame"):
        compile_in_session(run, changed, destination)
    workspace = read_json(destination / "workspace.json")
    assert workspace["results"] == []
    assert len(workspace["executions"]) == 1
    assert workspace["executions"][0]["status"] == "refused"
    assert workspace["run"] == run


def test_mutating_caller_source_after_compilation_cannot_change_retained_payload(source, tmp_path):
    run, contract, artifacts = source
    original = deepcopy(contract)
    payload = compile_in_session(run, contract, tmp_path / "compiled")
    retained = deepcopy(payload)
    contract["semantics"]["properties"][0]["value"] = -999
    contract["semantics"]["assumptions"].clear()
    contract["bindings"]["evidence_id"] = content_identity({"altered": True})
    assert payload == retained
    assert payload["result"]["data"] == compile_bundle(original, artifacts)
    workspace = read_json(tmp_path / "compiled" / "workspace.json")
    assert workspace["results"][0]["data"] == compile_bundle(original)
    assert workspace["results"][0]["parameters"]["contract"] == original


class SurfaceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_html_escapes_supplied_values_and_cannot_load_remote_assets(source):
    _, contract, _ = source
    contract["object"]["label"] = '<img src="https://attacker.invalid/x" onerror="alert(1)">'
    contract["claims"][0]["statement"] += '</script><script>alert("claim")</script>'
    contract["semantics"]["assumptions"].append('<iframe src="https://attacker.invalid/y"></iframe>')
    contract["vision"]["annotations"][0]["annotation_id"] = '<svg onload="alert(2)">'
    bundle = compile_bundle(contract)
    html = render_html(bundle, verify_bundle(bundle))
    parser = SurfaceParser()
    parser.feed(html)
    assert not ({tag for tag, _ in parser.elements} & {"script", "img", "iframe", "object", "embed", "link", "svg"})
    assert not any(key in attrs for _, attrs in parser.elements for key in ("src", "href", "action", "onload", "onerror"))
    assert "&lt;img" in html and "&lt;script&gt;" in html and "&lt;iframe" in html
    assert "url(" not in html and "@import" not in html
    assert "default-src &#x27;none&#x27;" in html or "default-src 'none'" in html
    assert "Unsigned convenience rendering" in html
    assert "Artifact bytes not checked" in html
    assert "detector unevaluated" in html
    assert "Standard uncertainty not supplied" in html
    assert "Contains declared synthetic content" in html


def test_html_counts_only_failed_and_unresolved_and_preserves_declaration_priority(source):
    _, contract, _ = source
    contract["claims"] = [
        {"claim_id": "measured-id", "statement": "Measured declaration", "status": "measured", "evidence_refs": []},
        {"claim_id": "simulated-id", "statement": "Simulated declaration", "status": "simulated", "evidence_refs": []},
        {"claim_id": "assumed-id", "statement": "Assumed declaration", "status": "assumed", "evidence_refs": []},
        {"claim_id": "unresolved-id", "statement": "Unresolved declaration", "status": "unresolved", "evidence_refs": []},
        {"claim_id": "failed-id", "statement": "Failed declaration", "status": "failed", "evidence_refs": []},
    ]
    html = render_html(compile_bundle(contract))
    assert "1 failed · 1 unresolved claims" in html
    ordered = ["failed-id", "unresolved-id", "assumed-id", "simulated-id", "measured-id"]
    positions = [html.index("<code>" + identity + "</code>") for identity in ordered]
    assert positions == sorted(positions)
    assert '<span class="pill neutral">measured</span>' in html
    assert '<span class="pill neutral">simulated</span>' in html


@pytest.mark.parametrize("defect", ["other_bundle", "invalid_seal", "missing_seal", "altered_source", "altered_view"])
def test_html_never_promotes_checks_from_mismatched_or_unsealed_report(source, defect):
    _, contract, _ = source
    bundle = compile_bundle(contract)
    report = verify_bundle(bundle)
    report["signature_valid"] = True
    report["issuer_trusted"] = True
    report["version_current"] = True
    report["report_id"] = content_identity({key: value for key, value in report.items() if key != "report_id"})
    assert "Signature valid" in render_html(bundle, report)
    if defect == "other_bundle":
        changed = deepcopy(contract)
        changed["object"]["version"] = "2"
        bundle = compile_bundle(changed)
    elif defect == "invalid_seal":
        report["artifact_status"] = "verified"
    elif defect == "missing_seal":
        del report["report_id"]
    elif defect == "altered_source":
        bundle["source"]["object"]["label"] += " altered"
    else:
        bundle["representations"]["reasoning"]["semantics"]["assumptions"].clear()
    html = render_html(bundle, report)
    assert "Verification report mismatch" in html
    assert "Signature valid" not in html
    assert "Content intact" not in html
    assert "Issuer trusted" not in html
    assert "Version current" not in html
    assert html.count("Not assessed") >= 4
