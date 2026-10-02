"""Execute qualified IFC ingress through the existing pinned CSE workload."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .bim_interop import execute_bim_mapping, validate_bim_mapping_witness
from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .semantic_capabilities import builtin_semantic_registry


def _semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net interop-bim", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    execute = commands.add_parser("execute")
    execute.add_argument("registry", type=Path)
    execute.add_argument("preservation_contract", type=Path)
    execute.add_argument("profile", type=Path)
    execute.add_argument("ingress", type=Path)
    execute.add_argument("ingress_verification", type=Path)
    execute.add_argument("qualification", type=Path)
    execute.add_argument("bim_source", type=Path)
    execute.add_argument("spec", type=Path)
    execute.add_argument("--cse-repository", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("witness", type=Path)
    inspect.add_argument("registry", type=Path)
    inspect.add_argument("preservation_contract", type=Path)
    inspect.add_argument("profile", type=Path)
    inspect.add_argument("ingress", type=Path)
    inspect.add_argument("ingress_verification", type=Path)
    inspect.add_argument("qualification", type=Path)
    inspect.add_argument("bundle", type=Path)

    args = parser.parse_args(argv)
    try:
        semantic = _semantic()
        if args.command == "execute":
            value = execute_bim_mapping(
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.profile),
                load(args.ingress),
                load(args.ingress_verification),
                load(args.qualification),
                load(args.bim_source),
                {"cse": args.cse_repository},
                load(args.spec),
            )
            save_new(args.output, value)
            print(json.dumps({
                "status": value["mapping_outcome"],
                "execution_id": value["execution_id"],
                "payload_ref": value["payload_ref"],
                "native_result_ref": value["native_result_ref"],
                "preservation_verification_performed": False,
                "state_admission_performed": False,
                "output": str(args.output),
            }, indent=2))
            return 0 if value["mapping_outcome"] == "MAPPED" else 2

        checked = validate_bim_mapping_witness(
            load(args.witness),
            load(args.registry),
            semantic,
            load(args.preservation_contract),
            load(args.profile),
            load(args.ingress),
            load(args.ingress_verification),
            load(args.qualification),
            load(args.bundle),
        )
        print(json.dumps({
            "schema": "ciw.interop-mapping-witness-inspection.v1",
            "record_digest": checked["record_digest"],
            "mapping_outcome": checked["mapping_outcome"],
            "native_status": checked["native_status"],
            "native_reason": checked["native_reason"],
            "payload_ref": checked["payload_ref"],
            "target": checked["target"],
            "preservation_verification_performed": False,
            "physical_validity_established": False,
            "state_admission_performed": False,
        }, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
