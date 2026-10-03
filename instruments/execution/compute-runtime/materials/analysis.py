"""MaterialQuestion -> MaterialPropertyAnswer: the one supported
operation of this application layer.

Composes exactly the steps demonstrated by hand in Phase 26's workload
script -- resolve a Referent by natural key, run existing retrieval for
measured evidence, scan existing DerivedGroundings for predictions, call
the existing `ancestry_of` for each prediction's support -- into one
deterministic, side-effect-free function. Nothing here is a new SCOUT
capability: every step below was already possible with the public API
at db44142; this module only gives that composition a name and a
result shape, at the application layer, not the evidence layer.

OBSERVED / DERIVED / GROUNDING / PROVENANCE are never collapsed into a
single "value" or "truth": `MaterialPropertyAnswer` keeps `observed`
(raw `Observation`s) and `predictions` (each an unmodified `DerivedValue`
paired with its own `ProvenanceAncestry`) as separate tuples, and
computes descriptive disagreement statistics only -- min/max/spread,
never an average, a ranking, or a chosen "winner". Resolving or
adjudicating a disagreement is explicitly out of scope: nothing here
decides which measurement or prediction is correct.

Phase 29 (COMPARABILITY): filtering by `property` alone is not enough
to know two values are measurements/predictions of the *same physical
state* -- `content` may carry additional keys (`temperature`, etc.)
that distinguish otherwise same-labeled values. `_comparison_context`
treats every `content` key except `property` and the measured-value key
itself (`value` for Observation, `predicted_value` for DerivedValue) as
part of that state -- this is a general, content-structure-driven rule,
not a per-property special case: it produces one shared context (and
therefore the same behavior as before) for tensile_strength/Tg, where
no such extra key exists, and splits viscosity's 25C/40C readings into
two contexts automatically, with no `if property == "viscosity"`
anywhere. A key present on one value and absent on the other yields
different (non-equal) contexts, deliberately -- "unknown" is never
silently treated as "matches," the conservative choice per this phase's
own instruction. `method`/`confidence`/`derived_at` are DerivedValue's
own fields, never part of `content`, so two predictions from different
models are still compared exactly like today whenever they share a
context -- model identity was never, and is still not, a comparability
signal here.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from evidence.pool import EvidencePool
from evidence.provenance import ProvenanceAncestry, ancestry_of
from evidence.types import DerivedValue, Observation, Referent
from retrieval.engine import RetrievalEngine
from retrieval.query import make_retrieval_query

# The fixture shape this layer targets (Phase 26): a material/process
# Referent is connected to a shared process Referent one hop away via a
# ClaimedRelationship, so a bounded traversal must reach that second
# node for the relationship's own endpoint check to pass -- depth 0
# alone would see the seed referent only and match zero relationships.
# Not exposed as a MaterialQuestion field: no workload examined here
# needs a different depth, so none is offered speculatively.
_TRAVERSAL_DEPTH = 1


@dataclass(frozen=True)
class MaterialQuestion:
    """The smallest request shape this application layer needs --
    exactly the two things Phase 26's workload used: which entity, which
    property. Free text is deliberately not accepted here (no goal
    ontology exists to interpret it against, per the Phase 22
    investigation) -- `property` matches against the same open,
    caller-defined `content["property"]` key every Observation/
    DerivedValue.content already uses; there is no controlled
    vocabulary to validate it against, so none is invented here."""

    material_natural_key: str
    property: str


@dataclass(frozen=True)
class Disagreement:
    """A purely descriptive summary -- application interpretation, never
    computed or stored by SCOUT itself."""

    minimum: float
    maximum: float
    spread: float


@dataclass(frozen=True)
class ComparisonGroup:
    """Every observed (or predicted) value that shares an identical
    comparison context -- same `content` apart from `property` and the
    measured-value key -- and is therefore safe to compare against the
    others in this group. `disagreement` is computed only within the
    group (None if the group has fewer than two values); values in
    different groups are never combined into one statistic."""

    context: Mapping[str, object]
    values: Tuple[float, ...]
    disagreement: Optional[Disagreement]

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))
        object.__setattr__(self, "values", tuple(self.values))


@dataclass(frozen=True)
class GroundedPrediction:
    """One DerivedValue, unmodified, paired with its own provenance.
    Never merged with any other prediction's ancestry."""

    derived_value: DerivedValue
    provenance: ProvenanceAncestry


