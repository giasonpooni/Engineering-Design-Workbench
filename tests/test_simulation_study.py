"""Study contracts against the real controller and explicitly labelled native doubles.

These tests do not qualify SCR/Julia/C++ execution. The own-repository native
campaign uses the same production API with the genuine approved provider pair.
"""
from copy import deepcopy
import json
from pathlib import Path
import uuid

import pytest

from ciw import simulation as sim
from ciw import simulation_study as study
from ciw import simulation_observers as observers
from ciw import native_interop_contract as contract
from ciw.control_contracts import load, save_new
from ciw.operations.runner import seal
from ciw.session import envelope
from ciw.telemetry import digest, canonical


class ReferenceDouble:
    active = 0
    maximum_active = 0
    executions = 0
    fail = False
    runtime = {"test_double": "not-native-evidence"}

    def __init__(self, binding, expected_runtime=None):
        if expected_runtime is not None and expected_runtime != self.runtime:
            raise ValueError("runtime differs")
        type(self).active += 1
        type(self).maximum_active = max(type(self).active, type(self).maximum_active)
        self.closed = False

    def execute(self, source):
        if self.fail:
            raise RuntimeError("injected provider failure")
        type(self).executions += 1
        output = (contract.oscillator_reference(source["payload"]) if source["provider"] == "julia"
                  else contract.force_reference(source["payload"]))
        return {"request": deepcopy(source), "output": output,
                "execution_id": "execution-"+uuid.uuid4().hex,
                "result_id": digest({"source": source, "test_result": output})}

    def close(self):
        if not self.closed:
            type(self).active -= 1
            self.closed = True


@pytest.fixture
def reference(monkeypatch):
    ReferenceDouble.active = ReferenceDouble.maximum_active = ReferenceDouble.executions = 0
    ReferenceDouble.fail = False
    monkeypatch.setattr(sim, "ProviderPair", ReferenceDouble)
    monkeypatch.setattr(sim, "validate_step", lambda step, runtime: deepcopy(step["output"]))
    return ReferenceDouble


@pytest.fixture
def instance(tmp_path, reference):
    plan = study.default_plan()
    owner = sim.Simulation(plan["model"], plan["initial"], "unused", tmp_path/"live")
    session = study._session(owner, tmp_path/"session")
    yield owner, session
    owner.close()


@pytest.fixture
def completed(tmp_path, reference):
    out = tmp_path/"study"
    report = study.run(study.default_plan(), Path("unused"), out)
    return out, report


def cp(owner):
    name = owner.checkpoint()["filename"]
    return sim.read_checkpoint(owner.directory/name)


def command(owner, **extra):
    view = owner.inspect()
    return {"command_id":"command-"+uuid.uuid4().hex,"owner_id":view["owner_id"],
            "expected_revision":view["revision"],"at_tick":view["state"]["tick"],**extra}


def ask(session, kind, payload):
    return session.handle(envelope(kind, payload, uuid.uuid4().hex))


def overwrite(path, value):
    path.write_bytes(canonical(value))


def test_default_plan_and_no_native_listing(monkeypatch):
    monkeypatch.setattr(sim, "ProviderPair", lambda *a,**kw:pytest.fail("provider launched"))
    study.validate_plan(study.default_plan())
    assert study.describe()["capabilities"]["godot_world_restore"] is False


@pytest.mark.parametrize("bad", [True,0,121,1.5,"12"])
def test_invalid_step_budget(bad):
    plan=study.default_plan();plan["prefix"][0]["ticks"]=bad
    with pytest.raises(ValueError):study.validate_plan(plan)


@pytest.mark.parametrize("bad", [True,2,float("nan"),"1"])
def test_invalid_intervention(bad):
    plan=study.default_plan();plan["branches"][1]["actions"][0]["impulse_n_s"]=bad
    with pytest.raises(ValueError):study.validate_plan(plan)


@pytest.mark.parametrize("field,value", [("every_ticks",True),("every_ticks",0),("delay_ticks",-1),
    ("quantities",["secret"]),("quantities",["q_m","q_m"]),("quantities",[]),("phase","pre_tick"),
    ("observer_id","../private")])
def test_bad_observer_spec(field,value):
    spec=observers.policy("observer:test",["q_m"]);spec[field]=value
    with pytest.raises(ValueError):observers.validate_policy(spec)


