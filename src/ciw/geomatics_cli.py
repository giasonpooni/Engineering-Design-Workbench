"""Run small GIS, Earth observation, radiometry and urban-analysis examples."""
import argparse
import json
from pathlib import Path
import sys
from .control_contracts import load, save_new
from . import geomatics_workflow as workflow

def main(argv=None):
    parser = argparse.ArgumentParser(prog='net geomatics', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('catalog')
    example = commands.add_parser('example')
    example.add_argument('operation_id')
    example.add_argument('--output', type=Path, required=True)
    run = commands.add_parser('run')
    run.add_argument('request', type=Path)
    run.add_argument('--output-dir', type=Path, required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('directory', type=Path)
    replay = commands.add_parser('replay')
    replay.add_argument('directory', type=Path)
    replay.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'catalog':
            result = workflow.catalog()
        elif args.command == 'example':
            save_new(args.output, workflow.example(args.operation_id))
            result = {'status':'created','request':str(args.output)}
        elif args.command == 'run':
            result = workflow.run(load(args.request), args.output_dir)
        elif args.command == 'inspect':
            result = workflow.inspect(args.directory)
        else:
            result = workflow.replay(args.directory,args.output_dir)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get('status') == 'refused' or result.get('numerical_match') is False else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({'status':'refused','reason':str(exc)}), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
