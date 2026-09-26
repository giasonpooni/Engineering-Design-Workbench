"""Pinned SCR provider-host operations, retained through the existing Workbench.

Runtime paths are operator configuration. Retained inspection never launches a
process or repeats numerical checks. Original transport bytes remain evidence.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import tempfile
import threading
import time
import uuid

from . import native_interop_contract as contract
from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import _json
from .declared_workload import _commit
from .telemetry import canonical, digest, byte_digest, _bundle_digest, _now

KIND, OPERATION, ROLE = "native-interop", "ciw.native-interop.v1", "scr"
SCHEMA = "ciw.native-interop-session.v1"
SOURCE_SCHEMA = contract.SCHEMA
MAX_BYTES = 8*1024*1024
FRAME_LIMIT = 4*1024*1024
REQUEST_SCHEMA = "ciw.native-interop-request.v1"
RESPONSE_SCHEMA = "ciw.native-interop-response.v1"
RUNTIME_FILES = ("runtimes/native-interop/Project.toml", "runtimes/native-interop/Manifest.toml",
                 "runtimes/native-interop/worker.jl", "runtimes/julia-oscillator/oscillator_worker.jl")


def _pins():
    return _json(Path(__file__).with_name("native-interop-runtimes.json").read_bytes())


def _julia_closures(pin):
    return [pin["julia_files"], *pin.get("historical_julia_files", [])]


def _hex(value, limit=FRAME_LIMIT):
    if type(value) is not str or len(value)>2*limit or len(value)%2 or not re.fullmatch("[a-f0-9]*",value):
        raise ValueError("Malformed bounded native hexadecimal bytes")
    return bytes.fromhex(value)


def _blob(raw):
    return {"sha256":byte_digest(raw),"bytes_b64":base64.b64encode(raw).decode("ascii")}


def _unblob(value):
    contract.keys(value,{"sha256","bytes_b64"})
    if type(value["bytes_b64"]) is not str or len(value["bytes_b64"])>4*((FRAME_LIMIT+2)//3):
        raise ValueError("Retained native byte budget exceeded")
    raw=base64.b64decode(value["bytes_b64"],validate=True)
    if len(raw)>FRAME_LIMIT or value!=_blob(raw): raise ValueError("Retained native byte binding differs")
    return raw


def frame(raw):
    if not 1<=len(raw)<=FRAME_LIMIT: raise ValueError("Native frame size outside bounds")
    return struct.pack(">I",len(raw))+raw


def frames(raw):
    result=[];offset=0
    while offset<len(raw):
        if len(raw)-offset<4: raise ValueError("Truncated native frame header")
        size=struct.unpack_from(">I",raw,offset)[0];offset+=4
        if not 1<=size<=FRAME_LIMIT or size>len(raw)-offset: raise ValueError("Truncated or oversized native frame")
        result.append(raw[offset:offset+size]);offset+=size
    return result


def _git(root,*args):
    p=subprocess.run(["git","-C",str(root),*args],capture_output=True,timeout=15,check=True)
    return p.stdout.decode("utf-8").strip()


def _depot(value):
    paths = [Path(p).resolve(strict=True) for p in str(value).split(os.pathsep) if p]
    if not paths or not all(p.is_dir() for p in paths): raise ValueError("Julia depot unavailable")
    return os.pathsep.join(str(p) for p in paths)


def _runtime(bindings):
    required={"scr","host","host_sha256"}
    julia={"julia","julia_runtime","julia_depot"}
    if type(bindings) is not dict or not required<=bindings.keys() or not bindings.keys()<=required|julia:
        raise ValueError("Bind the explicit SCR checkout, host and expected binary digest")
    if (bindings.keys()&julia) and not julia<=bindings.keys(): raise ValueError("Julia bindings must be supplied together")
    pin=_pins()
    root=Path(bindings["scr"]).resolve(strict=True)
    revision=_git(root,"rev-parse","HEAD")
    if revision not in pin["scr_revisions"] or _git(root,"status","--porcelain","--untracked-files=all"):
        raise ValueError("SCR source must match an approved clean revision")
    host=Path(bindings["host"]).resolve(strict=True)
    host_bytes=host.read_bytes()
    if not 1<=len(host_bytes)<=64*1024*1024 or byte_digest(host_bytes)!=bindings["host_sha256"]:
        raise ValueError("SCR host binary differs from the operator binding")
    runtime={"schema":"ciw.native-interop-runtime.v1","revision":revision,
             "source_tree":_git(root,"rev-parse","HEAD^{tree}"),"host_sha256":byte_digest(host_bytes),
             "host_byte_count":len(host_bytes),"source_to_binary_attestation":"not_established",
             "julia":None}
    artifacts={}
    if julia<=bindings.keys():
        jroot=Path(bindings["julia_runtime"]).resolve(strict=True)
        for name in RUNTIME_FILES:
            raw=(jroot/name).read_bytes()
            if len(raw)>256*1024:
                raise ValueError("Julia source/environment differs from the approved provider")
            artifacts[name]=raw
        files={name:byte_digest(raw) for name,raw in artifacts.items()}
        if files not in _julia_closures(pin):
            raise ValueError("Julia source/environment differs from the approved provider")
        exe=Path(bindings["julia"]).resolve(strict=True)
        _depot(bindings["julia_depot"])
        runtime["julia"]={"executable_sha256":byte_digest(exe.read_bytes()),"files":files,
                           "threads":1,"startup_file":"disabled","package_resolution":"offline",
                           "depot_attestation":"not_established"}
    return runtime,host_bytes,artifacts


def _run(command,raw,*,cwd,env,timeout=210):
    """Bound both pipes while writing independently of child progress."""
    process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             start_new_session=os.name!="nt")
    buffers=[bytearray(),bytearray()];failed=[]
    def stop():
        if process.poll() is None:
            if os.name!="nt": os.killpg(process.pid,signal.SIGKILL)
            else: process.kill()
    def drain(pipe,index,limit):
        try:
            while chunk:=pipe.read(8192):
                if len(buffers[index])+len(chunk)>limit:
                    failed.append("Native host exceeded output budget");stop();return
                buffers[index].extend(chunk)
        except (OSError,ValueError): failed.append("Native host pipe failed")
    def write():
        try: process.stdin.write(raw);process.stdin.close()
        except (OSError,ValueError): pass
    workers=[threading.Thread(target=drain,args=(process.stdout,0,FRAME_LIMIT*2+8),daemon=True),
             threading.Thread(target=drain,args=(process.stderr,1,131072),daemon=True),threading.Thread(target=write,daemon=True)]
    for t in workers:t.start()
    try: process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        failed.append("Native host timed out");stop();process.wait(timeout=10)
    for t in workers:t.join(timeout=1)
    if any(t.is_alive() for t in workers): failed.append("Native host left pipes open")
    if failed: raise AdapterRefusal("RUNTIME_IO",failed[0])
    if process.returncode: raise AdapterRefusal("RUNTIME_FAILED",bytes(buffers[1]).decode("utf-8","replace")[-2000:])
    return bytes(buffers[0]),bytes(buffers[1])


def _invoke(s,bindings,runtime,execution_id):
    current,host_bytes,artifacts=_runtime(bindings)
    if current!=runtime: raise ValueError("Native runtime changed before invocation")
    request={"schema":REQUEST_SCHEMA,"request_id":"request-"+uuid.uuid4().hex,
             "parent_execution_id":execution_id,**{k:deepcopy(s[k]) for k in ("profile","arithmetic","semantics","payload")}}
    hello={"schema":"ciw.native-interop-handshake-request.v1","request_id":"handshake-"+uuid.uuid4().hex}
    raw_request=canonical(request);raw_hello=canonical(hello)
    env=os.environ.copy();env.update(JULIA_NUM_THREADS="1",JULIA_LOAD_PATH=os.pathsep.join(("@","@stdlib")),JULIA_PKG_OFFLINE="true")
    scratch=Path(bindings["host"]).resolve().parent/".ciw-provider-runs"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ciw-interop-",dir=scratch) as temp:
        root=Path(temp);exe=root/("scr-provider-host.exe" if os.name=="nt" else "scr-provider-host")
        exe.write_bytes(host_bytes);exe.chmod(0o700)
        command=[str(exe),"--provider",s["provider"],"--timeout-ms","180000"]
        if s["provider"]=="julia":
            if runtime["julia"] is None: raise AdapterRefusal("RUNTIME_UNAVAILABLE","Julia provider is not bound")
            for name,raw in artifacts.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            project=root/"runtimes/native-interop"
            command += ["--julia",str(Path(bindings["julia"]).resolve()),"--project",str(project),"--worker",str(project/"worker.jl")]
            env["JULIA_DEPOT_PATH"]=_depot(bindings["julia_depot"])
        started=time.perf_counter()
        out,err=_run(command,frame(raw_hello)+frame(raw_request),cwd=root,env=env)
        seconds=time.perf_counter()-started
        if exe.read_bytes()!=host_bytes: raise ValueError("Host snapshot changed during execution")
        for name,raw in artifacts.items():
            if s["provider"]=="julia" and (root/name).read_bytes()!=raw: raise ValueError("Julia snapshot changed during execution")
    if _runtime(bindings)[0]!=runtime: raise ValueError("Native runtime changed during invocation")
    hello_response,response=frames(out)
    identity=_json(hello_response)
    if identity.get("request_id")!=hello["request_id"] or identity.get("status")!="ok": raise ValueError("Host handshake mismatch")
    decoded=_json(response)
    if decoded.get("request_id")!=request["request_id"] or decoded.get("parent_execution_id")!=execution_id or decoded.get("profile")!=s["profile"]:
        raise ValueError("Host returned a stale or mismatched response")
    if decoded.get("status")!="ok":
        raise AdapterRefusal("NATIVE_PROVIDER_REFUSED",str(decoded.get("refusal"))[:2000])
    return {"handshake_request":_blob(raw_hello),"handshake_response":_blob(hello_response),
            "request":_blob(raw_request),"response":_blob(response),"stderr":_blob(err),"process_seconds":seconds}


def _host_check(s,request,response):
    contract.keys(response,{"schema","status","request_id","parent_execution_id","profile","data","host"})
    if response.get("schema")!=RESPONSE_SCHEMA or response.get("status")!="ok": raise ValueError("Invalid retained native response")
    for key in ("request_id","parent_execution_id","profile"):
        if response.get(key)!=request[key]: raise ValueError("Retained native occurrence binding differs")
    h=response["host"]
    contract.keys(h,{"schema","provider","process_id","occurrence","child_process_id","child_occurrence","status",
                     "program_bytes_hex","configuration_bytes_hex","input_bytes_hex","output_bytes_hex","program_id","input_id",
                     "output_id","specification_id","computation_id","child_request_bytes_hex","child_response_bytes_hex",
                     "child_stderr_hex","provider_runtime","proof","elapsed_seconds"})
    if h["schema"]!="scr.provider-host-record.v1" or h["provider"]!=s["provider"] or h["status"]!="completed":
        raise ValueError("Retained native host claim differs")
    program,config,inputs,output=(_hex(h[key]) for key in ("program_bytes_hex","configuration_bytes_hex","input_bytes_hex","output_bytes_hex"))
    if _json(inputs)!=s["payload"] or inputs!=canonical(s["payload"]) or canonical(_json(output))!=canonical(response["data"]):
        raise ValueError("SCR retained input/output bytes differ")
    if _json(config)!={"arithmetic":s["arithmetic"],"semantics":s["semantics"]}:
        raise ValueError("SCR specification configuration differs")
    if _json(program)!={"profile":s["profile"],"runtime":h["provider_runtime"]}:
        raise ValueError("SCR program/profile binding differs")
    expected={"program_id":_commit("program",[program]),"input_id":_commit("input",[inputs]),
              "output_id":_commit("output",[output]),"specification_id":_commit("specification",[program,config,inputs])}
    expected["computation_id"]=_commit("computation",[bytes.fromhex(expected[k]) for k in ("program_id","input_id","output_id")]+[struct.pack("<I",0)])
    if any(h[k]!=v for k,v in expected.items()): raise ValueError("SCR commitment mismatch")
    if h["proof"] is not None: raise ValueError("This numerical operation does not admit proof records")
    for name in ("process_id","occurrence"):
        if type(h[name]) is not int or h[name] < (1 if name=="process_id" else 0): raise ValueError("Invalid host occurrence")
    contract.number(h["elapsed_seconds"],0,210)
    _hex(h["child_stderr_hex"],65536)
    if s["provider"]=="julia":
        for name in ("child_process_id","child_occurrence"):
            if type(h[name]) is not int or h[name] < (1 if name=="child_process_id" else 0): raise ValueError("Invalid child occurrence")
        if _hex(h["child_request_bytes_hex"])!=canonical(request): raise ValueError("Child request differs")
        child=_json(_hex(h["child_response_bytes_hex"]))
        if canonical(child)!=canonical({k:v for k,v in response.items() if k!="host"}): raise ValueError("Child response differs")
        if s["profile"]=="oscillator-tsit5.v1" and response["data"]["request_id"]!=request["request_id"]:
            raise ValueError("Inner oscillator occurrence differs")
    elif any(h[k] is not None for k in ("child_process_id","child_occurrence","child_request_bytes_hex","child_response_bytes_hex")) or h["child_stderr_hex"]:
        raise ValueError("C++ result has unexpected child execution")


def _runtime_link(runtime,s,hello,reply,response):
    contract.keys(hello,{"schema","request_id"})
    contract.keys(reply,{"schema","request_id","status","identity","profiles","limits","cancellation"})
    if hello["schema"]!="ciw.native-interop-handshake-request.v1" or not re.fullmatch(r"handshake-[a-f0-9]{32}",hello["request_id"]):
        raise ValueError("Invalid handshake request")
    if reply["schema"]!="ciw.native-interop-handshake-response.v1" or reply["request_id"]!=hello["request_id"] or reply["status"]!="ok" or reply["cancellation"]!="unsupported":
        raise ValueError("Invalid handshake response")
    profiles=(["affine-binary64.v1","affine-d256.v1","oscillator-force-energy.v1"] if s["provider"]=="cpp" else
              ["affine-binary64.v1","affine-d256.v1","oscillator-tsit5.v1","control-oscillator.v1","design-qp.v1"])
    if reply["profiles"]!=profiles or reply["limits"]!={"request_bytes":1048576,"response_bytes":4194304,"diagnostic_bytes":65536,"timeout_ms":180000,"max_requests":256}:
        raise ValueError("Host capabilities differ")
    identity=reply["identity"]
    common={"provider","host_executable_sha256","native_source_id","native_build","bridge_version"}
    extra={"julia_executable_sha256","worker_sha256","project_sha256","manifest_sha256","oscillator_worker_sha256","worker_identity"}
    contract.keys(identity,common|(extra if s["provider"]=="julia" else set()))
    if identity!=response["host"]["provider_runtime"] or identity["provider"]!=s["provider"] or identity["host_executable_sha256"]!=runtime["host_sha256"]:
        raise ValueError("Host runtime identity differs from retained binding")
    if identity["bridge_version"]!="1.0.202" or not re.fullmatch(r"[a-f0-9]{64}",identity["native_source_id"]) or type(identity["native_build"]) is not str or not 1<=len(identity["native_build"])<=32768:
        raise ValueError("Malformed native build identity")
    if s["provider"]=="julia":
        j=runtime["julia"]
        if j is None or identity["julia_executable_sha256"]!=j["executable_sha256"]: raise ValueError("Julia runtime binding differs")
        file_keys=dict(zip(("project_sha256","manifest_sha256","worker_sha256","oscillator_worker_sha256"),RUNTIME_FILES))
        worker=identity["worker_identity"]
        contract.keys(worker,{"schema","julia_version","platform","threads","packages",*file_keys})
        if worker["schema"]!="ciw.native-interop-julia-identity.v1" or worker["julia_version"]!="1.10.12" or type(worker["threads"]) is not int or worker["threads"]!=1:
            raise ValueError("Julia worker identity differs")
        for key,name in file_keys.items():
            if identity[key]!=j["files"][name] or worker[key]!=identity[key]: raise ValueError("Julia worker source/environment binding differs")
        if worker["packages"]!={"ControlSystemsBase":"1.22.0","HiGHS":"1.25.4","JSON3":"1.14.3","JuMP":"1.31.2","OrdinaryDiffEqTsit5":"1.12.0","SciMLBase":"2.155.2"}:
            raise ValueError("Julia package versions differ")


def _numeric(s,data):
    value=deepcopy(data)
    # Timing and transport occurrence metadata are not numerical content.
    value.pop("request_id",None)
    if type(value.get("solver")) is dict: value["solver"].pop("solve_seconds",None)
    return {"profile":s["profile"],"arithmetic":s["arithmetic"],"semantics":s["semantics"],"data":value}


class NativeInteropWorkflow:
    kind,role,operation,schema=KIND,ROLE,OPERATION,SCHEMA
    SOURCE_SCHEMA,MAX_BYTES=SOURCE_SCHEMA,MAX_BYTES
    ROLES = {"runtime"}
    _source=staticmethod(contract.source)
    _runtime_projection=staticmethod(deepcopy)

    def _adapters(self,repositories,expected=None):
        contract.keys(repositories,{"runtime"})
        binding_path=Path(repositories["runtime"]).resolve(strict=True)
        raw=binding_path.read_bytes()
        if len(raw)>65536: raise ValueError("Host binding exceeds byte budget")
        bindings=_json(raw)
        for name in ("scr","host","julia","julia_runtime"):
            if name in bindings: bindings[name]=str((binding_path.parent/str(bindings[name])).resolve())
        runtime,_,_=_runtime(bindings)
        if expected is not None and expected!={ROLE:runtime}: raise ValueError("Native replay requires the original runtime")
        return bindings,runtime

    def _step(self,s,evidence,bound):
        bindings,runtime=bound
        occurrence="execution-"+uuid.uuid4().hex
        transport=_invoke(s,bindings,runtime,occurrence)
        response=_json(_unblob(transport["response"]))
        _host_check(s,_json(_unblob(transport["request"])),response)
        contract.validate_output(s,response["data"])
        started=time.perf_counter();check=contract.check_output(s,response["data"]);check_seconds=time.perf_counter()-started
        data={"output":deepcopy(response["data"]),"reference_check":check,"authority":deepcopy(contract.AUTHORITY)}
        result={"schema":"ciw.native-interop-result.v1","operation_id":OPERATION,"execution_ref":occurrence,
                "input_refs":[evidence],"data":data,"authority":deepcopy(contract.AUTHORITY)}
        result["result_id"]=digest(result)
        numerical=_numeric(s,response["data"])
        return {"runtime_ref":ROLE,"operation_id":OPERATION,"execution_id":occurrence,"input_refs":[evidence],
                "request":deepcopy(s),"request_sha256":digest(s),"transport":transport,"check_seconds":check_seconds,
                "result":result,"result_sha256":digest(result),"result_id":result["result_id"],
                "numerical_result":numerical,"numerical_result_id":digest(numerical)}

    def _validate_step(self,step,s,evidence,runtime):
        contract.keys(step,{"runtime_ref","operation_id","execution_id","input_refs","request","request_sha256","transport","check_seconds",
                            "result","result_sha256","result_id","numerical_result","numerical_result_id"})
        if step["runtime_ref"]!=ROLE or step["operation_id"]!=OPERATION or not re.fullmatch(r"execution-[a-f0-9]{32}",step["execution_id"]):
            raise ValueError("Native execution identity differs")
        if step["request"]!=s or step["request_sha256"]!=digest(s) or step["input_refs"]!=[evidence]: raise ValueError("Native source binding differs")
        t=step["transport"]
        contract.keys(t,{"handshake_request","handshake_response","request","response","stderr","process_seconds"})
        raw={name:_unblob(t[name]) for name in t if name!="process_seconds"}
        request,response=_json(raw["request"]),_json(raw["response"])
        expected={"schema":REQUEST_SCHEMA,"request_id":request["request_id"],"parent_execution_id":step["execution_id"],
                  **{k:s[k] for k in ("profile","arithmetic","semantics","payload")}}
        if request!=expected or canonical(request)!=raw["request"] or not re.fullmatch(r"request-[a-f0-9]{32}",request["request_id"]):
            raise ValueError("Native request envelope differs")
        hello,reply=_json(raw["handshake_request"]),_json(raw["handshake_response"])
        if reply.get("request_id")!=hello.get("request_id") or reply.get("status")!="ok": raise ValueError("Retained handshake differs")
        _host_check(s,request,response)
        _runtime_link(runtime,s,hello,reply,response)
        result=step["result"]
        contract.keys(result,{"schema","operation_id","execution_ref","input_refs","data","authority","result_id"})
        if result["schema"]!="ciw.native-interop-result.v1" or result["operation_id"]!=OPERATION or result["execution_ref"]!=step["execution_id"] or result["input_refs"]!=[evidence]:
            raise ValueError("Native result occurrence differs")
        data=result["data"];contract.keys(data,{"output","reference_check","authority"})
        contract.validate_output(s,data["output"])
        if canonical(data["output"])!=canonical(response["data"]) or data["authority"]!=contract.AUTHORITY or result["authority"]!=contract.AUTHORITY:
            raise ValueError("Retained native output/authority differs")
        check=data["reference_check"]
        contract.keys(check,{"outcome","method","max_abs_discrepancy","policy","authority"})
        method={"affine-binary64.v1":"independent_python_affine_binary64","affine-d256.v1":"independent_python_affine_integer", "oscillator-force-energy.v1":"independent_python_force_energy", "oscillator-tsit5.v1":"independent_python_analytic_oscillator", "control-oscillator.v1":"independent_python_analytic_oscillator", "design-qp.v1":"independent_python_objective_box_projected_gradient"}[s["profile"]]
        if check["outcome"]!="passed" or check["method"]!=method or check["policy"]!=contract.POLICY or check["authority"]!=contract.AUTHORITY:
            raise ValueError("Retained numerical check scope differs")
        contract.number(check["max_abs_discrepancy"],0,1e20)
        if s["arithmetic"]=="exact-d256" and check["max_abs_discrepancy"]!=0: raise ValueError("Exact check cannot claim a nonzero discrepancy")
        for v in (step["check_seconds"],t["process_seconds"]): contract.number(v,0,3600)
        numeric=_numeric(s,data["output"])
        if step["numerical_result"]!=numeric or step["numerical_result_id"]!=digest(numeric): raise ValueError("Native numerical identity differs")
        if result["result_id"]!=digest({k:v for k,v in result.items() if k!="result_id"}) or step["result_id"]!=result["result_id"] or step["result_sha256"]!=digest(result):
            raise ValueError("Native result content binding differs")

    def _verification(self,bundle,reproduced):
        old=bundle["steps"][0]["numerical_result"];new=reproduced["numerical_result"]
        if old["profile"]!=new["profile"] or old["arithmetic"]!=new["arithmetic"] or old["semantics"]!=new["semantics"]:
            raise ValueError("Native reproduction semantics differ")
        discrepancy=contract.compare(old["data"],new["data"],exact=old["arithmetic"]=="exact-d256")
        v={"schema":"ciw.native-interop-verification.v1","subject_ref":bundle["bundle_digest"],"outcome":"passed",
           "independent":False,"method":"fresh_provider_reproduction_with_separate_python_reference_checks",
           "max_abs_discrepancy":discrepancy,"runtime_digest":digest(bundle["runtimes"]),"reproduction":deepcopy(reproduced),"authority":deepcopy(contract.AUTHORITY)}
        v["verification_id"]=byte_digest(v["schema"].encode()+b"\0"+canonical(v))
        return v

    def _check_verification(self,bundle,v,s,evidence):
        self._validate_step(v["reproduction"],s,evidence,bundle["runtimes"][ROLE])
        if v!=self._verification(bundle,v["reproduction"]) or v["reproduction"]["execution_id"]==bundle["steps"][0]["execution_id"]:
            raise ValueError("Native reproduction/verification binding differs")

    def _validate(self,bundle):
        try:
            contract.keys({k:v for k,v in bundle.items() if k!="replay_receipts"},{"schema","session_id","created_at","source","configuration","runtimes","steps","bundle_digest","verification"})
            if len(canonical(bundle))>MAX_BYTES or bundle["schema"]!=SCHEMA or bundle["bundle_digest"]!=_bundle_digest(bundle): raise ValueError("Native bundle binding differs")
            if not re.fullmatch(r"session-[a-f0-9]{32}",bundle["session_id"]): raise ValueError("Native session occurrence differs")
            evidence,=bundle["source"]["evidence"]
            raw=base64.b64decode(evidence["bytes_b64"],validate=True);s=self._source(raw)
            expected={"experiment_id":s["experiment_id"],"experiment_digest":digest(s),
                      "evidence":[{"artifact_ref":byte_digest(raw),"sha256":byte_digest(raw),"bytes_b64":base64.b64encode(raw).decode()}]}
            if bundle["source"]!=expected or bundle["configuration"]!=s["configuration"]: raise ValueError("Native source/configuration differs")
            contract.keys(bundle["runtimes"],{ROLE})
            r=bundle["runtimes"][ROLE]
            contract.keys(r,{"schema","revision","source_tree","host_sha256","host_byte_count","source_to_binary_attestation","julia"})
            if r["schema"]!="ciw.native-interop-runtime.v1" or r["revision"] not in _pins()["scr_revisions"] or r["source_to_binary_attestation"]!="not_established":
                raise ValueError("Unsupported retained SCR runtime")
            if not re.fullmatch(r"[a-f0-9]{40}",r["source_tree"]) or not re.fullmatch(r"sha256:[a-f0-9]{64}",r["host_sha256"]): raise ValueError("Malformed retained runtime identity")
            if type(r["host_byte_count"]) is not int or not 1<=r["host_byte_count"]<=64*1024*1024: raise ValueError("Invalid host size")
            if r["julia"] is not None:
                j=r["julia"]
                contract.keys(j,{"executable_sha256","files","threads","startup_file","package_resolution","depot_attestation"})
                if j["files"] not in _julia_closures(_pins()) or not re.fullmatch(r"sha256:[a-f0-9]{64}",j["executable_sha256"]) or type(j["threads"]) is not int or j["threads"]!=1 or j["startup_file"]!="disabled" or j["package_resolution"]!="offline" or j["depot_attestation"]!="not_established":
                    raise ValueError("Unapproved Julia environment identity")
            step,=bundle["steps"];self._validate_step(step,s,byte_digest(raw),r)
            self._check_verification(bundle,bundle["verification"],s,byte_digest(raw))
            for receipt in bundle.get("replay_receipts",[]):
                if receipt["replayed_bundle_digest"]!=bundle["bundle_digest"] or receipt["replay_id"]!=digest({k:v for k,v in receipt.items() if k!="replay_id"}):
                    raise ValueError("Native replay receipt differs")
            return raw
        except (KeyError,TypeError,IndexError,AttributeError,OverflowError) as exc:
            raise ValueError("Malformed native interoperability bundle") from exc

    def _execute(self,raw,bound):
        s=self._source(raw);evidence=byte_digest(raw)
        first=self._step(s,evidence,bound)
        bundle={"schema":SCHEMA,"session_id":"session-"+uuid.uuid4().hex,"created_at":_now(),
                "source":{"experiment_id":s["experiment_id"],"experiment_digest":digest(s),
                          "evidence":[{"artifact_ref":evidence,"sha256":evidence,"bytes_b64":base64.b64encode(raw).decode()}]},
                "configuration":deepcopy(s["configuration"]),"runtimes":{ROLE:deepcopy(bound[1])},"steps":[first]}
        bundle["bundle_digest"]=_bundle_digest(bundle)
        bundle["verification"]=self._verification(bundle,self._step(s,evidence,bound))
        self._validate(bundle);return bundle

    def create_session(self,raw,bindings):
        self._source(raw)
        return self._execute(raw,self._adapters(bindings))

    def replay_session(self,bundle,bindings):
        raw=self._validate(bundle)
        fresh=self._execute(raw,self._adapters(bindings,bundle["runtimes"]))
        receipt={"schema":"ciw.native-interop-replay.v1","source_bundle_digest":bundle["bundle_digest"],
                 "replayed_bundle_digest":fresh["bundle_digest"],"numerical_match":True,
                 "verification":self._verification(bundle,fresh["steps"][0]),"admission":"not_performed"}
        receipt["replay_id"]=digest(receipt);fresh["replay_receipts"]=[receipt]
        self._validate(fresh);return {"session":fresh,"replay_receipt":receipt}


def validate_dependency(s,bundles):
    """Resolve an optional force/energy source to an exact retained trajectory."""
    ref=s["upstream"]
    if ref is None:return
    record=bundles.get(ref["bundle_digest"])
    if record is None or record["kind"]!=KIND: raise ValueError("Native force input requires its retained trajectory")
    b=record["native"];raw=NativeInteropWorkflow()._validate(b);parent=contract.source(raw)
    step=b["steps"][0]
    if parent["profile"] not in {"oscillator-tsit5.v1","control-oscillator.v1"} or step["result_id"]!=ref["result_id"]:
        raise ValueError("Native force dependency is not the named trajectory")
    output=step["result"]["data"]["output"]
    expected={"model":parent["payload"]["model"],**{k:output[k] for k in ("time_s","q_m","v_m_s")}}
    if s["payload"]!=expected: raise ValueError("Native force source differs from its retained trajectory")
