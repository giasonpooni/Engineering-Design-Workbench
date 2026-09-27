"""Proof planning tests never pretend to verify a cryptographic proof."""
from copy import deepcopy
import pytest
from ciw.proof_obligations import obligation, validate_obligation, compose_exact
from ciw.telemetry import digest


def subject(): return obligation("example.predicate.v1",b"program",b"input",b"intermediate")
def nodes():
    return [{"node_id":"a","obligation":subject()},
            {"node_id":"b","obligation":obligation("next.v1",b"next",b"intermediate",b"output")}]
def edges(): return [{"source":"a","target":"b","mapping":"identity-bytes.v1"}]


def test_explicit_claims_and_unbound_guest_nodes():
    first=subject(); assert validate_obligation(first)==first
    assert first["status"]=="obligation_only_not_verified"
    result=compose_exact(nodes(),edges(),["a"])
    assert result["unbound_guest_nodes"]==["a","b"]
    assert result["recursive_aggregation"]=="not_performed"
    assert result["cryptographic_verification"]=="not_performed"


@pytest.mark.parametrize("field,value",[("exit_code",True),("status","verified"),("disclosure","zero_knowledge"),
    ("public_values_convention","other"),("input_identity","0"*64),("output_identity","0"*64),
    ("specification_identity","0"*64),("guest_sha256","mock"),("expected_output","FF")])
def test_resealed_authority_or_statement_mutations_refuse(field,value):
    value_ = subject();value_[field]=value
    value_["obligation_id"]=digest({k:v for k,v in value_.items() if k!="obligation_id"})
    with pytest.raises(ValueError): validate_obligation(value_)


def test_native_configuration_cannot_be_claimed_as_proved():
    value=subject();value["specification"]["configuration"]="01"
    with pytest.raises(ValueError,match="configuration"): validate_obligation(value)


def test_metadata_is_explicitly_unproved_and_copied():
    context={"unit":"m","calibration":{"identity":"declared"}}
    value=obligation("example.v1",b"program",b"input",b"output",unproved_context=context)
    context["calibration"]["identity"]="changed"
    assert value["unproved_context"]["calibration"]["identity"]=="declared"
    assert value["status"]=="obligation_only_not_verified"


@pytest.mark.parametrize("mutation",["missing","duplicate","misordered","self","mapping","input","roots","root-duplicate","node-duplicate","cycle"])
def test_composition_rejects_unchecked_handoffs(mutation):
    ns,es,rs=nodes(),edges(),["a"]
    if mutation=="missing":es[0]["source"]="missing"
    if mutation=="duplicate":es.append(deepcopy(es[0]))
    if mutation=="misordered":ns.reverse()
    if mutation=="self":es[0]["source"]="b"
    if mutation=="mapping":es[0]["mapping"]="convert-by-prose"
    if mutation=="input":ns[1]["obligation"]=obligation("next.v1",b"next",b"changed",b"output")
    if mutation=="roots":rs=[]
    if mutation=="root-duplicate":rs=["a","a"]
    if mutation=="node-duplicate":ns.append(deepcopy(ns[0]))
    if mutation=="cycle":es.append({"source":"b","target":"a","mapping":"identity-bytes.v1"})
    with pytest.raises(ValueError):compose_exact(ns,es,rs)


def test_known_guest_hash_does_not_create_proof_authority():
    value=obligation("example.v1",b"program",b"input",b"output",guest_sha256="sha256:"+"a"*64)
    plan=compose_exact([{"node_id":"a","obligation":value}],[],["a"])
    assert plan["unbound_guest_nodes"]==[]
    assert plan["status"]=="plan_only_not_verified"


def test_plan_and_returned_obligation_are_detached():
    ns=nodes();result=compose_exact(ns,edges(),["a"])
    ns[0]["obligation"]["unproved_context"]["x"]="changed"
    assert not result["nodes"][0]["obligation"]["unproved_context"]
    assert result["plan_id"]==digest({k:v for k,v in result.items() if k!="plan_id"})
