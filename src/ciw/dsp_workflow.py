"""Bounded FIR execution through the original NET Session; no compiler at run time."""
import argparse
import json
from pathlib import Path
import sys
from . import dsp
from .control_contracts import load, save_new


def main(argv=None):
    parser=argparse.ArgumentParser(prog='net dsp',description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    view=commands.add_parser('inspect'); view.add_argument('workspace',type=Path)
    for name in ('run','demo'):
        cmd=commands.add_parser(name)
        cmd.add_argument('--library',type=Path,required=True)
        cmd.add_argument('--library-sha256',required=True)
        cmd.add_argument('--output-dir',type=Path,required=True)
        if name=='run':
            cmd.add_argument('--source',type=Path,required=True)
            cmd.add_argument('--channel',required=True)
            cmd.add_argument('--interval',type=float,nargs=2,required=True)
            cmd.add_argument('--taps',type=Path,required=True,help='JSON array of dimensionless coefficients')
            cmd.add_argument('--initial-history',type=Path,required=True,help='Explicit samples preceding recording; oldest first')
            cmd.add_argument('--clock-id',required=True)
            cmd.add_argument('--semantics',choices=['estimated','simulated','reference'],required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='inspect':
            print(json.dumps(dsp.inspect(args.workspace),indent=2));return 0
        from .instruments import make_demo_run
        from .session import Session
        from .control_plane import experiment,run_graph,plan_graph
        source=make_demo_run() if args.command=='demo' else load(args.source)
        params={'channel':'q','interval_s':[0.,12.],'taps':[.25,.5,.25], 'initial_history':[0.,0.],'clock_id':'oscillator-model-time'} if args.command=='demo' else {
            'channel':args.channel,'interval_s':args.interval,'taps':load(args.taps),
            'initial_history':load(args.initial_history),'clock_id':args.clock_id}
        dsp.inputs(source,params)  # Validate before native load or destination creation.
        binding=dsp.FirBinding(args.library,expected_sha256=args.library_sha256)
        registry=dsp.registry(binding)
        graph=experiment('dsp-fir',model_id='dsp-fir.v1',nodes=[{'node_id':'filter','operation_id':dsp.OPERATION,'parameters':params,'inputs':{},'depends_on':[]}])
        plan_graph(graph,registry)
        if args.output_dir.is_symlink(): raise ValueError('Output cannot be a symlink')
        args.output_dir.mkdir(parents=True,exist_ok=False)
        session=Session(source,args.output_dir,operations=registry.operations)
        try:
            report=run_graph(session,graph,registry)
        finally:
            session.save_workspace(args.output_dir/'workspace.json')
        save_new(args.output_dir/'graph-run.json',report)
        if report['status']=='completed':
            result=report['nodes']['filter']['result']
            save_new(args.output_dir/'observations.json',dsp.observations(result,semantics='reference' if args.command=='demo' else args.semantics))
        print(json.dumps({'status':report['status'],'executions':len(session.executions),'results':len(session.results),'output_dir':str(args.output_dir)}))
        return 0 if report['status']=='completed' else 2
    except (ValueError,TypeError,OSError,KeyError) as exc:
        print(json.dumps({'status':'refused','reason':str(exc)}),file=sys.stderr);return 1

if __name__=='__main__': raise SystemExit(main())
