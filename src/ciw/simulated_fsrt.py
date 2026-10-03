"""Bound one engine-owned simulated mass observation to the existing FSRT worker.

No engine is imported or advanced here. Reference truth is a separate artifact,
never an estimator input. The original RCI-backed operations are unchanged.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import uuid

from .adapters.protocol import InstrumentManifest
from .adapters.covariance_records import validate_snapshot_covariance_payload
from .core.covariance import create_covariance_artifact
from .core.identities import canonical_json, content_identity, evidence_id
from .core.records import finite_tree
from .operations.registry import Operation
from .session import Session, loads_json

SOURCE_SCHEMA = 'ciw.simulated-mass-observation.v1'
OPERATION = 'ciw.simulated-fsrt.v1'
NATIVE_OPERATION = 'fsrt.tank-reconstruct.v2'
INSTRUMENT = 'org.notationsystems.simulated-mass-observation'
STATE = ['tank-1.mass', 'tank-2.mass']
FRAME = 'reservoir2.mass'
MAX_SOURCE_BYTES = 65536
MAX_WORKSPACE_BYTES = 8 * 1024 * 1024
INDEPENDENCE = ('prior_independent_of_observations', 'declared_total_independent_of_observations',
                'prior_independent_of_declared_total')
NOTICE = ('Native FSRT calibrated_observation is its historical unit-normalized input label; '
          'these readings are simulated, not physically measured or calibrated.')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _object(value, fields, name):
    _require(isinstance(value, dict) and set(value) == set(fields), name + ' fields differ')
    return value


def _digest(value):
    _require(isinstance(value, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', value), 'Complete SHA-256 required')


def _text(value):
    _require(isinstance(value, str) and 0 < len(value) <= 256
             and all(ord(c) >= 32 and ord(c) != 127 for c in value), 'Bounded text required')


def _number(value):
    _require(type(value) in (int, float), 'A number is required, not coercion')
    finite_tree(value)


def _equal(a, b, name):
    _require(canonical_json(a) == canonical_json(b), name + ' binding differs')


def sha256(raw: bytes) -> str:
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _read(path: Path, expected: str, limit: int) -> bytes:
    _digest(expected)
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    _require(len(raw) <= limit, 'Artifact exceeds byte budget')
    _require(sha256(raw) == expected, 'Artifact differs from selected digest')
    return raw


def validate_observation(value: dict) -> None:
    _object(value, ('schema','source_class','producer','clock','entity_ids','source_ids','unit','frame',
                    'values','mask','covariance','reference_values','sensor_model_id'), 'Observation')
    _require(value['schema'] == SOURCE_SCHEMA and value['source_class'] == 'simulated_observation',
             'Only explicitly simulated observations are accepted')
    finite_tree(value)
    p = _object(value['producer'], ('engine','version','source_revision','executable_sha256',
        'execution_id','simulation_id','state_owner','clock_owner','scenario_id','model_id','asset_ids'), 'Producer')
    for key in ('engine','version','state_owner','clock_owner'):
        _text(p[key])
    _require(p['state_owner'] == p['clock_owner'] == p['engine'], 'One engine must own state and clock')
    _require(isinstance(p['source_revision'], str) and re.fullmatch(r'[0-9a-f]{40}', p['source_revision']), 'Exact producer source revision required')
    for key in ('executable_sha256','scenario_id','model_id'):
        _digest(p[key])
    for key, prefix in (('execution_id','execution'),('simulation_id','simulation')):
        _require(isinstance(p[key],str) and re.fullmatch(prefix+r'-[0-9a-f]{32}',p[key]), 'Producer occurrence identity required')
    _require(isinstance(p['asset_ids'],list) and len(p['asset_ids']) <= 32, 'Bounded asset identities required')
    for item in p['asset_ids']:
        _digest(item)
    _require(len(set(p['asset_ids'])) == len(p['asset_ids']), 'Duplicate asset identity')
    clock = _object(value['clock'], ('tick','ticks_per_second','phase'), 'Clock')
    _require(type(clock['tick']) is int and 0 <= clock['tick'] <= 2**31-1, 'Integer simulation tick required')
    _require(type(clock['ticks_per_second']) is int and 1 <= clock['ticks_per_second'] <= 1000000, 'Integer tick rate required')
    _require(clock['phase'] == 'post_step', 'Observation must declare the post-step phase')
    _require(value['unit'] == 'kg' and value['frame'] == FRAME, 'Only declared reservoir mass coordinates in kg are supported')
    for key in ('entity_ids','source_ids'):
        entries = value[key]
        _require(isinstance(entries,list) and len(entries)==2, 'Two ordered entity/source identities required')
        for item in entries:
            _text(item)
        _require(len(set(entries))==2, 'Duplicate entity/source identity')
    _require(isinstance(value['mask'],list) and len(value['mask'])==2
             and all(type(x) is bool for x in value['mask']), 'Two Boolean presence masks required')
    _require(isinstance(value['values'],list) and len(value['values'])==2, 'Two observation slots required')
    _require(isinstance(value['reference_values'],list) and len(value['reference_values'])==2, 'Two reference values required')
    for actual, ref, present in zip(value['values'],value['reference_values'],value['mask']):
        _number(ref)
        if present:
            _number(actual)
            _require(actual >= 0, 'Negative simulated mass observation')
            _equal(actual,ref,'Present observation reference')
        else:
            _require(actual is None, 'A missing observation must remain null')
    _digest(value['sensor_model_id'])
    # Reuse the existing validator without clipping/diagonalizing the matrix.
    create_covariance_artifact(matrix=value['covariance'],quantity_ids=value['source_ids'],units=['kg','kg'],
        frame=FRAME,reference_values=value['reference_values'],method='declared_simulated_sensor_covariance',
        basis={'kind':'observation','id':value['sensor_model_id']},
        provenance={'provider':'simulation-observation','source_evidence_ids':[], 'source_covariance_ids':[]},
        assumptions=['Declared synthetic covariance; not empirically calibrated.'])


def _manifest(source):
    return InstrumentManifest(instrument_id=INSTRUMENT, role='simulation_observation_adapter',
        inputs=(SOURCE_SCHEMA,), outputs=('run.v1',),
        units={q:'kg' for q in source['source_ids']}, frames=(FRAME,),
        sampling={'mode':'single_simulated_event','selection_seconds':'local selection support, not elapsed simulation time'},
        normalization={'values':'unchanged simulated mass readings'}, supported_operations=(),
        determinism={'inspection':'no engine or estimator execution'},
        tolerance_policy={'binding':'exact retained content'},
        calibration_requirements={'status':'not_applicable_simulated_reading'})


def _scientific_content(raw):
    source = loads_json(raw.decode('utf-8'))
    validate_observation(source)
    source_digest = sha256(raw)
    channels = {q:{'unit':'kg','kind':'simulated_observation','values':[v],
                  'evidence_id':content_identity({'source_sha256':source_digest,'index':i,'source_id':q})}
                for i,(q,v) in enumerate(zip(source['source_ids'],source['values']))}
    metadata = {'sample_count':1,'sample_rate_hz':None,'duration_s':1.0,'coordinate_frame':FRAME,
        'manifest':_manifest(source).to_dict(),
        'provenance':{'source_class':'simulated_observation','source':source['producer']['engine'],
            'time_reference':'Single retained snapshot; local 1-second selection support only. Original simulation tick/phase retained.',
            'physical_validation':'not_established'},
        'simulation_source':{'source_sha256':source_digest,'raw_b64':base64.b64encode(raw).decode('ascii')}}
    return source, channels, metadata


def validate_source(run):
    _require(run.get('instrument')==INSTRUMENT, 'Not a simulated observation source')
    record = _object(run.get('metadata',{}).get('simulation_source'), ('source_sha256','raw_b64'), 'Retained source')
    _digest(record['source_sha256'])
    _require(isinstance(record['raw_b64'],str) and len(record['raw_b64']) <= 4*((MAX_SOURCE_BYTES+2)//3), 'Source bytes exceed budget')
    raw = base64.b64decode(record['raw_b64'],validate=True)
    _require(len(raw)<=MAX_SOURCE_BYTES and sha256(raw)==record['source_sha256'], 'Source bytes/digest differ')
    source, channels, metadata = _scientific_content(raw)
    _equal(run['channels'],channels,'Simulated channels')
    _equal(run['metadata'],metadata,'Simulated source metadata')
    _equal(run['time_s'],[0.0],'Local snapshot support')
    _equal(run.get('render',{}),{},'No implied geometry')
    return source


def native_inputs(run, parameters):
    source = validate_source(run)
    _object(parameters, ('model','independence','state_bindings'), 'Estimator parameters')
    flags = _object(parameters['independence'], INDEPENDENCE, 'Independence')
    _require(all(flags[k] is True for k in INDEPENDENCE), 'Unsupported source dependence; declarations must be explicit')
    bindings = [{'entity_id':e,'state_quantity':q} for e,q in zip(source['entity_ids'],STATE)]
    _equal(parameters['state_bindings'],bindings,'Entity/state order')
    _object(parameters['model'],('kind','prior_mean','prior_std','total_mass_kg','total_mass_variance_kg2'),'Model')
    finite_tree(parameters['model'])
    _require(parameters['model']['kind']=='reservoir2-linear-v1', 'Unsupported fluid model')
    _require(isinstance(parameters['model']['prior_mean'],list) and len(parameters['model']['prior_mean'])==2,'Two prior means required')
    for x in [*parameters['model']['prior_mean'], parameters['model']['prior_std'],parameters['model']['total_mass_kg'],parameters['model']['total_mass_variance_kg2']]:
        _number(x)
    source_digest = run['metadata']['simulation_source']['source_sha256']
    evidence = [run['channels'][q]['evidence_id'] for q in source['source_ids']]
    t = source['clock']['tick'] / source['clock']['ticks_per_second']
    obs = {'t':t,'arrival_t':t,'values':deepcopy(source['values']),'covariance':deepcopy(source['covariance']),
        'mask':deepcopy(source['mask']),'source_ids':deepcopy(source['source_ids']), 'evidence_ids':evidence,'unit':'kg'}
    covariance = create_covariance_artifact(matrix=obs['covariance'],quantity_ids=obs['source_ids'],units=['kg','kg'],
        frame=FRAME,reference_values=source['reference_values'],method='identity_simulated_mass_units_no_physical_calibration',
        basis={'kind':'calibrated_observation','id':source_digest},
        provenance={'provider':OPERATION,'source_evidence_ids':evidence,'source_covariance_ids':[],
            'metadata':{**deepcopy(flags),'shared_dependencies':[source['sensor_model_id']],
                'source_class':'simulated_observation','calibration_status':'not_applicable_simulated_reading',
                'native_label_notice':NOTICE,'clock':deepcopy(source['clock']),
                'producer_execution_id':source['producer']['execution_id']}},
        assumptions=['Declared simulated sensor covariance, not field calibration.',NOTICE])
    return {'model':deepcopy(parameters['model']),'observations':[obs],'state_order':STATE[:],
            'observation_covariance':covariance}


def _wrap(data, run, parameters):
    return {'schema':'ciw.simulated-fsrt-result.v1','source_class':'simulated_observation',
        'source_sha256':run['metadata']['simulation_source']['source_sha256'],
        'native_operation_id':NATIVE_OPERATION,'native_input_digest':content_identity(native_inputs(run,parameters)),
        'native_label_notice':NOTICE,'reference_truth_supplied':False,'data':deepcopy(data)}


def validate_payload(operation_id,data,run,parameters,selection):
    _require(operation_id==OPERATION, 'Unsupported simulated observation operation')
    expected = native_inputs(run,parameters)
    _object(data, ('schema','source_class','source_sha256','native_operation_id','native_input_digest',
                  'native_label_notice','reference_truth_supplied','data'), 'Result')
    _equal(data,_wrap(data['data'],run,parameters),'Result provenance')
    validate_snapshot_covariance_payload(data['data'],expected)


def bind(session, fsrt_repo, python_executable=None, expected_runtime=None):
    from .investigation import _runtime
    adapter = _runtime('fsrt',fsrt_repo,python_executable,expected_runtime)
    session.operations.register(Operation(OPERATION,'state_estimator',
        lambda run,params:_wrap(adapter.invoke(NATIVE_OPERATION,native_inputs(run,params)),run,params),
        adapter.runtime_identity))
    return adapter


def _execute(session, parameters):
    response = session.handle({'protocol_version':1,'request_id':uuid.uuid4().hex,'type':'operation.execute',
                               'payload':{'operation_id':OPERATION,'parameters':deepcopy(parameters)}})
    _require(response['type']!='error', str(response.get('payload')))
    return session.save_workspace(session.output_dir/'workspace.json')


def create(source_path, expected_source_sha256, parameters, fsrt_repo, output_dir, python_executable=None):
    parameters=deepcopy(parameters)
    raw = _read(source_path,expected_source_sha256,MAX_SOURCE_BYTES)
    _,channels,metadata = _scientific_content(raw)
    run = {'run_schema':'run.v1','run_id':'run-'+uuid.uuid4().hex,'instrument':INSTRUMENT,
           'metadata':metadata,'channels':channels,'time_s':[0.0],'render':{}}
    run['evidence_id']=evidence_id(run)
    native_inputs(run,parameters)  # Reject unsupported source/parameter mappings before any write.
    output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=False)
    session=Session(run,output_dir)
    bind(session,fsrt_repo,python_executable)
    return _execute(session,parameters)


def inspect(workspace_path, expected_workspace_sha256):
    raw=_read(workspace_path,expected_workspace_sha256,MAX_WORKSPACE_BYTES)
    with tempfile.TemporaryDirectory(prefix='ciw-simulated-inspect-') as directory:
        source=Path(directory)/'workspace.json';source.write_bytes(raw)
        session=Session.from_workspace(source,Path(directory)/'opened')
        validate_source(session.run)
        return {'source':validate_source(session.run),'evidence_id':session.run['evidence_id'],
                'executions':deepcopy(list(session.executions.values())),
                'results':deepcopy(list(session.results.values())), 'inspection_only':True}


def replay(workspace_path, expected_workspace_sha256, fsrt_repo, output_dir, python_executable=None):
    raw=_read(workspace_path,expected_workspace_sha256,MAX_WORKSPACE_BYTES)
    with tempfile.TemporaryDirectory(prefix='ciw-simulated-replay-') as directory:
        source=Path(directory)/'workspace.json';source.write_bytes(raw)
        old=Session.from_workspace(source,Path(directory)/'opened');validate_source(old.run)
        eligible=[e for e in old.executions.values() if e['operation_id']==OPERATION]
        _require(eligible,'No retained simulated FSRT execution to replay')
        previous=eligible[-1]
        _require(previous['runtime'] is not None,'A replay needs an original bound runtime')
        from .investigation import _runtime
        _runtime('fsrt',fsrt_repo,python_executable,previous['runtime']).runtime_identity()
        output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=False)
        session=Session.from_workspace(source,output_dir)
        bind(session,fsrt_repo,python_executable,previous['runtime'])
        return _execute(session,previous['parameters'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('create','inspect','replay'):
        p=sub.add_parser(command);p.add_argument('source',type=Path);p.add_argument('--expect-sha256',required=True)
        if command!='inspect':
            p.add_argument('--fsrt-repo',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
            p.add_argument('--python',dest='python_executable')
        if command=='create':
            p.add_argument('--parameters',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='inspect':
            outcome=inspect(args.source,args.expect_sha256)
        elif args.command=='create':
            _require(args.parameters.stat().st_size<=MAX_SOURCE_BYTES,'Parameter file too large')
            params=loads_json(args.parameters.read_text(encoding='utf-8'))
            path=create(args.source,args.expect_sha256,params,args.fsrt_repo,args.output_dir,args.python_executable)
            outcome={'workspace':str(path),'workspace_sha256':sha256(path.read_bytes())}
        else:
            path=replay(args.source,args.expect_sha256,args.fsrt_repo,args.output_dir,args.python_executable)
            outcome={'workspace':str(path),'workspace_sha256':sha256(path.read_bytes())}
    except (ValueError,OSError,TypeError,KeyError,RecursionError) as exc:
        parser.exit(2,f'Simulated FSRT refused: {exc}\n')
    print(json.dumps(outcome,allow_nan=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