def test_control_gate_and_explicit_step(instance):
    owner,session=instance
    request={"owner_id":owner.inspect()["owner_id"],"expected_control_revision":0}
    assert ask(session,"simulation.pause",request)["payload"]["paused"] is True
    before=owner.inspect()
    assert ask(session,"simulation.advance",command(owner,ticks=12))["type"]=="error"
    assert owner.inspect()==before
    assert ask(session,"simulation.step",command(owner,ticks=12))["payload"]["state"]["tick"]==12
    assert ask(session,"simulation.control",{})["payload"]["paused"] is True
    assert ask(session,"simulation.resume",request)["type"]=="error"
    request["expected_control_revision"]=1
    assert ask(session,"simulation.resume",request)["payload"]["paused"] is False
    assert owner.inspect()["state"]["tick"]==12
    assert ask(session,"operation.list",{})["type"]=="response"


def test_control_boolean_revision_refused(instance):
    owner,session=instance
    response=ask(session,"simulation.pause",{"owner_id":owner.inspect()["owner_id"],"expected_control_revision":False})
    assert response["type"]=="error"


def test_delayed_observer_has_no_full_state(instance):
    owner,session=instance
    owner.mutate("advance",command(owner,ticks=24))
    spec=observers.policy("observer:position",["q_m"],every_ticks=6,delay_ticks=12)
    view=ask(session,"simulation.observe",{"observer":spec})["payload"]
    assert view["sample_ticks"]==[0,6,12]
    assert view["available_ticks"]==[12,18,24]
    assert set(view["streams"])=={"q_m"}
    raw=canonical(view)
    assert b'v_m_s' not in raw and b'native_steps' not in raw and b'energy_j' not in raw
    assert all(o["identity"]["execution_id"] is None for o in view["streams"]["q_m"])
    assert all(o["uncertainty"] is None for o in view["streams"]["q_m"])


def test_empty_delayed_observation_not_zero(instance):
    owner,_=instance;checkpoint=cp(owner)
    result=observers.project(checkpoint,observers.policy("observer:p",["q_m"],delay_ticks=1),expected_checkpoint_id=checkpoint["checkpoint_id"])
    assert result["sample_ticks"]==[] and result["streams"]["q_m"]==[]


def test_same_tick_intervention_phase_and_frozen_prior(instance):
    owner,_=instance;before=cp(owner)
    spec=observers.policy("observer:d",["v_m_s"])
    old=observers.project(before,spec,expected_checkpoint_id=before["checkpoint_id"])
    owner.mutate("impulse",command(owner,impulse_n_s=.25));after=cp(owner)
    new=observers.project(after,spec,expected_checkpoint_id=after["checkpoint_id"])
    assert old["streams"]["v_m_s"][0]["value"]==0
    assert new["streams"]["v_m_s"][0]["value"]==.25
    observers.validate_view(old,before)
    with pytest.raises(ValueError):observers.validate_view(old,after)


def test_observer_inspection_never_integrates(instance,reference,monkeypatch):
    owner,_=instance;checkpoint=cp(owner);n=reference.executions
    monkeypatch.setattr(contract,"oscillator_reference",lambda *a:pytest.fail("integration"))
    view=observers.project(checkpoint,observers.policy("observer:q",["q_m"]),expected_checkpoint_id=checkpoint["checkpoint_id"])
    observers.validate_view(view,checkpoint)
    assert reference.executions==n


def test_real_controller_checkpoints_and_branches(completed,reference):
    root,report=completed
    assert report["status"]=="completed" and len(report["branches"])==2
    assert reference.maximum_active==1 and reference.active==0
    summary=study.inspect(root)
    assert summary["provider_execution"]=="not_performed"
    baseline=sim.read_checkpoint(root/"branch-00/payload.json")
    candidate=sim.read_checkpoint(root/"branch-01/payload.json")
    a=sim.inspect_checkpoint(baseline);b=sim.inspect_checkpoint(candidate)
    assert a["simulation_id"]==b["simulation_id"]
    assert a["model_id"]==b["model_id"] and a["owner_id"]!=b["owner_id"]
    assert a["state"]["tick"]==b["state"]["tick"]==144
    assert abs(a["state"]["q_m"]-b["state"]["q_m"])>.01
    assert all(check["outcome"]["status"]=="FAIL" for check in report["comparisons"][0]["checks"].values())


def test_reopened_study_never_starts_provider(completed,monkeypatch):
    root,_=completed
    monkeypatch.setattr(sim,"ProviderPair",lambda *a,**kw:pytest.fail("provider launch"))
    monkeypatch.setattr(contract,"oscillator_reference",lambda *a,**kw:pytest.fail("oracle"))
    assert study.inspect(root)["status"]=="retained_study_checked"


