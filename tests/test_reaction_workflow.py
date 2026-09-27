"""Live retained workflow gates. No fake engine qualifies a provider here."""
from copy import deepcopy
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw import native_interop as ni, native_interop_contract as nc, reaction_contract as rc
from ciw.adapters.oscillator import make_demo_run
from ciw.session import Session
from ciw.telemetry import canonical, _bundle_digest
from test_reaction_contract import payload


@pytest.fixture(scope="module",params=["catalyst","cantera"])
def live(request):
    provider=request.param
    path=os.environ.get("CIW_REACTION_"+provider.upper()+"_BINDING")
    if not path:pytest.skip("requires qualified "+provider+" binding")
    workflow=ni.NativeInteropWorkflow()
    binding={"runtime":Path(path)}
    source=nc.make_source(rc.PROFILE,provider,payload())
    bundle=workflow.create_session(canonical(source),binding)
    return provider,workflow,binding,source,bundle


def test_live_reference_and_occurrence_separation(live):
    provider,w,b,s,bundle=live
    first,second=bundle["steps"][0],bundle["verification"]["reproduction"]
    assert first["execution_id"]!=second["execution_id"]
    assert first["result_id"]!=second["result_id"]
    assert first["result"]["data"]["reference_check"]["method"]==rc.METHOD
    assert first["result"]["data"]["authority"]==nc.AUTHORITY
    assert w._validate(bundle)==canonical(s)


def test_live_offline_inspection_never_calls_runtime_or_reference(live):
    _,w,b,s,bundle=live
    def no(*a,**kw):raise AssertionError("offline evaluation")
    with patch.object(ni,"_runtime",no),patch.object(ni,"_invoke",no),patch.object(nc,"check_output",no),patch.object(rc,"reference",no):
        assert w._validate(bundle)==canonical(s)


@pytest.mark.parametrize("mutation",["mechanism","worker_identity","provider","uncertainty","result_occurrence","reference_scope"])
def test_live_corrupt_retained_bindings_are_rejected(live,mutation):
    _,w,b,s,original=live
    bundle=deepcopy(original);step=bundle["steps"][0]
    if mutation=="mechanism":step["result"]["data"]["output"]["mechanism"]["sha256"]="sha256:"+"f"*64
    elif mutation=="worker_identity":bundle["runtimes"]["scr"]["reaction"]["worker_identity"]["packages"]["invented"]="1"
    elif mutation=="provider":bundle["runtimes"]["scr"]["reaction"]["provider"]="julia"
    elif mutation=="uncertainty":step["result"]["data"]["authority"]["measurement_uncertainty"]="established"
    elif mutation=="result_occurrence":step["result"]["execution_ref"]=bundle["verification"]["reproduction"]["execution_id"]
    else:step["result"]["data"]["reference_check"]["method"]="physical_validation"
    bundle["bundle_digest"]=_bundle_digest(bundle)
    with pytest.raises(ValueError):w._validate(bundle)


def test_live_replay_requires_exact_binding_and_new_occurrences(live):
    _,w,b,s,bundle=live
    result=w.replay_session(bundle,b)
    fresh=result["session"]
    assert fresh["steps"][0]["execution_id"]!=bundle["steps"][0]["execution_id"]
    assert fresh["steps"][0]["result_id"]!=bundle["steps"][0]["result_id"]
    assert result["replay_receipt"]["admission"]=="not_performed"
    with pytest.raises(ValueError):w._adapters(b,{"scr":{}})
