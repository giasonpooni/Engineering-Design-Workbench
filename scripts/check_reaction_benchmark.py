#!/usr/bin/env python3
"""Bounded two-engine reaction gate using the existing native operation/workspace.

Requires installed CIW (or an explicitly configured development PYTHONPATH).
No package installation, provider selection from data, or physical execution.
"""
import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch

from ciw import native_interop as ni, native_interop_contract as nc, reaction_contract as rc
from ciw.adapters.oscillator import make_demo_run
from ciw.session import Session
from ciw.telemetry import canonical, byte_digest


def output(bundle):
    return bundle["steps"][0]["result"]["data"]["output"]


def numerical(data):
    return {k:deepcopy(data[k]) for k in ("model","species_order","time_s","concentration_mol_m3","production_rate_mol_m3_s")}


def forbidden(*a, **kw):
    raise AssertionError("Read-only reopen attempted runtime/reference execution")


def inspect_workspace(path, artifacts):
    with patch.object(ni,"_invoke",forbidden), patch.object(ni,"_runtime",forbidden), patch.object(nc,"check_output",forbidden), patch.object(rc,"reference",forbidden):
        session=Session.from_workspace(path,artifacts)
        summaries=session.workbench.list_bundles()
        for row in summaries:
            session.workbench.inspect_experiment({"bundle_id":row["bundle_id"]})
    return summaries


def run(catalyst, cantera, fixtures, destination):
    destination.mkdir(parents=True,exist_ok=False)
    raw=fixtures.read_bytes()
    spec=json.loads(raw)
    nc.keys(spec,{"schema","cases"})
    if spec["schema"]!="ciw.reaction-benchmark-fixtures.v1" or not 1<=len(spec["cases"])<=16:
        raise ValueError("Unsupported bounded reaction fixture set")
    if len({r["name"] for r in spec["cases"]})!=len(spec["cases"]):raise ValueError("Duplicate case name")
    for case in spec["cases"]:
        nc.keys(case,{"name","payload"});rc.validate_payload(case["payload"])
    session=Session(make_demo_run(),destination/"artifacts")
    bindings={"catalyst":catalyst.resolve(),"cantera":cantera.resolve()}
    report={"schema":"ciw.reaction-benchmark-report.v1","fixture_sha256":byte_digest(raw),
            "authority":deepcopy(nc.AUTHORITY),"rows":[],"runtime_pins":{},
            "scope":"Sampled mathematical A-to-B benchmark; no empirical chemical validation or actuation."}
    records={}
    workspace=destination/"workspace.json"
    try:
        for provider,binding in bindings.items():
            _,runtime=ni.NativeInteropWorkflow()._adapters({"runtime":binding})
            report["runtime_pins"][provider]=runtime
        for case in spec["cases"]:
            for provider,binding in bindings.items():
                name=case["name"]+":"+provider
                print("reaction benchmark: "+name,file=sys.stderr,flush=True)
                session.workbench.bind_workflow(ni.KIND,{"runtime":binding})
                source=nc.make_source(rc.PROFILE,provider,case["payload"],experiment_id=name)
                retained=session.workbench.add_source({"kind":ni.KIND,"label":name,"bytes_b64":base64.b64encode(canonical(source)).decode()})
                summary=session.workbench.execute({"operation_id":ni.OPERATION,"source_id":retained["source_id"]})
                bundle=session.workbench.get_bundle(summary["bundle_id"])
                records[(case["name"],provider)]=(summary,bundle)
                report["rows"].append({"gate":name,"status":"PASS","bundle_id":summary["bundle_id"],
                    "execution_id":bundle["steps"][0]["execution_id"],"result_id":bundle["steps"][0]["result_id"],
                    "check":deepcopy(bundle["steps"][0]["result"]["data"]["reference_check"])})
                session.save_workspace(workspace)
            a,b=(output(records[(case["name"],p)][1]) for p in bindings)
            nc.compare(numerical(a),numerical(b))
            report["rows"].append({"gate":case["name"]+":cross-engine","status":"PASS",
                "concentration_max_abs_mol_m3":nc.compare(a["concentration_mol_m3"],b["concentration_mol_m3"]),
                "production_rate_max_abs_mol_m3_s":nc.compare(a["production_rate_mol_m3_s"],b["production_rate_mol_m3_s"])})
        # Fresh execution and replay records for each provider retain distinct occurrences.
        for provider,binding in bindings.items():
            summary,old=records[(spec["cases"][0]["name"],provider)]
            session.workbench.bind_workflow(ni.KIND,{"runtime":binding})
            fresh_summary=session.workbench.replay({"bundle_id":summary["bundle_id"]})["bundle"]
            fresh=session.workbench.get_bundle(fresh_summary["bundle_id"])
            for key in ("execution_id","result_id"):
                if fresh["steps"][0][key]==old["steps"][0][key]:raise ValueError("Replay reused occurrence identity")
            nc.compare(numerical(output(old)),numerical(output(fresh)))
            report["rows"].append({"gate":provider+":fresh-replay","status":"PASS","bundle_id":fresh_summary["bundle_id"]})
        session.save_workspace(workspace)
        reopened=inspect_workspace(workspace,destination/"reopened")
        if len(reopened)!=len(spec["cases"])*2+2:raise ValueError("Reopen lost history")
        report["rows"].append({"gate":"provider-free-reopen","status":"PASS","bundle_count":len(reopened)})
        report["outcome"]="passed"
    except Exception as exc:
        session.save_workspace(workspace)
        report["outcome"]="failed"
        report["rows"].append({"gate":"execution","status":"FAIL","reason":str(exc)[:4000]})
        raise
    finally:
        (destination/"report.json").write_bytes(canonical(report))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    r=sub.add_parser("run");r.add_argument("--catalyst",type=Path,required=True);r.add_argument("--cantera",type=Path,required=True)
    r.add_argument("--fixtures",type=Path,required=True);r.add_argument("--output",type=Path,required=True)
    i=sub.add_parser("inspect");i.add_argument("--workspace",type=Path,required=True);i.add_argument("--artifacts",type=Path,required=True)
    a=parser.parse_args()
    if a.command=="run":value=run(a.catalyst,a.cantera,a.fixtures,a.output)
    else:value={"mode":"retained-inspection","bundles":inspect_workspace(a.workspace,a.artifacts),"fresh_execution":False}
    print(json.dumps(value,sort_keys=True,allow_nan=False))


if __name__=="__main__":main()
