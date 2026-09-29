"""Run explicitly pinned GSC raster operations or inspect their retained results."""
from pathlib import Path
import argparse
import json
import sys
import tempfile
from .control_contracts import keys, load, save_new
from .control_plane import builtin_registry, run_graph
from .rs_operations import RasterBinding, add_rs_routes, make_plan, mean_observations, open_workspace, OPERATIONS


def main(argv=None):
    parser=argparse.ArgumentParser(prog='net spatial raster',description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    cmd=sub.add_parser('run',help='Dispatch a selected local scene to an explicitly pinned GSC worker')
    cmd.add_argument('request',type=Path);cmd.add_argument('--run',type=Path,required=True,help='Existing CIW host recording; not treated as raster pixels')
    cmd.add_argument('--gsc-repo',type=Path,required=True);cmd.add_argument('--gsc-revision',required=True)
    cmd.add_argument('--bundle',type=Path,required=True);cmd.add_argument('--bundle-sha256',required=True)
    cmd.add_argument('--python-executable',type=Path);cmd.add_argument('--output-dir',type=Path,required=True)
    cmd=sub.add_parser('inspect',help='Reopen retained results without a provider or raster library')
    cmd.add_argument('workspace',type=Path)
    cmd=sub.add_parser('observations',help='Export a source-bound window mean for the existing numerical comparator')
    cmd.add_argument('workspace',type=Path);cmd.add_argument('--result-id',required=True);cmd.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command == 'run':
            from .session import Session
            from .instruments import validate_run
            request=load(args.request); keys(request, {'operation','parameters'})
            parameters={'bundle_ref':args.bundle_sha256,'request':request['parameters']}
            graph=make_plan(request['operation'],parameters)
            run=load(args.run);validate_run(run)
            binding=RasterBinding(args.gsc_repo,args.gsc_revision,args.bundle,args.bundle_sha256,python_executable=args.python_executable)
            registry=builtin_registry();add_rs_routes(registry,binding=binding)
            args.output_dir.mkdir(parents=True,exist_ok=False)
            session=Session(run,args.output_dir,operations=registry.operations)
            try:
                save_new(args.output_dir/'experiment.json',graph)
                outcome=run_graph(session,graph,registry)
                save_new(args.output_dir/'graph-run.json',outcome)
            finally:
                session.save_workspace(args.output_dir/'workspace.json')
            value={'status':outcome['status'],'executions':len(session.executions),'results':len(session.results),
                   'result_ids':list(session.results),'state_admission':'not_performed','state_release':'not_performed'}
            print(json.dumps(value,indent=2));return 0 if outcome['status']=='completed' else 2
        with tempfile.TemporaryDirectory(prefix='net-rs-read-') as tmp:
            session=open_workspace(args.workspace,output_dir=Path(tmp))
            if args.command == 'observations':
                stream=mean_observations(session.results[args.result_id]);save_new(args.output,stream)
                value={'status':'observation_projection_written','provider_executed':False,'record_digest':stream['record_digest']}
            else:
                value={'status':'retained_rs_results_checked','provider_executed':False,
                       'results':[r for r in session.results.values() if r.get('operation_id') in OPERATIONS],
                       'refusals':[e for e in session.executions.values() if e.get('operation_id') in OPERATIONS and e['status']=='refused']}
            print(json.dumps(value,indent=2,allow_nan=False));return 0
    except (ValueError,TypeError,KeyError,OSError) as exc:
        print(json.dumps({'status':'refused','code':getattr(exc,'code','invalid_rs_request'),'message':str(exc)}),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
