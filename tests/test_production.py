"""Real NET Session/graph tests; Godot doubles here are explicitly non-native.

The separate production qualification script exercises an actual Godot process.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.control_contracts import bytes_ref, load, save_new
from ciw.control_plane import builtin_registry, experiment
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.production import (AUTHORITY, Gate, Worker, acceptance, inspect_production,
                            plan, preflight, run_production, validate_plan)
from ciw.production_gates import builtin_gates, game_gates
from ciw.production_workflow import builtin_plan, game_plan, game_registry, main
from test_game_session import FixtureBinding
from ciw import game_workflow as game


WORKERS = (Worker("local-analysis", ("statistics.v1", "spectrum.periodogram.v1")),)


@pytest.fixture
def setup_case():
    source = make_demo_run()
    return source, builtin_plan(source), builtin_registry(bind=True), builtin_gates()


def run(case, destination, **kwargs):
    source, specification, registry, gates = case
    return run_production(source, specification, registry, WORKERS, gates, destination, **kwargs)


def reseal(value):
    return seal(value)


def test_complete_fail_repair_unblock_loop_and_original_identities(tmp_path, setup_case):
    before = deepcopy(setup_case[0])
    report = run(setup_case, tmp_path / "campaign")
    assert report["status"] == "completed"
    assert report["attempt_count"] == report["execution_count"] == report["result_count"] == 3
    assert report["authority"] == AUTHORITY
    first = load(tmp_path / "campaign/attempt-0001.json")
    second = load(tmp_path / "campaign/attempt-0002.json")
    assert (first["status"], second["status"]) == ("rejected", "accepted")
    workspace = load(tmp_path / "campaign/session/workspace.json")
    assert len({r["execution_id"] for r in workspace["results"]}) == 3
    assert all(r["verification_id"] is None and r["verification_status"] == "not_verified" for r in workspace["results"])
    assert setup_case[0] == before
    assert inspect_production(tmp_path / "campaign", setup_case[3])["status"] == "completed"


def test_all_failed_attempts_retained_and_descendant_blocked(tmp_path, setup_case):
    source, spec, registry, gates = setup_case
    spec["jobs"][0]["checks"][0]["policy"]["expected"] = 900
    reseal(spec)
    report = run(setup_case, tmp_path / "campaign")
    assert report["jobs"]["select-window"]["status"] == "rejected"
    assert report["jobs"]["dependent-analysis"] == {"status": "blocked", "blocked_by": ["select-window"], "attempts": []}
    assert report["execution_count"] == 2
    assert inspect_production(tmp_path / "campaign", gates)["status"] == "incomplete"


def test_missing_evidence_holds_and_does_not_consume_repair(tmp_path, setup_case):
    setup_case[1]["jobs"][0]["checks"][0]["policy"]["path"] = ["not_present"]
    reseal(setup_case[1])
    report = run(setup_case, tmp_path / "campaign")
    assert report["jobs"]["select-window"]["status"] == "held"
    assert report["attempt_count"] == 1
    assert inspect_production(tmp_path / "campaign", setup_case[3])["status"] == "incomplete"


def test_independent_work_continues_after_rejection(tmp_path, setup_case):
    spec = setup_case[1]
    spec["jobs"][0]["checks"][0]["policy"]["expected"] = 900
    spec["jobs"][1]["depends_on"] = []
    reseal(spec)
    report = run(setup_case, tmp_path / "campaign")
    assert report["jobs"]["select-window"]["status"] == "rejected"
    assert report["jobs"]["dependent-analysis"]["status"] == "accepted"
    assert report["attempt_count"] == 3


@pytest.mark.parametrize("change", ["cycle", "missing_dependency", "duplicate_job", "empty_jobs", "empty_checks", "unknown_node",
                                   "duplicate_check", "too_many_attempts", "repair_route", "repair_model", "duplicate_requires", "unexpected_field"])
def test_malformed_declarations_rejected(change, setup_case):
    spec = setup_case[1]
    job = spec["jobs"][0]
    if change == "cycle": job["depends_on"] = ["dependent-analysis"]
    elif change == "missing_dependency": job["depends_on"] = ["missing"]
    elif change == "duplicate_job": spec["jobs"].append(deepcopy(job))
    elif change == "empty_jobs": spec["jobs"] = []
    elif change == "empty_checks": job["checks"] = []
    elif change == "unknown_node": job["checks"][0]["node_id"] = "unknown"
    elif change == "duplicate_check": job["checks"].append(deepcopy(job["checks"][0]))
    elif change == "too_many_attempts": job["attempts"] *= 2
    elif change in {"repair_route", "repair_model"}:
        graph = job["attempts"][1]
        if change == "repair_route": graph["nodes"][0]["operation_id"] = "spectrum.periodogram.v1"
        else: graph["model_id"] = "other-model"
        reseal(graph)
    elif change == "duplicate_requires": job["requires"] *= 2
    else: spec["shell"] = "execute arbitrary command"
    reseal(spec)
    with pytest.raises(ValueError): validate_plan(spec)


def test_unsealed_change_refused_before_destination(tmp_path, setup_case):
    setup_case[1]["project_id"] = "changed"
    with pytest.raises(ValueError): run(setup_case, tmp_path / "never-created")
    assert not (tmp_path / "never-created").exists()


@pytest.mark.parametrize("change", ["worker", "operation", "capability", "gate", "gate_policy", "source", "budget"])
def test_full_preflight_refuses_before_any_write_or_execution(tmp_path, setup_case, change):
    source, spec, registry, gates = setup_case
    if change == "worker": spec["jobs"][0]["worker_id"] = "unbound"
    elif change == "operation":
        for g in spec["jobs"][0]["attempts"]:
            g["nodes"][0]["operation_id"] = "not.bound.v1"
            reseal(g)
    elif change == "capability": spec["jobs"][0]["requires"] = ["mesh.generate"]
    elif change == "gate": spec["jobs"][0]["checks"][0]["gate_id"] = "unbound.gate.v1"
    elif change == "gate_policy": spec["jobs"][0]["checks"][0]["policy"]["executable"] = "/bin/sh"
    elif change == "source": spec["source_evidence_id"] = "sha256:" + "0" * 64
    reseal(spec)
    with patch("ciw.production.run_graph", side_effect=AssertionError("preflight dispatched")):
        with pytest.raises(Exception) as error:
            run(setup_case, tmp_path / "never-created", max_operations=2 if change == "budget" else 128)
    assert not isinstance(error.value, AssertionError)
    assert not (tmp_path / "never-created").exists()


@pytest.mark.parametrize("budget", [True, 0, -1, 257, 1.5, "5"])
def test_invalid_operator_budgets_refused(setup_case, budget):
    with pytest.raises(ValueError): preflight(setup_case[1], setup_case[2], WORKERS, setup_case[3], max_operations=budget)


def test_worker_allowlist_is_not_a_second_capability_registry(setup_case):
    registry = setup_case[2]
    workers = (Worker("local-analysis", ("spectrum.periodogram.v1",)),)
    with pytest.raises(ValueError): preflight(setup_case[1], registry, workers, setup_case[3])
    assert set(registry.catalog()["operations"]) == {"statistics.v1", "spectrum.periodogram.v1"}


def test_unbound_advertisement_cannot_execute(tmp_path, setup_case):
    source, spec, _, gates = setup_case
    with pytest.raises(Exception): run_production(source, spec, builtin_registry(), WORKERS, gates, tmp_path / "no")
    assert not (tmp_path / "no").exists()


def test_every_graph_sink_requires_a_check(setup_case):
    spec = setup_case[1]
    for graph in spec["jobs"][0]["attempts"]:
        node = deepcopy(graph["nodes"][0]); node["node_id"] = "unchecked"
        graph["nodes"].append(node); reseal(graph)
    reseal(spec)
    with pytest.raises(ValueError): validate_plan(spec)


def test_repeated_run_has_fresh_occurrences_and_preserves_original_files(tmp_path, setup_case):
    first = run(setup_case, tmp_path / "first")
    original = {p.relative_to(tmp_path / "first"): p.read_bytes() for p in (tmp_path / "first").rglob("*.json")}
    second = run(setup_case, tmp_path / "second")
    assert first["production_id"] != second["production_id"]
    a, b = [load(tmp_path / p / "session/workspace.json") for p in ("first", "second")]
    assert not {e["execution_id"] for e in a["executions"]} & {e["execution_id"] for e in b["executions"]}
    assert all((tmp_path / "first" / p).read_bytes() == data for p, data in original.items())


def test_existing_destination_is_never_overwritten(tmp_path, setup_case):
    root = tmp_path / "campaign"
    root.mkdir()
    (root / "sentinel").write_text("preserve")
    with pytest.raises(FileExistsError): run(setup_case, root)
    assert (root / "sentinel").read_text() == "preserve"


def test_inspection_does_not_execute_or_change_any_retained_bytes(tmp_path, setup_case):
    root = tmp_path / "campaign"
    run(setup_case, root)
    old = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with patch("subprocess.Popen", side_effect=AssertionError("process")), patch("ciw.production.run_graph", side_effect=AssertionError("graph")):
        report = inspect_production(root, setup_case[3])
    assert report["fresh_execution"] is False
    assert all(p.read_bytes() == data for p, data in old.items())


def test_changed_gate_binding_cannot_reopen_as_verified(tmp_path, setup_case):
    run(setup_case, tmp_path / "campaign")
    gates = setup_case[3]
    gates["result.equals.v1"] = replace(gates["result.equals.v1"], runtime={"provider": "different"})
    with pytest.raises(ValueError): inspect_production(tmp_path / "campaign", gates)


@pytest.mark.parametrize("value,expected,status", [(None, 0, "INDETERMINATE"), (True, 1, "FAIL"), (0, False, "FAIL"), (64, 64, "PASS"), (65, 64, "FAIL")])
def test_exact_gate_is_type_sensitive_and_does_not_impute(value, expected, status):
    gate = builtin_gates()["result.equals.v1"]
    assert gate.evaluate({"data": {"count": value}}, {"path": ["count"], "expected": expected})["status"] == status


def test_gate_exception_preserves_completed_session_and_never_marks_campaign_complete(tmp_path, setup_case):
    source, spec, registry, gates = setup_case
    def broken(*unused): raise ValueError("deliberate gate defect")
    gates["result.equals.v1"] = replace(gates["result.equals.v1"], evaluate=broken)
    root = tmp_path / "partial"
    with pytest.raises(ValueError): run(setup_case, root)
    assert not (root / "production.json").exists()
    workspace = load(root / "session/workspace.json")
    assert len(workspace["executions"]) == len(workspace["results"]) == 1


def test_bad_gate_status_does_not_publish_success(tmp_path, setup_case):
    gate = setup_case[3]["result.equals.v1"]
    setup_case[3][gate.gate_id] = replace(gate, evaluate=lambda *_: {"status": "APPROVED", "detail": None})
    with pytest.raises(ValueError): run(setup_case, tmp_path / "partial")
    assert not (tmp_path / "partial/production.json").exists()


def test_local_cli_demo_and_installed_dispatch(tmp_path):
    from ciw.net import main as net_main
    root = tmp_path / "demo"
    assert net_main(["production", "demo", "--output-dir", str(root)]) == 0
    assert main(["inspect", str(root), "--profile", "builtin"]) == 0


def test_example_is_data_only_and_create_only(tmp_path):
    root = tmp_path / "example"
    with patch("ciw.production.run_graph", side_effect=AssertionError("execution")):
        assert main(["example", "--output-dir", str(root)]) == 0
    assert main(["example", "--output-dir", str(root)]) == 1
    assert validate_plan(load(root / "plan.json"))


def test_cli_saved_catalog_does_not_supply_godot_executable(tmp_path):
    root = tmp_path / "example"
    assert main(["example", "--profile", "godot-courier", "--output-dir", str(root)]) == 0
    assert main(["run", str(root / "plan.json"), "--source", str(root / "source.json"), "--profile", "godot-courier", "--output-dir", str(tmp_path / "no")]) == 1
    assert not (tmp_path / "no").exists()


@pytest.mark.parametrize("fault,repair,status,calls", [("none", True, "accepted", 2), ("early-knowledge", True, "accepted", 3),
    ("duplicate-reward", True, "accepted", 3), ("drop-sample", True, "held", 1), ("early-knowledge", False, "rejected", 1)])
def test_game_boundaries_with_labelled_unit_double(tmp_path, fault, repair, status, calls):
    source = game.make_run(game.courier_scenario())
    binding = FixtureBinding()
    registry = game_registry(binding)
    workers = (Worker("godot-capture", (game.CAPTURE_OP,)),)
    root = tmp_path / "campaign"
    report = run_production(source, game_plan(source, fault=fault, repair=repair), registry, workers, game_gates(), root)
    assert report["jobs"]["courier-candidate"]["status"] == status
    assert binding.calls == calls
    with patch.object(FixtureBinding, "invoke", side_effect=AssertionError("native invocation during inspection")), patch("subprocess.Popen", side_effect=AssertionError("process")):
        assert inspect_production(root, game_gates())["fresh_execution"] is False
    assert all(r["runtime"]["execution_mode"] == "unit_test_double" for r in load(root / "session/workspace.json")["results"])


def test_provider_refusal_never_retries_and_has_no_result(tmp_path):
    source = game.make_run(game.courier_scenario()); binding = FixtureBinding(fail=True)
    root = tmp_path / "campaign"
    report = run_production(source, game_plan(source), game_registry(binding), (Worker("godot-capture", (game.CAPTURE_OP,)),), game_gates(), root)
    assert binding.calls == report["execution_count"] == 1
    assert report["result_count"] == 0
    assert report["jobs"]["courier-candidate"]["status"] == "refused"
    assert inspect_production(root, game_gates())["status"] == "incomplete"


def _rewrite(path, value):
    path.write_text(json.dumps(reseal(value), indent=2), encoding="utf-8")


@pytest.mark.parametrize("tamper", ["claim", "count", "job_status", "ref_path", "workspace", "attempt", "gate", "graph", "bindings"])
def test_retained_tampering_refused(tmp_path, setup_case, tamper):
    root = tmp_path / "campaign"; run(setup_case, root)
    path = root / "production.json"; report = load(path)
    if tamper == "claim": report["authority"]["publication"] = "performed"
    elif tamper == "count": report["execution_count"] += 1
    elif tamper == "job_status": report["jobs"]["select-window"]["status"] = "held"
    elif tamper == "ref_path": report["plan"]["name"] = "../elsewhere.json"
    elif tamper == "workspace": (root / "session/workspace.json").write_text("{}")
    elif tamper == "attempt": (root / "attempt-0001.json").write_text("{}")
    elif tamper == "gate": (root / "attempt-0001-checks.json").write_text("{}")
    elif tamper == "graph": (root / "attempt-0001-graph.json").write_text("{}")
    else: (root / "bindings.json").write_text("{}")
    _rewrite(path, report)
    with pytest.raises((ValueError, KeyError)): inspect_production(root, setup_case[3])


def test_resealed_false_acceptance_is_recomputed_not_trusted(tmp_path, setup_case):
    root = tmp_path / "campaign"; run(setup_case, root)
    check = load(root / "attempt-0001-checks.json")
    check["status"] = "PASS"; check["checks"][0]["status"] = "PASS"
    _rewrite(root / "attempt-0001-checks.json", check)
    receipt = load(root / "attempt-0001.json")
    receipt["acceptance"]["sha256"] = bytes_ref((root / "attempt-0001-checks.json").read_bytes())
    _rewrite(root / "attempt-0001.json", receipt)
    report = load(root / "production.json")
    report["jobs"]["select-window"]["attempts"][0]["sha256"] = bytes_ref((root / "attempt-0001.json").read_bytes())
    _rewrite(root / "production.json", report)
    with pytest.raises(ValueError, match="acceptance contradicts"):
        inspect_production(root, setup_case[3])


def test_independent_jobs_do_not_share_mutable_check_objects(setup_case):
    jobs = setup_case[1]["jobs"]
    jobs[0]["checks"][0]["policy"]["expected"] = 900
    assert jobs[1]["checks"][0]["policy"]["expected"] == 64


def test_gate_identity_drift_during_evaluation_refuses(tmp_path, setup_case):
    gate = setup_case[3]["result.equals.v1"]
    def changing(*unused):
        gate.runtime["changed"] = True
        return {"status": "PASS", "detail": None}
    setup_case[3][gate.gate_id] = replace(gate, evaluate=changing)
    with pytest.raises(ValueError, match="identity changed"):
        run(setup_case, tmp_path / "partial")
    assert not (tmp_path / "partial/production.json").exists()
    assert (tmp_path / "partial/attempt-0001-graph.json").exists()


@pytest.mark.parametrize("name", ["attempt_count", "execution_count", "result_count"])
def test_boolean_counts_cannot_masquerade_as_integers(tmp_path, setup_case, name):
    root = tmp_path / "campaign"; run(setup_case, root)
    report = load(root / "production.json"); report[name] = True
    _rewrite(root / "production.json", report)
    with pytest.raises(ValueError, match="count"): inspect_production(root, setup_case[3])


def test_resealed_invalid_budget_is_not_trusted(tmp_path, setup_case):
    root = tmp_path / "campaign"; run(setup_case, root)
    bindings = load(root / "bindings.json"); bindings["max_operations"] = 1
    _rewrite(root / "bindings.json", bindings)
    report = load(root / "production.json")
    report["bindings"]["sha256"] = bytes_ref((root / "bindings.json").read_bytes())
    _rewrite(root / "production.json", report)
    with pytest.raises(ValueError, match="budget"): inspect_production(root, setup_case[3])


def test_interruption_never_retries_and_preserves_original_records(tmp_path, setup_case):
    def stop(*unused): raise KeyboardInterrupt()
    gate = setup_case[3]["result.equals.v1"]
    setup_case[3][gate.gate_id] = replace(gate, evaluate=stop)
    root = tmp_path / "partial"
    with pytest.raises(KeyboardInterrupt): run(setup_case, root)
    assert not (root / "production.json").exists()
    assert len(load(root / "session/workspace.json")["executions"]) == 1
