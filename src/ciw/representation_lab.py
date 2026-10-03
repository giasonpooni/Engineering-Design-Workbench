"""Exact two-dimensional representation laboratory using NET preservation gates.

Coordinates are rational strings, basis columns map to a fixed object frame.
The verifier derives checks from objects; it does not accept caller PASS flags.
"""
from __future__ import annotations
from fractions import Fraction as F
from copy import deepcopy
import uuid

from .control_contracts import keys, text, detached
from .core.identities import content_identity
from .operations.runner import seal
from .preservation_contracts import contract_from_spec, verification_from_spec, admission_gate_from_spec
from .representation_morphisms import registry_from_specs
from .control_plane import builtin_registry
from .semantic_capabilities import builtin_semantic_registry

PROPERTIES = ('identity', 'frame', 'unit', 'object', 'covariance', 'invertibility', 'metadata')

def rational(x):
    if type(x) is not str or len(x) > 80: raise ValueError('RATIONAL_STRING_REQUIRED')
    q = F(x)
    if abs(q.numerator) > 10**18 or q.denominator > 10**18: raise ValueError('RATIONAL_BUDGET')
    return q

def matrix(x):
    if type(x) is not list or len(x) != 2 or any(type(r) is not list or len(r) != 2 for r in x):
        raise ValueError('MATRIX_SHAPE')
    return [[rational(v) for v in row] for row in x]

def vector(x):
    if type(x) is not list or len(x) != 2: raise ValueError('VECTOR_SHAPE')
    return [rational(v) for v in x]

def det(a): return a[0][0]*a[1][1]-a[0][1]*a[1][0]
def inv(a):
    d = det(a)
    if d == 0: raise ValueError('NONINVERTIBLE_BASIS')
    return [[a[1][1]/d,-a[0][1]/d],[-a[1][0]/d,a[0][0]/d]]
