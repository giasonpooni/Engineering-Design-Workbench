"""First-slice walk: admit a morphism, refuse spill, compose instead."""

from __future__ import annotations

from pathlib import Path

from ywir import Proposal, Settlement, decide, open_host, reserve, settle
from ywir.reports import write_report

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "quickstart.md"


def main() -> None:
    host = open_host(
        "pe-loop",
        {"ledger": 200, "evidence": 80, "exploration": 40, "gauge": 20},
    )
    letters = []

    first = Proposal(
        loop="pe-loop",
        department="ledger",
        tokens=32,
        expected_rank_delta=1,
        expected_new_morphism=True,
    )
    v1 = decide(host, first)
    letters.append(v1)
    if v1.admitted:
        reservation = reserve(host, first)
        settle(
            host,
            first,
            Settlement(
                tokens_spent=32,
                rank_delta=1,
                glued=True,
                new_morphism_id="clearance-law-v1",
                new_morphism_type="ledger-section",
            ),
            reservation=reservation,
        )

    spill = decide(
        host,
        Proposal(
            loop="pe-loop",
            department="ledger",
            tokens=48,
            similarity_to_store=0.94,
        ),
    )
    letters.append(spill)

    compose = decide(
        host,
        Proposal(
            loop="pe-loop",
            department="ledger",
            tokens=48,
            expected_rank_delta=1,
            compose_candidates=("clearance-law-v1",),
        ),
    )
    letters.append(compose)

    evidence = decide(
        host,
        Proposal(
            loop="pe-loop",
            department="evidence",
            tokens=16,
            plant_refuse="REQUEST_EVIDENCE",
        ),
    )
    letters.append(evidence)

    write_report(OUT, host, letters)
    print(OUT.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()
