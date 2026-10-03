"""Algebraic oracles, original thermal provider, and inert visual export contracts."""
from copy import deepcopy
import base64
import json
import math
from pathlib import Path
import re

import numpy as np
import pytest

from ciw import uncertainty_display as algebra
from ciw.control_contracts import bytes_ref, save_new, load
from ciw.control_checks import inspect_record
from ciw.math_inspector import analyze, analyze_file, validate_report
from ciw.math_visual import render_html, write_html
from ciw.net import main
from ciw.operations.runner import seal
from ciw.scientific_observations import export_observations
from test_scientific_observations import make_case


@pytest.fixture(scope='module')
def samples(tmp_path_factory):
    out = {}
    for mask in range(4):
        session, summary, path, digest = make_case(tmp_path_factory.mktemp('math-' + str(mask)),mask)
        view = export_observations(path, expected_sha256=digest, bundle_id=summary['bundle_id'],
                                   stage='posterior', entity_id='test/core-shell')
        raw = json.dumps(view, ensure_ascii=False).encode()
        out[mask] = (raw, analyze(raw, expected_sha256=bytes_ref(raw)))
    return out


def test_contour_satisfies_full_covariance_quadratic_form():
    matrix = [[4., 1.5], [1.5, 3.]]
    original = deepcopy(matrix)
    g = algebra.covariance_geometry(matrix)
    assert g['status'] == 'available'
    assert matrix == original
    assert len(g['unit_contour']) == 65
    assert g['unit_contour'][0] == g['unit_contour'][-1]
    determinant = 4*3 - 1.5**2
    # Closed-form inverse oracle independent of the lower factor construction.
    for x,y in g['unit_contour']:
        assert (3*x*x - 3*x*y + 4*y*y) / determinant == pytest.approx(1, abs=1e-12)
    assert g['correlation'][0][1] == pytest.approx(1.5/math.sqrt(12))
    assert g['principal_variances'] == pytest.approx([(7-math.sqrt(10))/2,(7+math.sqrt(10))/2])
    assert g['log_volume'] == pytest.approx(.5*math.log(determinant))


@pytest.mark.parametrize('radius',[1,2,3])
def test_contour_radius_is_mahalanobis_not_joint_coverage(radius):
    p = np.array([[4.,2.],[2.,3.]])
    contour = np.array(algebra.covariance_geometry(p.tolist())['unit_contour']) * radius
    for xy in contour:
        assert xy @ np.linalg.solve(p,xy) == pytest.approx(radius**2,abs=1e-12)


def test_whitening_correlated_example_and_gain_oracles():
    white=algebra.whiten_innovation([2.,3.],[[4.,2.],[2.,3.]])
    assert white['components']==pytest.approx([1.,math.sqrt(2)])
    assert white['squared_norm']==pytest.approx(3)
    one=algebra.whiten_innovation([3.],[[9.]])
    assert one['components']==[1.] and one['squared_norm']==1
    a=algebra.covariance_geometry([[4.,0.],[0.,9.]])
    b=algebra.covariance_geometry([[1.,0.],[0.,1.]])
    assert algebra.conditioning_gain(a,b)==pytest.approx(math.log(6))


@pytest.mark.parametrize('matrix,reason',[
    ([[1.,.1],[.100000000000001,1.]],'asymmetric_no_repair'),
    ([[1.,1.],[1.,1.]],'not_numerically_positive_definite'),
    ([[1.,2.],[2.,1.]],'not_numerically_positive_definite'),
    ([[0.,0.],[0.,0.]],'not_numerically_positive_definite'),
    ([[-1.,0.],[0.,1.]],'not_numerically_positive_definite'),
    ([[1e-14,0.],[0.,1.]],'display_condition_limit'),
])
def test_unsupported_covariance_never_repaired(matrix,reason):
    before=deepcopy(matrix)
    g=algebra.covariance_geometry(matrix)
    assert g['status']=='unavailable' and g['reason']==reason
    assert g['unit_contour'] is None and g['lower_factor'] is None
    assert matrix==before
    assert algebra.whiten_innovation([1.,1.],matrix)['status']=='unavailable'
    assert algebra.conditioning_gain(g,g) is None


@pytest.mark.parametrize('matrix',[[],[[1.,0.,0.]]*3,[[1.],[0.,1.]],[[True]],[[float('nan')]],[[float('inf')]],'matrix'])
def test_malformed_covariance_rejected(matrix):
    with pytest.raises(ValueError):algebra.covariance_geometry(matrix)


@pytest.mark.parametrize('r,s',[([True],[[1.]]),([1.,2.,3.],[[1.]*3]*3),([],[[]]),([1.],[[1.,0.],[0.,1.]]),([None],[[1.]])])
def test_invalid_innovations_rejected(r,s):
    with pytest.raises(ValueError):algebra.whiten_innovation(r,s)


def test_empty_measurements_are_missing_not_zero():
    data=algebra.whiten_innovation([],[])
    assert data['status']=='missing' and data['squared_norm'] is None
    assert data['components'] is None and data['dimension']==0