@pytest.mark.parametrize("mutation", ["plan","actor","observation","comparison","owner","parent","authority"])
def test_resealed_tampering_refused(completed,mutation):
    root,report=completed
    if mutation=="plan":
        plan=load(root/"plan.json");plan["prefix"][0]["ticks"]=12
        overwrite(root/"plan.json",plan)
    elif mutation=="actor":
        path=root/"branch-01/intent-000.json";v=load(path);v["actor_id"]="other";seal(v);overwrite(path,v)
    elif mutation=="observation":
        report["branches"][0]["observers"][0]["streams"]["q_m"][0]["value"]+=1
        seal(report["branches"][0]["observers"][0])
    elif mutation=="comparison":report["comparisons"][0]["checks"]["q_m"]["outcome"]["status"]="PASS"
    elif mutation=="owner":report["branches"][1]["owner_id"]=report["branches"][0]["owner_id"]
    elif mutation=="parent":report["branches"][1]["parent_checkpoint_id"]="sha256:"+"0"*64
    else:report["authority"]["verification_id"]="made-up-proof"
    seal(report);overwrite(root/"study.json",report)
    with pytest.raises(ValueError):study.inspect(root)


def test_exact_parent_envelope_binding(completed):
    root,_=completed;path=root/"branch-00/checkpoint.json"
    wrapper=load(path);wrapper["provider"]["clock"]["time_s"]+=1;seal(wrapper);overwrite(path,wrapper)
    with pytest.raises(ValueError):study.inspect(root)


def test_invalid_plan_fails_before_provider_or_writes(tmp_path,monkeypatch):
    monkeypatch.setattr(sim,"ProviderPair",lambda *a,**kw:pytest.fail("provider launch"))
    plan=study.default_plan();plan["branches"][1]["name"]="baseline"
    with pytest.raises(ValueError):study.run(plan,Path("unused"),tmp_path/"none")
    assert not (tmp_path/"none").exists()


def test_existing_output_is_not_overwritten(completed):
    root,_=completed;before=(root/"study.json").read_bytes()
    with pytest.raises(FileExistsError):study.run(study.default_plan(),Path("unused"),root)
    assert (root/"study.json").read_bytes()==before


def test_runtime_failure_is_retained_and_no_completed_study(tmp_path,reference):
    reference.fail=True
    with pytest.raises(RuntimeError):study.run(study.default_plan(),Path("unused"),tmp_path/"failed")
    assert (tmp_path/"failed/failure.json").exists()
    assert not (tmp_path/"failed/study.json").exists() and reference.active==0


def test_reproduce_new_occurrences_same_numerics(completed,tmp_path,monkeypatch):
    root,original=completed
    from ciw.native_interop import NativeInteropWorkflow
    monkeypatch.setattr(NativeInteropWorkflow,"_adapters",lambda *a,**kw:({},ReferenceDouble.runtime))
    result=study.reproduce(root,Path("unused"),tmp_path/"again",expected_report_digest=original["record_digest"])
    fresh=load(tmp_path/"again/study.json")
    assert fresh["study_id"]!=original["study_id"]
    assert fresh["branches"][0]["owner_id"]!=original["branches"][0]["owner_id"]
    assert all(c["outcome"]["status"]=="PASS" for p in result["checks"] for c in p["checks"].values())


def test_reproduce_wrong_digest_no_native(completed,tmp_path,monkeypatch):
    root,_=completed
    monkeypatch.setattr(sim,"ProviderPair",lambda *a,**kw:pytest.fail("provider launch"))
    with pytest.raises(ValueError):study.reproduce(root,Path("unused"),tmp_path/"again",expected_report_digest="sha256:"+"0"*64)
    assert not (tmp_path/"again").exists()


def test_unknown_action_cannot_be_executed(tmp_path):
    plan=study.default_plan();plan["prefix"]=[{"action":"shell","command":"anything","actor_id":"x"}]
    with pytest.raises(ValueError):study.run(plan,Path("unused"),tmp_path/"bad")


def test_cli_provider_free(tmp_path,capsys):
    assert study.main(["describe"])==0
    assert json.loads(capsys.readouterr().out)["inspection_launches_provider"] is False
    assert study.main(["plan","--output",str(tmp_path/"plan.json")])==0
    capsys.readouterr()
    assert study.main(["plan","--output",str(tmp_path/"plan.json")])==2


def test_unit_frame_and_time_mismatch_not_compared(completed):
    root,report=completed
    from ciw.control_checks import compare
    a=report["branches"][0]["observers"][1]["streams"]["q_m"]
    b=deepcopy(a)
    for obs in b:obs["unit"]="cm";seal(obs)
    assert compare(a,b,atol=0)["outcome"]["status"]=="INDETERMINATE"


