"""Actual Godot qualification of the 1792-owned Foundry operation.

Normal campaigns use unchanged pinned game source. Missing-output and refusing
campaigns use explicitly modified disposable diagnostic adapter copies.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
from unittest.mock import patch

from ciw.control_contracts import bytes_ref, load, save_new
from ciw.foundry_project import ENTRYPOINT, FILES, snapshot
from ciw.foundry_workflow import compile_order, run_order, inspect_order, report_order, export_artifact, _accepted_result
from ciw.interactive_simulation import file_sha
from ciw.production import _read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve(); root.mkdir(parents=True, exist_ok=False)
    game = args.game_root.resolve()
    digest = file_sha(args.godot)
    lock, sources = snapshot(game)
    results = {}
    cases = [("baseline", 2, True, "completed", 2), ("repair", 1, True, "completed", 3),
             ("exhausted", 1, False, "incomplete", 1)]
    for name, trips, repair, status, count in cases:
        order, campaign = root / (name + "-order"), root / name
        compile_order(game, order, candidate_trips=trips, repair=repair)
        report = run_order(order, game, args.godot, digest, campaign)
        assert report["status"] == status and report["attempt_count"] == count, report
        assert report["result_count"] == count, report
        results[name] = report
    assert _read(root / "repair", "attempt-0001.json")["status"] == "rejected"
    assert _read(root / "repair", "attempt-0002.json")["status"] == "accepted"
    assert results["exhausted"]["jobs"]["water-round-regression"]["status"] == "blocked"
    # Actual native process diagnostics, with their own distinct locked source.
    for name in ("missing-output", "native-refusal"):
        altered = root / (name + "-source")
        for path, raw in sources.items():
            target = altered / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        adapter = altered / ENTRYPOINT
        text = adapter.read_text()
        if name == "missing-output":
            needle = '\tvar encoded := JSON.stringify(response, "", true, true)'
            assert text.count(needle) == 1
            text = text.replace(needle, '\tresponse.samples.clear() # qualification-only observation-loss injection\n' + needle)
        else:
            text = 'extends SceneTree\nfunc _initialize() -> void:\n\tpush_error("FOUNDRY qualification-only native refusal")\n\tquit(2)\n'
        adapter.write_text(text)
        order, campaign = root / (name + "-order"), root / name
        compile_order(altered, order)
        report = run_order(order, altered, args.godot, digest, campaign)
        expected = "held" if name == "missing-output" else "refused"
        assert report["status"] == "incomplete" and report["attempt_count"] == 1, report
        assert report["jobs"]["water-round"]["status"] == expected, report
        assert report["jobs"]["water-round-regression"]["status"] == "blocked", report
        assert report["result_count"] == (1 if name == "missing-output" else 0), report
        results[name] = report
    # Pin all retained bytes before pure inspection and export.
    original = {p: bytes_ref(p.read_bytes()) for p in root.rglob("*.json")}
    with patch("subprocess.Popen", side_effect=AssertionError("offline inspection started a process")):
        for name, report in results.items():
            checked = inspect_order(root / name)
            assert checked["status"] == report["status"]
            assert checked["fresh_execution"] is False
        baseline = _accepted_result(root / "baseline", inspect_order(root / "baseline"), "water-round")[1]
        repaired = _accepted_result(root / "repair", inspect_order(root / "repair"), "water-round")[1]
        values = [json.loads(r["data"]["source_utf8"]) for r in (baseline, repaired)]
        assert values[0]["request_nonce"] != values[1]["request_nonce"]
        for value in values: value.pop("request_nonce")
        assert values[0] == values[1], "corrected PRIMARY candidate differs from baseline"
        manifest = export_artifact(root / "repair", root / "accepted-artifact")
        assert manifest["source_result_id"] == repaired["result_id"]
        assert (root / "accepted-artifact/water-round-observations.json").read_bytes() == repaired["data"]["source_utf8"].encode()
        metrics = report_order(root / "repair")
        assert metrics["accepted_jobs"] == 2 and metrics["rejected_attempts"] == 1
        for name in ("exhausted", "missing-output", "native-refusal"):
            try: export_artifact(root / name, root / (name + "-forbidden-export"))
            except ValueError: pass
            else: raise AssertionError("unaccepted artifact exported")
            assert not (root / (name + "-forbidden-export")).exists()
    assert all(bytes_ref(p.read_bytes()) == digest for p, digest in original.items())
    assert snapshot(game)[0] == lock, "qualification changed original game source"
    qualification = {"schema": "ciw.foundry-native-qualification.v1", "status": "PASS",
        "godot_sha256": file_sha(args.godot), "normal_source_lock": lock,
        "native_attempts": sum(r["attempt_count"] for r in results.values()),
        "capture_results": sum(r["result_count"] for r in results.values()),
        "campaigns": {name: {"status": r["status"], "attempts": r["attempt_count"], "results": r["result_count"],
                             "jobs": {k: v["status"] for k, v in r["jobs"].items()}} for name, r in results.items()},
        "corrected_primary_matches_baseline": True, "offline_inspection_processes": 0,
        "original_game_source_unchanged": True, "accepted_export": manifest, "metrics": metrics,
        "scope": "game-owned domain/clock/save workflow; diagnostic source copies explicitly labelled; not renderer or playability validation"}
    save_new(root / "qualification.json", qualification)
    print(json.dumps(qualification, indent=2))


if __name__ == "__main__":
    main()
