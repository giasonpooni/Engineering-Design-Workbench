from ywir import (
    DOES_NOT_CLAIM,
    Proposal,
    decide,
    from_verdict,
    open_host,
    support_code_for,
)


def test_admit_receipt_does_not_claim_world():
    host = open_host("mill-loop", {"ledger": 100, "evidence": 0, "exploration": 0, "gauge": 0})
    v = decide(
        host,
        Proposal(
            loop="mill-loop",
            department="ledger",
            tokens=16,
            expected_rank_delta=1,
            expected_new_morphism=True,
        ),
    )
    receipt = v.receipt("mill-loop", git_pin="in_development")
    assert receipt.instrument == "ywir"
    assert receipt.admitted
    assert receipt.support_code == "YIELD_ADMIT"
    assert receipt.does_not_claim == DOES_NOT_CLAIM
    payload = receipt.to_json_obj()
    assert "building_safe" in payload["does_not_claim"]


def test_support_codes_pin_taxonomy():
    assert support_code_for("admitted") == "YIELD_ADMIT"
    assert support_code_for("refused", "GAUGE_SPILL") == "GAUGE_SPILL"
    assert support_code_for("evidence", "REQUEST_EVIDENCE") == "REQUEST_EVIDENCE"


def test_from_verdict_roundtrip():
    r = from_verdict(
        "loop-a",
        "refused",
        "REFUSE_SPILL",
        "GAUGE_SPILL",
        git_pin="in_development",
        refuse_code="GAUGE_SPILL",
    )
    assert r.support_code == "GAUGE_SPILL"
    assert not r.admitted
