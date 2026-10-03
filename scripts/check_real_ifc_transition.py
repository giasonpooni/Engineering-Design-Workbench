"""Retain actual positive/negative IFC runs with bounded verification evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import runpy
import subprocess
import sys
from time import perf_counter

from ciw.control_contracts import load, save_new
from ciw.ifc_transition import execute_ifc, verify_ifc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cse", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output_dir.exists():
        raise FileExistsError("Use a fresh output directory to retain both occurrences")
    args.output_dir.mkdir(parents=True)
    previous_argv = sys.argv
    try:
        sys.argv = ["make_sources.py", str(args.output_dir / "declarations")]
        runpy.run_path(str(root / "examples/ifc-transition/make_sources.py"), run_name="__main__")
    finally:
        sys.argv = previous_argv
    reports = []
    for name, ifc in (("room", root / "examples/bim-quantity/room.ifc"),
                      ("public-wall", root / "examples/ifc-transition/buildingSMART-wall-opening-window.ifc")):
        declarations = args.output_dir / "declarations"
        start = perf_counter()
        run = execute_ifc(ifc.read_bytes(), (declarations / (name + "-observation.json")).read_bytes(),
                          load(declarations / (name + "-spec.json")), {"cse": args.cse})
        execution_seconds = perf_counter() - start
        save_new(args.output_dir / (name + "-run.json"), run)
        start = perf_counter()
        summary = verify_ifc(load(args.output_dir / (name + "-run.json")), {"cse": args.cse})
        verification_seconds = perf_counter() - start
        save_new(args.output_dir / (name + "-verification.json"), summary)
        expected = ("accepted", "QUALIFIED") if name == "room" else ("refused", "REFUSED")
        if (summary["native_status"], summary["qualification"]) != expected:
            raise AssertionError(f"Unexpected {name} mapping outcome: {summary}")
        if summary["state_admission_performed"] or summary["canonical_state_mutated"]:
            raise AssertionError("Qualification cannot admit state")
        if name == "room" and summary["transition_readiness"] != "READY_FOR_AUTHORITY_REVIEW":
            raise AssertionError("Positive control did not reach authority review")
        reports.append({"case": name, **summary,
                        "elapsed_seconds": {"audit_execution_and_reproduction": execution_seconds,
                                            "retained_verification_and_current_runtime_check": verification_seconds}})
    report = {"source_base_commit": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
              "execution_source_matches_commit": not subprocess.check_output(
                  ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--",
                   "src", "scripts", "examples", "tests", "pyproject.toml"], text=True).strip(),
              "python": sys.version, "platform": platform.platform(), "cases": reports,
              "timing_scope": "single-run diagnostic; no throughput or scaling claim"}
    save_new(args.output_dir / "experiment-summary.json", report)
    print(json.dumps({"status": "passed", "cases": [{"case": row["case"], "qualification": row["qualification"],
                                                      "transition_readiness": row["transition_readiness"]} for row in reports]}))


if __name__ == "__main__":
    main()
