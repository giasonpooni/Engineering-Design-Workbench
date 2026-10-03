"""Explicit retained Session workflow for finite conservative interface algebra.

Evidence contains one exact synthetic or declared-solver-output configuration,
not acquired measurements. Solver qualifications remain separate. Archives
validate declarations/results without activating providers; fresh verification
creates a distinct Session occurrence and leaves the archive unchanged.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import stat
import tempfile

from . import fluid_coupling as coupling
from .adapters.protocol import InstrumentManifest
from .control_contracts import content_ref,json_tree,keys,save_new,text
from .core.identities import evidence_id,new_identity,validate_evidence_identity,validate_identity
from .core.records import validate_run_structure
from .operations.registry import Operation
from .operations.runner import check_seal,digest

DECLARATION_SCHEMA="ciw.fluid-interface-declaration.v1"
PAYLOAD_SCHEMA="ciw.fluid-interface-verification-payload.v1"
OPERATION_ID="fluid.interface.transfer.v1"
VERIFY_OPERATION_ID="fluid.interface.verify.v1"
OPERATIONS=(OPERATION_ID,VERIFY_OPERATION_ID)
INSTRUMENT="fluid-interface-configuration-declaration.v1"
FRAME="fluid.interface.configuration.v1"
MAX_DECLARATION_FILE_BYTES=2*1024*1024
MAX_BUNDLE_FILE_BYTES=16*1024*1024
AUTHORITY={"input_semantics":"synthetic_or_declared_solver_output_configuration_only",
           "input_content_refs":"declared_only_not_authenticated_or_replayed",
           "physical_measurement_validation":"not_established","coupled_model_qualification":"not_established",
           "receiving_solver_qualification":"required_separately","clock_synchronization":"declared_compatibility_only",
           "solver_activation":"not_performed","state_admission":"not_performed","hardware_actuation":"not_performed"}


def validate_declaration(value,*,check_psd=True):
    json_tree(value)
    keys(value,{"schema","source","interface_request"})
    if value["schema"]!=DECLARATION_SCHEMA:
        raise ValueError("Unsupported retained interface declaration schema")
    source=value["source"]
    keys(source,{"kind","source_ref","fluid_result_ref","structural_result_ref"})
    if type(source["kind"]) is not str or source["kind"] not in {"synthetic","declared_solver_output"}:
        raise ValueError("Interface input must be synthetic or declared solver output; acquired measurements are unqualified")
    text(source["source_ref"])
    for name in ("fluid_result_ref","structural_result_ref"):
        if source["kind"]=="synthetic":
            if source[name] is not None:raise ValueError("Synthetic interface declarations cannot claim external solver result identities")
        else:
            content_ref(source[name])
    coupling.validate_request(value["interface_request"],check_psd=check_psd)
    return deepcopy(value)


def example_declaration():
    return {"schema":DECLARATION_SCHEMA,
            "source":{"kind":"synthetic","source_ref":"fluid.interface.default-finite-reference","fluid_result_ref":None,"structural_result_ref":None},
            "interface_request":coupling.example_request()}


def template():
    return example_declaration()


def make_source(declaration):
    declaration=validate_declaration(declaration,check_psd=False)
    manifest=InstrumentManifest(instrument_id=INSTRUMENT,role="synthetic_or_declared_solver_interface_configuration",
        units={"configuration_declaration":"1"},frames=(FRAME,),
        sampling={"kind":"one_interface_configuration_declaration","time_semantics":"synthetic_selection_envelope_not_interface_clock"},
        supported_operations=OPERATIONS,
        calibration_requirements={"physical_measurements":"none; interface inputs are declared solver output or synthetic configuration"})
    source={"run_schema":"run.v1","run_id":"run-fluid-interface-"+digest(declaration)[7:23],"instrument":INSTRUMENT,
            "metadata":{"duration_s":1.0,"sample_count":1,"sample_rate_hz":None,"coordinate_frame":FRAME,
                        "manifest":manifest.to_dict(),"fluid_interface_declaration":declaration,
                        "provenance":{"source":"exact interface configuration declaration; no acquired measurement, solver activation or coupled model qualification",
                                      "generator":"ciw.fluid_interface_workflow.make_source","generator_version":1}},
            "time_s":[0.0],"channels":{"configuration_declaration":{"unit":"1","values":[0.0]}},"render":{}}
    source["evidence_id"]=evidence_id(source)
    return source


def source_request(source):
    validate_run_structure(source)
    validate_evidence_identity(source)
    declaration=source["metadata"]["fluid_interface_declaration"]
    if digest(source)!=digest(make_source(declaration)):
        raise ValueError("Interface source must be the exact retained configuration declaration")
    return deepcopy(declaration)


def runtime_identity(kind):
    import numpy as np
    if kind not in {"transfer","verifier"}:raise ValueError("Unsupported interface runtime kind")
    modules=[coupling,__import__(__name__,fromlist=["*"])]
    raw=b"\0".join(Path(module.__file__).name.encode()+b"\0"+Path(module.__file__).read_text(encoding="utf-8").replace("\r\n","\n").encode() for module in modules)
    return {"provider":"ciw.fluid.interface."+kind,"version":"1","code_sha256":sha256(raw).hexdigest(),
            "source_normalization":"utf8_lf","scope":coupling.CLAIM_SCOPE,
            "environment":{"python":platform.python_version(),"numpy":np.__version__,"floating_point":"binary64"}}


def validate_runtime(operation,runtime,*,allow_absent=False):
    if operation not in OPERATIONS:raise ValueError("Unsupported interface operation")
    if runtime is None and allow_absent:return
    keys(runtime,{"provider","version","code_sha256","source_normalization","scope","environment"})
    kind="transfer" if operation==OPERATION_ID else "verifier"
    if runtime["provider"]!="ciw.fluid.interface."+kind or runtime["version"]!="1" or runtime["source_normalization"]!="utf8_lf" or runtime["scope"]!=coupling.CLAIM_SCOPE:
        raise ValueError("Interface runtime provider/version/scope differs")
    content_ref("sha256:"+runtime["code_sha256"] if type(runtime["code_sha256"]) is str else None)
    environment=runtime["environment"]
    keys(environment,{"python","numpy","floating_point"})
    if type(environment["python"]) is not str or not 1<=len(environment["python"])<=80 or environment["floating_point"]!="binary64":
        raise ValueError("Interface runtime Python/floating-point declaration differs")
    if type(environment["numpy"]) is not str or len(environment["numpy"])>80 or re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}[A-Za-z0-9.+-]*",environment["numpy"]) is None:
        raise ValueError("Interface runtime NumPy version must be a bounded version string")


def _candidate(source,parameters):
    keys(parameters,{"candidate"})
    candidate=parameters["candidate"]
    check_seal(candidate)
    if candidate.get("schema")!="ciw.operation-result.v1" or candidate.get("operation_id")!=OPERATION_ID or candidate.get("role")!="backend" or candidate.get("evidence_id")!=source["evidence_id"] or candidate.get("run_id")!=source["run_id"] or candidate.get("parameters")!={}:
        raise ValueError("Interface verification candidate must bind the exact declared source and transfer occurrence")
    validate_identity(candidate.get("result_id"),"result")
    validate_identity(candidate.get("execution_id"),"execution")
    validate_runtime(OPERATION_ID,candidate.get("runtime"))
    coupling.validate_result(source_request(source)["interface_request"],candidate["data"])
    return candidate


def result_dependencies(operation,parameters):
    if operation==OPERATION_ID:
        keys(parameters,set());return []
    if operation!=VERIFY_OPERATION_ID:raise ValueError("Unsupported interface dependency operation")
    keys(parameters,{"candidate"})
    candidate=parameters["candidate"]
    if type(candidate) is not dict:raise ValueError("Interface verification requires a declared candidate occurrence")
    validate_identity(candidate.get("result_id"),"result")
    return [candidate["result_id"]]


def validate_live_dependency(parameters,retained_results):
    keys(parameters,{"candidate"})
    candidate=parameters["candidate"]
    if type(candidate) is not dict:raise ValueError("Interface candidate must be retained before verification executes")
    identity=candidate.get("result_id")
    if type(identity) is not str or identity not in retained_results or digest(retained_results[identity])!=digest(candidate):
        raise ValueError("Interface candidate differs from the exact live retained result")


def _transfer(source,parameters):
    keys(parameters,set())
    return coupling.transfer(source_request(source)["interface_request"])


def _verify(source,parameters):
    candidate=_candidate(source,parameters)
    return {"schema":PAYLOAD_SCHEMA,"verification_id":new_identity("verification"),
            "candidate_result_id":candidate["result_id"],"candidate_execution_id":candidate["execution_id"],
            "candidate_record_digest":candidate["record_digest"],"source_evidence_id":source["evidence_id"],
            "report":coupling.verify(source_request(source)["interface_request"],candidate["data"]),"authority":deepcopy(AUTHORITY)}


def operations():
    return [Operation(OPERATION_ID,"backend",_transfer,lambda:runtime_identity("transfer")),
            Operation(VERIFY_OPERATION_ID,"verification",_verify,lambda:runtime_identity("verifier"))]


def registry():
    from .operations.registry import default_registry
    result=default_registry()
    for operation in operations():result.register(operation)
    return result


def validate_payload(operation,data,source,parameters,selection):
    request=source_request(source)["interface_request"]
    if operation==OPERATION_ID:
        keys(parameters,set());coupling.validate_result(request,data);return
    if operation!=VERIFY_OPERATION_ID:raise ValueError("Unsupported interface payload operation")
    candidate=_candidate(source,parameters)
    keys(data,{"schema","verification_id","candidate_result_id","candidate_execution_id","candidate_record_digest","source_evidence_id","report","authority"})
    validate_identity(data["verification_id"],"verification")
    expected={"schema":PAYLOAD_SCHEMA,"candidate_result_id":candidate["result_id"],"candidate_execution_id":candidate["execution_id"],
              "candidate_record_digest":candidate["record_digest"],"source_evidence_id":source["evidence_id"],"authority":AUTHORITY}
    if any(data[name]!=value for name,value in expected.items()):raise ValueError("Interface verification identity/authority/source differs")
    coupling.validate_report(request,candidate["data"],data["report"])


def validate_result_dependencies(results):
    verification_ids=set()
    for result in results.values():
        operation=result.get("operation_id")
        if operation not in OPERATIONS:continue
        validate_runtime(operation,result.get("runtime"))
        if operation==OPERATION_ID:continue
        validate_live_dependency(result["parameters"],results)
        identity=result["data"]["verification_id"]
        if identity in verification_ids:raise ValueError("Duplicate interface verification occurrence identity")
        verification_ids.add(identity)


def _execute(session,operation,parameters):
    reply=session.handle({"protocol_version":1,"request_id":"fluid-interface","type":"operation.execute",
                          "payload":{"operation_id":operation,"parameters":parameters}})
    if reply["type"]!="response":raise ValueError(reply["payload"]["message"])
    return reply["payload"]


def run(declaration,destination):
    from .session import Session
    declaration=validate_declaration(declaration)
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    save_new(destination/"request.json",declaration)
    session=Session(make_source(declaration),destination,operations=registry())
    candidate=_execute(session,OPERATION_ID,{})
    verification=None
    if candidate["status"]=="completed":verification=_execute(session,VERIFY_OPERATION_ID,{"candidate":candidate["result"]})
    session.save_workspace(destination/"workspace.json")
    if verification is not None and verification["status"]=="completed":save_new(destination/"verification.json",verification["result"]["data"])
    return inspect(destination)


def load_regular(path,*,max_bytes=MAX_DECLARATION_FILE_BYTES):
    from .session import loads_json
    path=Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):raise ValueError("Interface files must be bounded regular files without symlinks")
    descriptor=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    try:
        actual=os.fstat(descriptor)
        if not stat.S_ISREG(actual.st_mode) or not 0<actual.st_size<=max_bytes:raise ValueError("Interface file exceeds bounded regular-file budget")
        with os.fdopen(descriptor,"rb",closefd=False) as stream:raw=stream.read(max_bytes+1)
        if not raw or len(raw)>max_bytes:raise ValueError("Interface file exceeds bounded byte budget")
    finally:os.close(descriptor)
    result=loads_json(raw.decode("utf-8"));json_tree(result);return result


def _read(destination):
    from .session import Session
    destination=Path(destination)
    artifacts={"workspace.json":load_regular(destination/"workspace.json",max_bytes=MAX_BUNDLE_FILE_BYTES),
               "request.json":load_regular(destination/"request.json")}
    receipt=destination/"verification.json"
    if receipt.exists() or receipt.is_symlink():artifacts["verification.json"]=load_regular(receipt)
    with tempfile.TemporaryDirectory(prefix="fluid-interface-inspect-") as temporary:
        root=Path(temporary);snapshot=root/"snapshot.json"
        snapshot.write_text(json.dumps(artifacts["workspace.json"],allow_nan=False),encoding="utf-8")
        session=Session.from_workspace(snapshot,root/"restored")
    declaration=source_request(session.run)
    if digest(validate_declaration(artifacts["request.json"],check_psd=False))!=digest(declaration):raise ValueError("Retained interface request differs from exact source")
    candidates=[row for row in session.results.values() if row["operation_id"]==OPERATION_ID]
    verifications=[row for row in session.results.values() if row["operation_id"]==VERIFY_OPERATION_ID]
    executions=list(session.executions.values())
    if any(row["operation_id"] not in OPERATIONS for row in executions):raise ValueError("Interface archive contains unrelated execution")
    if len(executions)==1 and executions[0]["operation_id"]==OPERATION_ID and executions[0]["status"]=="refused":
        if session.results or "verification.json" in artifacts:raise ValueError("Refused transfer archive may not contain results/receipts")
        return session,None,None
    if len(executions)==2 and len(candidates)==1 and not verifications and sum(row["operation_id"]==VERIFY_OPERATION_ID and row["status"]=="refused" for row in executions)==1:
        if len(session.results)!=1 or "verification.json" in artifacts:raise ValueError("Refused interface verifier archive contains unexpected result/receipt")
        return session,candidates[0],None
    if len(candidates)!=1 or len(verifications)!=1 or len(session.results)!=2 or len(executions)!=2:
        raise ValueError("Interface archive requires one transfer and one verification occurrence")
    candidate,verification=candidates[0],verifications[0]
    validate_live_dependency(verification["parameters"],session.results)
    if digest(artifacts.get("verification.json"))!=digest(verification["data"]):raise ValueError("Interface verification artifact differs from retained result")
    return session,candidate,verification


def _inspection(session,candidate,verification):
    declaration=source_request(session.run)
    base={"schema":"ciw.fluid-interface-inspection.v1","status":"REFUSE","evidence_id":session.run["evidence_id"],
          "source_kind":declaration["source"]["kind"],"fresh_execution":False,"fresh_numerical_verification":False,"authority":deepcopy(AUTHORITY)}
    if verification is None:
        base["executions"]=[{name:deepcopy(value) for name,value in row.items() if name!="parameters"} for row in session.executions.values()]
        return base
    report=verification["data"]["report"]
    base.update(status=report["qualification"]["action"],qualification=deepcopy(report["qualification"]),checks=deepcopy(report["checks"]),
                operation_id=OPERATION_ID,execution_id=candidate["execution_id"],result_id=candidate["result_id"],
                verification_operation_id=VERIFY_OPERATION_ID,verification_execution_id=verification["execution_id"],verification_result_id=verification["result_id"],
                verification_id=verification["data"]["verification_id"],report_digest=report["record_digest"])
    return base


def inspect(destination):
    return _inspection(*_read(destination))


def verify_retained(destination):
    from .session import Session
    session,candidate,verification=_read(destination)
    if verification is None:return _inspection(session,candidate,verification)
    with tempfile.TemporaryDirectory(prefix="fluid-interface-verify-") as temporary:
        audit=Session(session.run,Path(temporary),operations=registry())
        audit.results[candidate["result_id"]]=deepcopy(candidate)
        audit.selection=deepcopy(session.selection)
        fresh=_execute(audit,VERIFY_OPERATION_ID,{"candidate":candidate})
    if fresh["status"]!="completed":raise ValueError("Fresh interface verification refused: "+fresh["execution"]["refusal"]["message"])
    result=fresh["result"]
    if digest(result["data"]["report"])!=digest(verification["data"]["report"]):raise ValueError("Fresh independent interface verification differs from retained report")
    checked=_inspection(session,candidate,verification)
    checked.update(fresh_execution=True,fresh_numerical_verification=True,fresh_verification_id=result["data"]["verification_id"],
                   fresh_verification_execution_id=result["execution_id"],fresh_verification_result_id=result["result_id"],
                   fresh_verification_record=deepcopy(result["data"]),recomputed_report_digest=result["data"]["report"]["record_digest"],
                   recomputed_with_runtime=deepcopy(result["runtime"]))
    return checked
