import numpy as np
from ciw.preservation_experiments import sensor_experiment
from ciw.representation_lab import vector,matrix

def test_sensor_conditioning_and_basis_covariance():
    d=sensor_experiment()
    assert d['witness']['gate']['decision']=='ELIGIBLE'
    x=np.array(d['prior']); p=np.array(d['prior_covariance']); z=np.array(d['calibrated_observation']); r=np.array(d['observation_covariance'])
    k=np.linalg.solve((p+r).T,p.T).T
    expected=x+k@(z-x)
    assert np.allclose(expected,d['posterior'],rtol=0,atol=1e-14)
    exact=np.array([float(v) for v in vector(d['source_representation']['coordinates'])])
    assert np.allclose(expected,exact,rtol=0,atol=1e-14)
    c=np.array([[float(v) for v in row] for row in matrix(d['source_representation']['covariance'])])
    assert np.linalg.eigvalsh(c).min()>0
    assert np.allclose(c,d['posterior_covariance'],rtol=1e-12,atol=1e-16)
    assert d['source_class']=='synthetic' and not d['calibration_authenticated']


def test_execution_evidence_into_scoped_ingress_and_identity():
    from ciw.experiment_receipts import external_scalar_ingress
    from ciw.control_contracts import bytes_ref
    # Boundary unit test; no native extraction claimed for these fixture bytes.
    r=external_scalar_ingress(b'unit-test-fixture','fixture-id',bytes_ref(b'unit-test-diagnostic'),True)
    assert r['qualification']['status']=='QUALIFIED'
    assert r['contract']['effects'][-1]['effect']=='FORGET'
    assert r['identity_binding']['claims']['canonical_entity_created'] is False
    rejected=external_scalar_ingress(b'unit-test-fixture','fixture-id',bytes_ref(b'unit-test-diagnostic'),False)
    assert rejected['qualification']['status']=='REFUSED' and rejected['identity_binding'] is None
