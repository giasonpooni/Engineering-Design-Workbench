"""Qualify production work orders using actual, explicitly bound Godot processes."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

from ciw import game_trace, game_workflow as game
from ciw.control_contracts import load, save_new
from ciw.interactive_simulation import file_sha
from ciw.production import Worker, inspect_production, run_production
from ciw.production_gates import game_gates
from ciw.production_workflow import game_plan, game_registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--adapter-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=False)
    binding = game.GodotCourierBinding(args.godot, args.adapter_root, expected_sha256=file_sha(args.godot))
    workers = (Worker("godot-capture", (game.CAPTURE_OP,)),)
    checks, campaigns, captures = [], {}, {}
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    def campaign(name, fault, repair, expected, attempts, selected_binding=binding):
        source = game.make_run(game.courier_scenario())
        before = deepcopy(source)
        specification = game_plan(source, fault=fault, repair=repair)
        directory = root / name
        report = run_production(source, specification, game_registry(selected_binding), workers, game_gates(), directory)
        check(name + ": expected disposition", report["jobs"]["courier-candidate"]["status"] == expected)
        check(name + ": bounded attempts", report["attempt_count"] == attempts)
        check(name + ": source unchanged", source == before)
        workspace = load(directory / "session/workspace.json")
        check(name + ": native runtime", all(e["runtime"]["execution_mode"] == "native_process" for e in workspace["executions"]))
        check(name + ": separate verification", all(r["verification_id"] is None and r["verification_status"] == "not_verified" for r in workspace["results"]))
        check(name + ": retained occurrence uniqueness", len({e["execution_id"] for e in workspace["executions"]}) == report["execution_count"])
        frozen = {p: p.read_bytes() for p in directory.rglob("*.json")}
        with patch("subprocess.Popen", side_effect=AssertionError("Inspection started a process")), patch.object(game.GodotCourierBinding, "invoke", side_effect=AssertionError("Inspection called Godot")):
            inspected = inspect_production(directory, game_gates())
        check(name + ": provider-free inspection", inspected["fresh_execution"] is False and inspected["status"] == report["status"])
        check(name + ": inspection preserves bytes", all(p.read_bytes() == raw for p, raw in frozen.items()))
        if expected != "accepted":
            check(name + ": downstream blocked", report["jobs"]["dependent-regression"]["status"] == "blocked")
        if repair and fault in {"early-knowledge", "duplicate-reward"}:
            check(name + ": failed attempt retained", load(directory / "attempt-0001.json")["status"] == "rejected")
            check(name + ": corrected attempt retained", load(directory / "attempt-0002.json")["status"] == "accepted")
        campaigns[name] = {k: report[k] for k in ("status", "attempt_count", "execution_count", "result_count")}
        # Select this work order's final candidate by its retained receipt, not
        # the last Session result (which may be the downstream regression).
        candidate_ref = report["jobs"]["courier-candidate"]["attempts"][-1]
        candidate_receipt = load(directory / candidate_ref["name"])
        candidate_graph = load(directory / candidate_receipt["graph"]["name"])
        candidate_payload = candidate_graph["nodes"]["candidate"]
        if candidate_payload["status"] == "completed":
            captures[name] = candidate_payload["result"]
            check(name + ": comparison selects primary candidate", captures[name]["parameters"]["nonce"] ==
                  specification["jobs"][0]["attempts"][candidate_receipt["attempt_index"]]["nodes"][0]["parameters"]["nonce"])
        return report
    campaign("baseline", "none", True, "accepted", 2)
    campaign("early-knowledge-repair", "early-knowledge", True, "accepted", 3)
    campaign("duplicate-reward-repair", "duplicate-reward", True, "accepted", 3)
    campaign("missing-evidence", "drop-sample", True, "held", 1)
    campaign("exhausted", "early-knowledge", False, "rejected", 1)
    # A real engine process with an explicitly substituted qualification adapter
    # exits unsuccessfully. This is not a mocked runtime failure or a game change.
    with tempfile.TemporaryDirectory(prefix="net-broken-production-adapter-") as directory:
        adapter = Path(directory)
        shutil.copy2(args.adapter_root / "recorder.gd", adapter / "recorder.gd")
        (adapter / "courier.gd").write_text("extends SceneTree\nfunc _initialize():\n\tquit(7)\n", encoding="utf-8")
        broken = game.GodotCourierBinding(args.godot, adapter, expected_sha256=file_sha(args.godot))
        refused = campaign("native-refusal", "none", True, "refused", 1, broken)
        check("native-refusal: no fabricated result", refused["result_count"] == 0)
    reference = captures["baseline"]
    for name in ("early-knowledge-repair", "duplicate-reward-repair"):
        candidate = captures[name]
        comparison = game_trace.comparison(candidate["data"], reference["data"], candidate["execution_id"], reference["execution_id"], atol=0, rtol=0)
        check(name + ": original comparator matches baseline", comparison["status"] == "PASS")
        save_new(root / (name + "-comparison.json"), comparison)
    report = {"schema": "ciw.production-qualification.v1", "runtime": binding.runtime_identity(), "source_class": "synthetic_fixture",
              "campaigns": campaigns, "check_count": len(checks), "passed_checks": checks,
              "native_process_attempts": sum(c["execution_count"] for c in campaigns.values()),
              "successful_capture_results": sum(c["result_count"] for c in campaigns.values()),
              "scope": "existing courier adapter only; no 1792 world, LLM worker, Blender asset, visual or physical qualification"}
    save_new(root / "qualification.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
