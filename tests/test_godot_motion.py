"""Host/transport tests. Python child fixtures are NOT native Godot evidence."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import threading
import time
from unittest.mock import patch

import pytest

from ciw import godot_motion as native
from ciw.adapters.protocol import AdapterRefusal
from ciw.simulation_reference import ReferenceMotion
from ciw.telemetry import canonical


@pytest.mark.parametrize('seed', [0, 7, 2**31-1])
def test_reference_shape_is_accepted(seed):
    source = ReferenceMotion(seed=seed)
    assert native.validate_snapshot(source.snapshot(), source.configuration())['state']['rng'] == seed


@pytest.mark.parametrize('bad', [True, -1, 2**31, 7.0, '7', None])
def test_seed_refusal(bad):
    with pytest.raises(ValueError):
        native.configuration(bad)


@pytest.mark.parametrize('mutation', ['rng_absent', 'rng_boolean', 'queue_absent', 'queue_past',
    'queue_large', 'history_absent', 'history_cut', 'history_last', 'revision', 'position', 'unknown', 'config'])
def test_incomplete_or_malformed_continuation_refuses(mutation):
    provider = ReferenceMotion()
    provider.lifecycle('start');provider.step(1)
    value = json.loads(provider.snapshot());s = value['state']
    if mutation == 'rng_absent':s.pop('rng')
    elif mutation == 'rng_boolean':s['rng'] = True
    elif mutation == 'queue_absent':s.pop('queued')
    elif mutation == 'queue_past':s['queued'] = [{'at_tick': 1, 'delta_v': 1}]
    elif mutation == 'queue_large':s['queued'] = [{'at_tick': 2, 'delta_v': 1}]*17
    elif mutation == 'history_absent':s.pop('history')
    elif mutation == 'history_cut':s['history'] = s['history'][:-1]
    elif mutation == 'history_last':s['position'] += 1
    elif mutation == 'revision':s['revision'] = 0
    elif mutation == 'position':s['position'] = float('inf')
    elif mutation == 'unknown':value['program'] = 'do not execute'
    else:value['configuration_ref'] = 'sha256:'+'0'*64
    with pytest.raises((ValueError, AdapterRefusal)):
        native.validate_snapshot(json.dumps(value).encode(), provider.configuration())


@pytest.mark.parametrize('raw', [b'', b'[]', b'{"state":{},"state":{}}', b'null', b' '*32769], ids=['empty','array','duplicate','null','oversize'])
def test_bad_snapshot_encoding(raw):
    with pytest.raises((ValueError, AdapterRefusal)):
        native.validate_snapshot(raw, native.configuration())


def test_binary_pin_refused_before_process(tmp_path, monkeypatch):
    monkeypatch.setattr(native.subprocess, 'Popen', lambda *a,**kw:pytest.fail('unbound binary executed'))
    with pytest.raises(ValueError, match='digest mismatch'):
        native.GodotMotion(Path(sys.executable), 'sha256:'+'0'*64)


def test_asset_resource_presence():
    assets=native.files('ciw').joinpath('engine_assets','godot_motion')
    script=assets.joinpath('worker.gd').read_text(encoding='utf-8')
    assert 'extends SceneTree' in script and '1103515245' in script
    for forbidden in ['OS.execute','OS.create_process','HTTPRequest','WebSocket','load(args','eval(']:
        assert forbidden not in script
    assert '[autoload]' not in assets.joinpath('project.godot').read_text()


# This child only tests the bounded mailbox transport. No model or engine is
# emulated; actual native evidence must come from the separate Godot campaign.
CHILD = r'''
import json, pathlib, sys, time, os
root=pathlib.Path.cwd(); mode=sys.argv[1]
(root/'ready').write_text('ready')
for _ in range(10):
    request=root/'request.json'
    while not request.exists():time.sleep(.001)
    value=json.loads(request.read_bytes());request.unlink()
    if mode=='die':sys.exit(3)
    if mode=='timeout':time.sleep(5);sys.exit(3)
    if mode=='log':
        sys.stdout.buffer.write(b'x'*70000);sys.stdout.flush();time.sleep(5);sys.exit(3)
    response=dict(schema='ciw.godot-motion-response.v1',sequence=value['sequence'],nonce=value['nonce'],status='ok',data=value['arguments'],error=None)
    if mode=='nonce':response['nonce']='bad'
    if mode=='sequence':response['sequence']=True
    if mode=='refused':response.update(status='refused',data={},error='explicit fixture refusal')
    raw=json.dumps(response).encode()
    if mode=='large':raw=b'x'*140000
    if mode=='json':raw=b'not json'
    if mode=='duplicate':raw=b'{"schema":"a","schema":"b"}'
    tmp=root/'response.pending';tmp.write_bytes(raw);os.replace(tmp,root/'response.json')
'''


def mailbox(tmp_path, mode, timeout=5):
    transport = native._Mailbox([sys.executable,'-I','-u','-c',CHILD,mode],tmp_path,timeout=timeout)
    end=time.monotonic()+10
    while not (tmp_path/'ready').exists():
        if time.monotonic()>end or transport.process.poll() is not None:
            transport.close();pytest.fail('Transport fixture did not start')
        time.sleep(.005)
    return transport


def test_actual_persistent_mailbox_transport(tmp_path):
    transport=mailbox(tmp_path,'echo')
    try:
        pid=transport.process.pid
        for i in range(3):
            assert transport.exchange('echo',{'value':i})=={'value':i}
            assert transport.process.pid==pid and transport.process.poll() is None
        assert transport.sequence==3
    finally:transport.close()
    assert transport.process.poll() is not None


@pytest.mark.parametrize('mode',['die','timeout','log','nonce','sequence','refused','large','json','duplicate'])
def test_failed_mailbox_is_killed_and_cannot_be_reused(tmp_path,mode):
    transport=mailbox(tmp_path,mode,timeout=.25 if mode=='timeout' else 5)
    expected={'die':'exited|unavailable','timeout':'deadline','log':'diagnostic lifetime',
              'nonce':'identity mismatch','sequence':'identity mismatch','refused':'explicit fixture refusal',
              'large':'byte budget','json':'unambiguous JSON','duplicate':'unambiguous JSON'}[mode]
    with pytest.raises(AdapterRefusal,match=expected):transport.exchange('fixture',{})
    assert transport.closed and transport.process.poll() is not None
    assert len(transport.log)<=native.LOG_LIMIT
    with pytest.raises(AdapterRefusal):transport.exchange('fixture',{})
    transport.close()


def test_concurrent_mailbox_refuses_without_second_request(tmp_path):
    transport=mailbox(tmp_path,'echo')
    transport._lock.acquire()
    try:
        with pytest.raises(AdapterRefusal,match='One engine request'):
            transport.exchange('fixture',{})
        assert transport.sequence==0 and not (tmp_path/'request.json').exists()
    finally:
        transport._lock.release();transport.close()


def test_stale_response_refuses(tmp_path):
    transport=mailbox(tmp_path,'echo')
    (tmp_path/'response.json').write_text('{}')
    with pytest.raises(AdapterRefusal, match='Contaminated'):
        transport.exchange('fixture',{})
    assert transport.closed


def test_restoration_requires_unchanged_configuration():
    original=ReferenceMotion(seed=7)
    with pytest.raises(ValueError, match='configuration'):
        native.validate_snapshot(original.snapshot(),native.configuration(8))


def test_no_numeric_native_execution_during_validation(monkeypatch):
    source=ReferenceMotion().snapshot()
    monkeypatch.setattr(native.subprocess,'Popen',lambda *a,**k:pytest.fail('engine launched'))
    assert native.validate_snapshot(source,native.configuration())['state']['tick']==0


def test_existing_study_route_and_new_native_route_coexist(capsys):
    from ciw.net import main
    assert main(['simulate','describe']) == 0
    assert json.loads(capsys.readouterr().out)['state_owner']=='existing ciw.simulation.Simulation'
    with pytest.raises(SystemExit) as exc:
        main(['simulation','godot','--help'])
    assert exc.value.code==0


def test_existing_output_refused_before_engine(tmp_path,monkeypatch):
    from ciw.godot_motion_study import demo
    monkeypatch.setattr(native,'GodotMotion',lambda *a,**kw:pytest.fail('engine started'))
    with pytest.raises(ValueError,match='new study directory'):
        demo(Path('unused'),'unused',tmp_path)


def test_inspector_cannot_execute_saved_data(tmp_path,monkeypatch):
    from ciw.godot_motion_study import inspect
    monkeypatch.setattr(native.subprocess,'Popen',lambda *a,**kw:pytest.fail('engine started'))
    (tmp_path/'study.json').write_text('{"program":"do not execute"}')
    with pytest.raises(ValueError):inspect(tmp_path)
