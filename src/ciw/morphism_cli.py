"""Create and inspect Representation + Morphism Registry records."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .representation_morphisms import inspect_registry, registry_from_specs, witness_from_spec
from .semantic_capabilities import builtin_semantic_registry

def _semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))

def main(argv=None):
    parser=argparse.ArgumentParser(prog="net morphism",description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    create=commands.add_parser("create-registry"); create.add_argument("spec",type=Path); create.add_argument("--output",type=Path,required=True)
    witness=commands.add_parser("create-witness"); witness.add_argument("registry",type=Path); witness.add_argument("spec",type=Path); witness.add_argument("--output",type=Path,required=True)
    inspect=commands.add_parser("inspect"); inspect.add_argument("record",type=Path)
    args=parser.parse_args(argv)
    try:
        semantic=_semantic()
        if args.command=="create-registry":
            spec=load(args.spec)
            if set(spec)!={"representations","morphisms"}: raise ValueError("Registry spec requires representations and morphisms only")
            value=registry_from_specs(spec["representations"],spec["morphisms"],semantic)
            save_new(args.output,value)
            print(json.dumps({"status":"created","representations":len(value["representations"]),"morphisms":len(value["morphisms"]),"selects_engine":False,"authorizes_execution":False,"output":str(args.output)}))
            return 0
        if args.command=="create-witness":
            value=witness_from_spec(load(args.registry),semantic,load(args.spec)); save_new(args.output,value)
            print(json.dumps({"status":"created","witness_id":value["witness_id"],"morphism_id":value["morphism_id"],"general_morphism_law_proved":False,"physical_validity_established":False,"output":str(args.output)}))
            return 0
        value=load(args.record)
        if value.get("schema")=="ciw.morphism-registry.v1":
            result=inspect_registry(value,semantic)
        elif value.get("schema")=="ciw.morphism-witness.v1":
            result={"schema":"ciw.morphism-witness-inspection.v1","record_digest":value["record_digest"],"registry_ref":value["registry_ref"],"morphism_id":value["morphism_id"],"checks":{"PASS":sum(r["status"]=="PASS" for r in value["checks"]),"FAIL":sum(r["status"]=="FAIL" for r in value["checks"]),"UNRESOLVED":sum(r["status"]=="UNRESOLVED" for r in value["checks"])},"general_morphism_law_proved":False,"physical_validity_established":False}
        else: raise ValueError("Unsupported representation/morphism record schema")
        print(json.dumps(result,indent=2)); return 0
    except (OSError,ValueError,TypeError,KeyError,OverflowError) as exc:
        print(json.dumps({"status":"refused","reason":str(exc)}),file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
