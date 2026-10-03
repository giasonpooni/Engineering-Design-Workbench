from ywir import Proposal, decide, open_host, reserve, settle
from ywir.observation import Settlement


def _host():
    return open_host(
        "loop-a",
        {"ledger": 400, "evidence": 200, "exploration": 80, "gauge": 40},
    )


def test_gauge_department_is_spill():
    v = decide(
        _host(),
        Proposal(loop="loop-a", department="gauge", tokens=12),
    )
    assert v.refuse_code == "GAUGE_SPILL"


def test_high_similarity_without_rank_is_spill():
    v = decide(
        _host(),
        Proposal(
            loop="loop-a",
            department="ledger",
            tokens=30,
            similarity_to_store=0.92,
        ),
    )
    assert v.refuse_code == "GAUGE_SPILL"


def test_rank_flat_on_ship_channel():
    v = decide(
        _host(),
        Proposal(loop="loop-a", department="ledger", tokens=30),
    )
    assert v.refuse_code == "RANK_FLAT"


def test_exploration_may_be_rank_flat():
    v = decide(
        _host(),
        Proposal(loop="loop-a", department="exploration", tokens=20),
    )
    assert v.admitted
    assert v.letter == "ADMIT"


def test_meta_precision_unstable():
    v = decide(
        _host(),
        Proposal(
            loop="loop-a",
            department="ledger",
            tokens=80,
            expected_rank_delta=1,
            confidence_rising=True,
            eta_falling=True,
        ),
    )
    assert v.refuse_code == "META_PRECISION_UNSTABLE"


def test_compose_instead_when_store_has_map():
    host = _host()
    first = Proposal(
        loop="loop-a",
        department="ledger",
        tokens=20,
        expected_rank_delta=1,
        expected_new_morphism=True,
    )
    assert decide(host, first).admitted
    reservation = reserve(host, first)
    settle(
        host,
        first,
        Settlement(
            tokens_spent=20,
            rank_delta=1,
            glued=True,
            new_morphism_id="op-a",
            new_morphism_type="section",
        ),
        reservation=reservation,
    )
    v = decide(
        host,
        Proposal(
            loop="loop-a",
            department="ledger",
            tokens=40,
            expected_rank_delta=1,
            compose_candidates=("op-a",),
        ),
    )
    assert v.letter == "COMPOSE"
    assert v.compose_ids == ("op-a",)
    assert v.refuse_code == "COMPOSE_INSTEAD"
