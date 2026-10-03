"""Run the REAL Godot game-trace campaign against an installed NET package.

No native skip/fallback. Headless logical-tick qualification, not rendering,
physics, gameplay quality, historical evidence or a shipped game integration.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import ciw
from ciw import game_trace as c
from ciw import game_workflow as g
from ciw.control_contracts import save_new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--adapter-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=False)
    binding = g.GodotCourierBinding(args.godot, args.adapter_root, expected_sha256=g.file_sha(Path(args.godot)))
    checks = []
    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)
    def latest(session, operation):
        return [r for r in session.results.values() if r["operation_id"] == operation][-1]
    baseline, source = g.run_case(g.courier_scenario(), binding, output / "baseline")
    source_bytes = (output / "baseline/workspace.json").read_bytes()
    check("baseline authored rules pass", latest(baseline, g.AUDIT_OP)["data"]["status"] == "PASS")
    scenario, trace = c.unpack(source["data"])
    check("actual Godot engine", trace["engine"] == "godot" and trace["engine_version"].startswith("4.5.2"))
    check("native rather than double", source["runtime"]["execution_mode"] == "native_process")
    check("36 selected samples and five events", len(trace["samples"]) == 36 and len(trace["events"]) == 5)
    repeated, repeat = g.extend_case(output / "baseline/workspace.json", binding, output / "reproduced",
        source_execution_id=source["execution_id"], reproduce=True)
    check("fresh execution identity", repeat["execution_id"] != source["execution_id"])
    check("fresh request nonce", repeat["parameters"]["nonce"] != source["parameters"]["nonce"])
    check("same executable and adapters", repeat["runtime"] == source["runtime"])
    check("reproduction comparison passes", latest(repeated, g.COMPARE_OP)["data"]["status"] == "PASS")
    check("baseline file remains byte-identical", (output / "baseline/workspace.json").read_bytes() == source_bytes)
    path = output / "reproduced/workspace.json"
    expected = [("early-knowledge", "FAIL", 1), ("duplicate-reward", "FAIL", 7), ("drop-sample", "INDETERMINATE", None), ("none", "PASS", None)]
    for index, (fault, status, tick) in enumerate(expected):
        target = output / f"candidate-{index}-{fault}"
        session, candidate = g.extend_case(path, binding, target, source_execution_id=source["execution_id"], reproduce=False, fault=fault)
        report = latest(session, g.COMPARE_OP)["data"]
        check(f"{fault}: capture completed", candidate["runtime"]["execution_mode"] == "native_process")
        check(f"{fault}: audit status", latest(session, g.AUDIT_OP)["data"]["status"] == status)
        check(f"{fault}: comparison status", report["status"] == status)
        check(f"{fault}: first divergence", report["first_divergence_tick"] == tick)
        check(f"{fault}: baseline preserved", session.results[source["result_id"]] == source)
        path = target / "workspace.json"
    check("all capture/check/comparison history retained", len(session.executions) == len(session.results) == 17)
    check("old failures remain after correction", any(r["data"].get("status") == "FAIL" for r in session.results.values()))
    before_results, before_executions = deepcopy(session.results), deepcopy(session.executions)
    with patch("subprocess.Popen", side_effect=AssertionError("Inspection launched a runtime")), patch.object(g.GodotCourierBinding, "invoke", side_effect=AssertionError("Inspection invoked a provider")):
        report = g.inspect(path)
        reopened = g.open_saved(path, output / "offline-reopened")
    check("provider-free history is unchanged", reopened.results == before_results and reopened.executions == before_executions)
    check("inspection reports all executions", len(report["executions"]) == 17)
    save_new(output / "observations.json", c.observations(source["data"], source["execution_id"]))
    with tempfile.TemporaryDirectory(prefix="game-runtime-failure-") as tmp:
        root = Path(tmp)
        (root / "recorder.gd").write_bytes(binding.scripts["recorder.gd"])
        (root / "courier.gd").write_text('extends SceneTree\nfunc _init() -> void:\n\tquit(9)\n', encoding="utf-8")
        broken = g.GodotCourierBinding(args.godot, root, expected_sha256=g.file_sha(Path(args.godot)))
        try:
            g.run_case(g.courier_scenario(), broken, output / "runtime-refused")
        except ValueError:
            pass
        else:
            raise AssertionError("Failed native process was accepted")
    refused = g.open_saved(output / "runtime-refused/workspace.json", output / "refusal-reopened")
    check("native failure retains one attempt", len(refused.executions) == 1)
    check("native failure has no fabricated result", not refused.results)
    check("checks never manufacture verification identities", all(r["verification_id"] is None and r["verification_status"] == "not_verified" for r in session.results.values()))
    check("installed package outside repository", "site-packages" in str(Path(ciw.__file__).resolve()))
    final = {"schema": "ciw.game-native-qualification.v1", "status": "PASS", "checks": checks,
             "check_count": len(checks), "native_runtime": binding.identity, "engine_version": trace["engine_version"],
             "package_location": str(Path(ciw.__file__).resolve()), "retained_execution_count": 17,
             "retained_result_count": 17, "separate_refusal_count": 1,
             "scope": "Linux headless Godot logical-tick fixture; no visual, physics or real-game qualification"}
    save_new(output / "qualification.json", final)
    print(json.dumps(final, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
