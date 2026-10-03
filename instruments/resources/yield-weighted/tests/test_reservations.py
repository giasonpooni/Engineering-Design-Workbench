from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from ywir import (
    CompositionStore, Morphism, Proposal, Settlement, YwirRefuse,
    cancel, decide, open_host, reserve, settle, snapshot,
)


def proposal(**changes):
    return replace(Proposal("loop-a", "ledger", 10, expected_rank_delta=1), **changes)


def outcome(**changes):
    return replace(Settlement(10, 1, True), **changes)


def host(budget=100):
    return open_host("loop-a", {"ledger": budget})


def test_decision_is_advisory_and_cannot_be_settled_without_reservation():
    h, p = host(), proposal()
    before = snapshot(h)
    first, second = decide(h, p), decide(h, p)
    assert first.admitted and second.admitted
    assert snapshot(h) == before
    assert first.proposal_id == second.proposal_id
    assert first.decision_id != second.decision_id
    assert first.receipt(h.loop).decision_id == first.decision_id
    with pytest.raises(YwirRefuse, match="reservation_required"):
        settle(h, p, outcome())
    with pytest.raises(YwirRefuse, match="loop_mismatch"):
        first.receipt("other-loop")
    assert snapshot(h) == before


def test_reserve_and_partial_settlement_have_distinct_bound_identities():
    h, p = host(), proposal()
    r1, r2 = reserve(h, p), reserve(h, p)
    assert r1.reservation_id != r2.reservation_id
    assert r1.decision_id != r2.decision_id
    assert r1.proposal_id == r2.proposal_id
    assert snapshot(h)["budget"]["ledger"] == 100
    assert snapshot(h)["reserved"]["ledger"] == 20
    assert snapshot(h)["available"]["ledger"] == 80
    record = settle(h, p, outcome(tokens_spent=7), reservation=r1)
    assert record.reservation_id == r1.reservation_id
    assert record.decision_id == r1.decision_id
    assert record.base == r1.base
    assert record.reserved_tokens == 10
    assert len({record.settlement_id, record.proposal_id, record.decision_id, record.reservation_id, record.host_id}) == 5
    assert snapshot(h)["budget"]["ledger"] == 93
    assert snapshot(h)["reserved"]["ledger"] == 10
    assert snapshot(h)["available"]["ledger"] == 83


@pytest.mark.parametrize("retry_spend", [10, 0, 5])
def test_replayed_or_changed_settlement_cannot_spend_again(retry_spend):
    h, p = host(), proposal()
    r = reserve(h, p)
    settle(h, p, outcome(), reservation=r)
    after = snapshot(h)
    with pytest.raises(YwirRefuse, match="reservation_consumed"):
        settle(h, p, outcome(tokens_spent=retry_spend), reservation=r)
    assert snapshot(h) == after


@pytest.mark.parametrize("other_loop", ["loop-a", "loop-b"])
def test_foreign_host_and_reopened_host_cannot_replay_reservation(other_loop):
    original, p = host(), proposal()
    r = reserve(original, p)
    reopened = open_host(other_loop, {"ledger": 100})
    before = snapshot(reopened)
    with pytest.raises(YwirRefuse, match="reservation_host_mismatch"):
        settle(reopened, p, outcome(), reservation=r)
    assert snapshot(reopened) == before


def test_cross_loop_proposal_is_rejected_without_touching_pending_hold():
    h, p = host(), proposal()
    r = reserve(h, p)
    before = snapshot(h)
    with pytest.raises(YwirRefuse, match="loop_mismatch"):
        settle(h, replace(p, loop="loop-b"), outcome(), reservation=r)
    assert snapshot(h) == before


@pytest.mark.parametrize("field,value", [("tokens", 20), ("department", "evidence"), ("expected_rank_delta", 2)])
def test_changed_proposal_cannot_use_original_reservation(field, value):
    h, p = host(), proposal()
    r = reserve(h, p)
    before = snapshot(h)
    with pytest.raises(YwirRefuse, match="reservation_proposal_mismatch"):
        settle(h, replace(p, **{field: value}), outcome(), reservation=r)
    assert snapshot(h) == before


