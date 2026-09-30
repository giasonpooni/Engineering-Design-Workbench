"""Create and inspect Representation + Morphism Registry records."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

from .control_contracts import load, save_new
from .finite_preservation import example_specs, finite_witness_from_spec, validate_finite_witness
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
    demo=commands.add_parser("finite-demo"); demo.add_argument("--output-dir",type=Path,required=True)
    for name in ("finite-check", "finite-verify"):
        finite=commands.add_parser(name)
        finite.add_argument("registry",type=Path)
        finite.add_argument("input",type=Path)
        if name=="finite-check": finite.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        semantic=_semantic()
        if args.command=="finite-demo":
            # Refuse an existing directory: demonstrations never overwrite retained evidence.
            args.output_dir.mkdir(parents=True,exist_ok=False)
            registry_spec,good,bad=example_specs()
            registry=registry_from_specs(registry_spec["representations"],registry_spec["morphisms"],semantic)
            save_new(args.output_dir/"registry.json",registry)
            summary={}
            for name,spec in (("compatible",good),("incompatible",bad)):
                value=finite_witness_from_spec(registry,semantic,spec)
                validate_finite_witness(value,registry,semantic)
                save_new(args.output_dir/(name+"-spec.json"),spec)
                save_new(args.output_dir/(name+"-witness.json"),value)
                summary[name]={"commutativity":value["results"]["commutativity_status"],
                               "distribution_equal":value["results"]["intervened_distributions_equal"],
                               "local_support_check":value["contract_and_finite_check_pass"]}
            print(json.dumps({"status":"completed","synthetic":True,"results":summary,
                              "execution_authority":False,"output_dir":str(args.output_dir)},indent=2))
            return 0
        if args.command in {"finite-check","finite-verify"}:
            registry=load(args.registry)
            if args.command=="finite-check":
                value=finite_witness_from_spec(registry,semantic,load(args.input))
                save_new(args.output,value)
            else:
                value=validate_finite_witness(load(args.input),registry,semantic)
            passed=value["contract_and_finite_check_pass"]
            print(json.dumps({"status":"PASS" if passed else "FAIL",
                              "record_digest":value["record_digest"],"results":value["results"],
                              "execution_authority":False},indent=2))
            return 0 if passed else 2
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
