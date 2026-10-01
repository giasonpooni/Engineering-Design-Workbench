"""Qualify the coupled concrete experiments with operator-selected pinned runtimes."""
from __future__ import annotations
import argparse
import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from ciw.preservation_experiments import bim_roundtrip,external_probe,external_scalar_experiment,sensor_experiment
from ciw.bim_quantity import PIN
from ciw.adapters.subprocess import PinnedSubprocessAdapter
from ciw.control_contracts import save_new
from ciw.telemetry import canonical
from ciw.representation_lab import example,rebase,verify,laboratory
from ciw.foundry_childhood import execute

ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--cse-root',type=Path,required=True)
 p.add_argument('--godot',type=Path);p.add_argument('--game-root',type=Path)
 p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args()
 if args.output_dir.exists():raise ValueError('OUTPUT_ALREADY_EXISTS')
 args.output_dir.mkdir(parents=True)
 spec=importlib.util.spec_from_file_location('source_builder',ROOT/'examples/bim-quantity/make_source.py')
 builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
 source=builder.source()
 adapter=PinnedSubprocessAdapter(args.cse_root,PIN['revision'],PIN['module'],source_root='.',max_output_bytes=8*1024*1024)
 positive=bim_roundtrip(adapter,source);assert positive['status']=='VERIFIED'
 save_new(args.output_dir/'bim.json',positive)
 external=ROOT/'examples/preservation-experiments/external'
 refusal=external_probe(adapter,(external/'wall.ifc').read_bytes())
 assert refusal['result']['status']=='REFUSED';save_new(args.output_dir/'external-full-model-refusal.json',refusal)
 scalar=external_scalar_experiment(adapter,(external/'structural.ifc').read_bytes(),'0fqX614OH1YO1Njdxms2$Q')
 assert scalar['status']=='VERIFIED' and scalar['witness']['gate']['decision']=='ELIGIBLE'
 save_new(args.output_dir/'external-scalar.json',scalar)
 negatives={}
 for defect in ('missing_frame','units','coarsening','identity_alias','missing_covariance','noninvertible','contradictory_metadata'):
  bad=deepcopy(source);obs=json.loads(base64.b64decode(bad['observation_bytes_b64']))
  if defect=='missing_frame': bad['model_frame']=None
  elif defect=='units': obs['unit']='mm'
  elif defect=='coarsening':
   # Deleting a source coordinate while keeping the original observation binding
   # must not enter as the same evidence occurrence.
   text=base64.b64decode(bad['ifc_bytes_b64']).decode().replace('(0.,0.,0.)','(0.,0.)',1)
   bad['ifc_bytes_b64']=base64.b64encode(text.encode()).decode()
  elif defect=='identity_alias':
   text=base64.b64decode(bad['ifc_bytes_b64']).decode().replace('ENDSEC;\nEND-ISO',"#450=IFCSPACE('CIWSPACE00000000000300',$,'Alias',$,$,#301,$,$,$,$,$);\nENDSEC;\nEND-ISO")
   bad['ifc_bytes_b64']=base64.b64encode(text.encode()).decode()
  elif defect=='missing_covariance':obs.pop('variance')
  elif defect=='contradictory_metadata':obs['frame']='another-frame'
  elif defect=='noninvertible':
   s=example();c=rebase(s,[['1','1'],['0','1']]);c['basis']=[['1','0'],['0','0']]
   v=verify(s,c);assert v['gate']['decision']=='REFUSED';negatives[defect]={'boundary':'shared_representation_gate','reason':'NONINVERTIBLE_BASIS','witness':v};continue
  bad['observation_bytes_b64']=base64.b64encode(canonical(obs)).decode()
  try:
   v=bim_roundtrip(adapter,bad)
   assert v['status']=='REFUSED',defect
   negatives[defect]={'boundary':'native_CSE','reason':v['native_result']['reason'],'experiment':v}
  except ValueError as e:
   negatives[defect]={'boundary':'native_execution' if str(e)=='NATIVE_CSE_FAILURE' else 'input_contract',
      'reason':'NATIVE_PROCESS_FAILED' if str(e)=='NATIVE_CSE_FAILURE' else 'MALFORMED_OR_MISSING_REQUIRED_FIELD','detail':str(e)}
 save_new(args.output_dir/'negative-experiments.json',negatives)
 save_new(args.output_dir/'laboratory.json',laboratory());save_new(args.output_dir/'sensor.json',sensor_experiment())
 report={'native_CSE_revision':PIN['revision'],'external_scalar':'VERIFIED','whole_IFC':'REFUSED',
   'synthetic_BIM_roundtrip':'VERIFIED','negative_cases':len(negatives),'state_admission_performed':False,
   'physical_validity_established':False,'human_hours':None,'accepted_output_per_human_hour':None}
 if args.godot and args.game_root:
  prod=execute(args.godot,args.game_root,args.output_dir/'foundry');report['childhood_production']=prod['status']
  assert prod['status']=='completed'
 save_new(args.output_dir/'qualification.json',report);print(json.dumps(report))
 return 0

if __name__=='__main__':raise SystemExit(main())
