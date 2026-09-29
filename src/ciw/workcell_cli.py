"""Operator launcher for NET's bounded executable agent workcell."""
import argparse
import json
import os
from pathlib import Path
import sys

from .control_contracts import keys,load,save_new,bytes_ref,content_ref
from .foundry_packets import inventory
from .workcell import WorkcellHost,inspect_attempt
from .workcell_container import DockerCell


def from_profile(path:Path):
    path=path.absolute();p=load(path)
    keys(p,{'schema','source_root','source_id','output_dir','docker','docker_sha256','image_id','socket',
            'writable','max_candidates','max_runs','allow_package'})
    if p['schema']!='ciw.workcell-profile.v1':raise ValueError('Unsupported workcell profile')
    backend=DockerCell(docker=Path(p['docker']),docker_sha256=p['docker_sha256'],image_id=p['image_id'],socket=p['socket'])
    return WorkcellHost(path.parent/p['source_root'],path.parent/p['output_dir'],backend,expected_source_id=p['source_id'],
        writable=tuple(p['writable']),max_candidates=p['max_candidates'],max_runs=p['max_runs'],allow_package=p['allow_package'])


def main(argv=None):
    parser=argparse.ArgumentParser(prog='net workcell',description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('configure');p.add_argument('--source-root',type=Path,required=True);p.add_argument('--docker',type=Path,required=True);p.add_argument('--image-id',required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--allow-package',action='store_true')
    p=sub.add_parser('serve');p.add_argument('--profile',type=Path,required=True)
    p=sub.add_parser('inspect');p.add_argument('attempt_dir',type=Path)
    p=sub.add_parser('run');p.add_argument('--profile',type=Path,required=True);p.add_argument('--changes',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='configure':
            content_ref(args.image_id)
            source=args.source_root.absolute();docker=args.docker.absolute()
            p={'schema':'ciw.workcell-profile.v1','source_root':str(source),'source_id':inventory(source)['inventory_id'],
               'docker':str(docker),'docker_sha256':bytes_ref(docker.read_bytes()),'image_id':args.image_id,
               'socket':'unix:///var/run/docker.sock','output_dir':'cell','writable':['compiler.py','motion.gd'],
               'max_candidates':8,'max_runs':8,'allow_package':args.allow_package}
            args.output_dir.mkdir(parents=True,exist_ok=False);save_new(args.output_dir/'profile.json',p)
            print(args.output_dir/'profile.json');return 0
        if args.command=='inspect':
            print(json.dumps(inspect_attempt(args.attempt_dir),indent=2));return 0
        if args.command=='run':
            host=from_profile(args.profile)
            c=host.call('net_cell_submit',{'attempt':'candidate','changes':load(args.changes)})
            result=host.call('net_cell_build',{'attempt':'build','candidate':c['candidate']})
            print(json.dumps(result,indent=2));return 0 if result['status']=='completed' else 2
        from .agent_mcp import serve
        with os.fdopen(os.dup(sys.stdout.fileno()),'wb',buffering=0) as wire:
            os.dup2(sys.stderr.fileno(),sys.stdout.fileno())
            host=from_profile(args.profile)
            return serve(host,sys.stdin.buffer,wire)
    except (ValueError,TypeError,OSError,KeyError) as exc:
        print(json.dumps({'status':'refused','reason':str(exc)}),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
