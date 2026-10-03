from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest

from ciw import workflow_algebra as a, workflow_production as p
from ciw.workflow_cli import audit_slot
from ciw.control_contracts import load, save_new
from ciw.core.identities import content_identity
from ciw.net import main


def test_installed_cli_compile_inspect_and_demo(tmp_path):
    source=tmp_path/'expressions'
    with patch('subprocess.Popen',side_effect=AssertionError('process')):
        assert main(['compose','example','--output-dir',str(source)])==0
        assert main(['compose','check',str(source/'graph.json')])==0
        for target in ('graph','production'):
            output=tmp_path/(target+'.json')
            assert main(['compose','compile',str(source/(target+'.json')),'--output',str(output)])==0
            assert main(['compose','inspect',str(output)])==0
        assert main(['compose','example','--output-dir',str(source)])==1
    assert main(['compose','demo','--output-dir',str(tmp_path/'demo')])==0
    report=load(tmp_path/'demo/summary.json')
    assert report['analysis_executions']==2 and report['production_executions']==3
    assert not report['parallel_scheduling']
    assert main(['compose','demo','--output-dir',str(tmp_path/'demo')])==1


def test_saved_file_never_selects_a_module(tmp_path):
    path=tmp_path/'untrusted.json'
    save_new(path,{'schema':'ciw.workflow-request.v1','target':'graph','expression':{'kind':'import','module':'os'}})
    assert main(['compose','compile',str(path),'--output',str(tmp_path/'absent.json')])==1
    assert not (tmp_path/'absent.json').exists()


def make_slot(tmp_path):
    from test_workcell import FixtureBackend,ROOT
    from ciw.workcell import WorkcellHost
    from ciw.foundry_packets import inventory
    source=ROOT/'examples/workcells/godot-prop';root=tmp_path/'cell'
    host=WorkcellHost(source,root,FixtureBackend(),expected_source_id=inventory(source)['inventory_id'])
    candidate=host.submit('one',{});host.build('one',candidate['candidate'])
    return root


def test_slot_audit_connects_original_run_and_compilation_without_execution(tmp_path):
    root=make_slot(tmp_path)
    old={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with patch('subprocess.Popen',side_effect=AssertionError('execution')):
        report=audit_slot(root)
    assert len(report['checked'])==1 and report['checked'][0]['execution_count']==3
    assert report['fresh_execution'] is False
    assert all(path.read_bytes()==raw for path,raw in old.items())


def test_slot_audit_rejects_alternative_valid_but_unexecuted_plan(tmp_path):
    from ciw.operations.runner import seal
    from ciw.workflow_production import _lower
    root=make_slot(tmp_path)
    receipt=load(root/'compilation-one.json')
    wrong=_lower(receipt['expression'],receipt['templates'],receipt['declarations'],receipt['contracts'],
                 receipt['gate_runtimes'],receipt['grant_snapshot'],plan_id='not-executed',
                 project_id=receipt['plan']['project_id'],source_evidence_id=receipt['plan']['source_evidence_id'])
    path=root/'compilation-one.json';path.unlink();save_new(path,wrong)
    with pytest.raises(ValueError,match='Executed plan'):audit_slot(root)


def test_slot_audit_rejects_linked_inputs(tmp_path):
    root=make_slot(tmp_path);path=root/'compilation-one.json'
    other=tmp_path/'other.json';other.write_bytes(path.read_bytes());path.unlink();path.symlink_to(other)
    with pytest.raises(ValueError):audit_slot(root)


def test_stage_barriers_do_not_claim_dataflow_interchange():
    from ciw.workflow_production import _stage_graph
    f,g,h,k=(p.stage(name) for name in 'abcd')
    whole=p._stage_graph(a.sequence(a.parallel(f,g),a.parallel(h,k)))
    separate=p._stage_graph(a.parallel(a.sequence(f,h),a.sequence(g,k)))
    assert whole[1]['c']=={'a','b'} and separate[1]['c']=={'a'}
    assert whole[1]!=separate[1]  # Do not optimize away a required acceptance barrier.
