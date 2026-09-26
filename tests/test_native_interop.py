"""Provider doubles below test retention only, never native conformance."""
import base64
from copy import deepcopy
from pathlib import Path
import struct

import pytest

from ciw import native_interop as ni, native_interop_contract as nc
from ciw.adapters.oscillator import make_demo_run
from ciw.session import Session
from ciw.telemetry import canonical, digest, byte_digest, _bundle_digest

AFFINE={"rows":2,"columns":3,"a_row_major":[2,1,-1,-1,3,2],"b":[5,-2],"x0":[3,4,2],"delta_x":[0.25,-0.5,0.125]}
RUNTIME={"schema":"ciw.native-interop-runtime.v1","revision":"a"*40,"source_tree":"b"*40,
         "host_sha256":"sha256:"+"c"*64,"host_byte_count":100,"source_to_binary_attestation":"not_established","julia":{"executable_sha256":"sha256:"+"d"*64,"files":{name:"sha256:"+"e"*64 for name in ni.RUNTIME_FILES},"threads":1,"startup_file":"disabled","package_resolution":"offline","depot_attestation":"not_established"}}


def mock_output(s):
    if s["profile"].startswith("affine-"):return nc.affine_reference(s["payload"],s["profile"]=="affine-d256.v1")
    if s["profile"]=="oscillator-force-energy.v1":return nc.force_reference(s["payload"])
    data=nc.oscillator_reference(s["payload"])
    data.update(state_order=["q","v"],solver={"retcode":"Success","algorithm":"ControlSystemsBase.lsim","method":"zoh","sample_interval_s":s["payload"]["time_s"][1]-s["payload"]["time_s"][0],"controlsystemsbase_version":"1.22.0"})
    return data


@pytest.fixture
def mock_provider(monkeypatch):
    count=[0]
    def invoke(s,bindings,runtime,execution):
        count[0]+=1
        request={"schema":ni.REQUEST_SCHEMA,"request_id":"request-"+f"{count[0]:032x}","parent_execution_id":execution,
                 **{k:deepcopy(s[k]) for k in ("profile","arithmetic","semantics","payload")}}
        data=mock_output(s)
        identity={"provider":s["provider"],"host_executable_sha256":runtime["host_sha256"],"native_source_id":"a"*64,"native_build":"EXPLICIT TEST DOUBLE", "bridge_version":"1.0.202"}
        if s["provider"]=="julia":
            files=dict(zip(("project_sha256","manifest_sha256","worker_sha256","oscillator_worker_sha256"),ni.RUNTIME_FILES))
            hashes={key:runtime["julia"]["files"][name] for key,name in files.items()}
            identity.update(julia_executable_sha256=runtime["julia"]["executable_sha256"],**hashes,
                worker_identity={"schema":"ciw.native-interop-julia-identity.v1","julia_version":"1.10.12","platform":"TEST DOUBLE","threads":1,
                    "packages":{"ControlSystemsBase":"1.22.0","HiGHS":"1.25.4","JSON3":"1.14.3","JuMP":"1.31.2","OrdinaryDiffEqTsit5":"1.12.0","SciMLBase":"2.155.2"},**hashes})
        program=canonical({"profile":s["profile"],"runtime":identity})
        config=canonical({"arithmetic":s["arithmetic"],"semantics":s["semantics"]})
        inp=canonical(s["payload"]);out=canonical(data)
        h={"schema":"scr.provider-host-record.v1","provider":s["provider"],"status":"completed","provider_runtime":identity,"proof":None,
           "program_bytes_hex":program.hex(),"configuration_bytes_hex":config.hex(),"input_bytes_hex":inp.hex(),"output_bytes_hex":out.hex(),
           "program_id":ni._commit("program",[program]),"input_id":ni._commit("input",[inp]),"output_id":ni._commit("output",[out]),
           "specification_id":ni._commit("specification",[program,config,inp])}
        h["computation_id"]=ni._commit("computation",[bytes.fromhex(h[k]) for k in ("program_id","input_id","output_id")]+[struct.pack("<I",0)])
        response={"schema":ni.RESPONSE_SCHEMA,"status":"ok","request_id":request["request_id"],"parent_execution_id":execution,"profile":s["profile"],"data":data,"host":h}
        h.update(process_id=1,occurrence=0,child_process_id=2 if s["provider"]=="julia" else None,child_occurrence=0 if s["provider"]=="julia" else None,
                 child_request_bytes_hex=canonical(request).hex() if s["provider"]=="julia" else None,
                 child_response_bytes_hex=canonical({k:v for k,v in response.items() if k!="host"}).hex() if s["provider"]=="julia" else None,
                 child_stderr_hex="",elapsed_seconds=0.01)
        hello={"schema":"ciw.native-interop-handshake-request.v1","request_id":"handshake-"+f"{count[0]:032x}"}
        reply={"schema":"ciw.native-interop-handshake-response.v1","request_id":hello["request_id"],"status":"ok","identity":identity,
            "profiles":(["affine-binary64.v1","affine-d256.v1","oscillator-force-energy.v1"] if s["provider"]=="cpp" else ["affine-binary64.v1","affine-d256.v1","oscillator-tsit5.v1","control-oscillator.v1","design-qp.v1"]),
            "limits":{"request_bytes":1048576,"response_bytes":4194304,"diagnostic_bytes":65536,"timeout_ms":180000,"max_requests":256},"cancellation":"unsupported"}
        return {"handshake_request":ni._blob(canonical(hello)),"handshake_response":ni._blob(canonical(reply)),
                "request":ni._blob(canonical(request)),"response":ni._blob(canonical(response)),"stderr":ni._blob(b""),"process_seconds":0.1}
    monkeypatch.setattr(ni,"_invoke",invoke)
    monkeypatch.setattr(ni,"_pins",lambda:{"scr_revisions":["a"*40],"julia_files":RUNTIME["julia"]["files"]})
    monkeypatch.setattr(ni.NativeInteropWorkflow,"_adapters",lambda self,bindings,expected=None:(bindings,deepcopy(RUNTIME)))
    return count


