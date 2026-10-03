from __future__ import annotations

import pytest

from ywir import Proposal, Settlement, YwirRefuse, decide, open_host, reserve, settle, snapshot


def _host(**budget: int):
    full = {"ledger": 0, "evidence": 0, "exploration": 0, "gauge": 0}
    full.update(budget)
    return open_host("loop-a", full)


def test_admits_rank_raising_ledger_burst():
    host = _host(ledger=200)
    v = decide(
        host,
        Proposal(
            loop="loop-a",
            department="ledger",
            tokens=40,
            expected_rank_delta=1,
            expected_new_morphism=True,
        ),
    )
    assert v.admitted
    assert v.letter == "ADMIT"
    assert v.status == "admitted"


def test_unknown_department_refused():
    host = _host(ledger=10)
    with pytest.raises(YwirRefuse) as err:
        decide(
            host,
            Proposal(loop="loop-a", department="atmosphere", tokens=8),
        )
    assert err.value.code == "unknown_department"


def test_department_starved():
    host = _host(ledger=10)
    v = decide(
        host,
        Proposal(
            loop="loop-a",
            department="ledger",
            tokens=40,
            expected_rank_delta=1,
            expected_new_morphism=True,
        ),
    )
    assert v.refuse_code == "DEPARTMENT_STARVED"
    assert not v.admitted


def test_budget_closed_letter():
    host = _host(ledger=100)
    v = decide(host, Proposal(loop="loop-a", department="ledger", tokens=1, close=True))
    assert v.letter == "CLOSE_BUDGET"
    again = decide(
        host,
        Proposal(
            loop="loop-a",
            department="ledger",
            tokens=8,
            expected_rank_delta=1,
            expected_new_morphism=True,
        ),
    )
    assert again.refuse_code == "BUDGET_CLOSED"


def test_request_evidence_from_plant_refuse():
    host = _host(evidence=80)
    v = decide(
        host,
        Proposal(
            loop="loop-a",
            department="evidence",
            tokens=20,
            plant_refuse="REQUEST_EVIDENCE",
        ),
    )
    assert v.letter == "REQUEST_EVIDENCE"
    assert v.refuse_code == "REQUEST_EVIDENCE"


def test_settle_debits_and_records_morphism():
    host = _host(ledger=100)
    proposal = Proposal(
        loop="loop-a",
        department="ledger",
        tokens=25,
        expected_rank_delta=1,
        expected_new_morphism=True,
    )
    v = decide(host, proposal)
    assert v.admitted
    reservation = reserve(host, proposal)
    settle(
        host,
        proposal,
        Settlement(
            tokens_spent=25,
            rank_delta=1,
            glued=True,
            new_morphism_id="clearance-law-v1",
            new_morphism_type="ledger-section",
        ),
        reservation=reservation,
    )
    snap = snapshot(host)
    assert snap["budget"]["ledger"] == 75
    assert "clearance-law-v1" in snap["store"]
    assert snap["eta_hat"] > 0.0


def test_unglued_settlement_refused():
    host = _host(ledger=100)
    proposal = Proposal(
        loop="loop-a",
        department="ledger",
        tokens=10,
        expected_rank_delta=1,
        expected_new_morphism=True,
    )
    decide(host, proposal)
    reservation = reserve(host, proposal)
    with pytest.raises(YwirRefuse) as err:
        settle(
            host,
            proposal,
            Settlement(tokens_spent=10, rank_delta=0, glued=False),
            reservation=reservation,
        )
    assert err.value.code == "H1_NO_GLUE"
    assert host.budget["ledger"] == 100


def test_loop_mismatch_refused():
    host = _host(ledger=50)
    with pytest.raises(YwirRefuse) as err:
        decide(
            host,
            Proposal(
                loop="loop-b",
                department="ledger",
                tokens=4,
                expected_rank_delta=1,
            ),
        )
    assert err.value.code == "loop_mismatch"


def test_reindex_changes_base():
    host = _host(ledger=10)
    v = decide(
        host,
        Proposal(
            loop="loop-a",
            department="ledger",
            tokens=1,
            reindex_base="model-pin-7",
        ),
    )
    assert v.letter == "REINDEX"
    assert host.base == "model-pin-7"


def test_negative_budget_refused():
    with pytest.raises(YwirRefuse) as err:
        open_host("loop-a", {"ledger": -1})
    assert err.value.code == "negative_budget"
