from copy import deepcopy
import json
import math
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry, run_graph
from ciw.core.identities import content_identity
from ciw.instruments import make_demo_run
from ciw.representation_morphisms import (
    registry_from_specs,
    representation_from_spec,
    witness_from_spec,
)
from ciw.semantic_capabilities import builtin_semantic_registry, compile_graph
from ciw.session import Session


def scale(label):
    return {"length_m":None,"time_s":None,"energy_j":None,"resolution":None,"label":label}


def representation_specs():
    return [
        {
            "representation_id":"signal.timeseries.uniform-scalar.v1",
            "role":"SIGNAL",
            "source_state_type":"retained-recording-channel",
            "schema_id":"ciw.run-channel.v1",
            "quantity_semantics":"finite uniformly sampled scalar physical channel",
            "unit_semantics":"source-channel-unit",
            "frame_semantics":"source-recording-coordinate-frame",
            "time_semantics":"source-declared uniform sample clock over half-open intervals",
            "scale":scale("source-declared sampling scale"),
            "uncertainty_semantics":"source-declared-or-none",
            "equivalence_contract":"EXACT",
            "preserved_queries":["retained-sample-values","sample-count","sample-rate"],
            "supported_interventions":["select-channel-and-half-open-interval"],
            "recovery_route":"retained source recording",
            "provenance_refs":[],
            "notes":"Representation of retained source signal, not canonical state.",
        },
        {
            "representation_id":"signal.periodogram.one-sided-density.v1",
            "role":"SPECTRAL",
            "source_state_type":"derived-spectral-result",
            "schema_id":"ciw.periodogram-data.v1",
            "quantity_semantics":"one-sided power spectral density",
            "unit_semantics":"(source-channel-unit)^2/Hz",
            "frame_semantics":"frequency axis derived from source sample rate",
            "time_semantics":"summary of one selected half-open source interval",
            "scale":scale("frequency-domain projection"),
            "uncertainty_semantics":"no uncertainty model declared by provider",
            "equivalence_contract":"TASK_SPECIFIC",
            "preserved_queries":["one-sided-periodogram-density","peak-frequency","frequency-grid"],
            "supported_interventions":[],
            "recovery_route":"retained source recording required for time-domain intervention",
            "provenance_refs":[],
            "notes":"Lossy spectral representation; phase and time-local structure are not retained.",
        },
    ]


def morphism_specs():
    return [{
        "morphism_id":"signal.periodogram.transform.v1",
        "kind":"TRANSFORM",
        "domain_representation_id":"signal.timeseries.uniform-scalar.v1",
        "codomain_representation_id":"signal.periodogram.one-sided-density.v1",
        "semantic_capability":"analysis.spectrum.v1",
        "parameter_names":["channel","interval_s"],
        "preconditions":[
            "source recording validates completely",
            "selected interval contains at least four retained samples",
            "selected channel is finite and uniformly sampled",
        ],
        "validity":{
            "assumptions":["periodic Hann window","constant detrending","one-sided density normalization"],
            "operating_regime":["finite float64 result range","source sample rate is finite and positive"],
            "failure_conditions":["fewer than four samples","nonfinite source data","nonfinite PSD result"],
        },
        "preservation":{
            "queries":["one-sided-periodogram-density","peak-frequency","frequency-grid"],
            "interventions":[],
            "invariants":[
                "source evidence identity remains retained",
                "output sample_count equals selected source sample count",
                "frequency grid derives from retained sample rate",
            ],
            "approximation_tolerance":None,
        },
        "loss":{
            "class":"LOSSY",
            "description":"Periodogram does not retain phase or time-local source ordering sufficient for arbitrary time-domain reconstruction/intervention.",
            "metrics":{"phase_retained":False,"time_locality_retained":False},
        },
        "uncertainty":{"behavior":"UNKNOWN","method":None},
        "reversibility":"NONE",
        "authority_requirements":["read:recording"],
        "verification_requirements":[
            "source evidence identity retained",
            "provider runtime retained",
            "periodogram method/window/detrend/scaling match contract",
            "frequency and PSD arrays have equal finite length",
            "frequency grid is nondecreasing and starts at zero",
        ],
        "provenance_refs":[],
        "notes":"Finite provider executions are witnesses only.",
    }]


def registry():
    concrete=builtin_registry(bind=True)
    semantic=builtin_semantic_registry(concrete)
    return concrete,semantic,registry_from_specs(representation_specs(),morphism_specs(),semantic)


def test_representation_separates_queries_from_interventions():
    rep=representation_from_spec(representation_specs()[1])
    assert "peak-frequency" in rep["preserved_queries"]
    assert rep["supported_interventions"]==[]
    assert rep["equivalence_contract"]=="TASK_SPECIFIC"
    assert rep["claims"]["representation_not_canonical_state"] is True


