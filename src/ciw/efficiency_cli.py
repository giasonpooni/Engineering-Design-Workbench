"""Create and compare measured investigation-efficiency records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .investigation_efficiency import (
    compare_trials, inspect_trial, trial_from_spec, validate_comparison,
)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net efficiency", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("spec", type=Path)
    create.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("trial", type=Path)

    compare = commands.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--output", type=Path, required=True)

    inspect_comparison = commands.add_parser("inspect-comparison")
    inspect_comparison.add_argument("comparison", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = trial_from_spec(load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "created",
                "record_digest": value["record_digest"],
                "task_id": value["task_id"],
                "method": value["method"],
                "output": str(args.output),
            }))
            return 0
        if args.command == "inspect":
            print(json.dumps(inspect_trial(load(args.trial)), indent=2))
            return 0
        if args.command == "compare":
            value = compare_trials(load(args.baseline), load(args.candidate))
            save_new(args.output, value)
            print(json.dumps({
                "status": "compared",
                "record_digest": value["record_digest"],
                "aggregate_winner": False,
                "output": str(args.output),
            }))
            return 0
        value = validate_comparison(load(args.comparison))
        print(json.dumps({
            "schema": "ciw.investigation-comparison-inspection.v1",
            "record_digest": value["record_digest"],
            "task_id": value["task_id"],
            "baseline_method": value["baseline_method"],
            "candidate_method": value["candidate_method"],
            "metric_comparisons": value["metric_comparisons"],
            "aggregate_winner": False,
            "general_domain_multiplier": False,
        }, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
