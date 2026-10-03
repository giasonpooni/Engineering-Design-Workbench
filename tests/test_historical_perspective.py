"""Synthetic authoring contracts; no historical, native-game or model qualification."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from ciw import historical_perspective as h
from ciw import perspective_workflow as w
from ciw.control_contracts import load, save_new
from ciw.core.identities import content_identity
from ciw.operations.runner import seal


def test_example_audit_preserves_expected_failures():
    result = h.audit(h.example())
    assert [c["status"] for c in result["checks"]] == ["FAIL", "PASS", "INDETERMINATE", "PASS", "FAIL", "PASS", "PASS"]
    assert result["status"] == "FAIL"
    assert result["verification_id"] is None
    assert result["historical_authentication"] == "not_performed"
    assert result["dialogue_semantics_checked"] is False


def test_three_actors_have_distinct_received_information():
    scenario = h.example()
    views = {a: h.compile_actor(scenario, a, 4) for a in scenario["actors"]}
    route = lambda a: next(b for b in views[a]["beliefs"] if b["proposition"] == "route_open" and b["about_actor"] is None)
    assert route("scout")["status"] == "supports"
    assert route("quartermaster")["status"] == "opposes"
    assert route("commander")["receipts"][0]["id"] == "scout-report"
    assert len({content_identity(v) for v in views.values()}) == 3


def test_before_arrival_unknown_is_absence_not_false():
    view = h.compile_actor(h.example(), "commander", 3)
    assert all(b["proposition"] != "route_open" for b in view["beliefs"])


def test_receipt_available_at_exact_boundary():
    assert any(b["proposition"] == "route_open" for b in h.compile_actor(h.example(), "commander", 4)["beliefs"])


def test_conflicts_retained_not_majority_voted():
    scenario = h.example()
    duplicate = deepcopy(scenario["observations"][2]); duplicate["id"] = "second-scout-report"
    scenario["observations"].append(duplicate)
    route = next(b for b in h.compile_actor(scenario, "commander", 6)["beliefs"] if b["proposition"] == "route_open" and b["about_actor"] is None)
    assert route["status"] == "conflicted" and len(route["receipts"]) == 3
    result = h.audit(scenario)
    assert result["checks"][1]["distinct_origin_count"] == 1
    assert len(result["checks"][1]["receipt_ids"]) == 2


def test_world_truth_is_not_a_belief_fallback_or_export_field():
    scenario = h.example()
    original = h.compile_actor(scenario, "commander", 6)
    for p in scenario["propositions"]:
        p["world_truth"] = False
    assert h.compile_actor(scenario, "commander", 6) == original
    encoded = json.dumps(original)
    for secret in ("world_truth", "private_fact", "Operator-only", "classification", "fixture:three-perspectives"):
        assert secret not in encoded


def test_explicit_attribution_is_not_target_private_state():
    view = h.compile_actor(h.example(), "commander", 5)
    attributed = next(b for b in view["beliefs"] if b["about_actor"] == "quartermaster")
    assert attributed["status"] == "supports"
    actual = h.compile_actor(h.example(), "quartermaster", 5)
    assert actual["beliefs"][0]["status"] == "opposes"
    assert all(b["about_actor"] is None for b in h.compile_actor(h.example(), "commander", 4)["beliefs"])


def test_undelivered_message_grants_no_knowledge():
    scenario = h.example(); scenario["observations"][2]["received_tick"] = None
    assert all(b["proposition"] != "route_open" or b["about_actor"] is not None
               for b in h.compile_actor(scenario, "commander", 5)["beliefs"])


def test_forecast_allowed_but_not_promoted_to_observed_fact():
    result = h.audit(h.example())
    assert result["checks"][4]["reason"] == "no_available_matching_observation"
    assert result["checks"][5]["status"] == "PASS"


def test_unannotated_dialogue_and_empty_scene_are_indeterminate():
    scenario = h.example()
    scenario["statements"] = [{"id": "unannotated", "actor": "commander", "tick": 0, "text": "He knows the future.", "claim": None}]
    assert h.audit(scenario)["checks"][0]["reason"] == "unannotated_text"
    assert h.audit(scenario)["status"] == "INDETERMINATE"
    scenario["statements"] = []
    assert h.audit(scenario)["status"] == "INDETERMINATE"


def test_evidence_reclassification_does_not_authenticate_fiction():
    scenario = h.example(); scenario["statements"] = [scenario["statements"][1]]
    scenario["statements"][0]["claim"]["evidence_class"] = "attested"
    assert h.audit(scenario)["checks"][0]["reason"] == "unsupported_evidence_reclassification"


def test_authored_attestation_remains_unverified_declaration():
    scenario = h.example(); scenario["source_class"] = "authored_reconstruction"
    scenario["evidence"][0]["classification"] = "attested"
    scenario["statements"] = [scenario["statements"][1]]
    scenario["statements"][0]["claim"]["evidence_class"] = "attested"
    result = h.audit(scenario)
    assert result["status"] == "PASS" and result["historical_authentication"] == "not_performed"


def test_input_and_output_mutations_are_detached():
    scenario = h.example(); baseline = deepcopy(scenario)
    view = h.compile_actor(scenario, "commander", 6)
    view["beliefs"][0]["receipts"][0]["id"] = "changed"
    h.audit(scenario)
    assert scenario == baseline
    validated = h.validate(scenario); validated["actors"].append("intruder")
    assert scenario == baseline


def test_input_order_is_not_causal_order():
    scenario = h.example(); original = h.compile_actor(scenario, "commander", 6)
    scenario["observations"].reverse(); scenario["propositions"].reverse()
    assert h.compile_actor(scenario, "commander", 6) == original


@pytest.mark.parametrize("change", ["duplicate_actor", "duplicate_prop", "duplicate_source", "duplicate_observation",
    "duplicate_statement", "unknown_actor", "unknown_prop", "unknown_source", "missing_parent", "early_arrival",
    "unreceived_parent", "wrong_sender", "changed_relay", "cycle", "extra_field", "bool_tick", "negative_tick",
    "calendar_guess", "synthetic_attestation", "nonboolean_truth", "too_many_actors", "byte_budget", "deep_attribution"])
def test_invalid_declarations_refuse(change):
    s = h.example()
    if change == "duplicate_actor": s["actors"].append(s["actors"][0])
    elif change == "duplicate_prop": s["propositions"].append(s["propositions"][0])
    elif change == "duplicate_source": s["evidence"].append(s["evidence"][0])
    elif change == "duplicate_observation": s["observations"].append(s["observations"][0])
    elif change == "duplicate_statement": s["statements"].append(s["statements"][0])
    elif change == "unknown_actor": s["observations"][2]["recipient"] = "intruder"
    elif change == "unknown_prop": s["observations"][0]["proposition"] = "unknown"
    elif change == "unknown_source": s["observations"][0]["evidence_id"] = "unknown"
    elif change == "missing_parent": s["observations"][2]["parent"] = "unknown"
    elif change == "early_arrival": s["observations"][2]["received_tick"] = 3
    elif change == "unreceived_parent": s["observations"][2]["received_tick"] = None; s["observations"][3]["parent"] = "scout-report"
    elif change == "wrong_sender": s["observations"][2]["sender"] = "quartermaster"
    elif change == "changed_relay": s["observations"][2]["value"] = False
    elif change == "cycle": s["observations"][0]["parent"] = "scout-sees"
    elif change == "extra_field": s["execute"] = "shell"
    elif change == "bool_tick": s["observations"][0]["sent_tick"] = True
    elif change == "negative_tick": s["statements"][0]["tick"] = -1
    elif change == "calendar_guess": s["clock"]["historical_binding"] = "1792"
    elif change == "synthetic_attestation": s["evidence"][0]["classification"] = "attested"
    elif change == "nonboolean_truth": s["propositions"][0]["world_truth"] = 1
    elif change == "too_many_actors": s["actors"] = [str(i) for i in range(33)]
    elif change == "byte_budget": s["scenario_id"] = "x" * 65537
    elif change == "deep_attribution": s["observations"][0]["about_actor"] = {"actor": "commander", "belief": "nested"}
    with pytest.raises((ValueError, TypeError)):
        h.validate(s)


def test_catalog_uses_existing_registry_without_execution_grant():
    catalog = w.registry().catalog()
    assert catalog["authorizes_execution"] is False
    assert set(catalog["operations"]) == {w.ACTOR_OP, w.AUDIT_OP}
    assert all(not entry["bound"] for entry in catalog["operations"].values())


def test_original_session_retention_and_offline_read(tmp_path):
    root = tmp_path / "run"
    session = w.run_case(h.example(), root, at_tick=4)
    assert len(session.executions) == len(session.results) == 4
    assert len({r["execution_id"] for r in session.results.values()}) == 4
    assert all(r["verification_id"] is None for r in session.results.values())
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with patch.object(w, "registry", side_effect=AssertionError("Inspection must not bind")), patch("subprocess.Popen", side_effect=AssertionError("No process")):
        report = w.inspect(root / "workspace.json")
    assert report["runtime_executed"] is False
    assert {e["execution_id"] for e in report["executions"]} == set(session.executions)
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_export_selects_exact_actor_result_without_workspace(tmp_path):
    session = w.run_case(h.example(), tmp_path / "run", at_tick=4)
    result = next(r for r in session.results.values() if r["operation_id"] == w.ACTOR_OP and r["data"]["actor"] == "commander")
    target = tmp_path / "actor.json"
    receipt = w.export_actor(tmp_path / "run/workspace.json", result["result_id"], target)
    assert load(target) == result["data"]
    assert receipt["execution_id"] == result["execution_id"]
    assert "world_truth" not in target.read_text()
    with pytest.raises(FileExistsError):
        w.export_actor(tmp_path / "run/workspace.json", result["result_id"], target)
    audit = next(r for r in session.results.values() if r["operation_id"] == w.AUDIT_OP)
    with pytest.raises(ValueError):
        w.export_actor(tmp_path / "run/workspace.json", audit["result_id"], tmp_path / "bad.json")
    assert not (tmp_path / "bad.json").exists()


def test_invalid_source_and_existing_output_do_not_publish(tmp_path):
    source = h.example(); source["observations"][2]["received_tick"] = 0
    with pytest.raises(ValueError): w.run_case(source, tmp_path / "invalid", at_tick=4)
    assert not (tmp_path / "invalid").exists()
    w.run_case(h.example(), tmp_path / "existing", at_tick=4)
    before = (tmp_path / "existing/workspace.json").read_bytes()
    with pytest.raises(FileExistsError): w.run_case(h.example(), tmp_path / "existing", at_tick=4)
    assert (tmp_path / "existing/workspace.json").read_bytes() == before


def test_resealed_fabricated_result_fails_independent_recomputation(tmp_path):
    w.run_case(h.example(), tmp_path / "run", at_tick=4)
    workspace = load(tmp_path / "run/workspace.json")
    actor = next(r for r in workspace["results"] if r["operation_id"] == w.ACTOR_OP)
    actor["data"]["beliefs"] = []
    seal(actor)
    save_new(tmp_path / "tampered.json", workspace)
    with pytest.raises(ValueError): w.inspect(tmp_path / "tampered.json")


def test_runtime_source_binding_is_checked(tmp_path):
    session = w.run_case(h.example(), tmp_path / "run", at_tick=4)
    result = next(iter(session.results.values()))
    result["runtime"]["source_files"]["kernel"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="source binding"): w.validate_session(session)


@pytest.mark.parametrize("command,expected", [("demo", 0), ("run", 2)])
def test_cli_demo_and_generic_run_have_distinct_exit_semantics(tmp_path, capsys, command, expected):
    args = [command, "--output-dir", str(tmp_path / command)]
    if command == "run":
        save_new(tmp_path / "scenario.json", h.example())
        args += ["--scenario", str(tmp_path / "scenario.json")]
    assert w.main(args) == expected
    data = json.loads(capsys.readouterr().out)
    assert data.get("deliberate_failures_match_expected", False) == (command == "demo")


def test_cli_indeterminate_and_invalid_refusal(tmp_path, capsys):
    scenario = h.example(); scenario["statements"] = []
    save_new(tmp_path / "empty.json", scenario)
    assert w.main(["run", "--scenario", str(tmp_path / "empty.json"), "--output-dir", str(tmp_path / "empty")]) == 3
    capsys.readouterr()
    assert w.main(["demo", "--at-tick", "-1", "--output-dir", str(tmp_path / "invalid")]) == 1
    assert json.loads(capsys.readouterr().err)["status"] == "refused"
    assert not (tmp_path / "invalid").exists()


def test_net_cli_dispatch_and_example(tmp_path, capsys):
    from ciw.net import main
    assert main(["history", "catalog"]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == "ciw.provider-catalog.v1"
    assert main(["history", "example", "--output", str(tmp_path / "example.json")]) == 0
    assert load(tmp_path / "example.json") == h.example()
