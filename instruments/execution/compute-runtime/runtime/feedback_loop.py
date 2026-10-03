"""Feedback loop (§16, §17, §20): the only bridge from simulation/neural
candidates back into canonical state.

    CandidateNextState / BeliefState.candidate
        |
        v
    validate_candidate()   <-- the one legal route into a new Version (§6)
        |
        v
    Version | ValidationError[]

There is no alternate fast path here for "just this once" -- every
candidate, regardless of producing subsystem, is wrapped into a
CandidateDelta and handed to the same `validate_candidate` that a manual
edit goes through.
"""

from __future__ import annotations

from typing import List, Union

from backends.neural.interface import BeliefState
from core.canonical.delta import CandidateDelta, CandidateNextState
from core.canonical.schema import StateSchema
from core.canonical.state import CanonicalState
from core.canonical.validation import ValidationError, validate_candidate
from core.canonical.version import Version


def submit_simulation_candidate(
    schema: StateSchema,
    base: CanonicalState,
    candidate: CandidateNextState,
    transaction_id: str,
    timestamp: str,
) -> Union[Version, List[ValidationError]]:
    delta = CandidateDelta(
        version_from=candidate.based_on_version,
        transaction_id=transaction_id,
        timestamp=timestamp,
        changes=candidate.proposed_changes,
    )
    return validate_candidate(schema, base, delta)


def submit_neural_belief(
    schema: StateSchema,
    base: CanonicalState,
    belief: BeliefState,
    transaction_id: str,
    timestamp: str,
) -> Union[Version, List[ValidationError]]:
    return submit_simulation_candidate(schema, base, belief.candidate, transaction_id, timestamp)
