"""Assess retained fluid-volume and material-mass balances through pinned FlowState."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .adapters.protocol import AdapterRefusal
from .control_contracts import save_new


def _backend(args):
    from .leakage_native import NativeLeakageBackend
    return NativeLeakageBackend(args.provider_checkout, python=args.python)


def _request(path: Path) -> dict:
    from . import leakage_contract
    return leakage_contract.load_file(path)


def main(argv=None) -> int:
    from . import leakage_contract, leakage_workflow as workflow
    parser = argparse.ArgumentParser(prog="net polymer leakage", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example", help="Create a synthetic integrated-amount balance fixture")
    example.add_argument("--basis", choices=("volume", "mass"), default="volume")
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Execute the explicitly selected native FlowState provider")
    run.add_argument("request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--polymer-workspace", type=Path,
                     help="Polymer run directory containing the assessment's workspace.json")
    inspect = commands.add_parser("inspect", help="Read retained balance evidence without provider execution")
    inspect.add_argument("directory", type=Path)
    verify = commands.add_parser("verify", help="Create a fresh finite numerical audit without native execution")
    verify.add_argument("directory", type=Path)
    verify.add_argument("--output", type=Path, help="Save a create-only fresh verification receipt")
    replay = commands.add_parser("replay", help="Repeat the retained request with a new native execution")
    replay.add_argument("directory", type=Path)
    replay.add_argument("--output-dir", type=Path, required=True)
    export = commands.add_parser("export", help="Export retained residuals, full uncertainty and evidence")
    export.add_argument("directory", type=Path)
    export.add_argument("--output-dir", type=Path, required=True)
    doctor = commands.add_parser("doctor", help="Check explicit native source and runtime readiness")
    qualify = commands.add_parser("qualify", help="Execute, audit, replay and export both finite fixtures")
    qualify.add_argument("--output-dir", type=Path, required=True)
    for command in (run, replay, doctor, qualify):
        command.add_argument("--provider-checkout", type=Path, required=True,
                             help="Operator-selected standalone FlowState checkout at the approved revision")
        command.add_argument("--python", type=Path,
                             help="Operator-selected Python interpreter with the native dependency closure")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "example":
            leakage_contract.save_file(args.output, leakage_contract.example_request(args.basis))
            result = {"status": "created", "basis": args.basis, "request": str(args.output)}
        elif args.command == "run":
            result = workflow.run(_request(args.request), args.output_dir, backend=_backend(args),
                                  polymer_directory=args.polymer_workspace)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
            if args.output is not None:
                save_new(args.output, result)
        elif args.command == "replay":
            result = workflow.replay(args.directory, args.output_dir, backend=_backend(args))
        elif args.command == "export":
            result = workflow.export(args.directory, args.output_dir)
        elif args.command == "doctor":
            result = workflow.doctor(_backend(args))
        else:
            result = workflow.qualify(args.output_dir, backend=_backend(args))
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if str(result.get("status", "")).upper() in {"REFUSE", "REFUSED", "FAIL", "FAILED", "BLOCKED", "UNAVAILABLE"} else 0
    except AdapterRefusal as exc:
        result = {"status": "REFUSE", "reason": str(exc), "code": exc.code}
        if exc.reason_code is not None:
            result["reason_code"] = exc.reason_code
        print(json.dumps(result), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
