from copy import deepcopy
import json
from pathlib import Path
import pytest
from ciw.foundry_childhood import evaluate_data,policy,bounded_state_equal

@pytest.fixture
def captured():
    # Retained native observation is data for verifier tests, not a new execution.
    return json.loads((Path(__file__).parent/'fixtures/childhood_native_capture.json').read_text())

def test_retained_native_capture(captured):
    assert evaluate_data(captured)['status']=='PASS'
    assert captured['capture_class']=='actual_input_driven_journey'

@pytest.mark.parametrize('fault',['future','cause','covariance','identity','reload','hidden','delivery','order','travel','clock','historical','probability'])
def test_verifier_rejects_retained_counterexamples(captured,fault):
    d=deepcopy(captured)
    if fault=='future': d['samples'][2]['memories'][1]['received_tick']=100000
    if fault=='cause': d['samples'][3]['perspective']['cause_identity']='invented-enemy'
    if fault=='covariance': d['samples'][3]['perspective']['weights']=[0,1]
    if fault=='identity': d['samples'][4]['state']['player']['character_id']='another'
    if fault=='reload': d['samples'][12]['state']['childhood']['tracks']=2
    if fault=='hidden': d['samples'][0]['memories']=[{'id':'secret'}]
    if fault=='delivery': d['samples'][2]['state']['childhood']['heard']=[]
    if fault=='order': d['samples'].reverse()
    if fault=='travel': d['samples'][4]['state']['childhood']['ride_gate']=0
    if fault=='clock': d['samples'][4]['state']['childhood']['tick']=True
    if fault=='historical': d['historical_authentication']=True
    if fault=='probability': d['samples'][3]['perspective']['calibrated_probability']=True
    d['failures']=0;d['assertions']=999999
    assert evaluate_data(d)['status']=='FAIL'

def test_policy_cannot_weaken():
    with pytest.raises(ValueError):policy({'ignore_knowledge':True})

def test_numeric_json_bound_does_not_erase_identity():
    assert bounded_state_equal({'x':0.1},{'x':0.1+1e-15})
    assert not bounded_state_equal({'tick':1},{'tick':True})
    assert not bounded_state_equal({'id':'a'},{'id':'b'})
    assert not bounded_state_equal({'x':0.1},{'x':0.1+1e-6})
