"""Explicit optional signal-processing instrument on the existing NET Session."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net dsp pipeline", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Synthetic pump-and-pipe diagnostic fixture")
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument("--output-dir", required=True, type=Path)
    run = commands.add_parser("run", help="Execute a declared JSON signal-processing chain")
    run.add_argument("--request", required=True, type=Path)
    run.add_argument("--output-dir", required=True, type=Path)
    inspect = commands.add_parser("inspect", help="Read retained results without numerical execution")
    inspect.add_argument("bundle", type=Path)
    replay = commands.add_parser("replay", help="Rerun and compare numerical payloads with separate identities")
    replay.add_argument("bundle", type=Path)
    replay.add_argument("--output-dir", required=True, type=Path)
    replay.add_argument("--atol", type=float, default=1e-10)
    replay.add_argument("--rtol", type=float, default=1e-9)
    args = parser.parse_args(argv)
    try:
        from . import dsp_pipeline
        if args.command == "inspect":
            result = dsp_pipeline.inspect(args.bundle)
        elif args.command == "replay":
            result = dsp_pipeline.replay(args.bundle, args.output_dir, atol=args.atol, rtol=args.rtol)
        else:
            if args.command == "demo":
                from stfe_dsp.pump import make_pump_request
                request = make_pump_request(seed=args.seed)
            else:
                request = dsp_pipeline.read_bounded(args.request)
            result = dsp_pipeline.run(request, args.output_dir)
        print(json.dumps(result, allow_nan=False, indent=2))
        return 0 if result["status"] in {"completed", "PASS"} else 2
    except (ImportError, OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        message = str(exc)
        if isinstance(exc, ImportError):
            message += "; install the monorepo instrument: pip install ./instruments/measurement/signal-processing './instruments/measurement/signal-conditioning[dsp]'"
        print(json.dumps({"status": "refused", "reason": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