def transpose(a): return [list(r) for r in zip(*a)]
def mul(a,b): return [[sum(a[i][k]*b[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
def mv(a,v): return [sum(a[i][j]*v[j] for j in range(2)) for i in range(2)]
def encode(x):
    return [encode(v) for v in x] if isinstance(x,list) else str(x)

def validate(value):
    keys(value, {'schema','entity_ids','frame','unit','basis','coordinates','covariance','metadata'})
    if value['schema'] != 'ciw.rational-vector-representation.v1': raise ValueError('SCHEMA')
    ids = value['entity_ids']
    if type(ids) is not list or not 1 <= len(ids) <= 16 or len(ids) != len(set(ids)): raise ValueError('IDENTITY_ALIAS')
    for v in ids: text(v)
    text(value['frame']); text(value['unit'])
    p=matrix(value['basis']); inv(p)
    vector(value['coordinates'])
    c=matrix(value['covariance'])
    if c != transpose(c) or c[0][0]<0 or c[1][1]<0 or det(c)<0: raise ValueError('COVARIANCE_NOT_PSD')
    keys(value['metadata'], {'frame','unit','source_class'})
    if value['metadata']['frame'] != value['frame'] or value['metadata']['unit'] != value['unit']:
        raise ValueError('CONTRADICTORY_METADATA')
    text(value['metadata']['source_class'])
    return detached(value)

def example():
    return {'schema':'ciw.rational-vector-representation.v1','entity_ids':['laboratory.vector'],
            'frame':'object-plane','unit':'m','basis':[['1','0'],['0','1']],
            'coordinates':['2','1'],'covariance':[['1/4','1/10'],['1/10','1/9']],
            'metadata':{'frame':'object-plane','unit':'m','source_class':'synthetic'}}

def rebase(source, basis):
    source=validate(source); p=matrix(basis); p_inv=inv(p)
    change=mul(p_inv,matrix(source['basis']))
    result=deepcopy(source); result['basis']=encode(p)
    result['coordinates']=encode(mv(change,vector(source['coordinates'])))
    result['covariance']=encode(mul(mul(change,matrix(source['covariance'])),transpose(change)))
    return validate(result)

def physical(value):
    p=matrix(value['basis'])
    return mv(p,vector(value['coordinates'])), mul(mul(p,matrix(value['covariance'])),transpose(p))

def contracts(properties=PROPERTIES, namespace="lab", schema_id="ciw.rational-vector-representation.v1"):
    sem=builtin_semantic_registry(builtin_registry(bind=True))
    is_lab=namespace=='lab'
    def rep(name):
        return {'representation_id':name,'role':'STATE','source_state_type':schema_id,
                'schema_id':schema_id,'quantity_semantics':'two components of one object' if is_lab else 'schema-specific quantities and installed checked predicates',
                'unit_semantics':'metres' if is_lab else 'declared by retained source','frame_semantics':'fixed object plane; explicitly supplied basis' if is_lab else 'declared scope; no inferred spatial authority',
                'time_semantics':'same instant','scale':{'length_m':None,'time_s':None,'energy_j':None,'resolution':None,'label':'exact rational'},
                'uncertainty_semantics':'full covariance; exact congruence' if is_lab else 'native covariance and explicit numerical round-trip bounds','equivalence_contract':'TASK_SPECIFIC',
                'preserved_queries':[],'supported_interventions':[],'recovery_route':None,'provenance_refs':[],'notes':''}
    m={'morphism_id':f'{namespace}.mapping.v1','kind':'TRANSFORM','domain_representation_id':f'{namespace}.source.v1',
       'codomain_representation_id':f'{namespace}.target.v1','semantic_capability':None,'parameter_names':['basis'] if is_lab else [],
       'preconditions':['invertible basis'] if is_lab else ['installed verifier obligations'],
       'validity':{'assumptions':['rational arithmetic; same object frame'] if is_lab else ['trusted installed experiment code; retained runtime identity'],
       'operating_regime':['two dimensions'] if is_lab else ['declared quantity-only scope'],
       'failure_conditions':['singular basis'] if is_lab else ['any refuted obligation']},
       'preservation':{'queries':[],'interventions':[],'invariants':[],'approximation_tolerance':None},
       'loss':{'class':'TASK_SPECIFIC','description':'exact change of basis' if is_lab else 'task-specific checked round-trip predicates','metrics':{}},
       'uncertainty':{'behavior':'UNKNOWN','method':None},'reversibility':'UNKNOWN',
       'authority_requirements':[],'verification_requirements':[],'provenance_refs':[],'notes':''}
    reg=registry_from_specs([rep(f'{namespace}.source.v1'),rep(f'{namespace}.target.v1')],[m],sem)
    contract=contract_from_spec(reg,sem,{'contract_id':f'{namespace}.preservation.v1','morphism_id':f'{namespace}.mapping.v1',
      'requires':[], 'effects':[{'property_id':f'{namespace}.{p}.v1','effect':'PRESERVE',
        'output_property_id':f'{namespace}.{p}.v1','transform_id':None,'bound':None,'notes':''} for p in properties], 'notes':''})
    return sem,reg,contract

def verify(source,candidate):
    """Recompute every obligation and then use the existing admission eligibility gate."""
    validate(source)
    errors=[]
    try: validate(candidate)
    except (ValueError,TypeError,ZeroDivisionError,KeyError) as e: errors.append(str(e))
    outcomes={p:False for p in PROPERTIES}
    if not errors:
        sx,sc=physical(source); tx,tc=physical(candidate)
        outcomes={'identity':source['entity_ids']==candidate['entity_ids'],
          'frame':source['frame']==candidate['frame'],'unit':source['unit']==candidate['unit'],
          'object':sx==tx,'covariance':sc==tc,'invertibility':True,
          'metadata':source['metadata']==candidate['metadata']}
    sem,reg,contract=contracts()
    diagnostic=seal({'schema':'ciw.lab-diagnostic.v1','source_ref':content_identity(source),
       'candidate_ref':content_identity(candidate),'checks':outcomes,'reasons':errors,
       'verifier_id':'verification-'+uuid.uuid4().hex,'method':'exact_rational_algebra'})
    checks=[{'kind':'PRESERVE','property_id':f'lab.{p}.v1',
       'status':'VERIFIED' if outcomes[p] else 'REFUTED','method':'EXACT_ALGEBRA',
       'evidence_ref':diagnostic['record_digest'],'notes':p} for p in PROPERTIES]
    receipt=verification_from_spec(reg,sem,contract,{'verification_id':'lab.verification.v1',
       'source_state_ref':content_identity(source),'candidate_state_ref':content_identity(candidate),
       'checks':checks,'notes':'Exact supplied objects only; no physical calibration or state admission.'})
    gate=admission_gate_from_spec(reg,sem,contract,receipt,{'gate_id':'lab.admission.v1',
       'forbidden_forgets':[f'lab.{p}.v1' for p in PROPERTIES],'notes':'Eligibility only.'})
    return {'registry':reg,'contract':contract,'diagnostic':diagnostic,'verification':receipt,'gate':gate}

def laboratory(operator=None,basis=None):
    source=example(); basis=basis or [['1','1'],['0','1']]
    candidate=rebase(source,basis)
    a=matrix(operator or [['2','1'],['0','3']]); p=matrix(basis)
    b=mul(mul(inv(p),a),p)
    original=mv(a,vector(source['coordinates'])); represented=mv(p,mv(b,vector(candidate['coordinates'])))
    naive=mv(p,mv(a,vector(candidate['coordinates'])))
    rank=2 if det(a) else (1 if any(v for r in a for v in r) else 0)
    row=next((r for r in a if any(r)),[F(0),F(0)])
    kernel=[] if rank==2 else ([[F(1),F(0)],[F(0),F(1)]] if rank==0 else [[-row[1],row[0]]])
    columns=transpose(a)
    image=columns if rank==2 else ([next(c for c in columns if any(c))] if rank==1 else [])
    return {'schema':'ciw.representation-laboratory.v1' ,'source':source,'candidate':candidate,
       'operator_A':encode(a),'operator_B':encode(b),'transformed_object':encode(original),
       'commutes':original==represented,'naive_operator_counterexample':{'object':encode(naive),'fails':naive!=original},
       'trace':str(a[0][0]+a[1][1]),'determinant':str(det(a)),
       'rank':rank,'kernel_basis_A':encode(kernel),'image_basis_A':encode(image),
       'characteristic_polynomial':{'lambda_squared':'1','lambda':str(-a[0][0]-a[1][1]),'constant':str(det(a))},
       'metric_B':encode(mul(transpose(p),p)), 'witness':verify(source,candidate),
       'proof_scope':'Exact evaluation and similarity formulas; not a machine-checked universal proof.'}
