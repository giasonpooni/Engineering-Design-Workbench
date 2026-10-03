"""Certificate receipt plants may cite. Not a safety stamp.

A receipt binds one YWIR verdict to a proposer-loop name and a git
pin. It does not prove the observations, the plant, or that an
answer is true. ADMIT is advisory: this receipt is not a reservation
and cannot authorize settlement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ywir.constitution import DOES_NOT_CLAIM, INSTRUMENT, PACKAGE_VERSION


SUPPORT_CODES = {
    "admitted": "YIELD_ADMIT",
    "composed": "COMPOSE_INSTEAD",
    "evidence": "REQUEST_EVIDENCE",
    "closed": "BUDGET_CLOSED",
    "refused": "YWIR_REFUSE",
}


@dataclass(frozen=True)
class YwirReceipt:
    instrument: str
    package_version: str
    git_pin: str
    loop: str
    status: str
    letter: str
    details: str
    support_code: str
    admitted: bool
    does_not_claim: tuple[str, ...] = DOES_NOT_CLAIM
    host_id: str | None = None
    proposal_id: str | None = None
    decision_id: str | None = None

    def to_json_obj(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["does_not_claim"] = list(self.does_not_claim)
        return payload


def support_code_for(status: str, refuse_code: str | None = None) -> str:
    if refuse_code in {
        "GAUGE_SPILL",
        "RANK_FLAT",
        "H1_NO_GLUE",
        "COMPOSE_INSTEAD",
        "DEPARTMENT_STARVED",
        "BUDGET_CLOSED",
        "META_PRECISION_UNSTABLE",
        "YIELD_BELOW_THRESHOLD",
        "REQUEST_EVIDENCE",
    }:
        return refuse_code
    return SUPPORT_CODES.get(status, "YWIR_REFUSE")


def from_verdict(
    loop: str,
    status: str,
    letter: str,
    details: str,
    *,
    git_pin: str,
    refuse_code: str | None = None,
    host_id: str | None = None,
    proposal_id: str | None = None,
    decision_id: str | None = None,
) -> YwirReceipt:
    return YwirReceipt(
        instrument=INSTRUMENT,
        package_version=PACKAGE_VERSION,
        git_pin=git_pin,
        loop=loop,
        status=status,
        letter=letter,
        details=details,
        support_code=support_code_for(status, refuse_code),
        admitted=status == "admitted",
        host_id=host_id,
        proposal_id=proposal_id,
        decision_id=decision_id,
    )
