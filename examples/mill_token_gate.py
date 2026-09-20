"""CNC-shaped fiber: observe first, refuse gauge motion, admit a typed pass.

Does not import CNC-Machine-MCP. The mill supervisor stays a sibling.
YWIR only decides whether the proposer may spend on this loop.
"""

from __future__ import annotations

from pathlib import Path

from ywir import Proposal, Settlement, decide, open_host, reserve, settle
from ywir.reports import write_report

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "mill_token_gate.md"


def main() -> None:
    host = open_host(
        "mill-loop",
        {"ledger": 120, "evidence": 60, "exploration": 0, "gauge": 0},
        base="observe-first",
    )
    letters = []

    observe = decide(
        host,
        Proposal(
            loop="mill-loop",
            department="evidence",
            tokens=12,
            request_evidence=True,
        ),
    )
    letters.append(observe)

    rough = Proposal(
        loop="mill-loop",
        department="ledger",
        tokens=24,
        expected_rank_delta=1,
        expected_new_morphism=True,
    )
    admitted = decide(host, rough)
    letters.append(admitted)
    if admitted.admitted:
        reservation = reserve(host, rough)
        settle(
            host,
            rough,
            Settlement(
                tokens_spent=24,
                rank_delta=1,
                glued=True,
                new_morphism_id="rough-pass-v1",
                new_morphism_type="mill-pass",
            ),
            reservation=reservation,
        )

    reprint = decide(
        host,
        Proposal(
            loop="mill-loop",
            department="ledger",
            tokens=24,
            compose_candidates=("rough-pass-v1",),
        ),
    )
    letters.append(reprint)

    write_report(OUT, host, letters)
    print(OUT.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()
