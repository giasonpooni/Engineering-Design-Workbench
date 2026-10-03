"""Executed CSE round trips and synthetic sensor estimation over NET contracts.

The operator binds provider code; source artifacts never select executable paths.
Native CSE owns compilation, transformations, export and ledger replay.
"""
from __future__ import annotations
import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
import uuid
import numpy as np

from .adapters.subprocess import PinnedSubprocessAdapter, _json
from .bim_quantity import PIN, _BOOTSTRAP, _check_data, _source
from .telemetry import canonical
from .control_contracts import bytes_ref, save_new
from .core.identities import content_identity
from .operations.runner import seal
from .experiment_receipts import receipts, external_scalar_ingress
from .representation_lab import example, rebase, verify, laboratory, encode

ROUNDTRIP = _BOOTSTRAP.replace("print(json.dumps(data,", r'''
# Export and reload are native CSE operations. Never import the exported IFC as
# though it contained full covariance: check it against the exact snapshot.
if data['status'] == 'accepted':
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        session.export_snapshot(str(root/'posterior.json'))
        restored = GatSession.load_snapshot(str(root/'posterior.json'))
        session.export_ifc(str(root/'posterior.ifc'))
        emitted = (root/'posterior.ifc').read_bytes()
        parsed = GatSession.from_text(emitted.decode('utf-8'), source=sha(emitted))
        from gat.adapters.ifc.writer import _serialize_instance
        changed_quantity_ids = {slot.source_ref for entity in session.world.module.entities.values()
                                for slot in entity.slots.values() if slot.source_ref is not None}
        protected = {str(i): _serialize_instance(inst) for i,inst in session.source_file.instances.items()
                     if i not in changed_quantity_ids}
        emitted_protected = {str(i): _serialize_instance(parsed.source_file.instances[i])
                             for i in session.source_file.instances if i not in changed_quantity_ids
                             and i in parsed.source_file.instances}
        data['roundtrip'] = {
            'source_protected_instances': protected, 'exported_protected_instances': emitted_protected,
            'snapshot': state(restored.world), 'ifc_state': state(parsed.world),
            'snapshot_bytes_b64': base64.b64encode((root/'posterior.json').read_bytes()).decode(),
            'ifc_bytes_b64': base64.b64encode(emitted).decode()}
else:
    data['roundtrip'] = None
print(json.dumps(data,''')

PROBE = r'''
import sys,json
sys.path.insert(0,sys.argv[1])
from gat.session import GatSession
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.errors import GatError
request=json.loads(sys.stdin.buffer.read())
try:
    scope=IfcLoweringScope(frozenset(request['scope'])) if request['scope'] else None
    session=GatSession.from_text(request['text'],scope=scope)
    print(json.dumps({'status':'COMPILED','invariants_passed':session.verify().passed}))
except GatError as e:
    print(json.dumps({'status':'REFUSED','reason':type(e).__name__,'detail':str(e)}))
'''

def external_probe(adapter, raw, scope=None):
    before=adapter.runtime_identity()
    code,out=adapter._run(PROBE,[str(adapter.source_root)],canonical({'text':raw.decode('utf-8'),'scope':scope or []}))
    if code: raise ValueError('NATIVE_PROBE_FAILURE')
    if before!=adapter.runtime_identity(): raise ValueError('RUNTIME_DRIFT')
    return seal({'schema':'ciw.external-ifc-probe.v1','execution_id':'execution-'+uuid.uuid4().hex,
       'source_ref':bytes_ref(raw),'runtime':before,'result':_json(out),'scope':scope or [],
       'state_admission_performed':False})

