"""Covariance-pair oracles and real retained thermal v1/v2 compatibility.

No live private provider or statistical coverage qualification is claimed.
"""
from copy import deepcopy
import json
import math
import numpy as np
import pytest

from ciw.information_display import contraction_geometry, DIRECTION_SAMPLES
from ciw.math_inspector import analyze, analyze_information, validate_report
from ciw.math_visual import render_html
from ciw.control_checks import inspect_record
from ciw.control_contracts import bytes_ref, save_new, load
from ciw.operations.runner import seal
from ciw.net import main
from ciw.scientific_observations import export_observations
from test_scientific_observations import make_case


def test_diagonal_ratio_log_volume_and_directional_oracles():
    g = contraction_geometry([[4.,0.],[0.,9.]], [[1.,0.],[0.,9.]])
    assert g['status']=='available'
    assert g['variance_ratios']==pytest.approx([.25,1.])
    assert g['area_ratio']==pytest.approx(.5)
    assert g['information_gain_nats']==pytest.approx(math.log(2))
    assert len(g['directions'])==DIRECTION_SAMPLES
    assert g['directions'][0]['variance_ratio']==pytest.approx(.25)
    assert g['directions'][18]['variance_ratio']==pytest.approx(1.)
    assert g['directions'][9]['variance_ratio']==pytest.approx(.625)


def test_correlated_full_matrix_support_is_not_radial_intercept():
    p=[[4.,1.],[1.,3.]];q=[[1.,.2],[.2,1.]]; before=deepcopy((p,q))
    g=contraction_geometry(p,q);w=np.array(g['normalized_covariance'])
    assert g['status']=='available' and (p,q)==before
    # Independent 2x2 generalized eigenvalue polynomial det(Q-lambda P)=0.
    det_p=11.;det_q=.96;b=-(1*3+1*4-2*.2*1)
    roots=sorted(((-b-math.sqrt(b*b-4*det_p*det_q))/(2*det_p),
                  (-b+math.sqrt(b*b-4*det_p*det_q))/(2*det_p)))
    assert g['variance_ratios']==pytest.approx(roots)
    assert g['area_ratio']==pytest.approx(math.sqrt(det_q/det_p))
    for xy in g['unit_contour']:
        assert np.array(xy) @ np.linalg.solve(w,xy)==pytest.approx(1,abs=1e-12)
    for row in g['directions']:
        n=np.array(row['unit_direction']);support=np.array(row['support_point'])
        assert n@support==pytest.approx(row['standard_deviation_ratio'])
        assert support@np.linalg.solve(w,support)==pytest.approx(1,abs=1e-12)
    n=np.array(g['directions'][0]['unit_direction'])
    radial=1/math.sqrt(n@np.linalg.solve(w,n))
    assert abs(radial-g['directions'][0]['standard_deviation_ratio'])>1e-4


@pytest.mark.parametrize('t', [[[1.,0.],[0.,1.]],[[2.,0.],[0.,.5]],[[0.,1.],[-1.,0.]],
                              [[1.,2.],[0.,1.]],[[3.,1.],[1.,2.]],[[10.,0.],[0.,.1]]])
def test_generalized_ratios_invariant_under_common_congruence(t):
    p=np.array([[4.,1.],[1.,3.]]);q=np.array([[1.,.2],[.2,1.]]);t=np.array(t)
    def exact_symmetric(x):
        a=t@x@t.T
        # Test-data construction declares an exact symmetric covariance.
        return [[float(a[0,0]),float(a[0,1])],[float(a[0,1]),float(a[1,1])]]
    a=contraction_geometry(p.tolist(),q.tolist());b=contraction_geometry(exact_symmetric(p),exact_symmetric(q))
    assert b['status']=='available'
    assert a['variance_ratios']==pytest.approx(b['variance_ratios'],rel=1e-10)
    assert a['information_gain_nats']==pytest.approx(b['information_gain_nats'],abs=1e-10)


@pytest.mark.parametrize('q,relation', [([[1.,0.],[0.,1.]],'unchanged'),
    ([[.5,0.],[0.,1.]],'contraction'),([[.5,0.],[0.,.2]],'contraction'),
    ([[2.,0.],[0.,3.]],'expansion'),([[.5,0.],[0.,3.]],'mixed')])
def test_expansion_and_mixed_change_are_not_clipped(q,relation):
    g=contraction_geometry([[1.,0.],[0.,1.]],q)
    assert g['relation'].startswith(relation)
    assert g['variance_ratios']==pytest.approx(sorted([q[0][0],q[1][1]]))
    if relation=='expansion': assert g['information_gain_nats']<0 and g['area_ratio']>1


@pytest.mark.parametrize('bad', [[[1.,.1],[.1000000001,1.]],[[1.,1.],[1.,1.]],
    [[-1.,0.],[0.,1.]],[[1e-14,0.],[0.,1.]]])
@pytest.mark.parametrize('side',['prior','posterior'])
def test_unavailable_inputs_are_never_repaired(bad,side):
    before=deepcopy(bad);args=[[[1.,0.],[0.,1.]]]*2;args[side=='posterior']=bad
    g=contraction_geometry(*args)
    assert g['status']=='unavailable' and g['directions'] is None
    assert g['reason'].startswith(side+':') and bad==before


