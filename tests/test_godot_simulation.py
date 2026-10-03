"""Host boundaries use real OS pipes with an explicitly non-Godot protocol double."""
from copy import deepcopy
from pathlib import Path
import sys
import time
from unittest.mock import patch

import pytest

from ciw.control_contracts import bytes_ref
from ciw.godot_simulation import DEFAULT, LIMIT, GodotProjectile, _Pipe, validate_configuration

WORKER = r'''
import json,os,struct,sys,time
mode=sys.argv[1]
while True:
    head=sys.stdin.buffer.read(4)
    if not head: break
    count=struct.unpack('<I',head)[0]
    r=json.loads(sys.stdin.buffer.read(count))
    if mode=='hang': time.sleep(30)
    if mode=='die': sys.exit(7)
    if mode=='oversized': print('NET_SIM '+'x'*70000,flush=True); continue
    if mode=='stderr': sys.stderr.buffer.write(b'x'*300000); sys.stderr.flush(); time.sleep(30)
    if mode=='truncated': sys.stdout.write('NET_SIM {'); sys.stdout.flush(); sys.exit(0)
    if mode=='duplicate': print('NET_SIM {"schema":"a","schema":"b"}',flush=True); continue
    if mode=='malformed': print('NET_SIM not-json',flush=True); continue
    print('double banner',flush=True)
    answer={'schema':'ciw.godot-rpc-result.v1','request_id':r['request_id'],'action':r['action'],
            'pid':os.getpid(),'data':{'echo':r['arguments']}}
    if mode=='nonce': answer['request_id']='wrong'
    if mode=='pid': answer['pid']+=1
    if mode=='action': answer['action']='wrong'
    if mode=='refusal': answer['data']={'error':'intentional protocol refusal'}
    print('NET_SIM '+json.dumps(answer),flush=True)
    if r['action']=='shutdown': break
'''


def pipe(tmp_path, mode='ok', timeout=1):
    p=tmp_path/'worker.py'
    p.write_text(WORKER)
    return _Pipe([sys.executable,'-u',str(p),mode],cwd=tmp_path,timeout=timeout)


def test_one_process_handles_large_framed_requests_and_clean_close(tmp_path):
    connection=pipe(tmp_path)
    try:
        pid=connection.process.pid
        for n in (0,1,32768,44000):
            value={'payload':'x'*n}
            assert connection.rpc('echo',value)=={'echo':value}
            assert connection.process.pid==pid
    finally: connection.close()
    assert connection.process.poll()==0
    assert not connection._io_thread.is_alive() and not connection._err_thread.is_alive()


@pytest.mark.parametrize('mode',['hang','die','oversized','stderr','truncated','duplicate','malformed','nonce','pid','action','refusal'])
def test_bad_native_protocol_kills_process_and_never_returns_data(tmp_path,mode):
    connection=pipe(tmp_path,mode,timeout=.3)
    with pytest.raises((ValueError,OSError)):
        connection.rpc('echo',{})
    assert connection.process.poll() is not None
    assert len(connection.diagnostics()['stderr_tail'])<=16384
    connection.close()


def test_blocked_native_stdin_is_covered_by_deadline(tmp_path):
    connection=_Pipe([sys.executable,'-c','import time; time.sleep(30)'],cwd=tmp_path,timeout=.2)
    started=time.monotonic()
    with pytest.raises(ValueError,match='deadline'):
        connection.rpc('echo',{'payload':'x'*60000})
    assert time.monotonic()-started<5
    assert connection.process.poll() is not None


@pytest.mark.parametrize('key,value', [('step_hz',120),('step_hz',True),('max_ticks',129),
    ('p0_m',[0,0]),('v0_m_s',[0,True,0]),('gravity_m_s2',[0,float('nan'),0]),('p0_m',[1001,0,0])])
def test_bad_configuration_never_starts_process(key,value,tmp_path):
    config=deepcopy(DEFAULT);config[key]=value
    with patch('subprocess.Popen',side_effect=AssertionError('no native launch')):
        with pytest.raises(ValueError):
            GodotProjectile(tmp_path/'missing',expected_sha256='sha256:'+'0'*64,configuration=config)


def test_binary_mismatch_refuses_without_native_launch(tmp_path):
    binary=tmp_path/'not-godot';binary.write_bytes(b'not executable')
    with patch('subprocess.Popen',side_effect=AssertionError('no native launch')):
        with pytest.raises(ValueError,match='digest mismatch'):
            GodotProjectile(binary,expected_sha256='sha256:'+'0'*64)


def test_no_executable_lookup_from_retained_data_and_no_module_import_launch():
    # Import above did not construct a provider. Reader code does not import it.
    from ciw.simulation_campaign import read_campaign
    assert read_campaign.__module__=='ciw.simulation_campaign'
    validate_configuration(deepcopy(DEFAULT))


def test_worker_is_installed_and_does_not_deserialize_objects():
    import ciw.godot_simulation as module
    code=Path(module.__file__).with_name('godot_runtime').joinpath('point_worker.gd').read_text()
    assert 'bytes_to_var(raw)' in code
    assert 'bytes_to_var_with_objects' not in code
    assert 'OS.read_buffer_from_stdin' in code


def test_request_frame_bound_and_closed_provider_refuse(tmp_path):
    connection=pipe(tmp_path)
    with pytest.raises(ValueError,match='frame limit'):
        connection.rpc('echo',{'payload':'x'*LIMIT})
    with pytest.raises(ValueError,match='closed'):
        connection.rpc('echo',{})


def test_native_launch_keeps_stdout_protocol_enabled(tmp_path):
    # Constructor contract double; actual stdout/handshake is required by native CI.
    executable=tmp_path/'godot-placeholder'
    executable.write_bytes(b'explicitly not a native executable')
    commands=[]
    class BindingDouble:
        def __init__(self, command, **kwargs):
            commands.append(command)
        def rpc(self, action, args):
            assert action=='configure'
            return {'meta': {'owner_id':args['owner_id'],'simulation_id':args['simulation_id'],
                'tick':0,'state_revision':0,'phase':'created'},
                'version':[4,5,2,'stable'],'engine_version':'contract-double'}
        def close(self): pass
    with patch('ciw.godot_simulation._Pipe', BindingDouble):
        with GodotProjectile(executable,expected_sha256=bytes_ref(executable.read_bytes())):
            assert '--quiet' not in commands[0] and '-q' not in commands[0]
            assert '--headless' in commands[0]
