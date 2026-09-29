"""NET DSP boundary tests with an actual separately supplied SCR native library."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import uuid
import pytest

from ciw import dsp
from ciw.control_contracts import load
from ciw.control_checks import compare
from ciw.instruments import make_demo_run
from ciw.operations.registry import OperationRegistry
from ciw.operations.runner import execute
from ciw.session import Session

@pytest.fixture
def source(): return make_demo_run()
@pytest.fixture
def params(): return {'channel':'q','interval_s':[0.,12.],'taps':[.25,.5,.25],'initial_history':[0.,0.],'clock_id':'oscillator-model-time'}
@pytest.fixture
def binding():
    # Ordinary NET installs need no native kernel. The dedicated qualification
    # explicitly requires it and also rejects skipped cases in its JUnit gate.
    value=os.environ.get('SCR_DSP_LIBRARY')
    if not value:
        if os.environ.get('CIW_REQUIRE_DSP_NATIVE') == '1':
            pytest.fail('Dedicated DSP qualification requires SCR_DSP_LIBRARY')
        pytest.skip('Optional SCR DSP library not bound; dedicated DSP CI requires it')
    path=Path(value)
    return dsp.FirBinding(path,expected_sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest())

def call(binding,source,params):
    registry=OperationRegistry();registry.register(binding.operation())
    selection={'revision':0,'channel':params['channel'],'interval_s':params['interval_s']}
    return execute(registry,source,selection,'recording.json',dsp.OPERATION,params)


def test_native_output_retains_source_and_separate_occurrences(binding,source,params):
    original=deepcopy(source);a,ra=call(binding,source,params);b,rb=call(binding,source,params)
    assert a['status']==b['status']=='completed' and source==original
    assert a['execution_id']!=b['execution_id'] and ra['result_id']!=rb['result_id']
    assert ra['data']==rb['data'] and ra['verification_id'] is None
    assert ra['data']['time_s']==source['time_s']
    assert ra['data']['uncertainty_propagation']=='not_performed'
    assert compare(dsp.observations(ra,semantics='reference')['observations'],dsp.observations(rb,semantics='reference')['observations'],atol=0)['outcome']['status']=='PASS'


def test_selected_chunks_keep_actual_predecessors(binding,source,params):
    _,whole=call(binding,source,params)
    first=deepcopy(params);first['interval_s']=[0.,3.]
    last=deepcopy(params);last['interval_s']=[3.,12.]
    _,left=call(binding,source,first);_,right=call(binding,source,last)
    assert left['data']['values']+right['data']['values']==whole['data']['values']
    assert right['data']['history_used']==source['channels']['q']['values'][190:192]

@pytest.mark.parametrize('field,value',[('taps',[]),('taps',[True]),('taps',[float('nan')]),('taps',[1.]*65),('initial_history',[]),('initial_history',[None,0.]),('clock_id',''),('channel','absent'),('interval_s',[2.,1.])])
def test_invalid_parameters_refuse_without_result(binding,source,params,field,value):
    params[field]=value
    try: occurrence,result=call(binding,source,params)
    except ValueError:
        assert field=='taps' and any(isinstance(x,float) and x!=x for x in value)
    else: assert occurrence['status']=='refused' and result is None


def test_oldest_history_orientation_and_explicit_initialization(binding,source,params):
    params['initial_history']=[4.,5.]
    _,result=call(binding,source,params)
    assert result['data']['values'][0]==.25*source['channels']['q']['values'][0]+.5*5.+.25*4.


def test_provider_free_inspection(binding,source,params,tmp_path):
    registry=OperationRegistry();registry.register(binding.operation())
    session=Session(source,tmp_path/'session',operations=registry)
    response=session.handle({'protocol_version':1,'request_id':uuid.uuid4().hex,'type':'operation.execute','payload':{'operation_id':dsp.OPERATION,'parameters':params}})
    assert response['type']!='error'
    path=tmp_path/'session/workspace.json';session.save_workspace(path);before=path.read_bytes()
    with patch('ctypes.CDLL',side_effect=AssertionError('native loading')),patch('subprocess.Popen',side_effect=AssertionError('process')):
        inspected=dsp.inspect(path)
    assert inspected['fresh_execution'] is False and path.read_bytes()==before
    assert inspected['numerical_verification']=='not_performed'

@pytest.mark.parametrize('field,value',[('unit','Hz'),('clock_id','other'),('source_evidence_id','sha256:'+'0'*64),('phase','zero_phase'),('final_history',[0.,0.]),('values',[None]),('extra',True)])
def test_offline_payload_tamper_refused(binding,source,params,field,value):
    _,result=call(binding,source,params);data=result['data'];data[field]=value
    with pytest.raises(ValueError):dsp.validate_payload(dsp.OPERATION,data,source,params,{})


def test_cli_demo_and_create_only(binding,tmp_path):
    from ciw.net import main
    args=['dsp','demo','--library',str(binding.native.path),'--library-sha256',binding.native.digest,'--output-dir',str(tmp_path/'demo')]
    assert main(args)==0
    assert main(['dsp','inspect',str(tmp_path/'demo/workspace.json')])==0
    assert main(args)==1


def test_no_new_default_operations():
    from ciw.operations.registry import default_registry
    assert dsp.OPERATION not in [r['operation_id'] for r in default_registry().describe()]


def signal_record():
    from ciw.adapters.protocol import InstrumentManifest
    from ciw.core.identities import evidence_id
    manifest=InstrumentManifest(instrument_id='test.dsp-signal',role='measurement_adapter',
        units={'q':'m'},frames=('test-rig',),sampling={'kind':'uniform'},supported_operations=())
    run={'run_schema':'run.v1','run_id':'run-dsp-fixture','instrument':manifest.instrument_id,
         'metadata':{'duration_s':2.,'sample_count':8,'sample_rate_hz':4.,'coordinate_frame':'test-rig',
                     'manifest':manifest.to_dict(),'provenance':{'source':'synthetic sensor fixture, not acquired measurements'}},
         'time_s':[i/4 for i in range(8)],'channels':{'q':{'unit':'m','values':[float(i) for i in range(8)]}},'render':{}}
    run['evidence_id']=evidence_id(run);return run

@pytest.mark.parametrize('fault',['selected_missing','predecessor_missing','unknown_rate','irregular_clock'])
def test_signal_contract_refuses_unqualified_samples(binding,params,fault):
    from ciw.core.identities import evidence_id
    source=signal_record();params['interval_s']=[1.,2.]
    if fault=='selected_missing': source['channels']['q']['values'][5]=None
    elif fault=='predecessor_missing': source['channels']['q']['values'][3]=None
    elif fault=='unknown_rate': source['metadata']['sample_rate_hz']=None
    else: source['time_s'][3]+=.01
    source['evidence_id']=evidence_id(source)
    occurrence,result=call(binding,source,params)
    assert occurrence['status']=='refused' and result is None


def test_generic_sensor_record_and_support_scoped_missingness(binding,params):
    from ciw.core.identities import evidence_id
    source=signal_record();source['channels']['q']['values'][0]=None
    source['evidence_id']=evidence_id(source);params['interval_s']=[1.,2.]
    occurrence,result=call(binding,source,params)
    assert occurrence['status']=='completed'
    assert result['data']['history_used']==[2.,3.] and result['data']['values']==[3.,4.,5.,6.]


@pytest.mark.parametrize('field', ['source_indices', 'time_s'])
def test_boolean_cannot_replace_numeric_source_metadata(binding,source,params,field):
    _,result=call(binding,source,params)
    result['data'][field][0]=False
    with pytest.raises(ValueError,match='source/clock/units/contract'):
        dsp.validate_payload(dsp.OPERATION,result['data'],source,params,{})