def bim_roundtrip(adapter, source):
    """Run the installed bounded BIM operation, then independently check carriers."""
    source=_source(canonical(source))
    before=adapter.runtime_identity()
    code,raw=adapter._run(ROUNDTRIP,[str(adapter.source_root)],canonical(source))
    if code: raise ValueError('NATIVE_CSE_FAILURE')
    if before!=adapter.runtime_identity(): raise ValueError('RUNTIME_DRIFT')
    data=_json(raw); roundtrip=data.pop('roundtrip')
    _check_data(source,data) # Existing operation-specific saved-payload validator.
    checks={}
    if roundtrip is not None:
        posterior=data['posterior']; snapshot=roundtrip['snapshot']; target=roundtrip['ifc_state']
        # IFC reserialization changes source/module/world identity. Entity and
        # quantity identities, values and full covariance are the checked invariants.
        for name,state in [('snapshot',snapshot),('ifc',target)]:
            checks[name+'_quantity_identity']=state['quantities']==posterior['quantities']
            checks[name+'_means']=bool(np.allclose(state['mean'],posterior['mean'],rtol=0,atol=1e-12))
            checks[name+'_full_covariance']=bool(np.allclose(state['covariance'],posterior['covariance'],rtol=1e-10,atol=1e-14))
        checks['protected_ifc_geometry_and_metadata']=roundtrip['source_protected_instances']==roundtrip['exported_protected_instances']
        checks['snapshot_world_identity']=snapshot['world_digest']==posterior['world_digest']
        checks['native_ledger_replay']=data['ledger_replay']['world_digest']==posterior['world_digest']
        checks['native_invariants']=data['invariants']['passed']
    status='VERIFIED' if checks and all(checks.values()) else 'REFUSED'
    return seal({'schema':'ciw.bim-roundtrip-experiment.v1',
        'evidence_ref':content_identity(source),'execution_id':'execution-'+uuid.uuid4().hex,
        'verification_id':'verification-'+uuid.uuid4().hex,'runtime':before,
        'native_result':data,'carriers':roundtrip,'checks':checks,'status':status,
        'admission':'ELIGIBLE' if status=='VERIFIED' else 'REFUSED',
        'authority':{'canonical_state_mutated':False,'state_admission_performed':False,
                     'physical_validity_established':False,'geometry_authority':'QUANTITY_ONLY'},
        'limits':['declared frames, no coordinate-frame execution','synthetic observation',
                  'native IFC carrier retains raw marginal sigmas; full covariance explicitly checked',
                  'numeric covariance tolerances are not exact proof']})

def sensor_experiment():
    """Two-channel affine calibration and Gaussian conditioning, explicitly synthetic."""
    # z_raw [mm], calibration x = scale*z + offset [m]. Calibration is supplied,
    # never learned or authenticated by this arithmetic demonstration.
    raw=np.array([1990.,1010.]); gain=np.diag([.001,.001]); offset=np.array([.01,-.01])
    noise_raw=np.array([[25.,5.],[5.,16.]])
    observed=gain@raw+offset; noise=gain@noise_raw@gain.T
    prior=np.array([2.05,.95]); covariance=np.array([[.0025,.0003],[.0003,.0016]])
    k=np.linalg.solve((covariance+noise).T,covariance.T).T
    mean=prior+k@(observed-prior)
    eye=np.eye(2); posterior=(eye-k)@covariance@(eye-k).T+k@noise@k.T
    # Freeze declared decimal prior/noise, then compute the same posterior exactly.
    from .representation_lab import matrix, vector, mul, mv, inv, transpose
    add=lambda a,b: [[a[i][j]+b[i][j] for j in range(2)] for i in range(2)]
    sub=lambda a,b: [[a[i][j]-b[i][j] for j in range(2)] for i in range(2)]
    c=matrix([['1/400','3/10000'],['3/10000','1/625']])
    n=matrix([['1/40000','1/200000'],['1/200000','1/62500']])
    prior_q=vector(['41/20','19/20']); obs=vector(['2','1'])
    kq=mul(c,inv(add(c,n))); delta=mv(kq,[obs[i]-prior_q[i] for i in range(2)])
    cq=sub(c,mul(kq,c))
    source=example();source['coordinates']=encode([prior_q[i]+delta[i] for i in range(2)])
    source['covariance']=encode(cq)
    candidate=rebase(source,[['1','1'],['0','1']]); witness=verify(source,candidate)
    return {'schema':'ciw.sensor-preservation-experiment.v1',
       'evidence_id':content_identity({'raw':raw.tolist(),'noise':noise_raw.tolist()}),
       'execution_id':'execution-'+uuid.uuid4().hex,'calibration_id':'sensor.synthetic-calibration.v1',
       'source_class':'synthetic','calibration_authenticated':False,'independent_noise_assumed':True,
       'raw_unit':'mm','output_unit':'m','frame':'object-plane','calibrated_observation':observed.tolist(),
       'observation_covariance':noise.tolist(),'prior':prior.tolist(),'prior_covariance':covariance.tolist(),
       'posterior':mean.tolist(),'posterior_covariance':posterior.tolist(),
       'source_representation':source,'mapped_representation':candidate,'witness':witness,
       'authority':{'physical_validity_established':False,'canonical_state_mutated':False,'state_admission_performed':False}}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cse-root',type=Path);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--ifc',type=Path);p.add_argument('--source',type=Path)
    p.add_argument('--external-scalar-ifc',type=Path);p.add_argument('--global-id')
    args=p.parse_args(argv)
    if args.output_dir.exists(): raise ValueError('OUTPUT_ALREADY_EXISTS')
    args.output_dir.mkdir(parents=True)
    save_new(args.output_dir/'laboratory.json',laboratory())
    save_new(args.output_dir/'sensor.json',sensor_experiment())
    if args.cse_root:
        adapter=PinnedSubprocessAdapter(args.cse_root,PIN['revision'],PIN['module'],source_root='.',max_output_bytes=8*1024*1024)
        if args.ifc: save_new(args.output_dir/'external-ifc.json',external_probe(adapter,args.ifc.read_bytes()))
        if args.external_scalar_ifc:
            if not args.global_id: raise ValueError('GLOBAL_ID_REQUIRED')
            save_new(args.output_dir/'external-scalar.json',external_scalar_experiment(adapter,args.external_scalar_ifc.read_bytes(),args.global_id))
        if args.source: save_new(args.output_dir/'bim-roundtrip.json',bim_roundtrip(adapter,_json(args.source.read_bytes())))
    return 0