def test_mutable_proposal_internals_refused_before_admission():
    h = host()
    before = snapshot(h)
    with pytest.raises(YwirRefuse, match="immutable tuple"):
        reserve(h, proposal(compose_candidates=["mutable"]))
    assert snapshot(h) == before


def test_forged_or_modified_reservation_cannot_increase_cap():
    h, p = host(), proposal()
    r = reserve(h, p)
    before = snapshot(h)
    with pytest.raises(YwirRefuse, match="unknown_reservation"):
        settle(h, p, outcome(tokens_spent=20), reservation=replace(r, tokens=20))
    with pytest.raises(YwirRefuse, match="overspend"):
        settle(h, p, outcome(tokens_spent=11), reservation=r)
    assert snapshot(h) == before


def test_returned_capability_cannot_mutate_retained_authorization():
    h, p = host(), proposal()
    r = reserve(h, p)
    before = snapshot(h)
    object.__setattr__(r, "tokens", 20)
    with pytest.raises(YwirRefuse, match="unknown_reservation"):
        settle(h, p, outcome(tokens_spent=20), reservation=r)
    assert snapshot(h) == before


def test_settlement_record_retains_admitted_context_and_snapshots_outcome():
    h, p = host(), proposal()
    r, observed = reserve(h, p), outcome()
    record = settle(h, p, observed, reservation=r)
    object.__setattr__(observed, "tokens_spent", 99)
    assert record.outcome.tokens_spent == 10
    decide(h, proposal(reindex_base="new-base"))
    retained = h._settlements[record.settlement_id]
    assert retained.base == "default"
    assert retained.reserved_tokens == 10
    assert retained.reservation_id == r.reservation_id


@pytest.mark.parametrize("command", [{"close": True}, {"reindex_base": "new-base"}])
def test_negative_tokens_refused_before_control_command_mutation(command):
    h = host()
    before = snapshot(h)
    with pytest.raises(YwirRefuse):
        decide(h, proposal(tokens=-1, **command))
    assert snapshot(h) == before


@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_eta_must_be_finite_at_host_creation(value):
    with pytest.raises(YwirRefuse):
        open_host("loop-a", {"ledger": 100}, eta_hat=value)


@pytest.mark.parametrize("field", ["glued", "confidence_rising", "eta_falling"])
def test_settlement_boolean_fields_are_strict(field):
    h, p = host(), proposal()
    r = reserve(h, p)
    before = snapshot(h)
    with pytest.raises(YwirRefuse, match="invalid_boolean"):
        settle(h, p, outcome(**{field: 1}), reservation=r)
    assert snapshot(h) == before


def test_cancel_releases_hold_once_and_invalidates_capability():
    h, p = host(10), proposal()
    r = reserve(h, p)
    assert not decide(h, p).admitted
    cancel(h, r)
    assert snapshot(h)["available"]["ledger"] == 10
    assert decide(h, p).admitted
    before = snapshot(h)
    with pytest.raises(YwirRefuse, match="reservation_consumed"):
        cancel(h, r)
    with pytest.raises(YwirRefuse, match="reservation_consumed"):
        settle(h, p, outcome(), reservation=r)
    assert snapshot(h) == before


@pytest.mark.parametrize("command", [{"close": True}, {"reindex_base": "new-base"}])
def test_close_and_reindex_refuse_while_reservations_are_pending(command):
    h, p = host(), proposal()
    r = reserve(h, p)
    before = snapshot(h)
    with pytest.raises(YwirRefuse, match="pending_reservations"):
        decide(h, proposal(**command))
    assert snapshot(h) == before
    cancel(h, r)
    decide(h, proposal(**command))


