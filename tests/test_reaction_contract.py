"""Independent reaction reference and rejection cases; no provider substitutes."""
from copy import deepcopy
import math

import pytest

from ciw import reaction_contract as rc, native_interop_contract as nc
from ciw.telemetry import byte_digest, canonical


def payload():
    return {"model":rc.MODEL,"species_order":["A","B"],"initial_concentration_mol_m3":[2.0,0.5],
            "rate_constant_s_inv":0.5,"temperature_k":300.0,"volume_m3":0.001,
            "time_s":[0.0,0.03,0.4,1.0,3.0],
            "solver":{"reltol":1e-9,"abstol_mol_m3":1e-11,"max_steps":100000}}


def reference_data(p=None, provider="catalyst"):
    p = payload() if p is None else p
    data = rc.reference(p)
    raw = b"EXPLICIT ANALYTIC TEST FIXTURE, not an engine result"
    data["mechanism"] = {"format":"catalyst-code-v1" if provider=="catalyst" else "cantera-yaml-v1",
                         "bytes_hex":raw.hex(),"sha256":byte_digest(raw)}
    data["solver"]={"algorithm":"Catalyst.Tsit5" if provider=="catalyst" else "Cantera.CVODES","retcode":"Success",**p["solver"]}
    return data


def test_source_roundtrip_and_contract_identity():
    for provider in ("catalyst","cantera"):
        s=nc.make_source(rc.PROFILE,provider,payload())
        assert nc.source(canonical(s))==s
        assert s["semantics"]==rc.SEMANTICS
        assert nc.check_output(s,reference_data(provider=provider))["method"]==rc.METHOD


@pytest.mark.parametrize("a,b,k", [(2,.5,.5),(0,2,2),(2,0,0),(1e-6,0,0.1),(0.25,999.75,1)])
def test_exact_reference_and_complementary_invariants(a,b,k):
    p=payload();p["initial_concentration_mol_m3"]=[a,b];p["rate_constant_s_inv"]=k
    data=reference_data(p);check=rc.check_output(nc.make_source(rc.PROFILE,"catalyst",p),data)
    assert check["metrics"]["conservation_max_abs_mol_m3"]<=2e-13
    assert check["metrics"]["minimum_concentration_mol_m3"]>=0
    assert data["concentration_mol_m3"][0]==[a,b]
    for t,row in zip(p["time_s"], data["concentration_mol_m3"]):
        assert row[0]==a*math.exp(-k*t)
        assert sum(row)==pytest.approx(a+b)


def test_species_permutation_is_lossless_not_a_new_mechanism():
    p=payload();q=deepcopy(p)
    q["species_order"].reverse();q["initial_concentration_mol_m3"].reverse()
    a,b=rc.reference(p),rc.reference(q)
    for key in ("concentration_mol_m3","production_rate_mol_m3_s"):
        assert a[key]==[row[::-1] for row in b[key]]
    assert nc.make_source(rc.PROFILE,"catalyst",p)!=nc.make_source(rc.PROFILE,"catalyst",q)


def test_conservation_cannot_pass_a_wrong_rate_trajectory():
    p=payload();wrong=deepcopy(p);wrong["rate_constant_s_inv"]*=2
    bad=reference_data(wrong)
    assert all(sum(row)==pytest.approx(2.5) for row in bad["concentration_mol_m3"])
    with pytest.raises(ValueError,match="reference"):
        rc.check_output(nc.make_source(rc.PROFILE,"catalyst",p),bad)


def test_exact_trajectory_cannot_hide_wrong_production_rate():
    p=payload();bad=reference_data(p);bad["production_rate_mol_m3_s"][2]=[0,0]
    with pytest.raises(ValueError,match="reference"):
        rc.check_output(nc.make_source(rc.PROFILE,"catalyst",p),bad)