# Installed projection: an explicitly scoped scalar quantity, not an IFC geometry
# rewrite. The original geometry remains an opaque, byte-preserved carrier.
EXTERNAL_SCALAR = r'''
import sys,json,math,base64,tempfile,hashlib
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from gat.session import GatSession
from gat.adapters.ifc.parser import parse_ifc,Ref
from gat.adapters.ifc.reader import properties_of,quantities_of
from gat.adapters.ifc.units import length_unit_context
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.adapters.ifc.writer import _serialize_instance
from gat.ids import EntityId,VarId
from gat.engine.transform import ObserveQuantity
from gat.ledger import replay_ledger
request=json.loads(sys.stdin.buffer.read())
raw=base64.b64decode(request['source_b64'],validate=True)
f=parse_ifc(raw.decode('utf-8'))
subjects=[i for i in f.by_type('IFCBEAM') if i.args[0]==request['global_id']]
if len(subjects)!=1: raise ValueError('SOURCE_IDENTITY_NOT_UNIQUE')
subject=subjects[0]
q=quantities_of(f,properties_of(f,{subject.step_id})[subject.step_id])
length,qref=q['Length'];units=length_unit_context(f)
if units.assumed: raise ValueError('SOURCE_UNITS_ASSUMED')
# Verify every declared placement chain reference exists, and retain exact
# placements. Do not pretend this scalar projection executes 3-D frame mapping.
placement=subject.args[5];chain=[];seen=set()
while placement is not None:
    if not isinstance(placement,Ref) or placement.step_id in seen: raise ValueError('FRAME_CHAIN_INVALID')
    seen.add(placement.step_id); inst=f.deref(placement)
    if inst.type_name!='IFCLOCALPLACEMENT': raise ValueError('FRAME_CHAIN_INVALID')
    axis=f.deref(inst.args[1])
    if axis.type_name!='IFCAXIS2PLACEMENT3D': raise ValueError('FRAME_CHAIN_INVALID')
    for ref in axis.args:
        if ref is not None: f.deref(ref)
    chain.append({'placement':_serialize_instance(inst),'axis':_serialize_instance(axis)})
    placement=inst.args[0]
if not chain: raise ValueError('FRAME_MISSING')
length_m=units.to_metres(length)
gid=request['global_id']
# CSE scalar frame is deliberately distinct from the external 3-D placement.
text="""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('NET scalar projection; original geometry retained separately'),'2;1');
FILE_NAME('projection.ifc','2026-10-01T00:00:00',('NET'),('NET'),'NET','NET','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('0000000000000000000001',$,'Scalar projection',$,$,$,$,$,#3);
#2=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#3=IFCUNITASSIGNMENT((#2));
#10=IFCBEAM('%s',$,'Scoped source beam',$,$,#11,$,$,$);
#11=IFCLOCALPLACEMENT($,#12);
#12=IFCAXIS2PLACEMENT3D(#13,$,$);
#13=IFCCARTESIANPOINT((0.,0.,0.));
#20=IFCQUANTITYLENGTH('Length',$,$,%s);
#21=IFCELEMENTQUANTITY('0000000000000000000021',$,'Qto_BeamBaseQuantities',$,$,(#20));
#22=IFCRELDEFINESBYPROPERTIES('0000000000000000000022',$,$,$,(#10),#21);
ENDSEC;
END-ISO-10303-21;
"""%(gid,repr(length_m))
scope=IfcLoweringScope(frozenset([gid]))
s=GatSession.from_text(text,source='external-quantity-projection',scope=scope)
v=VarId(EntityId('IfcBeam',gid),'Length');initial=s.world
if not s.verify().passed: raise ValueError('INITIAL_INVARIANTS')
# Synthetic independent observation of the source quantity; no physical claim.
mean=length_m-.01;noise=.000025
prior_var=initial.full.std(v)**2
result=s.run(ObserveQuantity.single(v,mean,math.sqrt(noise)),strict=False)
if not result.committed: raise ValueError('CONDITIONING_REFUSED')
def state(world):
    return {'ids':[str(v) for v in world.full.index.vars],
            'mean':world.full.mu.tolist(),'covariance':world.full.sigma.tolist(),
            'world_digest':world.digest()}
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);s.export_ifc(str(root/'candidate.ifc'));s.export_snapshot(str(root/'candidate.json'))
    reloaded=GatSession.from_text((root/'candidate.ifc').read_text(),scope=scope)
    snap=GatSession.load_snapshot(str(root/'candidate.json'))
    out={'global_id':gid,'source_step_id':subject.step_id,'quantity_step_id':qref,
         'source_length':length,'scale_to_metres':units.scale_to_metres,'source_length_m':length_m,
         'source_frame_chain':chain,'canonical_frame':'scoped-scalar-no-spatial-authority',
         'prior_variance':prior_var,'observation':mean,'observation_variance':noise,
         'posterior_length':s.world.full.mean(v),'posterior_variance':s.world.full.std(v)**2,
         'candidate':state(s.world),'reloaded':state(reloaded.world),'snapshot':state(snap.world),
         'candidate_ifc_b64':base64.b64encode((root/'candidate.ifc').read_bytes()).decode(),
         'candidate_snapshot_b64':base64.b64encode((root/'candidate.json').read_bytes()).decode(),
         'ledger':s.ledger.to_dict(),'replay_world':replay_ledger(initial,s.ledger).world.digest(),
         'invariants_passed':s.verify().passed}
print(json.dumps(out,allow_nan=False))
'''