def test_external_base_mutation_cannot_reinterpret_existing_reservation():
    h, p = host(), proposal()
    r = reserve(h, p)
    h.base = "different"
    with pytest.raises(YwirRefuse, match="reservation_base_mismatch"):
        settle(h, p, outcome(), reservation=r)
    assert h.budget["ledger"] == 100


@pytest.mark.parametrize("value", [True, False, 1.5, float("nan"), float("inf"), "10"])
def test_budget_requires_nonnegative_strict_integer(value):
    with pytest.raises(YwirRefuse):
        host(value)


@pytest.mark.parametrize("field", ["tokens", "expected_rank_delta"])
@pytest.mark.parametrize("value", [True, 1.5, float("nan"), float("inf")])
def test_proposal_integer_values_validated_before_reserving(field, value):
    h = host()
    before = snapshot(h)
    with pytest.raises(YwirRefuse):
        reserve(h, proposal(**{field: value}))
    assert snapshot(h) == before


@pytest.mark.parametrize("field", ["tokens_spent", "rank_delta", "similarity_to_store"])
@pytest.mark.parametrize("value", [True, float("nan"), float("inf")])
def test_invalid_settlement_numbers_leave_all_state_unchanged(field, value):
    h, p = host(), proposal()
    r = reserve(h, p)
    before = snapshot(h)
    with pytest.raises(YwirRefuse):
        settle(h, p, outcome(**{field: value}), reservation=r)
    assert snapshot(h) == before
    settle(h, p, outcome(), reservation=r)


@pytest.mark.parametrize("field", ["tokens_spent", "rank_delta"])
def test_fractional_token_and_rank_values_refused(field):
    h, p = host(), proposal()
    r = reserve(h, p)
    before = snapshot(h)
    with pytest.raises(YwirRefuse, match="invalid_integer"):
        settle(h, p, outcome(**{field: 1.5}), reservation=r)
    assert snapshot(h) == before


def test_conflicting_morphism_fails_before_debit_and_preserves_retry():
    h, p = host(), proposal()
    existing = Morphism("existing", "original", "ledger", h.loop)
    h.store.accept(existing)
    r = reserve(h, p)
    before = snapshot(h)
    with pytest.raises(YwirRefuse, match="morphism_conflict"):
        settle(h, p, outcome(new_morphism_id="existing", new_morphism_type="changed"), reservation=r)
    assert snapshot(h) == before
    assert h.store.get("existing") == existing
    settle(h, p, outcome(new_morphism_id="new"), reservation=r)


def test_store_failure_is_atomic_and_reservation_can_be_cancelled(monkeypatch):
    h, p = host(), proposal()
    r = reserve(h, p)
    before = snapshot(h)

    def fail_after_staged_write(store, item):
        store._items[item.morphism_id] = item
        raise RuntimeError("store failed")

    monkeypatch.setattr(CompositionStore, "accept", fail_after_staged_write)
    with pytest.raises(RuntimeError, match="store failed"):
        settle(h, p, outcome(new_morphism_id="staged-only"), reservation=r)
    assert snapshot(h) == before
    cancel(h, r)


def test_concurrent_reservation_cannot_overcommit():
    h, p = host(10), proposal()
    start = Barrier(2)

    def attempt():
        start.wait()
        try:
            return reserve(h, p)
        except YwirRefuse:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(item is not None for item in results) == 1
    assert snapshot(h)["reserved"]["ledger"] == 10
    assert snapshot(h)["available"]["ledger"] == 0


def test_concurrent_settlement_charges_once():
    h, p = host(), proposal()
    r = reserve(h, p)
    start = Barrier(2)

    def attempt():
        start.wait()
        try:
            return settle(h, p, outcome(), reservation=r)
        except YwirRefuse as error:
            assert error.code == "reservation_consumed"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(item is not None for item in results) == 1
    assert snapshot(h)["budget"]["ledger"] == 90
    assert snapshot(h)["settlement_count"] == 1
