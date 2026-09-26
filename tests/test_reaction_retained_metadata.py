"""Synthetic retained metadata tests; these do not qualify a native provider."""
from copy import deepcopy
import math

import pytest

from ciw import native_interop as ni, native_interop_contract as nc
from ciw import reaction_contract as rc
from ciw.telemetry import byte_digest, canonical, digest
from test_reaction_contract import payload, reference_data


def _forbidden(*args, **kwargs):
    raise AssertionError("Retained metadata inspection must not execute a provider or oracle")


def _reseal(step):
    result = step["result"]
    result["result_id"] = digest({k: v for k, v in result.items() if k != "result_id"})
    step["result_id"] = result["result_id"]
    step["result_sha256"] = digest(result)


@pytest.fixture(params=["catalyst", "cantera"])
def retained_step(request, monkeypatch):
    """Isolate metadata validation from separately tested runtime qualification."""
    source = nc.make_source(rc.PROFILE, request.param, payload())
    evidence = byte_digest(canonical(source))
    output = reference_data(provider=request.param)

    def synthetic_transport(source, bindings, runtime, execution):
        sent = {
            "schema": ni.REQUEST_SCHEMA,
            "request_id": "request-" + "1" * 32,
            "parent_execution_id": execution,
            **{k: deepcopy(source[k]) for k in ("profile", "arithmetic", "semantics", "payload")},
        }
        response = {
            "schema": ni.RESPONSE_SCHEMA, "request_id": sent["request_id"],
            "parent_execution_id": execution, "profile": source["profile"],
            "status": "ok", "data": deepcopy(output),
        }
        hello = {"schema": "ciw.native-interop-handshake-request.v1", "request_id": "synthetic-metadata-test"}
        reply = {"schema": "ciw.native-interop-handshake-response.v1", "request_id": hello["request_id"], "status": "ok"}
        return {
            "handshake_request": ni._blob(canonical(hello)),
            "handshake_response": ni._blob(canonical(reply)),
            "request": ni._blob(canonical(sent)), "response": ni._blob(canonical(response)),
            "stderr": ni._blob(b""), "process_seconds": 0.0,
        }

    # This unit fixture deliberately makes no host or runtime identity claim.
    monkeypatch.setattr(ni, "_host_check", lambda *args: None)
    monkeypatch.setattr(ni, "_runtime_link", lambda *args: None)
    monkeypatch.setattr(ni, "_invoke", synthetic_transport)
    workflow = ni.NativeInteropWorkflow()
    step = workflow._step(source, evidence, ({}, {}))
    for module, name in ((ni, "_invoke"), (ni, "_runtime"), (nc, "check_output"),
                         (rc, "check_output"), (rc, "reference")):
        monkeypatch.setattr(module, name, _forbidden)
    return workflow, step, source, evidence


def test_retained_matching_metadata_is_provider_free(retained_step):
    workflow, step, source, evidence = retained_step
    check = step["result"]["data"]["reference_check"]
    assert check["max_abs_discrepancy"] == check["metrics"]["trajectory_max_abs_mol_m3"]
    assert workflow._validate_step(step, source, evidence, {}) is None


@pytest.mark.parametrize("changed_field", ["scalar", "trajectory_metric", "one_ulp"])
def test_resealed_contradictory_trajectory_metadata_is_refused(retained_step, changed_field):
    workflow, step, source, evidence = retained_step
    check = step["result"]["data"]["reference_check"]
    if changed_field == "scalar":
        check["max_abs_discrepancy"] = 0.125
    elif changed_field == "trajectory_metric":
        check["metrics"]["trajectory_max_abs_mol_m3"] = 0.125
    else:
        check["max_abs_discrepancy"] = 0.125
        check["metrics"]["trajectory_max_abs_mol_m3"] = math.nextafter(0.125, math.inf)
    _reseal(step)
    with pytest.raises(ValueError):
        workflow._validate_step(step, source, evidence, {})


def test_coherent_retained_metrics_are_not_freshly_recomputed(retained_step):
    workflow, step, source, evidence = retained_step
    check = step["result"]["data"]["reference_check"]
    # Coherent fabrication stays structural evidence, not authenticated science.
    # Rate and conservation discrepancies remain separate quantities.
    check["max_abs_discrepancy"] = 1e-12
    check["metrics"]["trajectory_max_abs_mol_m3"] = 1e-12
    check["metrics"]["rate_law_max_abs_mol_m3_s"] = 2e-12
    check["metrics"]["conservation_max_abs_mol_m3"] = 3e-12
    _reseal(step)
    assert workflow._validate_step(step, source, evidence, {}) is None