@pytest.mark.parametrize("field,value", [
    ("model","A-to-C"),("species_order",["A","A"]),("species_order",["A","C"]),
    ("initial_concentration_mol_m3",[0,0]),("initial_concentration_mol_m3",[-1,2]),
    ("initial_concentration_mol_m3",[True,1]),("initial_concentration_mol_m3",[1001,0]),
    ("rate_constant_s_inv",-1),("rate_constant_s_inv",float("nan")),("rate_constant_s_inv",True),
    ("temperature_k",100),("volume_m3",0),("time_s",[0,0]),("time_s",[1,2]),
    ("time_s",[0,float("inf")]),("time_s",[0,100]),("time_s",[0]),
    ("solver",{"reltol":1e-9,"abstol_mol_m3":1e-11,"max_steps":True}),
    ("solver",{"reltol":1e-6,"abstol_mol_m3":1e-11,"max_steps":100}),
])
def test_invalid_domain_refused(field,value):
    p=payload();p[field]=value
    with pytest.raises(ValueError): nc.make_source(rc.PROFILE,"catalyst",p)


@pytest.mark.parametrize("mutation", ["units","unknown_payload","unknown_source","provider","arithmetic"])
def test_source_contract_not_reinterpreted(mutation):
    s=nc.make_source(rc.PROFILE,"catalyst",payload())
    if mutation=="units": s["semantics"]["concentration_unit"]="kmol/m^3"
    elif mutation=="unknown_payload":s["payload"]["code"]="exit()"
    elif mutation=="unknown_source":s["extra"]=True
    elif mutation=="provider":s["provider"]="julia"
    else:s["arithmetic"]="binary32"
    with pytest.raises(ValueError):nc.source(canonical(s))


@pytest.mark.parametrize("mutation", ["sample_count","shape","nan","solver","digest","grid","order"])
def test_structural_output_rejection(mutation):
    s=nc.make_source(rc.PROFILE,"catalyst",payload());d=reference_data()
    if mutation=="sample_count":d["concentration_mol_m3"].pop()
    elif mutation=="shape":d["production_rate_mol_m3_s"][0].pop()
    elif mutation=="nan":d["concentration_mol_m3"][0][0]=float("nan")
    elif mutation=="solver":d["solver"]["retcode"]="MaxIters"
    elif mutation=="digest":d["mechanism"]["bytes_hex"]="00"
    elif mutation=="grid":d["time_s"][1]+=0.1
    else:d["species_order"].reverse()
    with pytest.raises(ValueError):rc.validate_output(s,d)


def test_offline_shape_check_does_not_recompute_reference(monkeypatch):
    d=reference_data();s=nc.make_source(rc.PROFILE,"catalyst",payload())
    def forbidden(*a):raise AssertionError("offline inspection executed a reference")
    monkeypatch.setattr(rc,"reference",forbidden)
    assert nc.validate_output(s,d)==d

@pytest.mark.parametrize("changed",["file","executable","package","revision","source_tree"])
def test_qualification_rejects_mixed_closures(monkeypatch,changed):
    from ciw import reaction_runtime as rr, native_interop as ni
    # Qualification-binding unit fixture only; never used as numerical evidence.
    pin={"files":{path:"sha256:"+"a"*64 for path in rr.FILES["catalyst"]},
         "executable_sha256":"sha256:"+"b"*64,"worker_identity":{"fixture":"not a provider"},"scr_revisions":["c"*40],"scr_trees":{"c"*40:"e"*40}}
    monkeypatch.setattr(ni,"_pins",lambda:{"reaction_families":{"catalyst":pin}})
    runtime={"julia":None,"revision":"c"*40,"source_tree":"e"*40,"reaction":{"provider":"catalyst","files":deepcopy(pin["files"]),
             "executable_sha256":pin["executable_sha256"],"worker_identity":deepcopy(pin["worker_identity"]),
             "environment_attestation":"not_established"}}
    rr.validate_runtime(runtime,"catalyst")
    if changed=="file":runtime["reaction"]["files"][rr.FILES["catalyst"][0]]="sha256:"+"d"*64
    elif changed=="executable":runtime["reaction"]["executable_sha256"]="sha256:"+"d"*64
    elif changed=="package":runtime["reaction"]["worker_identity"]["unqualified"]="1"
    elif changed=="source_tree":runtime["source_tree"]="f"*40
    else:runtime["revision"]="d"*40
    with pytest.raises(ValueError):rr.validate_runtime(runtime,"catalyst")
