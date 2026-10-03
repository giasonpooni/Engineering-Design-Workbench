"""reevaluate_program(pool, engine, query, criteria) -> MaterialsIteration:
orchestration only -- turns the CURRENT state of an EvidencePool into a
fresh engineering assessment by calling the existing pipeline functions
in their existing order, unmodified:

    materials.program.analyze_program
        -> materials.decision.evaluate_program
        -> materials.audit.audit_program
        -> materials.experiment.analyze_experiment_gaps
        -> materials.specification.specify_experiment_requirements

No step's logic is reimplemented here; this module contributes nothing
but sequencing and one result shape. `reevaluate_program` is exactly as
read-only as `materials.analysis.analyze`/`materials.program.analyze_program`
already are -- it calls `pool.fingerprint()` (a read-only method every
`RetrievalEngine` implementation already calls) and nothing else on
`pool`. The only writer anywhere in `materials/` remains
`materials.results.admit_experimental_result` -- this module never
imports it and never calls `put_*`/`admit_*`, exactly like every layer
from `materials.decision` onward.

`MaterialsIteration` embeds `decision`/`audit`/`gap_analysis`/
`specification` as direct fields purely for ergonomic access -- this is
NOT duplication: `audit.decision is decision`, `gap_analysis.audit is
audit`, and `specification.gaps is gap_analysis` already hold by
construction (each layer since Phase 32 embeds the one immediately
below it), so `specification` alone already makes the entire chain
transitively reachable. Naming the intermediate objects directly here
just spares a caller from writing `iteration.specification.gaps.audit.
decision` to reach what they usually want directly.

`evidence_version_id` (`pool.fingerprint()` at the moment this iteration
was computed) is not a new concept: it is exactly the field
`retrieval.result.RetrievalResult` already carries for the same reason
-- a plain, honest marker of which pool state a derived result was
computed against, reused here rather than reinvented. Two calls to
`reevaluate_program` against a pool that has not changed between them
always produce the same `evidence_version_id` and equal derived state;
two calls straddling an `admit_experimental_result` call always produce
a different `evidence_version_id`, and the two `MaterialsIteration`
objects remain independently valid -- nothing about computing iteration
N+1 modifies iteration N's own objects, which is what lets a caller keep
`Iteration 0, Iteration 1, Iteration 2, ...` around simultaneously
without any of them going stale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from evidence.pool import EvidencePool
from materials.audit import ProgramAudit, audit_program
from materials.decision import Criterion, ProgramDecision, evaluate_program
from materials.experiment import ExperimentGapAnalysis, analyze_experiment_gaps
from materials.program import MaterialProgramAnswer, MaterialProgramQuery, analyze_program
from materials.specification import ExperimentSpecification, specify_experiment_requirements
from retrieval.engine import RetrievalEngine


@dataclass(frozen=True)
class MaterialsIteration:
    """One complete engineering assessment of an EvidencePool's current
    state, for one (query, criteria) pair. `criteria` is stored
    alongside `query` because a `ProgramDecision` is meaningless without
    knowing which criteria produced it, and `materials.program`'s own
    `MaterialProgramAnswer` never carries them (criteria are a
    `materials.decision`-level concept, one layer above)."""

    query: MaterialProgramQuery
    criteria: Tuple[Criterion, ...]
    evidence_version_id: str
    program_answer: MaterialProgramAnswer
    decision: ProgramDecision
    audit: ProgramAudit
    gap_analysis: ExperimentGapAnalysis
    specification: ExperimentSpecification

    def __post_init__(self) -> None:
        object.__setattr__(self, "criteria", tuple(self.criteria))


def reevaluate_program(
    pool: EvidencePool,
    engine: RetrievalEngine,
    query: MaterialProgramQuery,
    criteria: Tuple[Criterion, ...],
) -> MaterialsIteration:
    """Deterministic given a fixed pool state: same `pool.fingerprint()`
    + same `query`/`criteria` always produces an equal `MaterialsIteration`
    (the same guarantee `analyze_program`/`evaluate_program`/
    `audit_program`/`analyze_experiment_gaps`/`specify_experiment_requirements`
    already individually provide, composed). Calls no `put_*`/`admit_*`;
    never mutates `pool`, `query`, or `criteria`."""
    evidence_version_id = pool.fingerprint()
    criteria = tuple(criteria)
    program_answer = analyze_program(pool, engine, query)
    decision = evaluate_program(program_answer, criteria)
    audit = audit_program(decision)
    gap_analysis = analyze_experiment_gaps(audit)
    specification = specify_experiment_requirements(gap_analysis)
    return MaterialsIteration(
        query=query, criteria=criteria, evidence_version_id=evidence_version_id,
        program_answer=program_answer, decision=decision, audit=audit,
        gap_analysis=gap_analysis, specification=specification,
    )
