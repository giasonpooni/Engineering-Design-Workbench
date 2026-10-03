"""Criterion + evaluate_program: the smallest explicit engineering-
decision procedure over evidence `materials.program` already produced.

Pure function over an already-computed `MaterialProgramAnswer` -- this
module never touches `EvidencePool` or `RetrievalEngine` at all
(`evaluate_program`'s only argument besides `criteria` is the program
layer's own output), consuming what `materials.program` already
resolved rather than rebuilding any of its traversal or process
resolution (Phase 31 §10's one-responsibility-per-layer discipline,
carried one layer further).

Engineering criteria are caller-supplied data, never invented here --
`Criterion` is a plain (property, operator, target, context) record,
not a scoring model. `evaluate_program` answers exactly one question
per (formulation, property, criterion): does the COMPARABLE evidence
pass, fail, conflict, or fail to exist -- and answers it SEPARATELY for
observed and predicted evidence, never merging the two into one
verdict. There is no ranking, scoring, winner-selection, or
recommendation anywhere in this module, and none is added: it reports
`PASS`/`FAIL`/`CONFLICTING_EVIDENCE`/`INSUFFICIENT_EVIDENCE`/
`INCOMPARABLE` per (formulation, property, criterion) and stops there.

Comparability reuses Phase 29's `ComparisonGroup` machinery directly
(`MaterialPropertyAnswer.observed_comparison_groups`/
`predicted_comparison_groups`) rather than re-deriving grouping logic:
a criterion's `context` is matched against a group's `context` by
subset containment (every key the criterion names must be present and
equal in the group; the group may carry additional, criterion-
irrelevant keys) -- zero matching groups means the criterion's
condition was never measured under a comparable state (`INCOMPARABLE`,
if any evidence exists for the property at all) or that no evidence
exists for the property at all (`INSUFFICIENT_EVIDENCE`); more than one
matching group means the criterion's `context` did not uniquely select
one comparison state, which is also reported as `INCOMPARABLE` rather
than guessed at.
"""

from __future__ import annotations

import operator as operator_module
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Mapping, Optional, Tuple

from materials.analysis import ComparisonGroup, MaterialPropertyAnswer
from materials.program import FormulationProcessAssociation, FormulationProgramEntry, MaterialProgramAnswer
from evidence.types import Referent

PASS = "PASS"
FAIL = "FAIL"
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
INCOMPARABLE = "INCOMPARABLE"

ALL_STATUSES = (PASS, FAIL, CONFLICTING_EVIDENCE, INSUFFICIENT_EVIDENCE, INCOMPARABLE)

_OPERATORS = {
    ">=": operator_module.ge,
    "<=": operator_module.le,
    ">": operator_module.gt,
    "<": operator_module.lt,
    "==": operator_module.eq,
}


@dataclass(frozen=True)
class Criterion:
    """Caller-supplied engineering data, never invented by this module.
    `context` uses the same open, unschematized shape
    `Observation`/`DerivedValue.content` already establish -- e.g.
    `{"temperature": 25, "temperature_unit": "C"}` for a condition-
    dependent property, or `{}` when nothing needs to be specified."""

    property: str
    operator: str
    target: float
    context: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))
        if self.operator not in _OPERATORS:
            raise ValueError(f"unsupported operator {self.operator!r}; expected one of {sorted(_OPERATORS)}")


def make_criterion(property: str, operator: str, target: float, context: Optional[Mapping[str, object]] = None) -> Criterion:
    return Criterion(property=property, operator=operator, target=float(target), context=context or {})


@dataclass(frozen=True)
class PropertyDecision:
    """`observed_status`/`predicted_status` are computed independently
    and never combined -- a caller who wants one combined answer makes
    that decision themselves; this module does not make it for them."""

    criterion: Criterion
    evidence: Optional[MaterialPropertyAnswer]
    observed_status: str
    observed_group: Optional[ComparisonGroup]
    predicted_status: str
    predicted_group: Optional[ComparisonGroup]


@dataclass(frozen=True)
class FormulationDecision:
    formulation: Referent
    process_association: FormulationProcessAssociation
    properties: Tuple[PropertyDecision, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", tuple(self.properties))


@dataclass(frozen=True)
class ProgramDecision:
    process_natural_key: str
    criteria: Tuple[Criterion, ...]
    formulations: Tuple[FormulationDecision, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "criteria", tuple(self.criteria))
        object.__setattr__(self, "formulations", tuple(self.formulations))


def _context_matches(criterion_context: Mapping[str, object], group_context: Mapping[str, object]) -> bool:
    _missing = object()
    return all(group_context.get(k, _missing) == v for k, v in criterion_context.items())


def _matching_groups(groups: Tuple[ComparisonGroup, ...], criterion: Criterion) -> Tuple[ComparisonGroup, ...]:
    return tuple(g for g in groups if _context_matches(criterion.context, g.context))


def _status_for_groups(
    groups: Tuple[ComparisonGroup, ...], criterion: Criterion
) -> Tuple[str, Optional[ComparisonGroup]]:
    if not groups:
        return INSUFFICIENT_EVIDENCE, None
    matching = _matching_groups(groups, criterion)
    if len(matching) != 1:
        return INCOMPARABLE, None
    group = matching[0]
    op = _OPERATORS[criterion.operator]
    results = [op(v, criterion.target) for v in group.values]
    if all(results):
        return PASS, group
    if not any(results):
        return FAIL, group
    return CONFLICTING_EVIDENCE, group


def _decide_property(criterion: Criterion, evidence: Optional[MaterialPropertyAnswer]) -> PropertyDecision:
    if evidence is None:
        return PropertyDecision(
            criterion=criterion, evidence=None,
            observed_status=INSUFFICIENT_EVIDENCE, observed_group=None,
            predicted_status=INSUFFICIENT_EVIDENCE, predicted_group=None,
        )
    observed_status, observed_group = _status_for_groups(evidence.observed_comparison_groups, criterion)
    predicted_status, predicted_group = _status_for_groups(evidence.predicted_comparison_groups, criterion)
    return PropertyDecision(
        criterion=criterion, evidence=evidence,
        observed_status=observed_status, observed_group=observed_group,
        predicted_status=predicted_status, predicted_group=predicted_group,
    )


def _decide_formulation(entry: FormulationProgramEntry, criteria: Tuple[Criterion, ...]) -> FormulationDecision:
    evidence_by_property: Dict[str, MaterialPropertyAnswer] = {pe.property: pe.answer for pe in entry.properties}
    decisions = tuple(_decide_property(c, evidence_by_property.get(c.property)) for c in criteria)
    return FormulationDecision(formulation=entry.formulation, process_association=entry.process_association, properties=decisions)


def evaluate_program(program_answer: MaterialProgramAnswer, criteria: Tuple[Criterion, ...]) -> ProgramDecision:
    """Deterministic, side-effect-free, read-only -- does not call
    `EvidencePool`/`RetrievalEngine` at all. `criteria` order is
    preserved exactly as given (not deduplicated or sorted): unlike
    `MaterialProgramQuery`'s formulation/property sets, two identical
    criteria for the same property are a caller error, not a
    normalization concern this module resolves for them."""
    criteria = tuple(criteria)
    formulations = tuple(_decide_formulation(entry, criteria) for entry in program_answer.formulations)
    return ProgramDecision(process_natural_key=program_answer.process_natural_key, criteria=criteria, formulations=formulations)
