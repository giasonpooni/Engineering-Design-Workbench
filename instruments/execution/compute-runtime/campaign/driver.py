"""run_campaign: many executions, many occurrences, ONE evidence ledger.

Stage 6's driver, deliberately THIN: a campaign here is nothing but a
sequence of dispatches through the seam that already exists
(`experiment.step.run_experiment_step`), against ONE shared
`EvidencePool` and ONE shared `OperationTrace`, with whatever runner the
caller chooses per point (unproved engine, external process, or a
proved runner). No campaign ontology, no campaign store, no new
identity: `CampaignPoint` is a parameter bundle and `CampaignReport` is
a bag of counters and timings -- neither is content-addressed, admitted,
or persisted.

The ledger arithmetic the campaign is built to demonstrate (and that
the pool's own semantics provide by construction -- `put_observation`
is a content-keyed write, and the fingerprint history appends only on
semantic change):

    N executions  >=  M successful dispatches  >=  K unique evidence ids

Repeated computation re-derives known evidence without inflating it;
the operation trace retains every occurrence regardless.

A failed point (refused specification, halted execution, failed
verification, downstream rejection) raises inside the step exactly as
everywhere else in this architecture; the campaign records the failure
in its report and CONTINUES -- the seam has already recorded
FAILED/REJECTED in the trace and admitted nothing semantic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional

from evidence.admission import admit_document, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_document, make_referent, make_source
from execution.dispatcher import SpecificationDispatcher  # noqa: E501
from execution.engine import ExecutionResult
from execution.specification import ExecutionSpecification
from experiment.policy import ExperimentPolicy
from experiment.session import make_experiment_session
from experiment.step import run_experiment_step
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.information import InformationValueEstimate
from materials.iteration import reevaluate_program
from materials.optimization import OptimizationPolicy
from materials.program import make_material_program_query
from materials.selection import SelectionPolicy
from materials.utility import ExperimentUtilityInput
from operations.trace import OperationTrace
from retrieval.engine import DeterministicRetrievalEngine


@dataclass(frozen=True)
class CampaignPoint:
    """One planned dispatch: which cell of the scientific space, which
    specification, how to read its output. A parameter bundle -- not an
    identity-bearing object."""

    formulation: str
    property_name: str
    spec: ExecutionSpecification
    interpret: Callable[[object, ExecutionResult], Mapping[str, object]]
    #: None = the checked native engine; otherwise a proved or external
    #: runner (`execution.proving.proved_runner`, a GROMACS runner, ...).
    runner: Optional[Callable[[ExecutionSpecification], ExecutionResult]] = None
    #: Recorded verbatim in the report -- "unproved" / "sp1" / "nexus" /
    #: "external"; the campaign itself attaches no meaning to it.
    label: str = "unproved"


@dataclass
class CampaignReport:
    """Counters and wall-clock timings. Data about a run, never evidence."""

    executions: int = 0
    successes: int = 0
    failures: int = 0
    observation_ids: list = field(default_factory=list)
    failure_kinds: list = field(default_factory=list)
    seconds_per_point: list = field(default_factory=list)

    @property
    def unique_evidence(self) -> int:
        return len(set(self.observation_ids))


_ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)
_DECIDE_ONE = OptimizationPolicy(
    max_candidates=1, allowed_action_classes=None, allow_indeterminate_utility=True
)


def _benefit(estimate: InformationValueEstimate) -> ExperimentUtilityInput:
    if estimate.estimate is not None:
        return ExperimentUtilityInput(benefit=estimate.estimate, cost=1.0)
    return ExperimentUtilityInput(benefit=1.0, cost=1.0)


def make_campaign_pool(referent_keys, name: str = "STE-campaign"):
    """One pool, one campaign document, the referents the sweep spans.
    Plain reuse of the existing admission primitives."""
    pool = EvidencePool()
    source = make_source(kind="computational_campaign", name=name)
    pool.put_source(source)
    doc = make_document(
        source_id=source.id, raw_content=f"{name} session",
        retrieval_method="manual_entry", retrieved_at="2026-08-25T00:00:00Z",
    )
    admit_document(pool, doc)
    pool.put_document(doc)
    for key in referent_keys:
        referent = make_referent(natural_key=key, kind="formulation")
        admit_referent(pool, referent)
        pool.put_referent(referent)
    process = make_referent(natural_key="process-campaign-cell", kind="process")
    admit_referent(pool, process)
    pool.put_referent(process)
    return pool, doc


def run_campaign(
    pool: EvidencePool,
    document_id: str,
    trace: OperationTrace,
    points: list,
    engine: Optional[DeterministicRetrievalEngine] = None,
) -> CampaignReport:
    """Dispatch every point through the existing seam, sharing the pool
    and the trace. Failures are recorded and the campaign continues."""
    engine = engine or DeterministicRetrievalEngine()
    policy = ExperimentPolicy(
        selection_policy=_ALLOW_ALL, optimization_policy=_DECIDE_ONE,
        utility_input_source=_benefit,
    )
    report = CampaignReport()
    for point in points:
        started = time.monotonic()
        report.executions += 1
        try:
            query = make_material_program_query(
                [point.formulation], "process-campaign-cell", (point.property_name,)
            )
            iteration = reevaluate_program(
                pool, engine, query,
                (make_criterion(point.property_name, "<=", 10_000_000),),
            )
            session = make_experiment_session(pool, engine, iteration, document_id=document_id)
            dispatcher = SpecificationDispatcher(
                spec_for=lambda c, _p=point: _p.spec,
                interpret=point.interpret,
                extracted_at="2026-08-25T00:00:00Z",
                runner=point.runner,
            )
            candidates = generate_candidates(session.iteration.specification)
            step = run_experiment_step(
                session, candidates, dispatcher, policy, confidence=1.0, trace=trace
            )
            report.successes += 1
            report.observation_ids.append(step.observation.id)
        except Exception as error:  # noqa: BLE001 -- recorded, not handled
            report.failures += 1
            report.failure_kinds.append(f"{point.label}:{type(error).__name__}")
        report.seconds_per_point.append(time.monotonic() - started)
    return report
