"""Additional retained diagnostic tests; imported fixtures are explicit unit doubles."""
import json
from ciw import game_project_workflow as w
from ciw.control_contracts import bytes_ref
from test_game_project import FixtureBinding, profile, run


def test_feedback_keeps_original_checkpoint_diagnostic(tmp_path):
    class DiagnosticBinding(FixtureBinding):
        def invoke(self, spec, parameters):
            value = super().invoke(spec, parameters)
            native = json.loads(value['trace_utf8'])
            native['events'] = [{'id':'checkpoint', 'tick':1, 'kind':'fixture.checkpoint',
                'actor_id':'player', 'target_ids':[], 'causes':[],
                'payload':{'roundtrip_equal':False, 'game_tick':42, 'error':'',
                           'first_difference':{'path':'state.count', 'before':'1', 'after':'0'}}}]
            value['trace_utf8'] = json.dumps(native)
            value['trace_sha256'] = bytes_ref(value['trace_utf8'].encode())
            return value
    root = tmp_path/'campaign'
    run(root, binding=DiagnosticBinding(profile()))
    data = w.feedback(root)
    detail = data['jobs']['candidate']['attempts'][0]['candidates'][0]['checkpoint_diagnostics'][0]
    assert detail['payload']['first_difference']['path'] == 'state.count'
    assert detail['payload']['game_tick'] == 42


def test_feedback_retains_native_refusal_reason(tmp_path):
    root = tmp_path/'campaign'
    run(root, binding=FixtureBinding(profile(), fail=True))
    data = w.feedback(root)
    candidate = data['jobs']['candidate']['attempts'][0]['candidates'][0]
    assert candidate['runtime_refusal']['code'] == 'fixture_failure'
    assert candidate['result_id'] is None and candidate['checkpoint_diagnostics'] == []
