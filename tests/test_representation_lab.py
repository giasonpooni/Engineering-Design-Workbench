from copy import deepcopy
import pytest
from ciw.representation_lab import example,rebase,verify,laboratory

def test_exact_similarity_and_covariance():
    d=laboratory()
    assert d['commutes'] and d['naive_operator_counterexample']['fails']
    assert d['candidate']['coordinates']==['1','1']
    assert d['witness']['gate']['decision']=='ELIGIBLE'
    assert d['witness']['gate']['claims']['state_admission_performed'] is False

@pytest.mark.parametrize('failure',['frame','unit','coarsen','alias','covariance','singular','metadata'])
def test_deliberate_failures(failure):
    s=example(); c=rebase(s,[['1','1'],['0','1']])
    if failure=='frame': c['frame']=None
    if failure=='unit': c['unit']='mm';c['metadata']['unit']='mm'
    if failure=='coarsen': c['coordinates'][0]='0'
    if failure=='alias': c['entity_ids']=['same','same']
    if failure=='covariance': c['covariance']=None
    if failure=='singular': c['basis']=[['1','0'],['0','0']]
    if failure=='metadata': c['metadata']['frame']='another'
    assert verify(s,c)['gate']['decision']=='REFUSED'

@pytest.mark.parametrize('basis',[[['1','0'],['0','1']],[['0','-1'],['1','0']],[['2','1/3'],['1','2']]])
def test_roundtrip(basis):
    s=example();c=rebase(s,basis);back=rebase(c,s['basis'])
    assert back==s
    assert verify(s,c)['verification']['status']=='VERIFIED'
