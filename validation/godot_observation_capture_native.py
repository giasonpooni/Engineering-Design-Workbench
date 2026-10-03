"""Actual Godot viewport capture checks. Run under a real X11/Mesa display."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
from unittest.mock import patch

from ciw.control_contracts import bytes_ref, save_new
from ciw.godot_capture import capture, demo, inspect_capture
from ciw.simulation_capture import CHANNELS, OPERATION, project, selection, validate_result
from ciw.simulation_control import open_workspace


def run(executable: Path, binary_hash: str, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    checks = []
    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    summary = demo(executable, binary_hash, output / "demo")
    check(summary["source_execution_count"] == 15 and summary["source_process"]["returncode"] == 0, "actual_source_completed_and_closed")
    source = output / "demo/source/workspace.json"
    original_bytes = source.read_bytes()
    base = json.loads(original_bytes)
    results = {}
    for item in summary["captures"]:
        root = output / "demo" / item["name"]
        result = json.loads((root / "capture.json").read_text(encoding="utf-8"))
        results[item["name"]] = result
        png = (output / "demo" / item["image_file"]).read_bytes()
        validate_result(result, png)
        check(result["execution_id"] != item["source_execution_id"] and result["data"]["image"]["sha256"] == bytes_ref(png), item["name"] + "_image_and_occurrence_bound")
        inspect_capture(root)
        retained = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
        check(len(retained["executions"]) == len(retained["results"]) == 16, item["name"] + "_one_capture_appended")
        view = result["data"]["view"]
        check(view["channels"] == CHANNELS and all(s is None or s["quantity"] in CHANNELS for s in view["selected_samples"]), item["name"] + "_only_selected_positions")
        old = {r["result_id"]: r for r in base["results"]}
        current = {r["result_id"]: r for r in retained["results"]}
        check(all(current[k] == r for k, r in old.items()) and retained["run"] == base["run"], item["name"] + "_original_evidence_unchanged")
    current = results["current"]["data"]["view"]
    delayed = results["delayed"]["data"]["view"]
    missing = results["unavailable"]["data"]["view"]
    check(current["sample_time_s"] == 10 / 64 and current["available_at"]["time_s"] == 10 / 64, "current_sample_time")
    check(delayed["sample_time_s"] == 8 / 64 and delayed["available_at"]["time_s"] == 10 / 64, "delayed_sample_not_world_time")
    check(missing["availability"] == "no_samples" and missing["position_xyz_m"] is None
          and results["unavailable"]["data"]["native"]["marker_count"] == 0, "no_invented_empty_position")
    check(current["position_xyz_m"] == [1.3125, 2.361328125, -2.84375], "asymmetric_xyz_matches_dyadic_reference")
    check(delayed["position_xyz_m"] == [1.25, 2.3046875, -2.875], "delayed_xyz_matches_dyadic_reference")
    # Once source generation is complete, no simulation provider/controller may
    # be constructed by capture or retained reinspection. The renderer still runs.
    src_result = results["current"]["data"]["source_result"]
    options = dict(expected_workspace_sha256=bytes_ref(original_bytes), result_id=src_result["result_id"],
        entity_id="projectile", sample_index=10, camera="front", executable=executable, executable_sha256=binary_hash)
    with patch("ciw.godot_simulation.GodotProjectile", side_effect=AssertionError("no simulation launch")), \
         patch("ciw.simulation_control.SimulationControl", side_effect=AssertionError("no simulation control")):
        front = capture(source, output_dir=output / "front", **options)
        for name in ("current", "delayed", "unavailable"):
            inspect_capture(output / "demo" / name)
        inspect_capture(output / "front")
    check(front["data"]["view"] == current and front["data"]["native"]["position_xyz_m"] == current["position_xyz_m"], "camera_change_preserves_source_coordinates")
    check(front["data"]["image"]["sha256"] != results["current"]["data"]["image"]["sha256"], "different_view_has_different_pixels")
    check(front["execution_id"] != results["current"]["execution_id"], "second_view_has_fresh_capture_execution")
    with patch("subprocess.Popen", side_effect=AssertionError("no process on inspection")):
        inspect_capture(output / "front")
    check(True, "provider_and_renderer_free_reinspection")
    # Invalid selection refuses before requested output or executable creation.
    try:
        capture(source, output_dir=output / "invalid-selection", **{**options, "sample_index": 99})
    except ValueError:
        check(not (output / "invalid-selection").exists(), "invalid_selection_publishes_nothing")
    else:
        raise AssertionError("Invalid sample unexpectedly accepted")
    # A real failed display launch must remain a recorded failed render, without
    # altering source simulation state or returning a fabricated image.
    with patch.dict(os.environ, {"DISPLAY": ":54321", "WAYLAND_DISPLAY": "net-missing-display"}):
        try:
            capture(source, output_dir=output / "failed-render", **options)
        except ValueError:
            refused = json.loads((output / "failed-render/workspace.json").read_text(encoding="utf-8"))
            attempt = [e for e in refused["executions"] if e["operation_id"] == OPERATION]
            check(len(attempt) == 1 and attempt[0]["status"] == "refused" and attempt[0]["result_id"] is None,
                  "actual_failed_render_retained_as_refusal")
            check(not (output / "failed-render/capture.json").exists(), "failed_render_has_no_completion")
        else:
            raise AssertionError("Missing display unexpectedly rendered")
    check(source.read_bytes() == original_bytes, "all_renders_leave_source_bytes_unchanged")
    report = {"status": "passed", "checks": checks, "count": len(checks),
              "native_engine": results["current"]["data"]["native"]["engine_version"],
              "video_adapter": results["current"]["data"]["native"]["video_adapter"],
              "actual_native_render_count": 4, "intentional_failed_render_count": 1,
              "verification_status": "not_verified"}
    save_new(output / "native-capture-qualification.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--godot-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.godot, args.godot_sha256, args.output_dir), indent=2))
