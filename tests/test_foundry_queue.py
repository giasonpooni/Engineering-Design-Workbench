"""Exercise the real pipeline and packet boundary; no native provider is needed."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from ciw import foundry_pipeline as pipeline, foundry_packets as packets
from ciw.control_contracts import load, save_new
from ciw.foundry_pipeline_cli import main
from ciw.foundry_queue import queue, prepare_batch
from ciw.foundry_batch_review import check_batch
from ciw.operations.runner import seal


@pytest.fixture
def case(tmp_path):
    root = tmp_path / "game"
    root.mkdir()
    (root / "notes.txt").write_text("TEST FIXTURE, not actual 1792 acceptance\n")
    (root / "project.godot").write_text("config_version=5\n")
    project = pipeline.create_project("1792-queue-fixture", root, tmp_path / "project")
    return root, project


def spec(*ids):
    return {"schema": "ciw.foundry-batch-spec.v1", "assignments": [
        {"task_id": name, "assignee": "test-author", "writable": [],
         "context": ["notes.txt"], "max_changed_bytes": 131072} for name in ids]}


def test_focus_keeps_full_prerequisite_closure_without_dispatch(case):
    with patch("subprocess.Popen", side_effect=AssertionError("unexpected execution")):
        result = queue(*reversed(case), targets=["slice-journey", "art-target"])
    rows = {r["task_id"]: r for r in result["tasks"]}
    assert result["frontier"] == ["vision"]
    assert rows["slice-journey"]["root_blockers"] == ["vision"]
    assert "art-target" in rows and "historical-scope" in rows
    assert "release-signoff" not in rows and "water-domain" not in rows
    assert rows["vision"]["next_action"] == "human_review"
    assert result["fresh_execution"] is False


def test_unfiltered_queue_distinguishes_native_and_review(case):
    result = queue(case[1], case[0])
    assert set(result["frontier"]) == {"vision", "water-domain"}
    water = next(r for r in result["tasks"] if r["task_id"] == "water-domain")
    assert water["next_action"] == "run_installed_recipe"
    assert water["installed_recipe"] == "1792.water-round.v1"


@pytest.mark.parametrize("targets", [["missing"], ["vision", "vision"], "vision", [1]])
def test_bad_focus_refuses(case, targets):
    with pytest.raises(ValueError): queue(case[1], case[0], targets=targets)


def test_batch_uses_original_packet_ids_and_candidate_checker(case, tmp_path):
    root, project = case
    baseline = packets.inventory(root)
    out = tmp_path / "batch"
    with patch("subprocess.Popen", side_effect=AssertionError("unexpected execution")):
        result = prepare_batch(project, root, spec("vision", "water-domain"), out)
        for item in result["packets"]:
            packet = load(out / item["path"])
            checked = packets.check_candidate(packet, project, pipeline.task_for(project, item["task_id"]),
                root, expected_packet_id=item["packet_id"])
            assert checked["status"] == "scope_passed"
            assert checked["quality_acceptance"] == "not_performed"
            assert packet["rights"] == dict(execute=False, approve=False, merge=False, release=False)
    assert load(out / "batch.json") == result
    assert packets.inventory(root) == baseline
    assert result["executed"] is False
    assert result["conflicts"]["parallel_execution"] == "not_performed"
    with pytest.raises(FileExistsError): prepare_batch(project, root, spec("vision"), out)
    assert load(out / "batch.json") == result


@pytest.mark.parametrize("mutation", ["blocked", "duplicate", "protected", "native_write", "unknown", "too_many", "extra", "empty"])
def test_full_preflight_refuses_without_output(case, tmp_path, mutation):
    value = spec("vision", "water-domain")
    if mutation == "blocked": value["assignments"][1]["task_id"] = "slice-journey"
    if mutation == "duplicate": value["assignments"][1]["task_id"] = "vision"
    if mutation == "protected": value["assignments"][0]["writable"] = ["project.godot"]
    if mutation == "native_write": value["assignments"][1]["writable"] = ["new.txt"]
    if mutation == "unknown": value["assignments"][1]["task_id"] = "not-installed"
    if mutation == "too_many": value["assignments"] *= 9
    if mutation == "extra": value["execute"] = True
    if mutation == "empty": value["assignments"] = []
    out = tmp_path / "refused"
    with pytest.raises(ValueError): prepare_batch(case[1], case[0], value, out)
    assert not out.exists()


def test_drift_invalidates_assignment_even_unaffected_native_task(case, tmp_path):
    (case[0] / "notes.txt").write_text("changed")
    status = queue(case[1], case[0])
    assert next(r for r in status["tasks"] if r["task_id"] == "vision")["status"] == "stale"
    with pytest.raises(ValueError, match="drift"):
        prepare_batch(case[1], case[0], spec("water-domain"), tmp_path / "batch")
    assert not (tmp_path / "batch").exists()


def test_review_advances_frontier_without_inventing_acceptance(case, tmp_path):
    root, project = case
    artifact = tmp_path / "artifact"; artifact.mkdir()
    (artifact / "review.txt").write_text("TEST FIXTURE ONLY")
    review = tmp_path / "review"
    receipt = pipeline.review_task(project, "vision", root, artifact, review,
        reviewer="fixture-reviewer", producer="fixture-producer", decision="approved")
    evidence = {"vision": review}
    result = queue(project, root, evidence, targets=["art-target"])
    assert result["frontier"] == ["historical-scope"]
    vision = next(r for r in result["tasks"] if r["task_id"] == "vision")
    assert vision["evidence_id"] == receipt["record_digest"]
    assert vision["status"] == "operator_attested"
    out = tmp_path / "batch"
    prepare_batch(project, root, spec("historical-scope", "rights-register"), out, evidence)
    with pytest.raises(ValueError, match="already satisfied"):
        prepare_batch(project, root, spec("vision"), tmp_path / "completed", evidence)
    (review / "artifacts/review.txt").write_text("tampered")
    with pytest.raises(ValueError, match="changed"):
        queue(project, root, evidence)


def test_write_read_conflicts_remain_visible(case, tmp_path):
    value = spec("vision", "water-domain")
    value["assignments"][0]["writable"] = ["notes.txt"]
    result = prepare_batch(case[1], case[0], value, tmp_path / "batch")
    assert result["conflicts"]["conflicts"][0]["write_read"] == ["notes.txt"]


def test_output_containment_and_symlinks(case, tmp_path):
    with pytest.raises(ValueError, match="outside"):
        prepare_batch(case[1], case[0], spec("vision"), case[0] / "batch")
    link = tmp_path / "linked"
    try: link.symlink_to(case[0], target_is_directory=True)
    except OSError: pytest.skip("symlink unavailable")
    with pytest.raises(ValueError):
        prepare_batch(case[1], case[0], spec("vision"), link / "batch")


def test_readiness_changes_refuse_before_output(case, tmp_path):
    original = queue(case[1], case[0], targets=["vision"])
    changed = deepcopy(original)
    changed["tasks"][0]["evidence_id"] = "different-evidence"
    out = tmp_path / "batch"
    with patch("ciw.foundry_queue.queue", side_effect=[original, changed]):
        with pytest.raises(ValueError, match="Readiness changed"):
            prepare_batch(case[1], case[0], spec("vision"), out)
    assert not out.exists()


def test_cli_batch_and_queue(case, tmp_path, capsys):
    project = tmp_path / "project/project.json"
    assert main(["queue", str(project), "--source-root", str(case[0]), "--target", "art-target"]) == 0
    assert json.loads(capsys.readouterr().out)["frontier"] == ["vision"]
    save_new(tmp_path / "spec.json", spec("vision"))
    args = ["batch", str(project), "--source-root", str(case[0]), "--spec", str(tmp_path / "spec.json"),
            "--output-dir", str(tmp_path / "batch")]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["executed"] is False
    assert main(args) == 1


def issued(case, tmp_path):
    out = tmp_path / "batch"
    value = prepare_batch(case[1], case[0], spec("vision", "water-domain"), out)
    return out, value["record_digest"]


def test_batch_review_reuses_scope_checker_without_dispatch(case, tmp_path):
    directory, identity = issued(case, tmp_path)
    with patch("subprocess.Popen", side_effect=AssertionError("unexpected execution")):
        result = check_batch(case[1], case[0], directory, expected_batch_id=identity,
            candidates={"vision": case[0], "water-domain": case[0]}, destination=tmp_path / "review")
    assert result["status"] == "ready_for_quality_review"
    assert result["quality_acceptance"] == "not_performed"
    assert all(r["scope_check"]["status"] == "scope_passed" for r in result["candidates"])
    assert load(tmp_path / "review/review.json") == result
    assert "integration remain outstanding" in (tmp_path / "review/REVIEW.md").read_text()
    with pytest.raises(FileExistsError):
        check_batch(case[1], case[0], directory, expected_batch_id=identity,
            candidates={}, destination=tmp_path / "review")


def test_missing_refused_and_unreadable_candidates_are_retained(case, tmp_path):
    directory, identity = issued(case, tmp_path)
    candidate = tmp_path / "bad"; candidate.mkdir()
    (candidate / "injected.gd").write_text("unexpected")
    report = check_batch(case[1], case[0], directory, expected_batch_id=identity,
        candidates={"vision": candidate})
    assert report["status"] == "incomplete"
    assert [r["status"] for r in report["candidates"]] == ["scope_refused", "missing_candidate"]
    report = check_batch(case[1], case[0], directory, expected_batch_id=identity,
        candidates={"vision": tmp_path / "absent"})
    assert report["candidates"][0]["status"] == "candidate_unreadable"
    assert report["candidates"][0]["reason"]


@pytest.mark.parametrize("path", ["batch.json", "queue.json", "spec.json", "vision/packet.json"])
def test_review_refuses_tampering_even_resealed_batch(case, tmp_path, path):
    directory, identity = issued(case, tmp_path)
    value = load(directory / path)
    if path == "batch.json":
        value["conflicts"]["parallel_execution"] = "performed"
    elif path == "queue.json": value["frontier"] = []
    elif path == "spec.json": value["assignments"][0]["assignee"] = "other"
    else: value["assignee"] = "other"
    if "record_digest" in value:
        value.pop("record_digest")
        value = seal(value)
    (directory / path).write_text(json.dumps(value))
    with pytest.raises(ValueError):
        check_batch(case[1], case[0], directory, expected_batch_id=identity,
            candidates={}, destination=tmp_path / "review")
    assert not (tmp_path / "review").exists()


def test_current_source_drift_prevents_ready_even_if_old_candidate_passes(case, tmp_path):
    import shutil
    directory, identity = issued(case, tmp_path)
    candidate = tmp_path / "candidate"
    shutil.copytree(case[0], candidate)
    (case[0] / "notes.txt").write_text("new source baseline")
    report = check_batch(case[1], case[0], directory, expected_batch_id=identity,
        candidates={"vision": candidate, "water-domain": candidate})
    assert all(r["scope_check"]["status"] == "scope_passed" for r in report["candidates"])
    assert all(not r["ready_for_quality_review"] for r in report["candidates"])
    assert report["status"] == "incomplete"


def test_review_unknown_candidate_and_contained_output_refuse(case, tmp_path):
    directory, identity = issued(case, tmp_path)
    with pytest.raises(ValueError, match="outside this batch"):
        check_batch(case[1], case[0], directory, expected_batch_id=identity,
            candidates={"unknown": case[0]})
    for output in [case[0] / "review", directory / "review"]:
        with pytest.raises(ValueError, match="outside"):
            check_batch(case[1], case[0], directory, expected_batch_id=identity,
                candidates={}, destination=output)
        assert not output.exists()


def test_incomplete_batch_and_linked_packet_refuse(case, tmp_path):
    directory, identity = issued(case, tmp_path)
    packet = directory / "vision/packet.json"
    original = tmp_path / "original.json"
    packet.rename(original)
    try: packet.symlink_to(original)
    except OSError: pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="Symlinks"):
        check_batch(case[1], case[0], directory, expected_batch_id=identity, candidates={})
    packet.unlink(); original.rename(packet)
    (directory / "batch.json").unlink()
    with pytest.raises(OSError):
        check_batch(case[1], case[0], directory, expected_batch_id=identity, candidates={})


def test_batch_check_cli_returns_incomplete_and_complete(case, tmp_path, capsys):
    directory, identity = issued(case, tmp_path)
    args = ["batch-check", str(tmp_path / "project/project.json"), "--source-root", str(case[0]),
            "--batch-dir", str(directory), "--batch-id", identity]
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "incomplete"
    assert main(args + ["--candidate", "vision="+str(case[0]), "--candidate", "water-domain="+str(case[0])]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready_for_quality_review"