def test_completion_is_not_published_if_readback_fails(tmp_path, reference, monkeypatch):
    def reject(*a, **kw):
        raise ValueError('injected retained validation failure')
    monkeypatch.setattr(study, '_inspect_details', reject)
    with pytest.raises(ValueError):study.run(study.default_plan(), Path('unused'), tmp_path/'failed')
    assert (tmp_path/'failed/failure.json').exists()
    assert not (tmp_path/'failed/study.json').exists() and reference.active==0


def test_observer_stride_budget_before_allocation(tmp_path, reference):
    plan=study.default_plan()
    plan['branches'][0]['actions']=[{'action':'advance','ticks':120,'actor_id':'tester'}]*64
    plan['observers'][1]['every_ticks']=1
    with pytest.raises(ValueError):study.run(plan,Path('unused'),tmp_path/'failed')
    assert reference.executions==0 and not (tmp_path/'failed').exists()


def test_unknown_observer_field_is_not_ignored():
    spec=observers.policy('observer:x',['q_m']);spec['hidden_state']=True
    with pytest.raises(ValueError):observers.validate_policy(spec)


def test_mutation_inflight_refuses_pause_and_observe(instance):
    owner,session=instance
    session._study_lock.acquire()
    try:
        p={'owner_id':owner.inspect()['owner_id'],'expected_control_revision':0}
        assert ask(session,'simulation.pause',p)['type']=='error'
        assert ask(session,'simulation.observe',{'observer':observers.policy('q',['q_m'])})['type']=='error'
        assert ask(session,'simulation.control',{})['payload']['paused'] is False
    finally:session._study_lock.release()


@pytest.mark.parametrize('missing',['branch-00/receipt-000.json','branch-00/observer-00.json','parent/payload.json'])
def test_incomplete_study_refuses(completed,missing):
    root,_=completed;(root/missing).unlink()
    with pytest.raises((ValueError,OSError)):study.inspect(root)


def test_net_simulate_is_additive_cli(capsys):
    from ciw.net import main
    assert main(['simulate','describe'])==0
    assert json.loads(capsys.readouterr().out)['state_owner']=='existing ciw.simulation.Simulation'


def test_reproduction_offline_check_and_corruption(completed,tmp_path,monkeypatch):
    root,original=completed
    from ciw.native_interop import NativeInteropWorkflow
    monkeypatch.setattr(NativeInteropWorkflow,'_adapters',lambda *a,**kw:({},ReferenceDouble.runtime))
    target=tmp_path/'again'
    study.reproduce(root,Path('unused'),target,expected_report_digest=original['record_digest'])
    monkeypatch.setattr(sim,'ProviderPair',lambda *a,**kw:pytest.fail('launched'))
    monkeypatch.setattr(contract,'oscillator_reference',lambda *a,**kw:pytest.fail('integrated'))
    assert study.inspect_reproduction(root,target)['numerical_outcomes']==['PASS']*6
    value=load(target/'reproduction.json');value['checks'][0]['branch_name']='forged';seal(value)
    overwrite(target/'reproduction.json',value)
    with pytest.raises(ValueError):study.inspect_reproduction(root,target)


def test_reproduction_runtime_mismatch_before_execution(completed,tmp_path,monkeypatch):
    root,original=completed
    from ciw.native_interop import NativeInteropWorkflow
    monkeypatch.setattr(NativeInteropWorkflow,'_adapters',lambda *a,**kw:({}, {'other':'runtime'}))
    monkeypatch.setattr(sim,'ProviderPair',lambda *a,**kw:pytest.fail('launched'))
    with pytest.raises(ValueError):study.reproduce(root,Path('unused'),tmp_path/'again',expected_report_digest=original['record_digest'])
    assert not (tmp_path/'again').exists()


def test_html_preserves_observer_scope_and_source(completed,tmp_path,monkeypatch):
    from ciw.simulation_study_view import write, html
    root,report=completed;original=(root/'study.json').read_bytes()
    monkeypatch.setattr(sim,'ProviderPair',lambda *a,**kw:pytest.fail('launched'))
    out=tmp_path/'inspector.html';write(root,'observer:position',out)
    text=out.read_text(encoding="utf-8")
    assert '<svg' in text and '<script' not in text and 'http://' not in text and 'https://' not in text
    assert 'q_m' in text and 'v_m_s' not in text and 'energy_j' not in text and 'native_steps' not in text
    assert out.read_bytes()==html(root,'observer:position').encode('utf-8')
    assert (root/'study.json').read_bytes()==original
    with pytest.raises(FileExistsError):write(root,'observer:position',out)


def test_html_refuses_unknown_observer(completed):
    from ciw.simulation_study_view import html
    with pytest.raises(ValueError):html(completed[0],'omniscient')
