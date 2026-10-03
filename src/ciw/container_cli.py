"""Create and inspect backend-neutral Container / Experiment Calculus records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .container_calculus import (
    composition_from_spec,
    container_from_spec,
    summarize_telemetry,
    telemetry_from_spec,
    validate_composition,
    validate_container,
)
from .control_contracts import load, save_new


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net container", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("spec", type=Path)
    create.add_argument("--output", type=Path, required=True)

    compose = commands.add_parser("compose")
    compose.add_argument("spec", type=Path)
    compose.add_argument("--output", type=Path, required=True)

    telemetry = commands.add_parser("telemetry")
    telemetry.add_argument("spec", type=Path)
    telemetry.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("record", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            value = container_from_spec(load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "created",
                "container_id": value["container_id"],
                "record_digest": value["record_digest"],
                "execution_authority": False,
                "output": str(args.output),
            }))
            return 0
        if args.command == "compose":
            value = composition_from_spec(load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "created",
                "composition_id": value["composition_id"],
                "containers": len(value["containers"]),
                "provider_execution": False,
                "output": str(args.output),
            }))
            return 0
        if args.command == "telemetry":
            value = telemetry_from_spec(load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "recorded",
                "container_id": value["container_id"],
                "record_digest": value["record_digest"],
                "physical_theory_established": False,
                "output": str(args.output),
            }))
            return 0
        value = load(args.record)
        if value.get("schema") == "ciw.container-spec.v1":
            checked = validate_container(value)
            print(json.dumps({
                "schema": "ciw.container-spec-inspection.v1",
                "container_id": checked["container_id"],
                "operators": checked["operators"],
                "declared_behaviors": checked["declared_behaviors"],
                "executable_binding": False,
                "runtime_selected": False,
            }, indent=2))
            return 0
        if value.get("schema") == "ciw.container-composition.v1":
            checked = validate_composition(value)
            print(json.dumps({
                "schema": "ciw.container-composition-inspection.v1",
                "composition_id": checked["composition_id"],
                "containers": len(checked["containers"]),
                "relations": len(checked["relations"]),
                "provider_execution": False,
            }, indent=2))
            return 0
        print(json.dumps(summarize_telemetry(value), indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