def source():return nc.make_source("affine-binary64.v1","cpp",AFFINE)


def test_current_julia_closure_matches_checkout_bytes():
    root=Path(__file__).resolve().parents[1]
    pin=ni._pins()
    assert {name:byte_digest((root/name).read_bytes()) for name in ni.RUNTIME_FILES}==pin["julia_files"]


def test_historical_julia_closure_is_preserved_without_mixing_files(mock_provider,monkeypatch):
    w=ni.NativeInteropWorkflow()
    bundle=w.create_session(canonical(source()),{})
    historical=deepcopy(RUNTIME["julia"]["files"])
    current={name:"sha256:"+"f"*64 for name in ni.RUNTIME_FILES}
    monkeypatch.setattr(ni,"_pins",lambda:{"scr_revisions":["a"*40],"julia_files":current,"historical_julia_files":[historical]})
    assert w._validate(bundle)==canonical(source())
    bundle["runtimes"]["scr"]["julia"]["files"][ni.RUNTIME_FILES[0]]=current[ni.RUNTIME_FILES[0]]
    bundle["bundle_digest"]=_bundle_digest(bundle)
    with pytest.raises(ValueError,match="Unapproved Julia environment"):
        w._validate(bundle)


def test_framing_golden_and_adversarial():
    assert ni.frame(b"abc")==b"\x00\x00\x00\x03abc"
    assert ni.frames(ni.frame(b"abc")+ni.frame(b"d"))==[b"abc",b"d"]
    for bad in (b"\x00",b"\x00\x00\x00\x00",b"\xff\xff\xff\xff",ni.frame(b"abc")[:-1],b"diagnostics"):
        with pytest.raises(ValueError):ni.frames(bad)


def test_native_bindings_and_fresh_occurrences(mock_provider):
    w=ni.NativeInteropWorkflow();raw=canonical(source());b=w.create_session(raw,{})
    step,other=b["steps"][0],b["verification"]["reproduction"]
    assert step["execution_id"]!=other["execution_id"]
    assert step["result_id"]!=other["result_id"]
    assert step["numerical_result_id"]==other["numerical_result_id"]
    assert w._validate(b)==raw
    replay=w.replay_session(b,{})
    assert replay["session"]["steps"][0]["execution_id"] not in {step["execution_id"],other["execution_id"]}
    assert mock_provider[0]==4
    assert replay["replay_receipt"]["admission"]=="not_performed"


def test_offline_retained_validation_performs_no_calculations(mock_provider,monkeypatch):
    w=ni.NativeInteropWorkflow();b=w.create_session(canonical(source()),{})
    def forbidden(*a,**kw):raise AssertionError("inspection executed code")
    monkeypatch.setattr(ni,"_invoke",forbidden)
    monkeypatch.setattr(ni,"_runtime",forbidden)
    monkeypatch.setattr(nc,"check_output",forbidden)
    monkeypatch.setattr(nc,"affine_reference",forbidden)
    assert w._validate(b)==canonical(source())


@pytest.mark.parametrize("mutation",["output","request","specification","runtime","scope","identity"])
def test_corrupt_bindings_refused_even_with_resealed_bundle(mock_provider,mutation):
    w=ni.NativeInteropWorkflow();b=w.create_session(canonical(source()),{});s=b["steps"][0]
    if mutation=="output":s["result"]["data"]["output"]["predicted_output"][0]+=1
    elif mutation=="request":s["request"]["payload"]["b"][0]+=1
    elif mutation=="specification":
        response=ni._json(ni._unblob(s["transport"]["response"]));response["host"]["specification_id"]="f"*64
        s["transport"]["response"]=ni._blob(canonical(response))
    elif mutation=="runtime":b["runtimes"]["scr"]["revision"]="f"*40
    elif mutation=="scope":s["result"]["data"]["authority"]["sp1_verification"]="passed"
    else:s["execution_id"]=b["verification"]["reproduction"]["execution_id"]
    b["bundle_digest"]=_bundle_digest(b)
    with pytest.raises(ValueError):w._validate(b)


