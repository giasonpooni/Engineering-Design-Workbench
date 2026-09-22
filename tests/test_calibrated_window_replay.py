"""SET checks binding; fresh CIW/ICRH gates own the scientific composition."""
import base64
from copy import deepcopy

import pytest

from state_estimation_testbed import ContractError, canonical_bytes, content_digest, verify_replay_bundle
from test_replay import composite_bundle, runtime, step, seal, replay, reseal_step


def window_bundle():
    value = composite_bundle()
    source = {"schema": "ciw.calibrated-window-source.v1", "experiment_id": "window:fixture",
              "configuration": {"window": {"start": 0, "end": 2}}}
    raw = canonical_bytes(source)
    ref = content_digest(source)
    value.update(schema="ciw.calibrated-window-session.v1", configuration=source["configuration"],
                 source={"experiment_id": source["experiment_id"], "experiment_digest": content_digest(source),
                         "evidence": [{"artifact_ref": ref, "sha256": ref,
                                       "bytes_b64": base64.b64encode(raw).decode()}]},
                 runtimes={role: runtime() for role in ("tbrt", "mcur", "stfe", "gsie", "set")})
    gsie = value["steps"][1]
    value["steps"] = []
    for role, operation in [("tbrt", "ciw.tbrt-window.v1"), ("mcur", "ciw.mcur-window.v1"), ("stfe", "stfe.window-mean.v1")]:
        inputs = ([ref] if role == "tbrt" else [ref, value["steps"][0]["result_id"]] if role == "mcur"
                  else [s["result_id"] for s in value["steps"]])
        result = {"schema": "ciw.calibrated-operation-result.v1", "operation_id": operation,
                  "execution_ref": "execution:" + role, "input_refs": inputs, "data": {"fixture": role}}
        result["result_id"] = content_digest(result)
        item = step(role, operation, result["execution_ref"], inputs, result,
                    {"operation_id": operation, "data": result["data"]})
        value["steps"].append(item)
    value["steps"][0]["request"] = {"source": source}
    gsie["input_refs"] = [value["steps"][-1]["result_id"]]
    value["steps"].append(gsie)
    return reseal_step(value)


def test_window_binding_requires_reexecution_and_keeps_authority_bounded():
    value = window_bundle()
    assert verify_replay_bundle(value)["outcome"] == "indeterminate"
    receipt = verify_replay_bundle(value, replay_results=replay(value))
    assert receipt["outcome"] == "passed"
    assert receipt["independent"] is False
    changed = replay(value)
    changed[value["steps"][1]["execution_id"]] = {"different": 1}
    assert verify_replay_bundle(value, replay_results=changed)["outcome"] == "failed"


@pytest.mark.parametrize("attack", ["source", "configuration", "graph", "role", "runtime", "missing"])
def test_resealed_window_cannot_substitute_source_or_graph(attack):
    value = window_bundle()
    if attack == "source":
        value["steps"][0]["request"]["source"] = {"schema": "other"}
    elif attack == "configuration":
        value["configuration"] = {"window": "different"}
    elif attack == "graph":
        value["steps"][2]["input_refs"] = [value["steps"][1]["result_id"]]
    elif attack == "role":
        value["steps"][1]["runtime_ref"] = "tbrt"
    elif attack == "runtime":
        value["runtimes"]["extra"] = runtime()
    else:
        value["steps"].pop()
    with pytest.raises(ContractError):
        verify_replay_bundle(reseal_step(value), replay_results=replay(value))
