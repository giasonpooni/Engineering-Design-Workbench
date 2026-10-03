"""Foundry tests use explicit non-native doubles; native qualification is separate."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.control_contracts import bytes_ref, load, save_new
from ciw.core.identities import content_identity
from ciw.foundry_project import FILES, DEPENDENCY_FILES, PROJECT, GodotProjectBinding, snapshot, validate_lock
from ciw import foundry_water as water
from ciw import foundry_workflow as workflow
from ciw.production import run_production
from ciw.operations.runner import seal


def fixture_capture(declared, parameters):
    """A fabricated unit-test observation, never represented as native evidence."""
    initial = {"remaining": 6, "carried": 0, "stored": 0, "phase": "ready", "started_tick": -1, "completed_tick": -1}
    def sample(stage, tick, ledger):
        return {"stage": stage, "tick": tick, "ledger": deepcopy(ledger), "money": {"coins": 5}, "known_places": ["sukerchakia_home"]}
    samples = [sample("assigned", 10, initial)]
    events = []
    pending = None
    ledger = initial
    for i in range(parameters["trips"]):
        t = 10 + i * 180
        ledger = {"remaining": 6-i*3, "carried": 0, "stored": i*3, "phase": "drawing", "started_tick": t, "completed_tick": -1}
        if pending is None:
            pending = {"childhood": {"tick": t+90}, "water_round": {"ledger": deepcopy(ledger)}}
        samples.extend([sample("draw-start", t, ledger), sample("before-fill", t+179, ledger)])
        ledger = {"remaining": 3-i*3, "carried": 3, "stored": i*3, "phase": "carrying", "started_tick": -1, "completed_tick": -1}
        samples.append(sample("filled", t+180, ledger))
        ledger = {"remaining": 3-i*3, "carried": 0, "stored": (i+1)*3, "phase": "complete" if i == 1 else "ready", "started_tick": -1, "completed_tick": t+180 if i == 1 else -1}
        samples.append(sample("deposited", t+180, ledger))
        for tick, kind in [(t, "draw"), (t+180, "filled"), (t+180, "deposit")]:
            events.append({"seq": len(events)+1, "tick": tick, "kind": kind, "actor_id": "ranjit_singh", "position": [3, .14, 4] if kind == "deposit" else [26, .14, 14]})
    request = {"schema": "ciw.foundry-water-request.v1", **parameters, "source_lock_id": declared["source_lock"]["source_lock_id"]}
    probe = sample("duplicate-probe", samples[-1]["tick"], ledger)
    data = {"schema": "cartesian.foundry-water-observations.v1", "request_nonce": parameters["nonce"],
        "source_lock_id": request["source_lock_id"], "engine_version": "NON-NATIVE UNIT TEST DOUBLE", "model_id": water.MODEL,
        "clock_id": "1792.childhood.tick", "tick_hz": 60, "source_class": "authored_game_with_explicit_domain_fixture",
        "trips": parameters["trips"], "samples": samples, "water_round": {"schema": "gujranwala-water-round.v1", "model_id": water.MODEL,
        "origin_tick": 10, "events": events, "ledger": ledger}, "checkpoint_before": pending, "checkpoint_after": deepcopy(pending),
        "duplicate_error": "Empty carrier", "before_duplicate": probe, "after_duplicate": deepcopy(probe)}
    raw = json.dumps(data)
    return {"schema": "ciw.foundry-water-capture.v1", "request": request, "source_utf8": raw, "source_sha256": bytes_ref(raw.encode()),
        "logs": {n: {"utf8": "NON-NATIVE UNIT TEST DOUBLE", "sha256": bytes_ref(b"NON-NATIVE UNIT TEST DOUBLE")} for n in ("stdout.log", "stderr.log")}, "elapsed_wall_s": .01}


class FakeBinding:
    def __init__(self, lock, mode="normal"):
        self.lock, self.mode, self.calls = lock, mode, 0
    def runtime_identity(self):
        return {"provider": "foundry.test-double", "execution_mode": "non_native_test_double", "source_lock": deepcopy(self.lock)}
    def invoke(self, declared, params):
        from ciw.adapters.protocol import AdapterRefusal
        self.calls += 1
        if self.mode == "refuse":
            raise AdapterRefusal("test_refusal", "No native execution took place")
        value = fixture_capture(declared, params)
        if self.mode == "missing":
            data = json.loads(value["source_utf8"]); data["samples"] = []
            value["source_utf8"] = json.dumps(data); value["source_sha256"] = bytes_ref(value["source_utf8"].encode())
        return value


@pytest.fixture
def case(tmp_path):
    game = tmp_path / "game"
    for name in FILES:
        path = game / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# UNIT TEST SOURCE PLACEHOLDER\nextends RefCounted\n")
    lock, _ = snapshot(game)
    return game, lock, water.source(lock)


def run_case(case, destination, mode="normal", repair=True):
    _, lock, source = case
    binding = FakeBinding(lock, mode)
    report = run_production(source, water.compile_plan(source, repair=repair), water.registry(binding), water.WORKERS, water.gates(), destination)
    return report, binding


def test_fail_correct_accept_regression_and_original_session(case, tmp_path):
    root = tmp_path / "campaign"
    result, binding = run_case(case, root)
    assert result["status"] == "completed" and binding.calls == 3
    assert result["execution_count"] == result["result_count"] == 3
    assert [load(root / f"attempt-{i:04d}.json")["status"] for i in (1,2,3)] == ["rejected", "accepted", "accepted"]
    workspace = load(root / "session/workspace.json")
    assert all(r["verification_id"] is None for r in workspace["results"])
    assert len({r["execution_id"] for r in workspace["results"]}) == 3
    assert workflow.inspect_order(root)["status"] == "completed"


@pytest.mark.parametrize("mode,repair,outcome,results", [("normal", False, "rejected", 1), ("missing", True, "held", 1), ("refuse", True, "refused", 0)])
def test_failure_hold_refusal_block_descendant(case, tmp_path, mode, repair, outcome, results):
    root = tmp_path / "campaign"
    report, binding = run_case(case, root, mode, repair)
    assert report["status"] == "incomplete" and binding.calls == 1
    assert report["jobs"]["water-round"]["status"] == outcome
    assert report["jobs"]["water-round-regression"]["status"] == "blocked"
    assert report["result_count"] == results
    assert workflow.inspect_order(root)["status"] == "incomplete"
    with pytest.raises(ValueError): workflow.export_artifact(root, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_offline_inspection_report_and_byte_exact_export(case, tmp_path):
    root = tmp_path / "campaign"; run_case(case, root)
    original = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with patch("subprocess.Popen", side_effect=AssertionError("inspection executed")):
        report = workflow.report_order(root)
        exported = workflow.export_artifact(root, tmp_path / "export")
    assert report["accepted_jobs"] == 2 and report["rejected_attempts"] == 1
    assert report["rejection_fraction"] == 1/3
    assert report["human_supervisory_hours"] is report["model_token_cost"] is report["playable_minutes"] is None
    assert exported["publication"] == "not_performed"
    assert bytes_ref((tmp_path / "export/water-round-observations.json").read_bytes()) == exported["artifact"]["sha256"]
    assert all(p.read_bytes() == raw for p, raw in original.items())
    with pytest.raises(FileExistsError): workflow.export_artifact(root, tmp_path / "export")


def test_compile_is_data_only_and_fresh(case, tmp_path):
    with patch("subprocess.Popen", side_effect=AssertionError("compile executed")):
        result = workflow.compile_order(case[0], tmp_path / "order")
    assert result["fresh_execution"] is False
    with pytest.raises(FileExistsError): workflow.compile_order(case[0], tmp_path / "order")
    assert workflow.main(["compile", "1792.water-round.v1", "--game-root", str(case[0]), "--output-dir", str(tmp_path / "cli")]) == 0


@pytest.mark.parametrize("bad", [True, False, 0, 3, -1, 1.5, "2", None])
def test_invalid_trip_count(case, bad):
    with pytest.raises(ValueError): water.compile_plan(case[2], candidate_trips=bad)


def test_lock_source_drift_and_binary_drift(case, tmp_path):
    executable = tmp_path / "fake-godot"; executable.write_bytes(b"not executable test fixture")
    binding = GodotProjectBinding(executable, case[0], expected_sha256=bytes_ref(executable.read_bytes()), source_lock=case[1])
    first = binding.runtime_identity()
    (case[0] / FILES[0]).write_text("changed after binding")
    assert binding.runtime_identity() == first  # bound immutable snapshot, not moving checkout
    with pytest.raises(ValueError): GodotProjectBinding(executable, case[0], expected_sha256=bytes_ref(executable.read_bytes()), source_lock=case[1])
    executable.write_bytes(b"changed executable")
    with pytest.raises(ValueError): binding.runtime_identity()


def test_snapshot_symlink_and_missing(case, tmp_path):
    path = case[0] / FILES[0]
    path.unlink()
    with pytest.raises(ValueError): snapshot(case[0])
    target = tmp_path / "outside"; target.write_text("external")
    try: path.symlink_to(target)
    except OSError: pytest.skip("OS denied symlink creation")
    with pytest.raises(ValueError): snapshot(case[0])


@pytest.mark.parametrize("change", ["policy", "bool-policy", "source-byte", "nonce", "lock", "elapsed", "log", "model", "boolean-trips", "extra"])
def test_modified_contracts_refused(case, change):
    params = {"nonce": "test", "trips": 2}
    declared = water.objective(case[2]); value = fixture_capture(declared, params)
    if change in {"policy", "bool-policy"}:
        policy = deepcopy(water.POLICY); policy["required_trips"] = 1 if change == "policy" else True
        with pytest.raises(ValueError): water.gates()[water.GATE].validate_policy(policy)
        return
    if change == "source-byte": value["source_utf8"] += " "
    elif change == "nonce": value["request"]["nonce"] = "other"
    elif change == "lock": value["request"]["source_lock_id"] = "sha256:" + "0" * 64
    elif change == "elapsed": value["elapsed_wall_s"] = -1
    elif change == "log": value["logs"]["stdout.log"]["utf8"] += "changed"
    else:
        data = json.loads(value["source_utf8"])
        if change == "model": data["model_id"] = "other"
        elif change == "boolean-trips": data["trips"] = True
        else: data["claimed_pass"] = True
        value["source_utf8"] = json.dumps(data); value["source_sha256"] = bytes_ref(value["source_utf8"].encode())
    with pytest.raises(ValueError): water.validate_capture(value, declared, params)


@pytest.mark.parametrize("change", ["conservation", "early-fill", "mint-money", "knowledge", "duplicate", "replay", "wrong-actor", "location", "missing-sample", "false-seq"])
def test_independent_gate_does_not_trust_worker_success(case, change):
    value = fixture_capture(water.objective(case[2]), {"nonce": "test", "trips": 2})
    data = json.loads(value["source_utf8"])
    if change == "conservation": data["samples"][-1]["ledger"]["stored"] = 99
    elif change == "early-fill": data["water_round"]["events"][1]["tick"] -= 1
    elif change == "mint-money": data["samples"][-1]["money"]["coins"] += 10
    elif change == "knowledge": data["samples"][-1]["known_places"].append("unearned")
    elif change == "duplicate": data["after_duplicate"]["ledger"]["stored"] += 3
    elif change == "replay": data["checkpoint_after"]["childhood"]["tick"] += 1
    elif change == "wrong-actor": data["water_round"]["events"][0]["actor_id"] = "someone-else"
    elif change == "location": data["water_round"]["events"][0]["position"] = [999, 0, 0]
    elif change == "missing-sample": data["samples"] = []
    else: data["water_round"]["events"][0]["seq"] = True
    value["source_utf8"] = json.dumps(data); value["source_sha256"] = bytes_ref(value["source_utf8"].encode())
    verdict = water.evaluate({"operation_id": water.OP, "data": value}, water.POLICY)
    assert verdict["status"] == ("INDETERMINATE" if change == "missing-sample" else "FAIL")


def test_resealed_worker_pass_cannot_change_retained_acceptance(case, tmp_path):
    root = tmp_path / "campaign"; run_case(case, root)
    checks = load(root / "attempt-0001-checks.json")
    checks["status"] = "PASS"; seal(checks)
    (root / "attempt-0001-checks.json").write_text(json.dumps(checks))
    with pytest.raises(ValueError): workflow.inspect_order(root)


def test_net_cli_dispatch(case, tmp_path):
    from ciw.net import main
    assert main(["foundry", "compile", "1792.water-round.v1", "--game-root", str(case[0]), "--output-dir", str(tmp_path / "order")]) == 0


def test_current_title_dependencies_are_explicitly_locked(case, tmp_path):
    game, legacy_lock, _ = case
    for owner, dependency in zip(("childhood/childhood_state.gd", "territory/misl_rules.gd"), DEPENDENCY_FILES):
        (game / owner).write_text('extends RefCounted\nconst Rule = preload("res://' + dependency + '")\n')
        target = game / dependency
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# CURRENT TITLE DEPENDENCY TEST DOUBLE\nextends RefCounted\n")
    lock, sources = snapshot(game)
    assert set(sources) == set(FILES) | set(DEPENDENCY_FILES)
    assert lock["files"] == {name: bytes_ref(raw) for name, raw in sources.items()}
    assert lock["source_lock_id"] != legacy_lock["source_lock_id"]
    validate_lock(lock)
    validate_lock(legacy_lock)  # Existing retained eleven-file evidence remains readable.
    executable = tmp_path / "fake-godot"
    executable.write_bytes(b"not executable test fixture")
    binding = GodotProjectBinding(executable, game, expected_sha256=bytes_ref(executable.read_bytes()), source_lock=lock)
    assert binding.sources == sources
    (game / DEPENDENCY_FILES[0]).write_text("changed since compilation")
    with pytest.raises(ValueError, match="changed since the work order"):
        GodotProjectBinding(executable, game, expected_sha256=bytes_ref(executable.read_bytes()), source_lock=lock)


def test_unreferenced_optional_rules_do_not_change_legacy_lock(case):
    game, legacy_lock, _ = case
    for name in DEPENDENCY_FILES:
        target = game / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# NOT IN THIS WORKLOAD\nextends RefCounted\n")
    lock, sources = snapshot(game)
    assert lock == legacy_lock and set(sources) == set(FILES)


def test_registered_dependency_missing_refuses_before_native_or_output(case, tmp_path):
    game, _, _ = case
    owner = "childhood/childhood_state.gd"
    (game / owner).write_text('extends RefCounted\nconst Rule = preload("res://' + DEPENDENCY_FILES[0] + '")\n')
    output = tmp_path / "order"
    with patch("subprocess.Popen", side_effect=AssertionError("compile executed")):
        with pytest.raises(ValueError) as failure:
            workflow.compile_order(game, output)
    assert DEPENDENCY_FILES[0] in str(failure.value) and owner in str(failure.value)
    assert not output.exists()


def test_unregistered_transitive_rule_refuses_without_reading_it(case, tmp_path):
    game, _, _ = case
    (game / "childhood/childhood_state.gd").write_text('extends RefCounted\nconst Rule = preload("res://' + DEPENDENCY_FILES[0] + '")\n')
    (game / DEPENDENCY_FILES[0]).write_text('extends RefCounted\nconst Rule = preload("res://future_rule.gd")\n')
    (game / "future_rule.gd").write_text("# Not an installed source grant\nextends RefCounted\n")
    output = tmp_path / "order"
    with patch("subprocess.Popen", side_effect=AssertionError("compile executed")):
        with pytest.raises(ValueError, match="Unregistered game-owned dependency: future_rule.gd"):
            workflow.compile_order(game, output)
    assert not output.exists()


@pytest.mark.parametrize("change", ["missing-original", "unregistered-addition"])
def test_saved_lock_cannot_expand_or_drop_installed_sources(case, change):
    lock = deepcopy(case[1])
    if change == "missing-original":
        del lock["files"][FILES[0]]
    else:
        lock["files"]["future_rule.gd"] = bytes_ref(b"unregistered source")
    lock["source_lock_id"] = content_identity({k: v for k, v in lock.items() if k != "source_lock_id"})
    with pytest.raises(ValueError, match="installed game-owned source contract"):
        validate_lock(lock)


def test_long_native_failure_retains_complete_refused_campaign(case, tmp_path):
    game, lock, source = case
    executable = tmp_path / "fake-godot"
    executable.write_bytes(b"not executable test fixture")
    binding = GodotProjectBinding(executable, game, expected_sha256=bytes_ref(executable.read_bytes()), source_lock=lock)
    root = tmp_path / "long-refusal"
    diagnostic = "SCRIPT ERROR: fixture parse failure at res://foundry/water_round.gd:4; " + "detail " * 1000
    with patch("ciw.foundry_project.run_process", side_effect=RuntimeError(diagnostic)):
        report = run_production(source, water.compile_plan(source), water.registry(binding), water.WORKERS, water.gates(), root)
    assert report["status"] == "incomplete" and report["result_count"] == 0
    assert report["jobs"]["water-round"]["status"] == "refused"
    assert report["jobs"]["water-round-regression"]["status"] == "blocked"
    workspace = load(root / "session/workspace.json")
    refusal = workspace["executions"][0]["refusal"]
    assert refusal["code"] == "foundry_game_runtime_failed"
    assert refusal["message"] == diagnostic[:500] + " [truncated]"
    assert len(refusal["message"]) == 512
    with patch("subprocess.Popen", side_effect=AssertionError("inspection executed")):
        assert workflow.inspect_order(root)["status"] == "incomplete"