@dataclass(frozen=True)
class MaterialPropertyAnswer:
    material: Referent
    property: str
    observed: Tuple[Observation, ...]
    predictions: Tuple[GroundedPrediction, ...]

    # Unchanged in meaning from Phase 27: the Disagreement across ALL
    # observed (or predicted) values -- but now only when they all
    # share one comparison context. None whenever fewer than two values
    # exist OR the values span more than one context (Phase 29): a flat
    # spread across incomparable contexts would be exactly the
    # misleading number Phase 28 demonstrated. Equivalent to
    # `observed_comparison_groups[0].disagreement` when exactly one
    # group exists, and to None otherwise.
    observed_disagreement: Optional[Disagreement]
    predicted_disagreement: Optional[Disagreement]

    # Always populated (Phase 29): the full, never-collapsed picture --
    # one group per distinct comparison context, even when there is
    # only one context (the common case). This is what makes "these
    # values belong to different comparison contexts" visible rather
    # than silently disappearing into a bare `None`.
    observed_comparison_groups: Tuple[ComparisonGroup, ...]
    predicted_comparison_groups: Tuple[ComparisonGroup, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed", tuple(self.observed))
        object.__setattr__(self, "predictions", tuple(self.predictions))
        object.__setattr__(self, "observed_comparison_groups", tuple(self.observed_comparison_groups))
        object.__setattr__(self, "predicted_comparison_groups", tuple(self.predicted_comparison_groups))


def _resolve_referent(pool: EvidencePool, natural_key: str) -> Referent:
    """No dedicated lookup exists in EvidencePool for this (confirmed,
    Phases 24-26) -- a full scan over `all_referents()` is the existing,
    already-public way to do it. Convenience friction, not a capability
    gap: recorded here rather than added to EvidencePool."""
    matches = [r for r in pool.all_referents() if r.natural_key == natural_key]
    if not matches:
        raise KeyError(f"no Referent with natural_key {natural_key!r} in pool")
    return matches[0]


def _groundings_for(pool: EvidencePool, referent_id: str):
    """Same finding: no `derived_values_about`-style method exists.
    A full scan over `all_derived_groundings()` is the existing way."""
    return [g for g in pool.all_derived_groundings() if referent_id in g.referent_ids]


def _matches_property(content: Mapping[str, object], property_name: str) -> bool:
    return content.get("property") == property_name


def _as_float(value: object) -> float:
    """content values are an open `Mapping[str, object]` by design
    (`evidence/types.py`) -- this asserts the numeric shape this
    application layer actually requires, rather than silently coercing
    or suppressing the type check."""
    assert isinstance(value, (int, float)), f"expected a numeric content value, got {value!r}"
    return float(value)


def _disagreement(values: Tuple[float, ...]) -> Optional[Disagreement]:
    if len(values) < 2:
        return None
    return Disagreement(minimum=min(values), maximum=max(values), spread=max(values) - min(values))


def _comparison_context(content: Mapping[str, object], value_key: str) -> Mapping[str, object]:
    """Every `content` key except `property` (already constant -- see
    `analyze`'s property filter) and the measured-value key itself. A
    key present on one value and missing on another produces unequal
    contexts on purpose -- absence is never treated as a match."""
    return {k: v for k, v in content.items() if k not in ("property", value_key)}


def _group_by_comparison_context(
    contents_and_values: Tuple[Tuple[Mapping[str, object], float], ...]
) -> Tuple[ComparisonGroup, ...]:
    groups: dict = {}
    for context, value in contents_and_values:
        key = tuple(sorted(context.items(), key=lambda kv: kv[0]))
        bucket = groups.setdefault(key, {"context": context, "values": []})
        bucket["values"].append(value)

    result = [
        ComparisonGroup(
            context=bucket["context"],
            values=tuple(bucket["values"]),
            disagreement=_disagreement(tuple(bucket["values"])),
        )
        for bucket in groups.values()
    ]
    # Deterministic regardless of dict/insertion order -- sort by the
    # same canonical (key, value) representation used to group.
    result.sort(key=lambda g: repr(sorted(g.context.items(), key=lambda kv: kv[0])))
    return tuple(result)


def analyze(pool: EvidencePool, engine: RetrievalEngine, question: MaterialQuestion) -> MaterialPropertyAnswer:
    """Deterministic, side-effect-free: same evidence + same question
    always produces an equal `MaterialPropertyAnswer` (proven by
    `tests/test_materials_consumer.py`'s insertion-order and
    PYTHONHASHSEED tests). Calls only existing, unmodified evidence/
    retrieval public API -- no `pool.put_*`, no admission, no mutation."""
    referent = _resolve_referent(pool, question.material_natural_key)

    query = make_retrieval_query(entity_natural_keys=(question.material_natural_key,), traversal_depth=_TRAVERSAL_DEPTH)
    result = engine.retrieve(pool, query)
    observed = tuple(
        obs
        for obs in (pool.get_observation(oid) for oid in result.observation_ids)
        if _matches_property(obs.content, question.property)
    )

    predictions = tuple(
        GroundedPrediction(derived_value=dv, provenance=ancestry_of(pool, dv.id))
        for dv in (pool.get_derived_value(g.derived_value_id) for g in _groundings_for(pool, referent.id))
        if _matches_property(dv.content, question.property)
    )

    observed_contexts_and_values = tuple(
        (_comparison_context(o.content, "value"), _as_float(o.content["value"])) for o in observed
    )
    predicted_contexts_and_values = tuple(
        (_comparison_context(p.derived_value.content, "predicted_value"), _as_float(p.derived_value.content["predicted_value"]))
        for p in predictions
    )

    observed_groups = _group_by_comparison_context(observed_contexts_and_values)
    predicted_groups = _group_by_comparison_context(predicted_contexts_and_values)

    return MaterialPropertyAnswer(
        material=referent,
        property=question.property,
        observed=observed,
        predictions=predictions,
        observed_disagreement=observed_groups[0].disagreement if len(observed_groups) == 1 else None,
        predicted_disagreement=predicted_groups[0].disagreement if len(predicted_groups) == 1 else None,
        observed_comparison_groups=observed_groups,
        predicted_comparison_groups=predicted_groups,
    )
