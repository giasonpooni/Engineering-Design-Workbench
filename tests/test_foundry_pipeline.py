"""Real planning/filesystem contracts; native engines are qualified by the separate script."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest

from ciw import foundry_catalog as catalog, foundry_packets as packets, foundry_pipeline as pipeline
from ciw.foundry_pipeline_cli import main, evidence_map
from ciw.foundry_workflow import main as foundry_main
from ciw.control_contracts import bytes_ref, load, save_new
from ciw.core.identities import content_identity
from ciw.operations.runner import seal


@pytest.fixture
def case(tmp_path):
    root = tmp_path / "game"
    for name, text in {"player/player.gd": "# original motor\nextends Node\n", "tests/test_motor.gd": "# fixed original test\n", "project.godot": "config_version=5\n", "docs/notes.md": "# original design\n", "LICENSE": "Original terms\n"}.items():
        p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
    project = pipeline.create_project("1792-fixture", root, tmp_path / "project")
    return root, project


def packet(case, *, paths=None, task_id="vision", name="producer-1"):
    root, project = case
    return packets.make_packet(project, pipeline.task_for(project, task_id), root, writable=paths or [], context=["player/player.gd"], assignee=name)


def candidate(case, destination):
    shutil.copytree(case[0], destination)
    return destination


def scope(value, case, root):
    return packets.check_candidate(value, case[1], pipeline.task_for(case[1], value["task_id"]), root, expected_packet_id=value["record_digest"])


def review(case, tmp_path, task_id="vision", *, evidence=None, reviewer="EXPLICIT TEST FIXTURE REVIEWER", decision="approved", suffix=""):
    artifact = tmp_path / ("artifact-"+task_id+suffix); artifact.mkdir()
    (artifact / "notes.md").write_text("TEST FIXTURE: not an actual human quality approval.\n")
    out = tmp_path / ("review-"+task_id+suffix)
    value = pipeline.review_task(case[1], task_id, case[0], artifact, out, reviewer=reviewer,
                                 producer="TEST FIXTURE PRODUCER", decision=decision, evidence=evidence)
    return out, value


def reseal(value):
    value = deepcopy(value); value.pop("record_digest", None)
    return seal(value)


def test_catalog_is_complete_and_uses_original_bounded_order(case):
    root, p = case
    assert len(p["tasks"]) == 60 and len(p["stages"]) == 10
    assert all(sum(t["stage"] == s["stage_id"] for t in p["tasks"]) == 6 for s in p["stages"])
    order = pipeline.validate_project(p)
    for t in p["tasks"]:
        assert all(order.index(d) < order.index(t["task_id"]) for d in t["depends_on"])
    assert sum(t["installed_recipe"] is not None for t in p["tasks"]) == 1
    assert pipeline.task_for(p, "art-target")["depends_on"] != ["slice-journey"]
    assert pipeline.task_for(p, "cpu-profiling")["depends_on"] == ["telemetry", "slice-journey"]


@pytest.mark.parametrize("change", ["gate", "automation", "source", "authority", "stage", "template"])
def test_resealed_project_cannot_change_installed_contract(case, change):
    p = deepcopy(case[1])
    if change == "gate": p["tasks"][17]["acceptance"] = "Trust the worker's PASS"
    if change == "automation": p["tasks"][0]["automation"] = "deterministic"
    if change == "source": p["sources"] = []
    if change == "authority": p["authority"]["publication"] = "authorized"
    if change == "stage": p["stages"][0]["title"] = "Changed"
    if change == "template": p["template_id"] = "sha256:"+"0"*64
    with pytest.raises(ValueError): pipeline.validate_project(reseal(p))


def test_original_graph_validator_refuses_cycles_and_duplicates():
    tasks = catalog.tasks(); tasks[0]["depends_on"] = ["core-loop"]
    with pytest.raises(ValueError, match="cycle"): pipeline.dependency_order(tasks)
    tasks = catalog.tasks(); tasks[0]["task_id"] = tasks[1]["task_id"]
    with pytest.raises(ValueError, match="Duplicate"): pipeline.dependency_order(tasks)
    with pytest.raises(ValueError): pipeline.dependency_order(catalog.tasks()+catalog.tasks())


def test_empty_status_never_invents_completion_or_money(case):
    with patch("subprocess.Popen", side_effect=AssertionError("status executed a provider")):
        r = pipeline.assess(case[1], case[0])
    assert r["tasks"]["water-domain"]["status"] == "ready_to_run"
    assert r["tasks"]["vision"]["status"] == "awaiting_review"
    assert r["tasks"]["release-signoff"]["status"] == "blocked"
    assert r["metrics"]["machine_checked_tasks"] == 0
    assert r["metrics"]["human_hours"] is r["metrics"]["model_cost"] is r["metrics"]["accepted_playable_minutes"] is None
    assert r["release_authorized"] is False and r["fresh_execution"] is False


def test_scope_check_preserves_both_trees_and_is_not_acceptance(case, tmp_path):
    value = packet(case, paths=["player/player.gd"])
    root = candidate(case, tmp_path / "candidate")
    initial = packets.inventory(case[0])
    unchanged = scope(value, case, root)
    assert unchanged["status"] == "scope_passed" and not unchanged["changes"]
    (root / "player/player.gd").write_text("# candidate, deliberately not executed\nextends Node\n")
    with patch("subprocess.Popen", side_effect=AssertionError("scope executed candidate")):
        checked = scope(value, case, root)
    assert checked["status"] == "scope_passed"
    assert checked["quality_acceptance"] == "not_performed" and checked["executed"] is False
    assert packets.inventory(case[0]) == initial
    assert pipeline.assess(case[1], case[0])["metrics"]["machine_checked_tasks"] == 0


@pytest.mark.parametrize("path", ["tests/test_motor.gd", "project.godot", "LICENSE", "foundry/arbitrary.gd", ".github/workflows/run.yml", "tests/test_added_by_unassigned_worker.gd"])
def test_candidate_out_of_scope_is_refused(case, tmp_path, path):
    value = packet(case, paths=["player/player.gd"])
    root = candidate(case, tmp_path / "candidate")
    target = root / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text("candidate replacement")
    checked = scope(value, case, root)
    assert checked["status"] == "scope_refused" and path in checked["out_of_scope"]


@pytest.mark.parametrize("path", ["tests/test_motor.gd", "project.godot", "LICENSE", "foundry/water_round.gd", ".github/workflows/x.yml", "COPYING", "Project.godot"])
def test_operator_packet_cannot_grant_protected_writes(case, path):
    with pytest.raises(ValueError): packet(case, paths=[path])


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../x", "a//x", "./x", "C:/x", "a\\b", ".env", "x/.env.production", ".git/config", "x/.ssh/key", "a/CON.txt", "a/NUL", "a/end.", "a/end ", "a/*", "a/[x]", "a/line\nname"])
def test_portable_path_boundary(name):
    with pytest.raises(ValueError): packets.relative(name)


def test_context_reseal_and_independent_packet_identity(case, tmp_path):
    good = packet(case, paths=["player/player.gd"])
    root = candidate(case, tmp_path / "candidate")
    bad = deepcopy(good); bad["context"]["player/player.gd"] += "changed"; bad = reseal(bad)
    with pytest.raises(ValueError, match="operator-retained"):
        packets.check_candidate(bad, case[1], pipeline.task_for(case[1], "vision"), root, expected_packet_id=good["record_digest"])
    with pytest.raises(ValueError, match="Context"):
        scope(bad, case, root)
    bad = deepcopy(good); bad["rights"]["approve"] = True
    with pytest.raises(ValueError): scope(reseal(bad), case, root)


def test_added_and_removed_files_need_exact_grants(case, tmp_path):
    value = packet(case, paths=["player/player.gd", "tests/generated/addition.gd"])
    root = candidate(case, tmp_path / "candidate")
    (root / "player/player.gd").unlink()
    path = root / "tests/generated/addition.gd"; path.parent.mkdir(); path.write_text("# new candidate test")
    result = scope(value, case, root)
    assert result["status"] == "scope_passed"
    assert {d["change"] for d in result["changes"]} == {"added", "removed"}
    (root / "tests/test_motor.gd").unlink()
    assert scope(value, case, root)["status"] == "scope_refused"


def test_byte_budget_and_bool_refusal(case, tmp_path):
    value = packets.make_packet(case[1], pipeline.task_for(case[1], "vision"), case[0], writable=["player/player.gd"], context=[], assignee="a", max_changed_bytes=10)
    root = candidate(case, tmp_path / "candidate"); (root / "player/player.gd").write_text("X"*11)
    assert scope(value, case, root)["status"] == "scope_refused"
    with pytest.raises(ValueError): packets.make_packet(case[1], pipeline.task_for(case[1], "vision"), case[0], writable=[], context=[], assignee="a", max_changed_bytes=True)


def test_native_task_is_readonly_and_other_tasks_unbound(case, tmp_path):
    with pytest.raises(ValueError): packet(case, paths=["player/player.gd"], task_id="water-domain")
    with pytest.raises(ValueError, match="No installed"):
        pipeline.run_task(case[1], "vision", case[0], Path("nonexistent"), "sha256:"+"0"*64, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_inventory_drift_and_candidate_modes(case, tmp_path):
    original = packets.inventory(case[0])
    (case[0] / "player/player.gd").write_text("changed")
    drift = pipeline.impact(case[1], case[0])
    assert drift["changes"] == [{"path": "player/player.gd", "change": "modified"}]
    assert "water-domain" not in drift["direct_tasks"]
    assert "release-signoff" in drift["affected_tasks"]
    with pytest.raises(ValueError, match="Source drift"): packet(case)
    with pytest.raises(ValueError): pipeline.run_task(case[1], "water-domain", case[0], Path("no"), "sha256:"+"0"*64, tmp_path / "run")
    assert not (tmp_path / "run").exists()
    assert pipeline.assess(case[1], case[0])["tasks"]["vision"]["status"] == "stale"


def test_mode_change_is_not_invisible(case, tmp_path):
    import os
    if os.name == "nt": return  # no POSIX mode claim on Windows
    root = candidate(case, tmp_path / "candidate"); p = root / "docs/notes.md"
    p.chmod(p.stat().st_mode | 0o111)
    assert "docs/notes.md" in scope(packet(case), case, root)["out_of_scope"]


@pytest.mark.parametrize("kind", ["root", "directory", "file", "hardlink"])
def test_links_are_refused_before_packet_reads(case, tmp_path, kind):
    root = case[0]; external = tmp_path / "outside.txt"; external.write_text("do not read")
    try:
        if kind == "root":
            alias = tmp_path / "alias"; alias.symlink_to(root, target_is_directory=True)
            with pytest.raises(ValueError): packets.inventory(alias)
            return
        if kind == "directory": (root / "linked").symlink_to(tmp_path, target_is_directory=True)
        if kind == "file": (root / "linked.txt").symlink_to(external)
        if kind == "hardlink": (root / "linked.txt").hardlink_to(external)
    except OSError as exc:
        pytest.skip(f"platform does not permit link fixture: {exc}")
    with pytest.raises(ValueError): packets.inventory(root)


def test_inventory_budget_and_case_collision(case, monkeypatch):
    monkeypatch.setattr(packets, "MAX_FILES", 1)
    with pytest.raises(ValueError, match="budget"): packets.inventory(case[0])
    monkeypatch.setattr(packets, "MAX_FILES", 1024)
    monkeypatch.setattr(packets, "MAX_FILE", 2)
    with pytest.raises(ValueError, match="byte"): packets.inventory(case[0])


def test_review_is_distinct_attestation_not_native_acceptance(case, tmp_path):
    out, value = review(case, tmp_path)
    report = pipeline.assess(case[1], case[0], {"vision": out})
    assert report["tasks"]["vision"]["status"] == "operator_attested"
    assert report["tasks"]["core-loop"]["status"] == "awaiting_review"
    assert report["tasks"]["historical-scope"]["status"] == "ready_for_packet"
    assert report["metrics"]["machine_checked_tasks"] == 0
    assert report["release_authorized"] is False
    assert value["authority"]["authentication"] == "not_verified"
    with pytest.raises(ValueError, match="native acceptance"): review(case, tmp_path, "water-domain")


def test_review_requires_prerequisites_and_distinct_labels(case, tmp_path):
    with pytest.raises(ValueError, match="blocked"): review(case, tmp_path, "core-loop")
    with pytest.raises(ValueError, match="distinct"): review(case, tmp_path, reviewer="TEST FIXTURE PRODUCER")


def test_review_artifact_tampering_refuses_without_writes(case, tmp_path):
    out, value = review(case, tmp_path)
    raw = (out / "review.json").read_bytes()
    (out / "artifacts/notes.md").write_text("different decision artifact")
    with pytest.raises(ValueError, match="artifacts changed"):
        pipeline.assess(case[1], case[0], {"vision": out})
    assert (out / "review.json").read_bytes() == raw


def test_replaced_dependency_evidence_stales_downstream_review(case, tmp_path):
    vision, _ = review(case, tmp_path)
    loop, _ = review(case, tmp_path, "core-loop", evidence={"vision": vision})
    first = pipeline.assess(case[1], case[0], {"vision": vision, "core-loop": loop})
    assert first["tasks"]["core-loop"]["status"] == "operator_attested"
    other, _ = review(case, tmp_path, suffix="new", reviewer="OTHER DECLARED TEST REVIEWER")
    after = pipeline.assess(case[1], case[0], {"vision": other, "core-loop": loop})
    assert after["tasks"]["core-loop"]["status"] == "stale"
    assert after["tasks"]["scope-budget"]["status"] == "blocked"


def test_rejected_review_blocks_followers_and_unread_evidence_is_labeled(case, tmp_path):
    out, _ = review(case, tmp_path, decision="rejected")
    r = pipeline.assess(case[1], case[0], {"vision": out, "core-loop": tmp_path / "not-inspected"})
    assert r["tasks"]["vision"]["status"] == "review_rejected"
    assert r["tasks"]["core-loop"]["supplied_evidence_inspected"] is False


def test_conflicts_are_advisory_not_parallel_workers(case):
    a = packet(case, paths=["player/player.gd"], name="a")
    b = packet(case, paths=["docs/notes.md"], name="b")
    r = packets.compatible_wave([a, b])
    assert r["conflicts"] and not r["conflicts"][0]["write_write"]
    assert r["conflicts"][0]["write_read"]
    assert r["parallel_execution"] == "not_performed"
    c = packet(case, paths=["new-a.gd"]); d = packet(case, paths=["new-b.gd"])
    assert packets.compatible_wave([c, d])["conflicts"] == []


def test_unknown_evidence_and_duplicate_cli_bindings(case):
    with pytest.raises(ValueError): pipeline.assess(case[1], case[0], {"unknown": Path("elsewhere")})
    for fields in [["vision=x", "vision=y"], ["vision"], ["=x"], ["vision="]]:
        with pytest.raises(ValueError): evidence_map(fields)


def test_cli_end_to_end_no_runtime(case, tmp_path, capsys):
    root, project = case; filename = tmp_path / "project/project.json"
    with patch("subprocess.Popen", side_effect=AssertionError("offline CLI executed")):
        assert foundry_main(["pipeline", "status", str(filename), "--source-root", str(root)]) == 0
        status = json.loads(capsys.readouterr().out)
        assert status["tasks"]["release-signoff"]["status"] == "blocked"
        assert main(["report", str(filename), "--source-root", str(root), "--output", str(tmp_path / "report.md")]) == 0
        assert "60" in str(len(project["tasks"])) and "release-signoff" in (tmp_path / "report.md").read_text()
        assert main(["packet", str(filename), "--source-root", str(root), "--task", "core-loop", "--assignee", "agent", "--output-dir", str(tmp_path / "blocked")]) == 1
        capsys.readouterr()
        assert not (tmp_path / "blocked").exists()
        out = tmp_path / "packet"
        assert main(["packet", str(filename), "--source-root", str(root), "--task", "water-domain", "--assignee", "qa-host", "--context", "player/player.gd", "--output-dir", str(out)]) == 0
        packet_value = json.loads(capsys.readouterr().out)
        assert main(["check", str(filename), "--packet", str(out / "packet.json"), "--packet-id", packet_value["record_digest"], "--candidate-root", str(root)]) == 0
        assert json.loads(capsys.readouterr().out)["quality_acceptance"] == "not_performed"
        assert main(["packet", str(filename), "--source-root", str(root), "--task", "water-domain", "--assignee", "qa", "--output-dir", str(out)]) == 1
        assert (out / "AGENT_TASK.md").is_file()


def test_outputs_inside_source_and_existing_dirs_refused(case, tmp_path):
    with pytest.raises(ValueError): pipeline.create_project("x", case[0], case[0] / "recursive-output")
    assert not (case[0] / "recursive-output").exists()
    with pytest.raises(FileExistsError): pipeline.create_project("x", case[0], tmp_path / "project")


def test_native_evidence_cannot_be_a_worker_pass_flag(case, tmp_path):
    out = tmp_path / "fake"; out.mkdir()
    save_new(out / "task-run.json", {"PASS": True, "task_id": "water-domain"})
    with pytest.raises(ValueError): pipeline.assess(case[1], case[0], {"water-domain": out})