def test_registry_links_to_existing_semantic_capability_without_engine_authority():
    _,semantic,value=registry()
    morphism=value["morphisms"]["signal.periodogram.transform.v1"]
    assert morphism["semantic_capability"]=="analysis.spectrum.v1"
    assert morphism["kind"]=="TRANSFORM"
    assert morphism["loss"]["class"]=="LOSSY"
    assert morphism["reversibility"]=="NONE"
    assert value["claims"]["selects_engine"] is False
    assert value["semantic_catalog_ref"]==semantic.catalog()["record_digest"]


def test_registry_refuses_unknown_representation_endpoint():
    concrete=builtin_registry(bind=True); semantic=builtin_semantic_registry(concrete)
    bad=deepcopy(morphism_specs()); bad[0]["codomain_representation_id"]="signal.missing.v1"
    with pytest.raises(ValueError,match="declared representations"):
        registry_from_specs(representation_specs(),bad,semantic)


def test_registry_refuses_unknown_semantic_capability():
    concrete=builtin_registry(bind=True); semantic=builtin_semantic_registry(concrete)
    bad=deepcopy(morphism_specs()); bad[0]["semantic_capability"]="analysis.missing.v1"
    with pytest.raises(ValueError,match="not declared"):
        registry_from_specs(representation_specs(),bad,semantic)


def execute_real_periodogram(tmp_path):
    concrete,semantic,registry_value=registry()
    graph={
        "schema":"ciw.semantic-work-graph.v1",
        "graph_id":"morphism-periodogram-witness",
        "mandate":"Generate retained q-channel periodogram witness.",
        "model_id":"analytic-damped-oscillator.v1",
        "nodes":[{
            "node_id":"spectrum","capability":"analysis.spectrum.v1",
            "parameters":{"channel":"q","interval_s":[0.0,12.0]},
            "inputs":{},"depends_on":[],"resources":["cpu"],"acceptance":{},"inspection":False,
        }],
    }
    compilation=compile_graph(graph,semantic)
    source=make_demo_run()
    session=Session(source,tmp_path/"session",operations=concrete.operations)
    run=run_graph(session,compilation["experiment"],concrete)
    assert run["status"]=="completed"
    payload=run["nodes"]["spectrum"]; result=payload["result"]; data=result["data"]
    return source,run,result,data,semantic,registry_value


def test_real_periodogram_execution_satisfies_declared_finite_checks(tmp_path):
    source,run,result,data,semantic,registry_value=execute_real_periodogram(tmp_path)
    assert data["method"]=="periodogram"
    assert data["window"]=="hann"
    assert data["detrend"]=="constant"
    assert data["scaling"]=="density"
    assert data["sample_count"]==source["metadata"]["sample_count"]
    assert len(data["frequency_hz"])==len(data["psd"])
    assert data["frequency_hz"][0]==0.0
    assert all(b>=a for a,b in zip(data["frequency_hz"],data["frequency_hz"][1:]))
    assert all(math.isfinite(v) for v in data["psd"])
    assert data["unit"]=="(m)^2/Hz"

    execution_ref=content_identity(run["nodes"]["spectrum"]["execution"])
    result_ref=content_identity(result)
    data_ref=content_identity(data)
    witness=witness_from_spec(registry_value,semantic,{
        "witness_id":"oscillator-q-periodogram-witness",
        "morphism_id":"signal.periodogram.transform.v1",
        "source_evidence_id":source["evidence_id"],
        "execution_ref":execution_ref,
        "result_ref":result_ref,
        "checks":[
            {"check_id":"source-retained","kind":"PROVENANCE","status":"PASS","evidence_ref":source["evidence_id"],"notes":"Source evidence retained."},
            {"check_id":"periodogram-contract","kind":"CODOMAIN","status":"PASS","evidence_ref":data_ref,"notes":"Method/window/detrend/scaling and unit match."},
            {"check_id":"frequency-grid","kind":"PRESERVATION","status":"PASS","evidence_ref":data_ref,"notes":"Finite aligned frequency/PSD arrays starting at zero."},
            {"check_id":"physical-validation","kind":"VALIDITY","status":"UNRESOLVED","evidence_ref":None,"notes":"Synthetic oscillator is not empirical validation."},
        ],
        "notes":"Finite synthetic execution witness only.",
    })
    assert witness["claims"]["general_morphism_law_proved"] is False
    assert witness["claims"]["physical_validity_established"] is False
    assert sum(row["status"]=="PASS" for row in witness["checks"])==3
    assert sum(row["status"]=="UNRESOLVED" for row in witness["checks"])==1


def test_cli_creates_registry_and_inspects(tmp_path):
    spec_path=tmp_path/"registry-spec.json"; registry_path=tmp_path/"registry.json"
    spec_path.write_text(json.dumps({"representations":representation_specs(),"morphisms":morphism_specs()}))
    subprocess.run([sys.executable,"-m","ciw.net","morphism","create-registry",str(spec_path),"--output",str(registry_path)],cwd=tmp_path,check=True)
    result=json.loads(subprocess.check_output([sys.executable,"-m","ciw.net","morphism","inspect",str(registry_path)],cwd=tmp_path,text=True))
    assert result["representations"]==2
    assert result["morphisms"]==1
    assert result["semantic_capabilities"]==["analysis.spectrum.v1"]
    assert result["selects_engine"] is False
