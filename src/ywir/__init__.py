"""Yield-Weighted Inference Runtime.

Owns admission of token bursts on a declared department budget.
Does not own BIM belief, Lyapunov V, Jacobians, wording, or the LLM.
"""

from ywir.constitution import (
    DEPARTMENTS,
    DOES_NOT_CLAIM,
    GAUGE_SIMILARITY_CAP,
    INSTRUMENT,
    MAX_BURST_TOKENS,
    PACKAGE_VERSION,
    YIELD_THRESHOLD,
)
from ywir.errors import YwirRefuse
from ywir.observation import Proposal, Settlement
from ywir.receipts import YwirReceipt, from_verdict, support_code_for
from ywir.runtime import (
    GIT_PIN_UNSET,
    HostState,
    Verdict,
    Reservation,
    SettlementRecord,
    cancel,
    decide,
    observed_yield,
    open_host,
    reserve,
    settle,
    snapshot,
)
from ywir.store import CompositionStore, Morphism

__all__ = [
    "DEPARTMENTS",
    "DOES_NOT_CLAIM",
    "GAUGE_SIMILARITY_CAP",
    "GIT_PIN_UNSET",
    "INSTRUMENT",
    "MAX_BURST_TOKENS",
    "PACKAGE_VERSION",
    "YIELD_THRESHOLD",
    "CompositionStore",
    "HostState",
    "Morphism",
    "Proposal",
    "Settlement",
    "Verdict",
    "Reservation",
    "SettlementRecord",
    "YwirReceipt",
    "YwirRefuse",
    "decide",
    "cancel",
    "from_verdict",
    "observed_yield",
    "open_host",
    "reserve",
    "settle",
    "snapshot",
    "support_code_for",
]
