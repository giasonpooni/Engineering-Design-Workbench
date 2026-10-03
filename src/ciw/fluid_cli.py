"""Run, inspect, independently verify and export qualified synthetic fluid models."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import save_new
from . import fluid_workflow as workflow


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "coupling":
        from .fluid_interface_cli import main as coupling_main
        return coupling_main(arguments[1:])
    parser = argparse.ArgumentParser(prog="net fluid", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example")
    example.add_argument("--profile", choices=workflow.contract.ALL_PROFILES, default="reservoir")
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("request_path", type=Path, nargs="?")
    run.add_argument("--request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify", "export-csv"):
        command = commands.add_parser(name)
        command.add_argument("directory", type=Path)
        if name in {"verify", "export-csv"}:
            command.add_argument("--output", type=Path, required=name == "export-csv")
    handoff = commands.add_parser("handoff")
    handoff.add_argument("directory", type=Path)
    handoff.add_argument("--sample-index", type=int, required=True)
    handoff.add_argument("--output", type=Path, required=True)
    reduction = commands.add_parser("reduce", help="Freshly verify an instantaneous particle-to-bin observable map")
    reduction.add_argument("directory", type=Path)
    reduction.add_argument("--sample-index", type=int, required=True)
    reduction.add_argument("--bins", type=int, nargs="+", required=True)
    reduction.add_argument("--output", type=Path, required=True)
    experiment = commands.add_parser("experiment", help="Ingest declared observations and compare held-out reservoir data")
    experiments = experiment.add_subparsers(dest="experiment_command", required=True)
    template = experiments.add_parser("template")
    template.add_argument("--profile", choices=("reservoir",), default="reservoir")
    template.add_argument("--output", type=Path, required=True)
    ingestion = experiments.add_parser("ingest")
    ingestion.add_argument("--csv", type=Path, required=True)
    ingestion.add_argument("--metadata", type=Path, required=True)
    ingestion.add_argument("--output-dir", type=Path, required=True)
    comparison = experiments.add_parser("compare")
    comparison.add_argument("--model-dir", type=Path, required=True)
    comparison.add_argument("--measurement-dir", type=Path, required=True)
    comparison.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify"):
        inspection = experiments.add_parser(name)
        inspection.add_argument("directory", type=Path)
        inspection.add_argument("--output", type=Path)
    commands.add_parser("coupling", help="Retain and audit conservative CFD–structure interface transfers")
    args = parser.parse_args(arguments)
    if args.command == "run" and (args.request is None) == (args.request_path is None):
        parser.error("run requires exactly one --request path or positional request path")
    try:
        if args.command == "example":
            save_new(args.output, workflow.contract.example_request(args.profile))
            result = {"status": "created", "profile": args.profile, "request": str(args.output)}
        elif args.command == "run":
            result = workflow.run(workflow.load_regular(args.request or args.request_path), args.output_dir)
        elif args.command == "inspect":
            result = workflow.inspect(args.directory)
        elif args.command == "verify":
            result = workflow.verify_retained(args.directory)
            if args.output is not None:
                save_new(args.output, result)
        elif args.command == "handoff":
            from .fluid_handoff import export_snapshot
            result = export_snapshot(args.directory, args.output, sample_index=args.sample_index)
        elif args.command == "reduce":
            result = workflow.reduce_particles(args.directory, args.output, sample_index=args.sample_index, bins=args.bins)
        elif args.command == "experiment":
            from . import fluid_experiment
            if args.experiment_command == "template":
                save_new(args.output, fluid_experiment.template(args.profile))
                result = {"status": "created", "file": str(args.output)}
            elif args.experiment_command == "ingest":
                result = fluid_experiment.ingest(args.csv, args.metadata, args.output_dir)
            elif args.experiment_command == "compare":
                result = fluid_experiment.compare(args.model_dir, args.measurement_dir, args.output_dir)
            else:
                result = (fluid_experiment.inspect(args.directory) if args.experiment_command == "inspect"
                          else fluid_experiment.verify_retained(args.directory))
                if args.output is not None:
                    save_new(args.output, result)
        else:
            result = workflow.export_csv(args.directory, args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "EXPAND"} else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1