@pytest.mark.parametrize('bad', [[],[[1.]],[[1.,2.,3.]]*3,[[True,0.],[0.,1.]],
    [[None,0.],[0.,1.]],[[float('nan'),0.],[0.,1.]]])
def test_malformed_inputs_refuse(bad):
    with pytest.raises(ValueError):contraction_geometry(bad,[[1.,0.],[0.,1.]])


def test_pair_condition_limit_not_just_individual_matrices():
    g=contraction_geometry([[1e-6,0.],[0.,1e6]],[[1e6,0.],[0.,1e-6]])
    assert g['status']=='unavailable' and g['reason']=='relative_display_condition_limit'


@pytest.fixture(scope='module')
def samples(tmp_path_factory):
    out={}
    for mask in range(4):
        session,result,path,digest=make_case(tmp_path_factory.mktemp('information-'+str(mask)),mask)
        v=export_observations(path,expected_sha256=digest,bundle_id=result['bundle_id'],stage='posterior',entity_id='core-shell')
        raw=json.dumps(v).encode();out[mask]=(raw,analyze_information(raw,expected_sha256=bytes_ref(raw)))
    return out


@pytest.mark.parametrize('mask',range(4))
def test_version_two_preserves_every_original_field_and_native_decision(samples,mask):
    raw,new=samples[mask];old=analyze(raw,expected_sha256=bytes_ref(raw))
    for k,v in old.items():
        if k not in {'schema','record_digest'}:assert new[k]==v
    assert new['schema']=='ciw.thermal-math-inspection.v2'
    validate_report(old);validate_report(new);inspect_record(old);inspect_record(new)
    for native,derived in zip(new['retained']['selection']['candidates'],new['information']['forecast']):
        assert native['mask']==derived['mask']
        assert native['information_gain_nats']==pytest.approx(derived['geometry']['information_gain_nats'],abs=1e-12)
    if mask==0:
        for g in new['information']['rows']:assert g['variance_ratios']==pytest.approx([1.,1.])
    elif mask in {1,2}:
        for g in new['information']['rows']:assert g['variance_ratios'][1]==pytest.approx(1.)


@pytest.mark.parametrize('field',['ratio','direction','angle','support','matrix','candidate','score','basis','profile','decision','extra','producer'])
def test_resealed_information_cannot_contradict_retained_source(samples,field):
    v=deepcopy(samples[3][1]);g=v['information']['rows'][0]
    if field=='ratio':g['variance_ratios'][0]=1.
    elif field=='direction':g['directions'][0]['variance_ratio']=1.
    elif field=='angle':g['directions'][0]['angle_degrees']=False
    elif field=='support':g['directions'][0]['support_point'][0]+=1
    elif field=='matrix':g['normalized_covariance'][0][1]+=1
    elif field=='candidate':v['information']['forecast'].pop()
    elif field=='score':v['information']['forecast'][0]['geometry']['information_gain_nats']=99.
    elif field=='basis':v['information']['basis']='physical_sensor_axes'
    elif field=='profile':v['information']['profile']='unknown'
    elif field=='decision':v['retained']['selection']['selected_mask']=0
    elif field=='producer':v['information']['producer']['kernel_sha256']='not-a-hash'
    else:v['information']['extra']='hidden'
    seal(v)
    with pytest.raises(ValueError):validate_report(v)


def test_version_two_rejects_new_fields_disguised_as_v1(samples):
    v=deepcopy(samples[3][1]);v['schema']='ciw.thermal-math-inspection.v1';seal(v)
    with pytest.raises(ValueError):validate_report(v)


def test_info_inspection_and_rendering_do_not_execute_provider(samples,monkeypatch):
    from ciw.thermal_workflow import ThermalWorkflow
    def forbidden(*a,**kw):raise AssertionError('Provider execution is not inspection')
    for name in ('create_session','replay_session','_adapters','_step'):monkeypatch.setattr(ThermalWorkflow,name,forbidden)
    validate_report(samples[3][1]);assert b'information-panel' in render_html(samples[3][1])


def test_opt_in_cli_old_default_and_create_only(samples,tmp_path,capsys):
    raw,_=samples[3];source=tmp_path/'source.json';source.write_bytes(raw)
    args=['math',str(source),'--expected-sha256',bytes_ref(raw),'--output',str(tmp_path/'v1.json')]
    assert main(args)==0;assert json.loads(capsys.readouterr().out)['schema'].endswith('.v1')
    args[-1]=str(tmp_path/'v2.json');args+=['--information-geometry']
    assert main(args)==0;assert json.loads(capsys.readouterr().out)['schema'].endswith('.v2')
    before=(tmp_path/'v2.json').read_bytes()
    assert main(args)==1;capsys.readouterr();assert (tmp_path/'v2.json').read_bytes()==before
    assert main(['inspect',str(tmp_path/'v2.json'),'--json'])==0;capsys.readouterr()
    assert main(['view',str(tmp_path/'v2.json'),'--output',str(tmp_path/'view.html')])==0;capsys.readouterr()
