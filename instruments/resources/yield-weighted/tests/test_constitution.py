"""Pin first-slice identities. Copy numbers only from constitution.py."""

from ywir import (
    DEPARTMENTS,
    DOES_NOT_CLAIM,
    GAUGE_SIMILARITY_CAP,
    MAX_BURST_TOKENS,
    PACKAGE_VERSION,
    YIELD_THRESHOLD,
)
from ywir.constitution import ETA_BLEND, MAX_DEPARTMENTS, MIN_TOKENS


def test_pins():
    assert PACKAGE_VERSION == "0.2.0"
    assert DEPARTMENTS == ("ledger", "evidence", "exploration", "gauge")
    assert YIELD_THRESHOLD == 0.0
    assert GAUGE_SIMILARITY_CAP == 0.85
    assert MAX_DEPARTMENTS == 4
    assert MIN_TOKENS == 1
    assert MAX_BURST_TOKENS == 4096
    assert ETA_BLEND == 0.4


def test_does_not_claim_world():
    assert "building_safe" in DOES_NOT_CLAIM
    assert "lyapunov_certified" in DOES_NOT_CLAIM
    assert "jacobian_accuracy" in DOES_NOT_CLAIM
    assert "answer_true" in DOES_NOT_CLAIM
