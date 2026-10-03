"""Original production semantics exercised through the new compiler."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import pytest

from ciw import workflow_algebra as a, workflow_production as p
from ciw.control_contracts import load
from ciw.control_plane import builtin_registry
from ciw.core.identities import content_identity
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.production import Worker, inspect_production
from ciw.production_gates import builtin_gates
from ciw.production_workflow import builtin_plan


@pytest.fixture
def case():
    source=make_demo_run();original=builtin_plan(source)
    templates={job['job_id']:job for job in original['jobs']}
    declarations={name:p.declare_stage(job,effect=a.effects(reads=('recording/demo',)),permissions=('analyze',)) for name,job in templates.items()}
    return source,original,templates,declarations,builtin_registry(bind=True),builtin_gates(),a.grant(permissions=('analyze',))


def compile(expr,case):
    source,original,templates,declarations,registry,gates,rights=case
    return p.compile_plan(expr,templates,registry,declarations,gates,rights,
        **{key:original[key] for key in ('plan_id','project_id','source_evidence_id')})


def expression():
    return a.sequence(p.bounded_retry('select-window',max_attempts=2),p.stage('dependent-analysis'))


def run(value,case,root):
    source,_,templates,declarations,registry,gates,rights=case
    return p.run_compiled(source,value,registry,templates,declarations,gates,
        (Worker('local-analysis',('statistics.v1','spectrum.periodogram.v1')),),rights,root,max_operations=8)


def test_lowering_is_exact_original_plan_and_compilation_is_inert(case,tmp_path):
    with patch('ciw.production.run_graph',side_effect=AssertionError('execute')):
        value=compile(expression(),case)
    assert value['plan']==case[1]
    report=run(value,case,tmp_path/'run')
    assert report['status']=='completed' and report['execution_count']==3
    assert load(tmp_path/'run/attempt-0001.json')['status']=='rejected'
    assert load(tmp_path/'run/attempt-0002.json')['status']=='accepted'
    assert inspect_production(tmp_path/'run',case[5])['status']=='completed'
    assert p.inspect_compilation(value)['authorizes_execution'] is False


def test_no_retry_means_one_attempt_and_descendant_blocked(case,tmp_path):
    value=compile(a.sequence(p.stage('select-window'),p.stage('dependent-analysis')),case)
    report=run(value,case,tmp_path/'run')
    assert report['execution_count']==1
    assert report['jobs']['select-window']['status']=='rejected'
    assert report['jobs']['dependent-analysis']['status']=='blocked'


def test_missing_observation_holds_without_spending_next_variant(case,tmp_path):
    template=case[2]['select-window'];template['checks'][0]['policy']['path']=['absent']
    case[3]['select-window']=p.declare_stage(template,effect=a.effects(),permissions=('analyze',))
    value=compile(expression(),case);report=run(value,case,tmp_path/'run')
    assert report['jobs']['select-window']['status']=='held' and report['execution_count']==1


@pytest.mark.parametrize('expr',[p.stage('dependent-analysis'),a.parallel(p.stage('select-window'),p.stage('dependent-analysis')),
    a.sequence(p.stage('dependent-analysis'),p.stage('select-window'))])
def test_acceptance_prerequisites_cannot_be_removed_or_parallelized(case,expr):
    with pytest.raises(ValueError,match='acceptance predecessor'):compile(expr,case)


def test_series_barriers_are_associative_with_unit(case):
    first=p.bounded_retry('select-window',max_attempts=2);last=p.stage('dependent-analysis')
    one=compile(a.sequence(first,a.sequence(a.identity(),last)),case)
    two=compile(a.sequence(a.sequence(first,a.identity()),last),case)
    assert one['plan']==two['plan']==case[1]


def test_parallel_independent_jobs_continue_after_failure(case,tmp_path):
    case[2]['dependent-analysis']['depends_on']=[]
    case[3]['dependent-analysis']=p.declare_stage(case[2]['dependent-analysis'],effect=a.effects())
    value=compile(a.parallel(p.stage('select-window'),p.stage('dependent-analysis')),case)
    assert all(not j['depends_on'] for j in value['plan']['jobs'])
    report=run(value,case,tmp_path/'run')
    assert report['jobs']['dependent-analysis']['status']=='accepted' and report['jobs']['select-window']['status']=='rejected'


def test_parallel_conflict_requires_explicit_order(case):
    case[2]['dependent-analysis']['depends_on']=[]
    for name,job in case[2].items():case[3][name]=p.declare_stage(job,effect=a.effects(writes=('world',)))
    with pytest.raises(ValueError,match='effect conflict'):
        compile(a.parallel(p.stage('select-window'),p.stage('dependent-analysis')),case)
    assert compile(expression(),case)


@pytest.mark.parametrize('n',[0,4,True,1.5,'2'])
def test_bounded_feedback_refuses_invalid_limits(case,n):
    with pytest.raises(ValueError):compile(a.sequence(p.bounded_retry('select-window',max_attempts=n),p.stage('dependent-analysis')),case)


def test_retry_cannot_invent_missing_variants(case):
    with pytest.raises(ValueError,match='predeclared'):compile(p.bounded_retry('select-window',max_attempts=3),case)


@pytest.mark.parametrize('change',['route','global','model'])
def test_unselected_repair_cannot_hide_invalid_changes(case,change):
    job=case[2]['select-window'];graph=job['attempts'][1]
    if change=='route':graph['nodes'][0]['operation_id']='spectrum.periodogram.v1'
    elif change=='global':graph['parameters']={'new':'override'}
    else:graph['model_id']='other-model'
    seal(graph);case[3]['select-window']=p.declare_stage(job,effect=a.effects())
    with pytest.raises(ValueError):compile(p.stage('select-window'),case)


def test_same_receipt_cannot_self_award_missing_live_grant(case,tmp_path):
    value=compile(expression(),case)
    case[-1]['permissions']=['release']
    with pytest.raises(ValueError,match='permission'):run(value,case,tmp_path/'never-created')
    assert not (tmp_path/'never-created').exists()


def test_live_gate_or_template_changes_require_recompile(case,tmp_path):
    value=compile(expression(),case)
    gates=case[5];gate=gates['result.equals.v1']
    gates['result.equals.v1']=replace(gate,runtime={'provider':'other'})
    with pytest.raises(ValueError,match='Live stage'):run(value,case,tmp_path/'no')
    gates['result.equals.v1']=gate
    case[2]['select-window']['checks'][0]['policy']['expected']=128
    with pytest.raises(ValueError,match='template drift'):run(value,case,tmp_path/'no')
    assert not (tmp_path/'no').exists()


def test_scope_reference_does_not_get_inferred(case):
    ref=content_identity('held-out scope only')
    case[3]['select-window']['qualifications']={'synthetic.v1':ref}
    with pytest.raises(ValueError,match='qualification'):compile(expression(),case)
    case[-1]['qualifications']['synthetic.v1']=ref
    assert compile(expression(),case)


@pytest.mark.parametrize('mutation',['plan','authority','gate_runtime','expression','compiler'])
def test_resealed_receipt_inconsistency_refuses(case,mutation):
    value=compile(expression(),case)
    if mutation=='plan':value['plan']['jobs'][0]['checks'][0]['policy']['expected']=128;seal(value['plan'])
    elif mutation=='authority':value['authority']['release']='performed'
    elif mutation=='gate_runtime':value['gate_runtimes']={}
    elif mutation=='expression':value['expression']=a.parallel(p.stage('select-window'),p.stage('dependent-analysis'))
    else:value['compiler_sha256']=content_identity('changed')
    seal(value)
    with pytest.raises((ValueError,KeyError)):p.inspect_compilation(value)


def test_offline_recompile_no_providers_or_automatic_publication(case):
    value=compile(expression(),case);before=deepcopy(value)
    with patch('subprocess.Popen',side_effect=AssertionError('process')):
        report=p.inspect_compilation(value)
    assert value==before and report['fresh_execution'] is False and report['release']=='not_performed'


def test_all_check_policies_remain_operator_owned(case):
    expr=p.stage('select-window');expr['checks']=[]
    with pytest.raises(ValueError):compile(expr,case)
    with pytest.raises(ValueError):compile(a.identity([a.wire('any.v1')]),case)
    with pytest.raises(ValueError,match='no executable'):compile(a.identity(),case)


def test_real_workcell_path_retains_compilation_and_exact_native_plan(tmp_path):
    from test_workcell import FixtureBackend, ROOT
    from ciw.workcell import WorkcellHost
    from ciw.foundry_packets import inventory
    source=ROOT/'examples/workcells/godot-prop'
    backend=FixtureBackend()
    host=WorkcellHost(source,tmp_path/'cell',backend,expected_source_id=inventory(source)['inventory_id'])
    candidate=host.submit('first',{});host.build('first',candidate['candidate'])
    compiled=load(host.root/'compilation-first.json')
    assert p.inspect_compilation(compiled)['integrity']=='checked'
    assert compiled['plan']==load(host.root/'runs/first/plan.json')
    assert compiled['grant_snapshot']['permissions']==['workcell.build','workcell.package','workcell.test']
    assert backend.calls==['build','test','package']
