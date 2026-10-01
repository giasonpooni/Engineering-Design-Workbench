"""Execute one trusted Blender asset recipe against an existing operator packet."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load
from . import foundry_asset_worker as worker
from .foundry_pipeline_cli import evidence_map


def main(argv=None):
    parser=argparse.ArgumentParser(prog='net foundry asset',description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    run=commands.add_parser('run',help='explicitly authorize native author/import work for a packet; no model API')
    run.add_argument('project',type=Path)
    run.add_argument('--packet',type=Path,required=True)
    run.add_argument('--packet-id',required=True,help='independently operator-retained packet record_digest')
    run.add_argument('--source-root',type=Path,required=True)
    for name in ('blender','godot'):
        run.add_argument('--'+name,type=Path,required=True)
        run.add_argument('--'+name+'-sha256',required=True,help='sha256:<digest> of executable, not download archive')
    run.add_argument('--evidence',action='append',default=[],metavar='TASK=DIRECTORY')
    run.add_argument('--legs',type=int,choices=(3,4),default=4)
    run.add_argument('--repair',action='store_true',help='predeclare the four-leg correction, never weaken the checker')
    run.add_argument('--max-operations',type=int,default=3)
    run.add_argument('--output-dir',type=Path,required=True)
    inspect=commands.add_parser('inspect',help='recompute fixed acceptance without starting Blender/Godot')
    inspect.add_argument('production',type=Path)
    export=commands.add_parser('export',help='create a new complete accepted candidate tree, never apply it')
    export.add_argument('production',type=Path)
    export.add_argument('--source-root',type=Path,required=True)
    export.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='run':
            result=worker.run_asset(load(args.project),load(args.packet),args.source_root,args.blender,args.godot,args.output_dir,
                packet_id=args.packet_id,blender_sha256=args.blender_sha256,godot_sha256=args.godot_sha256,
                evidence=evidence_map(args.evidence),legs=args.legs,repair=args.repair,max_operations=args.max_operations)
        elif args.command=='inspect': result=worker.inspect_asset(args.production)
        else: result=worker.export_asset(args.production,args.source_root,output_dir=args.output_dir)
        print(json.dumps(result,indent=2,allow_nan=False))
        return 2 if result.get('status')=='incomplete' else 0
    except (OSError,ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError,UnicodeError) as exc:
        print(json.dumps({'status':'refused','reason':str(exc)}),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