@pytest.mark.parametrize('mask',range(4))
def test_actual_native_thermal_context_and_all_masks(samples,mask):
    raw,report=samples[mask]
    before=deepcopy(report)
    validate_report(report);inspect_record(report)
    assert report==before
    source=json.loads(raw)
    native=source['native_step']['result']['data']
    assert report['retained']['trace']==native['observer']['trace']
    assert report['retained']['selection']==native['selection']
    assert report['retained']['execution_id']==source['native_step']['execution_id']
    assert report['retained']['time_s']==[1.,2.,3.]
    for row,derived in zip(native['observer']['trace'],report['derived']):
        assert derived['whitened']['dimension']==row['innovation'].__len__()
        if mask==0:
            assert derived['whitened']['squared_norm'] is None
            assert derived['conditioning_gain_nats']==0
        else:assert derived['whitened']['squared_norm']==pytest.approx(row['nis'])
    assert report['authority']['new_estimator_execution']=='not_performed'


@pytest.mark.parametrize('change',['raw-source','value','matrix','time','context','dimension','contour','whitening','gain','status','policy','authority','unknown-producer','source-hash','extra'])
def test_resealed_report_cannot_change_evidence_or_mathematics(samples,change):
    value=deepcopy(samples[3][1])
    if change=='raw-source':value['source']['utf8']+=' '
    elif change=='source-hash':value['source']['sha256']='sha256:'+'0'*64
    elif change=='value':value['retained']['trace'][0]['posterior_mean'][0]+=1
    elif change=='matrix':value['retained']['trace'][0]['posterior_covariance'][0][1]=0
    elif change=='time':value['retained']['time_s'][0]=0
    elif change=='context':value['retained']['clock_id']='different'
    elif change=='dimension':value['derived'][0]['whitened']['dimension']=2.0
    elif change=='contour':value['derived'][0]['posterior']['unit_contour'][0][0]+=1
    elif change=='whitening':value['derived'][0]['whitened']['squared_norm']=0
    elif change=='gain':value['derived'][0]['conditioning_gain_nats']=0
    elif change=='status':value['derived'][0]['posterior']['status']='certified'
    elif change=='policy':value['policy']['contours']='95_percent_confidence'
    elif change=='authority':value['authority']['state_admission']='performed'
    elif change=='unknown-producer':value['producer']['profile']='untrusted.exec'
    else:value['extra']='hidden'
    seal(value)
    with pytest.raises(ValueError):validate_report(value)


@pytest.mark.parametrize('raw',[b'',b'{"x":1,"x":2}',b'{"x":NaN}',b'{}',b'\xff',b'x'*65537],ids=['empty','duplicate','nonfinite','unknown','encoding','budget'])
def test_invalid_sources_refuse_before_derivation(raw):
    with pytest.raises(ValueError):analyze(raw,expected_sha256=bytes_ref(raw))


def test_file_hash_and_mutation_isolation(samples,tmp_path):
    raw,_=samples[3];p=tmp_path/'native.json';p.write_bytes(raw)
    data=analyze_file(p,expected_sha256=bytes_ref(raw))
    data['retained']['trace'][0]['posterior_mean'][0]=999
    assert p.read_bytes()==raw
    p.write_bytes(raw+b' ')
    with pytest.raises(ValueError):analyze_file(p,expected_sha256=bytes_ref(raw))


def test_inspection_does_not_launch_or_bind_providers(samples,monkeypatch):
    from ciw.thermal_workflow import ThermalWorkflow
    def forbidden(*a,**kw):raise AssertionError('Unexpected provider lifecycle')
    for name in ('create_session','replay_session','_adapters','_step'):
        monkeypatch.setattr(ThermalWorkflow,name,forbidden)
    validate_report(samples[3][1]);render_html(samples[3][1])


def test_html_embeds_inert_exact_report_and_blocked_network(samples):
    value=samples[3][1];html=render_html(value).decode()
    encoded=re.search(r'<script id="net-report" type="application/octet-stream">(.*?)</script>',html).group(1)
    assert json.loads(base64.b64decode(encoded))==value
    assert "connect-src 'none'" in html
    assert 'src="http' not in html and 'href="http' not in html
    assert "eval(" not in html and "fetch(" not in html
    assert "script-src 'sha256-" in html and 'unsafe-inline' not in html


def test_create_only_html_and_cli(samples,tmp_path,capsys):
    raw,r=samples[3]
    path=tmp_path/'view.json';path.write_bytes(raw)
    out=tmp_path/'math.json'
    args=['math',str(path),'--expected-sha256',bytes_ref(raw),'--output',str(out)]
    assert main(args)==0;capsys.readouterr()
    before=out.read_bytes();assert main(args)==1;capsys.readouterr();assert out.read_bytes()==before
    assert main(['inspect',str(out),'--json'])==0;capsys.readouterr()
    page=tmp_path/'viewer.html'
    assert main(['view',str(out),'--output',str(page)])==0;capsys.readouterr()
    before=page.read_bytes();assert main(['view',str(out),'--output',str(page)])==1;capsys.readouterr();assert page.read_bytes()==before


def test_kernel_strict_symmetry_not_numpy_triangle_assumption():
    # A positive lower triangle must not hide contradictory upper entries.
    assert algebra.covariance_geometry([[2.,99.],[0.,2.]])['reason']=='asymmetric_no_repair'


def test_utf8_entity_is_data_not_html(samples):
    view=json.loads(samples[3][0]);evil='µ & </script><img src=x onerror="alert(1)">'
    view['entity_id']=evil
    for row in view['stream']['observations']:
        row['identity']['entity_id']=evil;seal(row)
    seal(view['stream']);seal(view)
    raw=json.dumps(view,ensure_ascii=False).encode()
    report=analyze(raw,expected_sha256=bytes_ref(raw));html=render_html(report)
    assert evil.encode() not in html
    assert report['retained']['entity_id']==evil
