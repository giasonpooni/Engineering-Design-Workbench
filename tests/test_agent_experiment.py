"""Measurement contracts; simulated unit data is not actual model/runtime evidence."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from ciw.agent_experiment import read_revision, summarize, audit_attempt
from ciw.control_contracts import bytes_ref
from test_workcell_smith import cell


def decision(tmp_path):
    source=tmp_path/'candidate.gd';source.write_text('synthetic candidate fixture')
    doc={'schema':'ciw.agent-revision.v1','revision_id':'r1','agent_id':'fixture',
        'mode':'interactive_llm_session','author_attestation':'current_assistant_session_self_reported_not_provider_signed',
        'decision_summary':'Unit-test source declaration, not an LLM run.',
        'observed_evidence':[{'kind':'native_preview','label':'view.png','sha256':'sha256:'+'a'*64}],
        'replacements':{'workshops/workshop_world.gd':{'file':'candidate.gd','sha256':bytes_ref(source.read_bytes())}},
        'provider_usage':None,'human_active_seconds':None,'external_review':'not_performed'}
    return doc


def read(tmp_path,doc):
    p=tmp_path/'decision.json';p.write_text(json.dumps(doc))
    return read_revision(p,bytes_ref(p.read_bytes()),agent_id='fixture',writable=('workshops/workshop_world.gd',))


def test_source_freeze_no_execution(tmp_path):
    doc=decision(tmp_path)
    with patch('subprocess.Popen',side_effect=AssertionError('execution')):
        got,changes=read(tmp_path,doc)
    assert got==doc and changes=={'workshops/workshop_world.gd':'synthetic candidate fixture'}


@pytest.mark.parametrize('fault',['agent','mode','usage','human','review','hash','path','target','empty','extra','bool_digest','summary'])
def test_invalid_or_self_awarded_fields(tmp_path,fault):
    doc=decision(tmp_path)
    if fault=='agent':doc['agent_id']='other'
    elif fault=='mode':doc['mode']='autonomous_provider'
    elif fault=='usage':doc['provider_usage']={'cost_usd':0}
    elif fault=='human':doc['human_active_seconds']=0
    elif fault=='review':doc['external_review']='approved'
    elif fault=='hash':doc['replacements']['workshops/workshop_world.gd']['sha256']='sha256:'+'0'*64
    elif fault=='path':doc['replacements']['workshops/workshop_world.gd']['file']='../escape'
    elif fault=='target':doc['replacements']['workcells/smith_probe.gd']=doc['replacements'].pop('workshops/workshop_world.gd')
    elif fault=='empty':doc['replacements']={}
    elif fault=='extra':doc['shell']='anything'
    elif fault=='bool_digest':doc['observed_evidence'][0]['sha256']=True
    else:doc['decision_summary']='x'*4097
    with pytest.raises((ValueError,TypeError)):read(tmp_path,doc)


def test_linked_candidate_refused(tmp_path):
    doc=decision(tmp_path);p=tmp_path/'candidate.gd';text=p.read_bytes();p.unlink()
    (tmp_path/'elsewhere').write_bytes(text);p.symlink_to(tmp_path/'elsewhere')
    with pytest.raises(ValueError):read(tmp_path,doc)


def measurement(cid, occurrence, accepted):
    return {'candidate_id':cid,'package_accepted':accepted,'execution_count':1,
            'captured_stage_wall_s':.2,'duration_coverage':'complete',
            'stages':[{'execution_id':occurrence,'container_id':occurrence}]}


def test_unique_changes_not_baseline_or_replays():
    base=measurement('base','b',True)
    summary=summarize(base,[measurement('base','repeat',True),measurement('c','c1',False),measurement('c','c2',True)])
    assert summary['unique_changed_candidates']==1
    assert summary['unique_technically_accepted_revisions']==1
    assert summary['workcell_execution_attempts']==4
    assert summary['accepted_revisions_per_human_hour'] is None
    assert summary['independently_art_accepted_revisions'] is None
    assert summary['model_cost_usd'] is None


def test_rejection_is_recorded_not_qualification_failure():
    summary=summarize(measurement('b','b',True),[measurement('c','c',False)])
    assert summary['unique_changed_candidates']==1 and summary['technical_acceptance_fraction']==0.0


def test_duplicate_occurrence_refused():
    m=measurement('c','same',True)
    with pytest.raises(ValueError):summarize(m,[m])


def test_missing_time_not_zero_or_full_coverage():
    row=measurement('c','c',False);row['duration_coverage']='partial_refused_execution'
    assert summarize(measurement('b','b',True),[row])['duration_coverage']=='partial'


def test_audit_reuses_original_gates_and_is_provider_free(cell):
    h,_,_=cell;candidate=h.submit('one',{});h.build('one',candidate['candidate'])
    root=h.root/'runs/one';before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with patch('subprocess.Popen',side_effect=AssertionError('execution')):
        result=audit_attempt(root)
    assert result['package_accepted'] and result['candidate_id']==candidate['candidate_id']
    assert result['captured_stage_wall_s']==pytest.approx(.3)
    assert all(p.read_bytes()==v for p,v in before.items())


def test_audit_refuses_tampered_gate(cell):
    h,_,_=cell;c=h.submit('one',{});h.build('one',c['candidate'])
    root=h.root/'runs/one';(root/'attempt-0002-checks.json').write_text('{}')
    with pytest.raises(ValueError):audit_attempt(root)
