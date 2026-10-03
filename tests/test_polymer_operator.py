"""Operator projections must preserve evidence, decisions and occurrence boundaries."""
import csv
import json
from copy import deepcopy
from pathlib import Path

import pytest

from ciw import polymer_operator as operator, polymer_workflow as workflow
from ciw.control_contracts import bytes_ref
from ciw.net import main
from ciw.polymer_contract import AUTHORITY, example_request


def files(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("process", ["injection_molding", "extrusion_blow_molding"])
def test_demo_exposes_distinct_decisions_and_traceable_sample_exports(tmp_path, process):
    directory = tmp_path / "demo"
    view = operator.demo(process, directory)
    assert view["workflow_status"] == view["numerical_audit_status"] == "PASS"
    assert view["part_conformity"] == "NONCONFORMING"
    assert view["copilot_context_status"] == "CONTEXT_READY"
    assert view["source_kind"] == "synthetic"
    assert view["authority"] == AUTHORITY
    request = json.loads((directory / "request.json").read_text())
    manifest = json.loads((directory / "report/manifest.json").read_text())
    for artifact in manifest["artifacts"]:
        assert bytes_ref((directory / "report" / artifact["path"]).read_bytes()) == artifact["sha256"]
    assert manifest["source_workspace_ref"] == bytes_ref((directory / "workspace.json").read_bytes())
    assert "does not encode joint covariance" in manifest["csv_limitations"]
    with (directory / "report/measurements.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == sum(len(s["samples"]) for s in request["sensors"])
    for sensor in request["sensors"]:
        projected = [r for r in rows if r["sensor_id"] == sensor["sensor_id"]]
        assert len(projected) == len(sensor["samples"])
        for row, sample in zip(projected, sensor["samples"]):
            assert float(row["time_s"]) == sample["time_s"]
            assert float(row["value"]) == sample["value"]
            assert float(row["standard_uncertainty"]) == sample["standard_uncertainty"]
            assert row["source_ref"] == sensor["source_ref"]
            assert row["unit"] == sensor["unit"]
        assert projected[-1]["is_latest_sample"] == "True"
    receipt = json.loads((directory / "fresh-verification.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["verification_id"] != view["verification_id"]
    before = files(directory)
    assert operator.summary(directory)["quantities"] == view["quantities"]
    operator.export(directory, tmp_path / "second-export")
    assert files(directory) == before


def test_summary_preserves_abstention_and_html_escapes_untrusted_identity(tmp_path):
    request = example_request()
    request["identity"]["cycle_id"] = "<script>alert(1)</script>"
    # A real missing required feature is visible as an indeterminate decision.
    next(s for s in request["sensors"] if s["quantity"] == "part_dimension")["samples"] = []
    directory = tmp_path / "cycle"
    workflow.run(request, directory)
    view = operator.summary(directory)
    assert view["workflow_status"] == "PASS"
    assert view["part_conformity"] == "INDETERMINATE"
    assert view["control_proposal_status"] == "ABSTAINED"
    assert view["copilot_context_status"] == "ABSTAIN"
    assert view["quantities"][0]["interval"] is None
    operator.export(directory, tmp_path / "report")
    html = (tmp_path / "report/report.html").read_text()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_export_and_audit_receipt_are_create_only_and_do_not_modify_source(tmp_path, capsys):
    directory = tmp_path / "cycle"
    workflow.run(example_request(), directory)
    before = files(directory)
    receipt = tmp_path / "audit.json"
    assert main(["polymer", "verify", str(directory), "--output", str(receipt)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert json.loads(receipt.read_text()) == printed
    retained = receipt.read_bytes()
    assert main(["polymer", "verify", str(directory), "--output", str(receipt)]) == 1
    assert json.loads(capsys.readouterr().err)["status"] == "REFUSE"
    assert receipt.read_bytes() == retained
    assert files(directory) == before
    report = tmp_path / "report"
    operator.export(directory, report)
    exported = files(report)
    with pytest.raises(FileExistsError):
        operator.export(directory, report)
    assert files(report) == exported


def test_doctor_never_executes_or_binds_providers(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Doctor executed a provider")
    for name in ("_assess", "_copilot", "_simulate", "_verify"):
        monkeypatch.setattr(workflow, name, forbidden)
    readiness = operator.doctor()
    assert readiness["status"] == "PASS"
    assert all(row["bound"] is False for row in readiness["operations"].values())
    assert readiness["operations"][workflow.VERIFY]["inputs"]["assessment"]["schema"] == "ciw.operation-result.v1"


def test_installed_tool_qualification_records_finite_scope_and_read_only_replay(tmp_path):
    destination = tmp_path / "qualification"
    report = operator.qualify(destination)
    assert report["status"] == "PASS"
    assert all(check["passed"] is True for check in report["checks"])
    assert "not_physical_validation" in report["scope"]
    assert json.loads((destination / "qualification.json").read_text()) == report
    before = files(destination)
    with pytest.raises(FileExistsError):
        operator.qualify(destination)
    assert files(destination) == before


def test_cli_summary_matches_retained_full_json_and_demo_is_compact(tmp_path, capsys):
    directory = tmp_path / "demo"
    assert main(["polymer", "demo", "--output-dir", str(directory)]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["schema"] == "ciw.polymer-operator-summary.v1"
    assert main(["polymer", "inspect", str(directory), "--summary"]) == 0
    compact = json.loads(capsys.readouterr().out)
    assert compact == operator.summary(directory)
    assert compact["part_conformity"] == view["part_conformity"]


def native_envelope():
    from ciw.polymer_ingress import make_envelope
    from ciw.telemetry import digest
    root = Path(__file__).resolve().parents[1] / "examples/polymer"
    native = json.loads((root / "native-dimension.bundle.json").read_text())
    template = json.loads((root / "native-dimension.template.json").read_text())
    return make_envelope(template, [native], [{"sensor_id": "sensor:level", "bundle_ref": digest(native),
        "quantity": "part_dimension", "modality": "vision_3d", "max_age_s": 2}])


def test_native_workflow_retains_full_lineage_and_export_replay_are_read_only(tmp_path, monkeypatch):
    from ciw import calibrated_window, polymer_ingress
    envelope = native_envelope()
    directory = tmp_path / "native"
    original = workflow.run(polymer_ingress.derive(envelope), directory, ingress=envelope)
    assert original["status"] == "PASS"
    assert original["assessment"]["engineering"]["cooling"]["status"] == "ABSTAINED"
    workspace = json.loads((directory / "workspace.json").read_text())
    assert workspace["run"]["metadata"]["polymer_ingress"] == envelope
    assert json.loads((directory / "ingress.json").read_text()) == envelope
    before = files(directory)
    replayed = workflow.replay(directory, tmp_path / "replay")
    assert replayed["evidence_id"] == original["evidence_id"]
    assert replayed["ingress_ref"] == original["ingress_ref"]
    assert set(o["execution_id"] for o in original["occurrences"]).isdisjoint(
        o["execution_id"] for o in replayed["occurrences"])
    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only view dispatched native or polymer science")
    for name in ("_assess", "_copilot", "_simulate", "_verify"):
        monkeypatch.setattr(workflow, name, forbidden)
    monkeypatch.setattr(calibrated_window, "_adapters", forbidden)
    monkeypatch.setattr(calibrated_window, "_invoke", forbidden)
    assert workflow.inspect(directory) == original
    operator.export(directory, tmp_path / "export")
    exported = json.loads((tmp_path / "export/ingress.json").read_text())
    assert exported == envelope
    assert files(directory) == before


@pytest.mark.parametrize("challenge", ["missing", "altered", "symlink"])
def test_native_sidecar_integrity_is_required_on_reopen(tmp_path, challenge):
    from ciw.polymer_ingress import derive
    envelope = native_envelope()
    directory = tmp_path / "native"
    workflow.run(derive(envelope), directory, ingress=envelope)
    sidecar = directory / "ingress.json"
    if challenge == "altered":
        value = json.loads(sidecar.read_text())
        value["derived_request"]["sensors"][0]["samples"][0]["value"] += 1
        sidecar.write_text(json.dumps(value))
    else:
        raw = sidecar.read_bytes()
        sidecar.unlink()
        if challenge == "symlink":
            (tmp_path / "elsewhere.json").write_bytes(raw)
            sidecar.symlink_to(tmp_path / "elsewhere.json")
    with pytest.raises(ValueError):
        workflow.inspect(directory)


def test_cli_prepares_and_runs_native_fixture_without_quantity_relabel(tmp_path, capsys):
    root = Path(__file__).resolve().parents[1] / "examples/polymer"
    envelope = tmp_path / "ingress.json"
    args = ["polymer", "prepare-ingress", str(root / "native-dimension.template.json"), "--bundle",
            str(root / "native-dimension.bundle.json"), "--sensor-id", "sensor:level", "--quantity",
            "part_dimension", "--modality", "vision_3d", "--max-age-s", "2", "--output", str(envelope)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "created"
    assert main(["polymer", "run-ingress", str(envelope), "--output-dir", str(tmp_path / "cycle"), "--summary"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["status"] == "PASS"
    assert view["cooling_status"] == "ABSTAINED"
    bad = args.copy()
    bad[bad.index("part_dimension")] = "wall_thickness"
    bad[-1] = str(tmp_path / "bad.json")
    assert main(bad) == 1
    assert json.loads(capsys.readouterr().err)["status"] == "REFUSE"
    assert not (tmp_path / "bad.json").exists()
