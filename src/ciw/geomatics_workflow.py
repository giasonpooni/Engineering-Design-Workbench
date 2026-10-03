"""NET lifecycle for fixed geospatial providers, using the existing Session.

Small inline rasters and aggregate tables are request evidence. This adapter
does not acquire scenes, register external programs, or admit canonical state.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import platform
import tempfile

import numpy as np

from .control_contracts import json_tree, keys, load, save_new, text
from .core.identities import evidence_id, new_identity, validate_evidence_identity
from .core.records import validate_run_structure
from .operations.registry import Operation, default_registry
from .operations.runner import digest, seal

REQUEST_SCHEMA = 'ciw.geomatics-request.v1'
RESULT_SCHEMA = 'ciw.geomatics-payload.v1'
AUTHORITY = {'physical_validation':'not_established', 'state_admission':'not_performed',
             'source_authenticity':'not_established', 'hardware_actuation':'not_performed'}
MAX_BYTES = 8 * 1024 * 1024
MAX_PRETTY_REQUEST_BYTES = 2 * 1024 * 1024
MAX_PRETTY_OUTPUT_BYTES = 1024 * 1024

def _check_pretty_size(value, limit, message):
    # Bound expanded JSON before Session writes its indented retained records.
    if len((json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf-8')) > limit:
        raise ValueError(message)

def validate_request(request):
    from net_geomatics.catalog import OPERATIONS
    json_tree(request)
    keys(request, {'schema','operation_id','provenance','parameters'})
    if request['schema'] != REQUEST_SCHEMA or request['operation_id'] not in OPERATIONS:
        raise ValueError('Unknown geomatics request or operation')
    keys(request['provenance'], {'source_kind','source_ref'})
    if request['provenance']['source_kind'] not in {'synthetic','operator_supplied'}:
        raise ValueError('Declare synthetic or operator_supplied source kind')
    text(request['provenance']['source_ref'])
    if type(request['parameters']) is not dict:
        raise ValueError('Parameters must be an object')
    from .core.identities import canonical_json
    if len(canonical_json(request).encode()) > 512 * 1024:
        raise ValueError('Inline geomatics request exceeds 512 KiB')
    _check_pretty_size(request, MAX_PRETTY_REQUEST_BYTES,
                       'Indented geomatics request exceeds 2 MiB')
    return deepcopy(request)

def example(operation_id):
    from net_geomatics.catalog import EXAMPLES
    if operation_id not in EXAMPLES:
        raise ValueError('Unknown geomatics example')
    return {'schema':REQUEST_SCHEMA, 'operation_id':operation_id,
            'provenance':{'source_kind':'synthetic','source_ref':'synthetic:geomatics-reference-example'},
            'parameters':deepcopy(EXAMPLES[operation_id])}

def runtime_identity():
    import net_geomatics
    files = sorted(Path(net_geomatics.__file__).parent.glob('*.py')) + [Path(__file__)]
    raw = b'\0'.join(p.name.encode()+b'\0'+p.read_text(encoding='utf-8').replace('\r\n','\n').encode() for p in files)
    return {'provider':'net_geomatics.reference.v1', 'code_sha256':sha256(raw).hexdigest(),
            'source_normalization':'utf8_lf','python':platform.python_version(),'numpy':np.__version__,
            'scope':'bounded_geospatial_reference_calculations'}

def make_source(request):
    from .adapters.protocol import InstrumentManifest
    request = validate_request(request)
    manifest = InstrumentManifest(instrument_id='geomatics-declaration.v1',
        role='declared_geospatial_inputs', units={'configuration_index':'1'},
        frames=('geomatics.declared-input.v1',),
        sampling={'kind':'one_configuration_declaration','time_semantics':'synthetic_selection_envelope'},
        supported_operations=(request['operation_id'],),
        calibration_requirements={'source_authenticity':'not_established'})
    source = {'run_schema':'run.v1','run_id':'run-geomatics-'+digest(request)[7:23],
              'instrument':'geomatics-declaration.v1',
              'metadata':{'duration_s':1.0,'sample_count':1,'sample_rate_hz':None,
                          'coordinate_frame':'geomatics.declared-input.v1',
                          'manifest':manifest.to_dict(),
                          'geomatics_request':request,
                          'provenance':{'source':'declared geomatics input; source authenticity not established',
                                        'generator':'ciw.geomatics_workflow.make_source','generator_version':1}},
              'time_s':[0.0], 'channels':{'configuration_index':{'unit':'1','values':[0.0]}},'render':{}}
    source['evidence_id'] = evidence_id(source)
    return source

def source_request(source):
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = validate_request(source['metadata']['geomatics_request'])
    if source != make_source(request):
        raise ValueError('Geomatics source differs from the exact declaration')
    return request

def _execute(source, parameters, operation_id):
    from net_geomatics.catalog import execute
    keys(parameters, set())
    request = source_request(source)
    if operation_id != request['operation_id']:
        raise ValueError('Operation differs from source declaration')
    output = execute(operation_id, request['parameters'])
    json_tree(output)
    _check_pretty_size(output, MAX_PRETTY_OUTPUT_BYTES,
                       'Indented geomatics output exceeds 1 MiB')
    return {'schema':RESULT_SCHEMA,'operation_id':operation_id,'request_digest':digest(request),
            'output':output, 'authority':deepcopy(AUTHORITY)}

def registry():
    from net_geomatics.catalog import OPERATIONS
    result = default_registry()
    for operation_id in OPERATIONS:
        result.register(Operation(operation_id, 'backend',
            lambda source, parameters, op=operation_id: _execute(source, parameters, op), runtime_identity))
    return result

def validate_payload(operation_id, data, source, parameters, selection):
    """Validate retained commitments without executing any numerical provider."""
    from net_geomatics.catalog import validate_output
    request = source_request(source)
    keys(parameters, set())
    keys(data, {'schema','operation_id','request_digest','output','authority'})
    if (request['operation_id'] != operation_id or data['operation_id'] != operation_id or
        data['schema'] != RESULT_SCHEMA or data['request_digest'] != digest(request) or
        data['authority'] != AUTHORITY or type(data['output']) is not dict):
        raise ValueError('Geomatics payload identity or authority mismatch')
    if selection['channel'] != 'configuration_index' or selection['interval_s'] != [0.0,1.0]:
        raise ValueError('Geomatics requires the full declared configuration')
    json_tree(data)
    _check_pretty_size(data['output'], MAX_PRETTY_OUTPUT_BYTES,
                       'Indented geomatics output exceeds 1 MiB')
    validate_output(operation_id, request['parameters'], data['output'])

def run(request, destination):
    from .session import Session, envelope
    source = make_source(request)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    session = Session(source, destination, operations=registry())
    reply = session.handle(envelope('operation.execute',
        {'operation_id':request['operation_id'],'parameters':{}},new_identity('execution')))
    session.save_workspace(destination/'workspace.json')
    if reply['type'] != 'response':
        raise ValueError(reply['payload']['message'])
    return inspect(destination)

def _read(destination):
    from .session import Session
    path = Path(destination)/'workspace.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Require regular bounded geomatics workspace')
    # Restore a single bounded snapshot, never reopen mutable source bytes.
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Workspace exceeds 8 MiB')
    with tempfile.TemporaryDirectory(prefix='geomatics-inspect-') as temporary:
        snapshot = Path(temporary)/'workspace.json'
        snapshot.write_bytes(raw)
        session = Session.from_workspace(snapshot, Path(temporary)/'restored')
    request = source_request(session.run)
    executions = list(session.executions.values())
    results = list(session.results.values())
    if len(executions) != 1 or executions[0]['operation_id'] != request['operation_id']:
        raise ValueError('Expected one declared geomatics execution')
    execution = executions[0]
    if execution['status'] == 'completed':
        if len(results) != 1 or results[0]['result_id'] != execution['result_id']:
            raise ValueError('Expected exact retained geomatics result')
    elif results:
        raise ValueError('Refused execution cannot contain results')
    return session, execution, results[0] if results else None

def inspect(destination):
    session, execution, result = _read(destination)
    return {'status':execution['status'],'source_evidence_id':session.run['evidence_id'],
            'operation_id':execution['operation_id'],'execution_id':execution['execution_id'],
            'result':result,'refusal':execution.get('refusal'), 'authority':deepcopy(AUTHORITY),
            'inspection_scope':'retained_record_integrity_only; no numerical execution'}

def replay(destination, output_dir):
    old_session, old_execution, old_result = _read(destination)
    if old_result is None:
        raise ValueError('Cannot reproduce a refused execution')
    if old_execution['runtime'] != runtime_identity():
        raise ValueError('Installed runtime differs from retained geomatics runtime')
    fresh = run(source_request(old_session.run), output_dir)
    if fresh['status'] != 'completed':
        raise ValueError('Fresh reproduction refused; inspect retained output')
    receipt = seal({'schema':'ciw.geomatics-reproduction.v1',
                   'verification_id':new_identity('verification'),
                   'source_evidence_id':old_session.run['evidence_id'],
                   'subject_result_id':old_result['result_id'],
                   'subject_record_digest':old_result['record_digest'],
                   'reproduced_result_id':fresh['result']['result_id'],
                   'reproduced_record_digest':fresh['result']['record_digest'],
                   'reproduced_execution_id':fresh['execution_id'],
                   'numerical_match':digest(old_result['data']) == digest(fresh['result']['data']),
                   'method':'same_runtime_fresh_execution_exact_payload_comparison',
                   'independent':False,'authority':deepcopy(AUTHORITY)})
    save_new(Path(output_dir)/'reproduction.json', receipt)
    return receipt

def catalog():
    from net_geomatics.catalog import OPERATIONS
    return {'schema':'ciw.geomatics-catalog.v1',
            'operations':[{'operation_id':op, 'provider':'net_geomatics.reference.v1',
                           'example_available':True} for op in sorted(OPERATIONS)],
            'scope':'bounded reference tools; course-aligned subset, not complete syllabus coverage',
            'authority':deepcopy(AUTHORITY)}