def external_scalar_experiment(adapter, raw, global_id):
    if not 0<len(raw)<=512*1024: raise ValueError('EXTERNAL_BYTE_BUDGET')
    runtime=adapter.runtime_identity()
    request={'source_b64':base64.b64encode(raw).decode(),'global_id':global_id}
    code,out=adapter._run(EXTERNAL_SCALAR,[str(adapter.source_root)],canonical(request))
    if code: raise ValueError('EXTERNAL_SCALAR_REFUSED')
    if runtime!=adapter.runtime_identity(): raise ValueError('RUNTIME_DRIFT')
    data=_json(out)
    p=data['candidate'];r=data['reloaded'];s=data['snapshot']
    expected_mean=(data['source_length_m']*data['observation_variance']+data['observation']*data['prior_variance'])/(data['prior_variance']+data['observation_variance'])
    expected_variance=data['prior_variance']*data['observation_variance']/(data['prior_variance']+data['observation_variance'])
    checks={'source_identity':data['global_id']==global_id,
      'identity_roundtrip':p['ids']==r['ids']==s['ids'],
      'mean_roundtrip':bool(np.allclose(p['mean'],r['mean'],rtol=0,atol=1e-12)),
      'covariance_roundtrip':bool(np.allclose(p['covariance'],r['covariance'],rtol=1e-10,atol=1e-14)),
      'snapshot_identity':p==s,'ledger_replay':p['world_digest']==data['replay_world'],
      'gaussian_mean':abs(data['posterior_length']-expected_mean)<1e-12,
      'gaussian_variance':abs(data['posterior_variance']-expected_variance)<1e-14,
      'native_invariants':data['invariants_passed'] is True}
    diagnostic=seal({'schema':'ciw.external-scalar-diagnostic.v1','source_ref':bytes_ref(raw),'result_ref':content_identity(data),'checks':checks})
    witness=receipts(checks,content_identity(p),content_identity(r),diagnostic['record_digest'],'bim.scalar','ciw.bim-quantity-state.v1')
    interop=external_scalar_ingress(raw,global_id,diagnostic['record_digest'],all(checks.values()))
    return seal({'schema':'ciw.external-scalar-roundtrip.v1','evidence_ref':bytes_ref(raw),
      'source_base64_chunks':[request['source_b64'][i:i+60000] for i in range(0,len(request['source_b64']),60000)],'execution_id':'execution-'+uuid.uuid4().hex,
      'verification_id':'verification-'+uuid.uuid4().hex,'runtime':runtime,'mapping_implementation_ref':bytes_ref(EXTERNAL_SCALAR.encode()),'result':data,
      'checks':checks,'diagnostic':diagnostic,'witness':witness,'interop':interop,'mapping_execution_performed':True,'status':'VERIFIED' if all(checks.values()) else 'REFUSED',
      'preserved':['source bytes including original geometry','scoped beam GlobalId','length unit semantics',
                   'posterior quantities and full covariance across export/reload'],
      'declared_loss':['3-D placement is audit-only; projected coordinates have no source spatial authority',
                       'off-scope objects have no computational state'],
      'authority':{'state_admission_performed':False,'canonical_state_mutated':False,
                   'physical_validity_established':False,'original_geometry_updated':False},
      'source_class':'external_buildingSMART_certification_dataset_with_synthetic_observation'})

if __name__=='__main__': raise SystemExit(main())
