"""Actual reference campaigns, existing Session receipts, and inert rendering."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.control_contracts import MAX_BYTES, bytes_ref, load, save_new
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.session import Session
from ciw.simulation_campaign import (
    plan, read_campaign, reference_demo, run_campaign, validate_campaign, validate_plan,
)
from ciw.simulation_campaign_view import render_campaign, save_view
from ciw.simulation_cli import main
from ciw.simulation_control import SimulationControl, completed, open_workspace
from ciw.simulation_records import observer
from ciw.simulation_reference import PROVIDER_ID, ReferenceMotion


@pytest.fixture(scope="module")
def campaign(tmp_path_factory):
    directory = tmp_path_factory.mktemp("campaign") / "actual"
    reference_demo(directory)
    return directory, read_campaign(directory / "campaign.json")


@pytest.fixture
def lab(tmp_path):
    session = Session(make_demo_run(), tmp_path / "session")
    control = SimulationControl(session)
    source = control.attach(ReferenceMotion(), provider_id=PROVIDER_ID, experiment_id="source")
    completed(source.command("start"))
    completed(source.command("pause"))
    checkpoint = completed(source.command("checkpoint"))
    declared = plan(checkpoint, campaign_id="test", variants=[
        {"variant_id": "baseline", "interventions": []},
        {"variant_id": "replicate", "interventions": []}], steps=1, dt=1,
        observer=observer("position", kind="debugger", channels=["position"]), quantity="position", atol=0)
    return session, control, source, checkpoint, declared


def test_actual_campaign_retains_all_occurrences_and_baseline_direction(campaign):
    directory, report = campaign
    assert report["summary"] == {"status": "completed", "variant_count": 4, "execution_count": 39,
        "comparison_counts": {"PASS": 0, "FAIL": 3, "INDETERMINATE": 0}, "ranking": "not_performed"}
    assert [c["comparison"]["outcome"]["metrics"]["max_abs_error"] for c in report["comparisons"]] == [8, 8, 16]
    baseline = next(r for r in report["cases"][0]["results"] if r["parameters"]["action"] == "observe")
    for comparison in report["comparisons"]:
        assert all(s["identity"]["execution_id"] == baseline["execution_id"] for s in comparison["comparison"]["right"])
    reopened = open_workspace(directory / "workspace.json", output_dir=directory / "reader")
    assert len(reopened.executions) == len(reopened.results) == 44
    for case in report["cases"]:
        assert case["results"][-1]["data"]["after"]["status"] == "stopped"
        for result in case["results"]:
            assert reopened.results[result["result_id"]] == result
    assert report["verification_id"] is None and report["verification_status"] == "not_verified"


@pytest.mark.parametrize("change", [
    "zero_steps", "many_steps", "bool_steps", "zero_dt", "infinite_dt", "bool_dt", "one_variant",
    "many_variants", "duplicate_id", "changed_baseline", "wrong_checkpoint", "negative_atol",
    "bool_rtol", "wrong_channel", "extra_field", "nonversioned_operation", "many_interventions",
])
def test_invalid_plan_never_calls_provider_factory(lab, change):
    session, control, source, checkpoint, declared = lab
    impulse = {"actor_id": "operator", "operation": "motion.queue-impulse.v1", "target": "body-1",
               "parameters": {"at_tick": 1, "delta_v": 2}}
    if change == "zero_steps": declared["steps"] = 0
    elif change == "many_steps": declared["steps"] = 33
    elif change == "bool_steps": declared["steps"] = True
    elif change == "zero_dt": declared["dt"] = 0
    elif change == "infinite_dt": declared["dt"] = float("inf")
    elif change == "bool_dt": declared["dt"] = True
    elif change == "one_variant": declared["variants"].pop()
    elif change == "many_variants": declared["variants"] *= 9
    elif change == "duplicate_id": declared["variants"][1]["variant_id"] = "baseline"
    elif change == "changed_baseline": declared["variants"][0]["interventions"] = [impulse]
    elif change == "wrong_checkpoint": declared["checkpoint_result_ref"] = "sha256:" + "0" * 64
    elif change == "negative_atol": declared["policy"]["atol"] = -1
    elif change == "bool_rtol": declared["policy"]["rtol"] = False
    elif change == "wrong_channel": declared["quantity"] = "velocity"
    elif change == "extra_field": declared["code"] = "execute-me"
    elif change == "nonversioned_operation":
        impulse["operation"] = "not versioned"
        declared["variants"][1]["interventions"] = [impulse]
    else: declared["variants"][1]["interventions"] = [impulse] * 17
    if change != "infinite_dt": seal(declared)
    before = source.inspect()
    with patch("ciw.simulation_reference.ReferenceMotion", side_effect=AssertionError("must not execute")) as factory:
        with pytest.raises((ValueError, TypeError)):
            run_campaign(control, checkpoint, declared, factory)
        factory.assert_not_called()
    assert len(session.executions) == 3 and source.inspect() == before


def test_replicates_preserve_parent_and_create_new_occurrences(lab):
    session, control, source, checkpoint, declared = lab
    before = source.inspect()
    report = run_campaign(control, checkpoint, declared, ReferenceMotion)
    assert report["summary"]["comparison_counts"]["PASS"] == 1
    assert source.inspect() == before
    assert len({c["results"][0]["data"]["after"]["provider"]["owner_id"] for c in report["cases"]}) == 2
    assert report["cases"][0]["results"][0]["execution_id"] != report["cases"][1]["results"][0]["execution_id"]
    assert len(session.executions) == 15


def test_missing_observations_are_indeterminate_not_pass(lab):
    _, control, _, checkpoint, declared = lab
    declared["observer"] = observer("delayed", kind="embodied_agent", channels=["position"])
    seal(declared)
    report = run_campaign(control, checkpoint, declared, ReferenceMotion)
    assert report["summary"]["comparison_counts"]["INDETERMINATE"] == 1
    assert report["comparisons"][0]["comparison"]["outcome"]["reason"] == "missing_evidence"
    assert "No samples available" in render_campaign(report)


def test_refused_variant_stops_campaign_and_retains_prefix(lab, tmp_path):
    session, control, source, checkpoint, declared = lab
    declared["variants"][1]["interventions"] = [{"actor_id": "operator", "operation": "motion.unsupported.v1",
        "target": "body-1", "parameters": {}}]
    seal(declared)
    before = source.inspect()
    with pytest.raises(ValueError, match="did not complete"):
        run_campaign(control, checkpoint, declared, ReferenceMotion)
    assert source.inspect() == before
    failures = [e for e in session.executions.values() if e["status"] == "refused"]
    assert len(failures) == 1 and failures[0]["result_id"] is None
    assert all(i._provider.status == "stopped" for i in control._instances.values() if i is not source)
    path = tmp_path / "failed-workspace.json"
    session.save_workspace(path)
    reopened = open_workspace(path, output_dir=tmp_path / "failed-reader")
    assert failures[0]["execution_id"] in reopened.executions


def test_factory_cannot_return_parent(lab):
    _, control, source, checkpoint, declared = lab
    before = source.inspect()
    with pytest.raises(ValueError, match="fresh"):
        run_campaign(control, checkpoint, declared, lambda: source._provider)
    assert source.inspect() == before and source._provider.status == "paused"


def test_factory_mutation_cannot_rewrite_frozen_plan(lab):
    _, control, _, checkpoint, declared = lab
    original = deepcopy(declared)
    def factory():
        declared["steps"] = 30
        return ReferenceMotion()
    report = run_campaign(control, checkpoint, declared, factory)
    assert report["plan"] == original


@pytest.mark.parametrize("change", ["summary", "authority", "comparison", "missing_case", "case_order",
    "command_order", "occurrence", "different_plan", "runtime", "source_ref"])
def test_resealed_reports_cannot_change_evidence_meaning(campaign, change):
    _, original = campaign
    report = deepcopy(original)
    if change == "summary": report["summary"]["status"] = "verified"
    elif change == "authority": report["verification_status"] = "verified"
    elif change == "comparison": report["comparisons"][0]["comparison"]["outcome"]["status"] = "PASS"
    elif change == "missing_case": report["cases"].pop()
    elif change == "case_order": report["cases"].reverse()
    elif change == "command_order": report["cases"][0]["results"][1:3] = report["cases"][0]["results"][2:0:-1]
    elif change == "occurrence":
        result = report["cases"][1]["results"][0]
        result["execution_id"] = report["cases"][0]["results"][0]["execution_id"]
        seal(result)
    elif change == "different_plan": report["plan"]["steps"] += 1; seal(report["plan"])
    elif change == "runtime":
        result = report["cases"][1]["results"][0]
        result["runtime"]["implementation_sha256"] = "sha256:" + "0" * 64
        seal(result)
    else: report["plan"]["checkpoint_result_ref"] = "sha256:" + "0" * 64; seal(report["plan"])
    seal(report)
    with pytest.raises(ValueError): validate_campaign(report)


def test_readers_and_rendering_are_provider_free(campaign, tmp_path):
    directory, report = campaign
    path = directory / "campaign.json"
    digest = bytes_ref(path.read_bytes())
    with patch.object(ReferenceMotion, "__init__", side_effect=AssertionError("no provider")), \
         patch.object(SimulationControl, "__init__", side_effect=AssertionError("no controller")):
        assert read_campaign(path, expected_sha256=digest) == report
        assert main(["campaign-check", str(path), "--expected-sha256", digest]) == 0
        assert main(["campaign-view", str(path), "--expected-sha256", digest, "--output", str(tmp_path / "view.html")]) == 0
    html = (tmp_path / "view.html").read_text()
    assert html == render_campaign(report)
    for forbidden in ("snapshot_b64", "configuration_ref", "delta_v", "<script", "<iframe", "<img"):
        assert forbidden not in html
    for case in report["cases"]:
        assert case["results"][0]["data"]["request"]["arguments"]["snapshot_b64"] not in html
    assert "script-src 'none'" in html and 'default-src \'none\'' in html


def test_external_digest_and_create_only_outputs(campaign, tmp_path):
    directory, report = campaign
    wrong = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="digest mismatch"):
        read_campaign(directory / "campaign.json", expected_sha256=wrong)
    target = tmp_path / "occupied.html"
    target.write_text("keep")
    with pytest.raises(FileExistsError): save_view(report, target)
    assert target.read_text() == "keep"
    with pytest.raises(FileExistsError): reference_demo(directory)


def test_bounded_reader_rejects_huge_and_duplicate_key_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b" " * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="8 MiB"): read_campaign(path)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(ValueError): read_campaign(path)


def test_html_escapes_labels_without_loading_embedded_code(lab):
    _, control, _, checkpoint, declared = lab
    declared["campaign_id"] = '</h1><script>alert("x")</script>'
    declared["variants"][1]["variant_id"] = '<img src="https://evil.example">'
    seal(declared)
    report = run_campaign(control, checkpoint, declared, ReferenceMotion)
    html = render_campaign(report)
    assert '<script>' not in html and '<img' not in html
    assert '&lt;script&gt;' in html and '&lt;img' in html


def test_visual_handles_scalar_missing_and_vector_without_imputation():
    from ciw.simulation_campaign_view import _plot
    from ciw.control_contracts import observation
    base = dict(identity={"model_id": "m", "entity_id": "e", "execution_id": None},
        clock={"id": "clock", "time_s": 0}, frame="world", quantity="q", unit="m",
        provenance={"provider": "p", "sources": ["sha256:" + "0" * 64], "semantics": "simulated"})
    assert "All samples are missing" in _plot([observation(**base, value=None)])
    assert "Vector values" in _plot([observation(**base, value=[1, 2])])
    assert _plot([observation(**base, value=1)]).count('<circle') == 1


def test_saved_plan_executes_fresh_reference_campaign(campaign, tmp_path):
    from ciw.simulation_campaign import run_reference
    directory, original = campaign
    summary = run_reference(directory / "workspace.json", directory / "plan.json", tmp_path / "fresh")
    assert summary == original["summary"]
    fresh = read_campaign(tmp_path / "fresh/campaign.json")
    assert fresh["plan"] == original["plan"]
    assert fresh["cases"][0]["results"][0]["execution_id"] != original["cases"][0]["results"][0]["execution_id"]
    assert original == read_campaign(directory / "campaign.json")


def test_reference_run_saves_failure_without_completed_report(campaign, tmp_path):
    from ciw.simulation_campaign import run_reference
    directory, original = campaign
    declared = deepcopy(original["plan"])
    declared["checkpoint_result_ref"] = "sha256:" + "0" * 64
    seal(declared)
    plan_file = tmp_path / "wrong-plan.json"
    save_new(plan_file, declared)
    with pytest.raises(ValueError, match="exactly one"):
        run_reference(directory / "workspace.json", plan_file, tmp_path / "failure")
    assert (tmp_path / "failure/workspace.json").is_file()
    assert not (tmp_path / "failure/campaign.json").exists()
