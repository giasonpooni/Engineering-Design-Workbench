"""Run retained polymer-cycle metrology, reference estimates and control simulations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .polymer_contract import MAX_BYTES, PROCESSES, example_request
from . import polymer_workflow as workflow
from . import polymer_operator as operator


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="net polymer", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example")
    example.add_argument("--process", choices=sorted(PROCESSES), default="injection_molding")
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--summary", action="store_true", help="Show separately labelled operator decisions")
    for name in ("inspect", "verify", "replay"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name == "replay":
            command.add_argument("--output-dir", type=Path, required=True)
        if name in {"inspect", "replay"}:
            command.add_argument("--summary", action="store_true")
        else:
            command.add_argument("--output", type=Path, help="Save a create-only fresh audit receipt")
    summary = commands.add_parser("summary", help="Read concise decisions without executing providers")
    summary.add_argument("directory", type=Path)
    summary.add_argument("--output", type=Path)
    export = commands.add_parser("export", help="Export a report and exact retained sample CSV")
    export.add_argument("directory", type=Path)
    export.add_argument("--output-dir", type=Path, required=True)
    demo = commands.add_parser("demo", help="Run a synthetic fixture and save its report and fresh audit")
    demo.add_argument("--process", choices=sorted(PROCESSES), default="injection_molding")
    demo.add_argument("--output-dir", type=Path, required=True)
    doctor = commands.add_parser("doctor", help="Inspect fixed local tool contracts without grants")
    doctor.add_argument("--output", type=Path)
    qualify = commands.add_parser("qualify", help="Execute both finite reference workflows, replay and audit")
    qualify.add_argument("--output-dir", type=Path, required=True)
    qualify.add_argument("--ingress", type=Path, help="Also qualify a retained native ingress envelope")
    ingress = commands.add_parser("run-ingress", help="Run a sealed retained native measurement envelope")
    ingress.add_argument("envelope", type=Path)
    ingress.add_argument("--output-dir", type=Path, required=True)
    ingress.add_argument("--summary", action="store_true")
    prepare = commands.add_parser("prepare-ingress", help="Bind one native calibrated stream to a cycle template")
    prepare.add_argument("template", type=Path)
    prepare.add_argument("--bundle", type=Path, required=True)
    prepare.add_argument("--sensor-id", required=True)
    prepare.add_argument("--quantity", required=True)
    prepare.add_argument("--modality", required=True)
    prepare.add_argument("--max-age-s", type=float, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            save_new(args.output, example_request(args.process))
            result = {"status": "created", "request": str(args.output)}
        elif args.command == "run":
            if args.request.is_symlink() or not args.request.is_file() or args.request.stat().st_size > MAX_BYTES:
                raise ValueError("Require a regular polymer request within the 2 MiB budget")
            result = workflow.run(load(args.request), args.output_dir)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
        elif args.command == "replay":
            result = workflow.replay(args.directory, args.output_dir)
        elif args.command == "summary":
            result = operator.summary(args.directory)
        elif args.command == "export":
            result = operator.export(args.directory, args.output_dir)
        elif args.command == "demo":
            result = operator.demo(args.process, args.output_dir)
        elif args.command == "doctor":
            result = operator.doctor()
        elif args.command == "qualify":
            envelope = None
            if args.ingress is not None:
                from . import polymer_ingress
                if (args.ingress.is_symlink() or not args.ingress.is_file()
                        or args.ingress.stat().st_size > polymer_ingress.MAX_BYTES):
                    raise ValueError("Require a bounded regular polymer ingress envelope")
                envelope = polymer_ingress.load_file(args.ingress)
            result = operator.qualify(args.output_dir, ingress=envelope)
        elif args.command == "prepare-ingress":
            from . import polymer_ingress
            from .telemetry import digest
            for path, budget in ((args.template, MAX_BYTES), (args.bundle, polymer_ingress.MAX_BYTES)):
                if path.is_symlink() or not path.is_file() or path.stat().st_size > budget:
                    raise ValueError("Require bounded regular template and native bundle files")
            from .session import read_json
            bundle = read_json(args.bundle)
            result = polymer_ingress.make_envelope(load(args.template), [bundle], [{
                "sensor_id": args.sensor_id, "bundle_ref": digest(bundle), "quantity": args.quantity,
                "modality": args.modality, "max_age_s": args.max_age_s}])
        else:
            from . import polymer_ingress
            if (args.envelope.is_symlink() or not args.envelope.is_file()
                    or args.envelope.stat().st_size > polymer_ingress.MAX_BYTES):
                raise ValueError("Require a bounded regular polymer ingress envelope")
            envelope = polymer_ingress.load_file(args.envelope)
            result = workflow.run(polymer_ingress.derive(envelope), args.output_dir, ingress=envelope)
        if getattr(args, "summary", False):
            result = operator.summarize(result)
        if getattr(args, "output", None) is not None and args.command != "example":
            if args.command == "prepare-ingress":
                polymer_ingress.save_file(args.output, result)
            else:
                save_new(args.output, result)
        if args.command == "prepare-ingress":
            result = {"schema": "ciw.polymer-ingress-created.v1", "status": "created",
                      "envelope": str(args.output), "request_ref": result["mapping_receipt"]["request_ref"],
                      "channel_count": len(result["bindings"]), "receipt_ref": result["receipt_ref"]}
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "FAIL"} else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1
