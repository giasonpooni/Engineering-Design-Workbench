"""Declare, transfer, inspect and freshly verify finite SI coupling interfaces."""
import argparse
import json
from pathlib import Path
import sys

from .control_contracts import save_new
from . import fluid_interface_workflow as workflow


def main(argv=None):
    parser=argparse.ArgumentParser(prog="net fluid coupling",description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    for name in ("template","example"):
        command=commands.add_parser(name);command.add_argument("--output",type=Path,required=True)
    run=commands.add_parser("run");run.add_argument("request_path",nargs="?",type=Path);run.add_argument("--request",type=Path);run.add_argument("--output-dir",type=Path,required=True)
    for name in ("inspect","verify"):
        command=commands.add_parser(name);command.add_argument("directory",type=Path)
        if name=="verify":command.add_argument("--output",type=Path)
    args=parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command=="run" and (args.request is None)==(args.request_path is None):parser.error("run requires exactly one --request path or positional request path")
    try:
        if args.command in {"template","example"}:
            save_new(args.output,workflow.template());result={"status":"created","file":str(args.output)}
        elif args.command=="run":result=workflow.run(workflow.load_regular(args.request or args.request_path),args.output_dir)
        elif args.command=="inspect":result=workflow.inspect(args.directory)
        else:
            result=workflow.verify_retained(args.directory)
            if args.output is not None:save_new(args.output,result)
        print(json.dumps(result,indent=2,allow_nan=False))
        return 2 if result.get("status") in {"REFUSE","EXPAND"} else 0
    except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:
        print(json.dumps({"status":"REFUSE","reason":str(exc)}),file=sys.stderr)
        return 1