def test_host_commitments_bind_profile_and_configuration(mock_provider):
    w=ni.NativeInteropWorkflow();b=w.create_session(canonical(source()),{})
    step=b["steps"][0]
    req=ni._json(ni._unblob(step["transport"]["request"]))
    response=ni._json(ni._unblob(step["transport"]["response"]))
    changed=deepcopy(response);changed["host"]["configuration_bytes_hex"]=canonical({"arithmetic":"exact-d256","semantics":source()["semantics"]}).hex()
    with pytest.raises(ValueError):ni._host_check(source(),req,changed)
    changed=deepcopy(response);changed["host"]["program_bytes_hex"]=canonical({"profile":"different.v1","runtime":{"test_double":True}}).hex()
    with pytest.raises(ValueError):ni._host_check(source(),req,changed)


def add_and_execute(session,s):
    source_record=session.workbench.add_source({"kind":ni.KIND,"label":"Test double","bytes_b64":base64.b64encode(canonical(s)).decode()})
    return session.workbench.execute({"operation_id":ni.OPERATION,"source_id":source_record["source_id"]})


def test_shared_save_reopen_replay_and_inspection(mock_provider,tmp_path,monkeypatch):
    session=Session(make_demo_run(),tmp_path/"first")
    session.workbench.bind_workflow(ni.KIND,{"runtime":tmp_path/"operator-binding.json"})
    original=add_and_execute(session,source())
    session.workbench.replay({"bundle_id":original["bundle_id"]})
    workspace=tmp_path/"workspace.json";session.save_workspace(workspace)
    before=mock_provider[0]
    def forbidden(*a,**kw):raise AssertionError("reopen attempted provider/reference")
    monkeypatch.setattr(ni,"_invoke",forbidden);monkeypatch.setattr(nc,"check_output",forbidden)
    reopened=Session.from_workspace(workspace,tmp_path/"reopened")
    assert len(reopened.workbench.list_bundles())==2
    assert mock_provider[0]==before
    view=reopened.workbench.inspect_experiment({"bundle_id":original["bundle_id"]})
    assert view["object_context"]["sp1_verification"]=="not_performed"


def test_force_link_requires_exact_retained_trajectory(mock_provider,tmp_path):
    session=Session(make_demo_run(),tmp_path/"first")
    session.workbench.bind_workflow(ni.KIND,{"runtime":tmp_path/"binding.json"})
    payload={"model":{"mass_kg":2,"omega_0_rad_s":2,"gamma_s_inv":0.1},"initial_state":{"q0_m":1,"v0_m_s":-0.25},"time_s":[0,0.25,0.5]}
    s=nc.make_source("control-oscillator.v1","julia",payload)
    summary=add_and_execute(session,s);b=session.workbench.get_bundle(summary["bundle_id"])
    step=b["steps"][0];out=step["result"]["data"]["output"]
    force=nc.make_source("oscillator-force-energy.v1","cpp",{"model":payload["model"],**{k:out[k] for k in ("time_s","q_m","v_m_s")}},
                         upstream={"bundle_digest":b["bundle_digest"],"result_id":step["result_id"]})
    result=add_and_execute(session,force)
    assert result["kind"]==ni.KIND
    force["payload"]["q_m"][1]+=1
    before=mock_provider[0]
    with pytest.raises(ValueError,match="differs"):add_and_execute(session,force)
    assert mock_provider[0]==before
@pytest.mark.parametrize("mutation",["handshake_binary","native_runtime","child_on_cpp","extra_response_field"])
def test_transport_runtime_substitutions_are_rejected(mock_provider,mutation):
    w=ni.NativeInteropWorkflow();b=w.create_session(canonical(source()),{})
    step=b["steps"][0];t=step["transport"]
    response=ni._json(ni._unblob(t["response"]))
    if mutation=="handshake_binary":
        reply=ni._json(ni._unblob(t["handshake_response"]))
        reply["identity"]["host_executable_sha256"]="sha256:"+"f"*64
        t["handshake_response"]=ni._blob(canonical(reply))
    elif mutation=="native_runtime":
        b["runtimes"]["scr"]["host_sha256"]="sha256:"+"f"*64
    elif mutation=="child_on_cpp": response["host"]["child_process_id"]=3
    else: response["authorized"]=True
    t["response"]=ni._blob(canonical(response))
    b["bundle_digest"]=_bundle_digest(b)
    with pytest.raises(ValueError):w._validate(b)


def test_occurrence_diagnostics_are_not_numerical_identity():
    s=nc.make_source("control-oscillator.v1","julia",{"model":{"mass_kg":2,"omega_0_rad_s":2,"gamma_s_inv":0.1},"initial_state":{"q0_m":1,"v0_m_s":-0.25},"time_s":[0,0.25,0.5]})
    a={"q_m":[1],"request_id":"first","solver":{"solve_seconds":1,"version":"pinned"}}
    b={"q_m":[1],"request_id":"second","solver":{"solve_seconds":2,"version":"pinned"}}
    assert digest(a)!=digest(b)
    assert ni._numeric(s,a)==ni._numeric(s,b)
