from copy import deepcopy
from hashlib import sha256
import json

import pytest

from ywir import (
    Proposal, Settlement, YwirRefuse, evaluate_token_admission, open_host,
    replay_token_admission, settle, snapshot,
)


def request(**changes):
    payload = {
        "schema": "ywir.observation-design-token-request.v1",
        "selection_content_id": "edspt:selection:" + "a" * 64,
        "selected_candidate_id": "tank-2-pressure",
        "budget_unit": "inference_token",
        "department": "exploration",
        "token_budget": 100,
        "requested_tokens": 16,
        "yield_claim": {"expected_rank_delta": 0, "expected_new_morphism": False},
        "eta_hat": 0.0,
        "similarity_to_store": 0.0,
    }
    payload.update(changes)
    return payload


def test_pure_advice_is_repeatable_bound_and_not_a_capability():
    payload = request()
    before = deepcopy(payload)
    first = evaluate_token_admission(payload)
    second = evaluate_token_admission(deepcopy(payload))
    assert payload == before
    assert first == second == replay_token_admission(payload, first)
    assert first["admitted"] is True
    assert first["advisory_token_cap"] == 16
    assert first["selection_content_id"] == payload["selection_content_id"]
    assert first["selected_candidate_id"] == payload["selected_candidate_id"]
    assert first["authority_scope"] == "advisory_only"
    assert not {"host_id", "decision_id", "reservation_id", "execution_id", "verification_id"} & first.keys()
    assert len({first[key] for key in ("request_content_id", "proposal_content_id", "result_content_id")}) == 3
    host = open_host("caller", {"exploration": 100})
    state = snapshot(host)
    with pytest.raises(YwirRefuse, match="reservation_required"):
        settle(host, Proposal("caller", "exploration", 16), Settlement(16, 0, True), reservation=first)
    assert snapshot(host) == state


@pytest.mark.parametrize("field,value", [
    ("selection_content_id", "edspt:selection:" + "b" * 64),
    ("selected_candidate_id", "tank-1-pressure"),
    ("token_budget", 101),
    ("requested_tokens", 17),
    ("yield_claim", {"expected_rank_delta": 1, "expected_new_morphism": False}),
])
def test_changed_selection_or_declaration_changes_bound_identities(field, value):
    baseline = evaluate_token_admission(request())
    changed_request = request(**{field: value})
    changed = evaluate_token_admission(changed_request)
    for name in ("request_content_id", "proposal_content_id", "result_content_id"):
        assert baseline[name] != changed[name]
    with pytest.raises(YwirRefuse, match="replay_mismatch"):
        replay_token_admission(changed_request, baseline)


@pytest.mark.parametrize("changes,code", [
    ({"token_budget": 0}, "BUDGET_CLOSED"),
    ({"token_budget": 15}, "DEPARTMENT_STARVED"),
    ({"department": "evidence"}, "RANK_FLAT"),
    ({"department": "gauge"}, "GAUGE_SPILL"),
    ({"similarity_to_store": 0.9}, "GAUGE_SPILL"),
    ({"department": "ledger", "eta_hat": -0.1,
      "yield_claim": {"expected_rank_delta": 1, "expected_new_morphism": False}}, "YIELD_BELOW_THRESHOLD"),
])
def test_existing_runtime_refusals_are_preserved(changes, code):
    payload = request(**changes)
    result = evaluate_token_admission(payload)
    assert result["admitted"] is False
    assert result["advisory_token_cap"] == 0
    assert result["support_code"] == code
    assert replay_token_admission(payload, result) == result


@pytest.mark.parametrize("field,value", [
    ("schema", "future.v2"),
    ("budget_unit", "USD"),
    ("budget_unit", "second"),
    ("department", "measurement"),
    ("selection_content_id", ""),
    ("selected_candidate_id", None),
    ("token_budget", True),
    ("token_budget", -1),
    ("token_budget", 1.0),
    ("token_budget", 10**400),
    ("requested_tokens", 0),
    ("requested_tokens", 4097),
    ("requested_tokens", 2.5),
    ("requested_tokens", False),
    ("eta_hat", float("nan")),
    ("eta_hat", True),
    ("similarity_to_store", float("inf")),
    ("similarity_to_store", -0.1),
    ("similarity_to_store", 1.1),
    ("yield_claim", {"expected_rank_delta": True, "expected_new_morphism": False}),
    ("yield_claim", {"expected_rank_delta": 1, "expected_new_morphism": 1}),
    ("yield_claim", {"expected_rank_delta": 1.5, "expected_new_morphism": False}),
])
def test_strict_requests_never_silently_convert_units_numbers_or_missing_selection(field, value):
    with pytest.raises(YwirRefuse):
        evaluate_token_admission(request(**{field: value}))


def test_unsupported_fields_and_omitted_declarations_are_refused():
    for name in request():
        payload = request()
        del payload[name]
        with pytest.raises(YwirRefuse, match="invalid_request"):
            evaluate_token_admission(payload)
    for extra in ({"sensor_cost": 5}, {"reservation_id": "forged"}, {"expected_uncertainty_reduction": 0.5}):
        with pytest.raises(YwirRefuse, match="invalid_request"):
            evaluate_token_admission(request(**extra))


def test_replay_reexecutes_even_when_forged_refusal_has_consistent_content_hash():
    payload = request(token_budget=1)
    result = evaluate_token_admission(payload)
    result.update(admitted=True, status="admitted", support_code="YIELD_ADMIT", advisory_token_cap=16)
    del result["result_content_id"]
    namespace = "ywir:token-admission"
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    result["result_content_id"] = namespace + ":" + sha256(namespace.encode() + b"\x00" + canonical).hexdigest()
    with pytest.raises(YwirRefuse, match="replay_mismatch"):
        replay_token_admission(payload, result)


def test_replay_refuses_boolean_integer_aliases_and_unexpected_authority():
    payload = request()
    for field, value in (("admitted", 1), ("reservation_id", "forged")):
        retained = evaluate_token_admission(payload)
        retained[field] = value
        with pytest.raises(YwirRefuse, match="replay_mismatch"):
            replay_token_admission(payload, retained)
