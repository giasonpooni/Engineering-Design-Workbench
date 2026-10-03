import json
from pathlib import Path

from ywir import DEPARTMENTS, DOES_NOT_CLAIM
from ywir.receipts import SUPPORT_CODES

ROOT = Path(__file__).resolve().parents[1]
CORPUS = json.loads((ROOT / "validation" / "invariant-corpus-v1.json").read_text())


def test_corpus_departments_match_constitution():
    assert tuple(CORPUS["departments"]) == DEPARTMENTS


def test_corpus_does_not_claim_match():
    assert tuple(CORPUS["does_not_claim"]) == DOES_NOT_CLAIM


def test_admit_support_code_pinned():
    assert SUPPORT_CODES["admitted"] == "YIELD_ADMIT"
    assert "ADMIT" in CORPUS["letters"]
    assert "GAUGE_SPILL" in CORPUS["refuse_codes"]
