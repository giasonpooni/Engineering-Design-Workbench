"""Bridge installed experiment predicates into existing typed preservation gates."""
from .representation_lab import contracts
from .preservation_contracts import verification_from_spec, admission_gate_from_spec

def receipts(checks, source_ref, candidate_ref, diagnostic_ref, namespace, schema_id):
    sem,registry,contract=contracts(tuple(checks),namespace,schema_id)
    # No caller-attestation CLI: installed experiment code supplies recomputed
    # checks and evidence digests. Receipt format alone does not verify bytes.
    verification=verification_from_spec(registry,sem,contract,{
      'verification_id':namespace+'.verification.v1','source_state_ref':source_ref,
      'candidate_state_ref':candidate_ref,'checks':[{
        'kind':'PRESERVE','property_id':namespace+'.'+name+'.v1',
        'status':'VERIFIED' if value is True else 'REFUTED','method':'NUMERICAL_BOUND',
        'evidence_ref':diagnostic_ref,'notes':'Installed experiment predicate; see retained method and tolerances.'}
        for name,value in checks.items()],
      'notes':'Eligibility for this declared experiment only. No state admission or physical authority.'})
    gate=admission_gate_from_spec(registry,sem,contract,verification,{
      'gate_id':namespace+'.admission.v1','forbidden_forgets':[namespace+'.'+name+'.v1' for name in checks],
      'notes':'Downstream of the installed verifier, scoped to checked properties.'})
    return {'registry':registry,'contract':contract,'verification':verification,'gate':gate}

def external_scalar_ingress(raw, global_id, diagnostic_ref, mapping_passed):
    """Qualify only the declared beam-quantity profile, with operational geometry loss."""
    from .control_contracts import bytes_ref
    from .interop_ingress import profile_from_spec,ingress_from_spec,verification_from_spec as ingress_verification,qualify_ingress,identity_reference_from_qualification
    from .industrial_transition import binding_from_spec
    from .preservation_contracts import contract_from_spec
    sem,registry,base=contracts(('identity','source_bytes'), 'bim.extraction','ciw.ifc-scoped-quantity.v1')
    contract=contract_from_spec(registry,sem,{'contract_id':'bim.extraction.preservation.v1',
       'morphism_id':'bim.extraction.mapping.v1','requires':[],
       'effects':base['effects']+[{'property_id':'bim.extraction.operational_geometry.v1','effect':'FORGET',
          'output_property_id':None,'transform_id':None,'bound':None,
          'notes':'Original geometry bytes remain audit evidence; no spatial authority in the computation carrier.'}],
       'notes':'Declared scalar projection, not whole IFC conformance.'})
    profile=profile_from_spec(registry,sem,contract,{
       'profile_id':'bim.scoped-ifc-beam-profile.v1','source_family':'STANDARD',
       'standard_id':'standard.ifc4.v1','source_profile_id':'bim.declared-beam-length.v1',
       'source_system_id':'buildingsmart.certification-dataset.v1',
       'source_schema_id':'IFC4 selected IfcBeam/Length/unit/placement-reference profile only',
       'morphism_id':'bim.extraction.mapping.v1','mapping_id':'bim.native-cse-quantity-projection.v1',
       'mapping_assumptions':['explicit unique GlobalId and quantity','placement retained without spatial computation',
          'synthetic independent scalar observation; native prior policy, not metrological calibration'],
       'uncertainty_semantics':'explicit declared prior/noise covariance, no authenticated calibration',
       'declared_loss_properties':['bim.extraction.operational_geometry.v1'],
       'verification_requirements':['selected subject mapping','declared covariance policy'],
       'notes':'Qualification is scoped to the selected quantity profile. No IFC certification.'})
    ingress=ingress_from_spec(profile,{'ingress_id':'bim.external-beam-ingress.v1','payload_ref':bytes_ref(raw),
       'payload_media_type':'application/x-step','source_identity':{'reference_id':'bim.external-beam-reference.v1',
       'namespace':'IFC.GlobalId','external_id':global_id,'object_kind':'BIM_OBJECT'},
       'mapping_parameters':{'global_id':global_id,'spatial_authority':'none_in_projection'},
       'mapping_evidence_refs':[diagnostic_ref],'notes':'Exact original IFC bytes retained separately.'})
    kinds=['PROFILE_CONFORMANCE','SOURCE_IDENTITY','REPRESENTATION_MAPPING','MAPPING_ASSUMPTIONS','UNCERTAINTY_HANDLING','PRESERVATION_PRECONDITIONS']
    verification=ingress_verification(profile,ingress,{'verification_id':'bim.external-ingress-verification.v1',
       'checks':[{'kind':kind,'status':'VERIFIED' if mapping_passed else 'REFUTED',
          'method':'DECLARED_PROFILE' if kind=='PROFILE_CONFORMANCE' else 'MAPPING_TEST',
          'evidence_ref':diagnostic_ref,'notes':'Installed bounded mapping experiment; see explicit scope and losses.'}
          for kind in kinds],'notes':'No physical authenticity inferred from successful arithmetic.'})
    qualification=qualify_ingress(registry,sem,contract,profile,ingress,verification)
    binding=None
    if qualification['status']=='QUALIFIED':
        reference=identity_reference_from_qualification(qualification,registry,sem,contract,profile,ingress,verification)
        binding=binding_from_spec({'binding_id':'bim.external-to-cse-binding.v1',
          'canonical_entity_id':'candidate-ifc-beam:'+global_id,
          'references':[reference,{'reference_id':'bim.cse-beam-reference.v1','system_id':'cse.quantity-projection.v1',
            'namespace':'IFC.GlobalId','external_id':global_id,'object_kind':'BIM_OBJECT','evidence_ref':diagnostic_ref}],
          'notes':'Candidate record continuity only; canonical entity and physical identity are not admitted.'})
    return {'registry':registry,'contract':contract,'profile':profile,'ingress':ingress,
            'verification':verification,'qualification':qualification,'identity_binding':binding}
