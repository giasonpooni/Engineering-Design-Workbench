"""Recover the pairing the analysis projection drops.

WHY THIS EXISTS. `materials.analysis.ComparisonGroup` carries exactly
`(context, values, disagreement)`, and `values` is a bare tuple of
floats. No observation id, no Record, no run identity travels with a
value into the group. So a set of replicate runs measuring TWO
properties produces two independent tuples, and nothing in the result
pairs the i-th value of one with the i-th value of the other.

A correlation is precisely a statement about that pairing. So a
correlation cannot be computed from what the projection produces, even
from perfect replicate data -- the grouping unpairs the observations
before any statistic is reached.

THE PAIRING IS NOT LOST, ONLY UNPROJECTED. Observations are
content-addressed, retained, and each names its Record. Joining on
Record recovers it. That is what this module does, and it is a CONSUMER
rather than a change: `analyze`, `ComparisonGroup` and
`_comparison_context` are untouched, so no grouping semantics move and
no core version does either.

THE FINDING IS THE ACQUISITION LAYER'S. It measured the unpairing, in
its own substrate, and stated the remedy precisely -- "joining on Record
outside the grouping, which is a consumer this repository does not
have, not a capability it lacks." That consumer is here because the
module it has to sit beside is here.

WHAT THIS REPOSITORY ADDS TO THAT FINDING, AND IT IS THE SHARPER HALF.
The unpairing is not merely an absence. A group's values arrive in the
order `RetrievalResult.observation_ids` gives them, and that field is
`tuple(sorted(set(...)))` with `ordering: sorted_by_id` -- so the values
are ordered by CONTENT-ADDRESSED OBSERVATION ID. Two properties
measured on the same runs have different content, therefore different
ids, therefore two unrelated permutations of the same runs.

  (This mechanism was first written here as "the group sorts by context
  repr", which is a real sort -- `_group_by_comparison_context` does
  sort, but it sorts the LIST OF GROUPS, not the values inside one. The
  explanation named a true fact that was not the cause. It was caught by
  a mutation aimed at the line the explanation named, which removed that
  sort and left the reordering exactly as it was. A wrong mechanism
  behind a right finding survives review easily, because the finding
  keeps reproducing.)

Measured on five replicate GPC runs:

    inserted   Mn = 3251, 3402, 3188, 3610, 3305
    returned   Mn = 3610, 3188, 3305, 3402, 3251

Same multiset, different order -- and stable, so it reproduces run to
run and across hash seeds. So pairing the two tuples by index does not
fail, and does not even flicker: it SUCCEEDS and returns the wrong
number, the same wrong number every time. On that data the
index pairing gives rho = +0.38 where the true value is -0.98: wrong in
SIGN, with nothing in the result to indicate it. The polymer vertical's
stated question is rho's sign. An absence announces itself; a confident
wrong answer does not, which is why this module never zips two value
tuples and why `correlation` takes a join rather than two sequences.

THE ACQUISITION CONTRACT THIS DEPENDS ON. Both halves are load-bearing
and they fail in OPPOSITE directions:

  one Record per RUN -- because Observation identity is over
  (record_ids, extraction_method, content), two runs reporting the same
  value from one Record collapse into ONE observation. That is correct
  for a re-read and wrong for a replicate, and it biases an estimated
  spread DOWNWARD, which is the overconfident direction.

  the run identifier NOT in content -- an acquisition locator in content
  makes every observation its own single-member comparison group, so
  nothing is comparable at all.

Neither is enforced here. This module cannot repair a corpus that
violates them; it can only refuse to guess, which is what `ambiguous`
below is for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Tuple

from evidence.pool import EvidencePool
from evidence.types import Referent
from materials.analysis import MaterialQuestion, analyze


class UndeclaredRunsError(ValueError):
    """A statistic that assumes its pairs are replicate runs was asked
    for over a join that has not been told which Records are runs."""


@dataclass(frozen=True)
class PairedRun:
    """One Record's worth of a replicate run: every requested property
    it carries, with the observation each value came from.

    `record_id` is retained rather than discarded because it is the
    join key, and a pairing whose key is thrown away is a pairing that
    cannot be checked."""

    record_id: str
    values: Mapping[str, float]
    observation_ids: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "observation_ids",
                           MappingProxyType(dict(self.observation_ids)))

    def complete_for(self, properties: Tuple[str, ...]) -> bool:
        return all(name in self.values for name in properties)


@dataclass(frozen=True)
class ReplicateJoin:
    """The recovered pairing, and everything it refused to pair.

    A JOIN IS A FACT; "THESE ARE RUNS" IS A CLAIM. Joining on Record is
    something this module can do from the pool alone. Asserting that the
    joined Records are replicate runs is not -- see `runs_declared` and
    `declaring_runs` below -- so the two are kept apart, the same split
    as STRUCTURE from WARRANT everywhere else here.

    `complete` is the only thing a statistic may be computed over.
    `incomplete` and `ambiguous` are RETAINED rather than dropped: a
    join that silently discarded what it could not pair would report a
    clean n over an unstated denominator, which is the same defect as a
    rejection rate over gates nothing reaches."""

    material: Referent
    properties: Tuple[str, ...]
    complete: Tuple[PairedRun, ...]
    incomplete: Tuple[PairedRun, ...]
    ambiguous: Tuple[str, ...]
    #: Has a caller stated which of these Records are replicate runs?
    #: False from `join_on_record`, and only `declaring_runs` sets it.
    #: `correlation` refuses while it is False.
    runs_declared: bool = False

    def declaring_runs(self, record_ids) -> "ReplicateJoin":
        """A caller states which Records are replicate runs, and gets a
        join restricted to them.

        THE CHANNEL EXISTS BECAUSE THE SUBSTRATE HAS NO OTHER. The
        acquisition layer measured a real replicate report -- Impact
        Analytical R190048, a table of two injections followed by
        Average, Standard Deviation and % RSD -- and found that with the
        incidental refusals removed it lands FIVE Records, three of them
        aggregates, with "nothing distinguishing them" and the
        aggregates' lineage to the injections unrecoverable, because
        that lineage is POSITIONAL IN THE DOCUMENT and position is what
        acquisition discards.

        Measured here, against that shape, this module inherited the
        defect exactly: `join_on_record` returned n = 5 with zero
        refusals, paired a % RSD with a % RSD and a standard deviation
        with a standard deviation, and reported rho = +0.9986 -- driven
        almost entirely by three aggregate rows spanning 8.4 to 24969.
        The real replicate set is n = 2.

        WHY IT IS NOT DERIVED INSTEAD. Two candidates were checked and
        both refused:

          the EVIDENCE CLASS is a total function of `extraction_method`,
          so every row from one adapter shares one class. A transcribed
          average and a transcribed injection are both the DOCUMENT's
          claim, and the class says so correctly. It does not separate
          them and was never meant to.

          the RECORD LOCATOR does separate them in this corpus
          (`Average/row-2` against `PA191 (S190109)/1`) and matching on
          it is the literal-enumeration hazard the acquisition layer has
          just watched fire on real data: a two-element tuple of
          identity-column names that did not contain the word the first
          real vendor used. A list of aggregate labels breaks on the
          next vendor and breaks SILENTLY, by admitting an aggregate.

        So the fact is not in the pool, cannot be inferred, and is
        declared. That is the same move the acquisition layer's later
        adapter makes for its four provenance fields -- and its own
        contrast records that the adapter WITH the declaration channel
        is the right one.
        """
        declared = tuple(record_ids)
        known = {run.record_id for run in self.complete} | {
            run.record_id for run in self.incomplete}
        unknown = [rid for rid in declared if rid not in known]
        if unknown:
            raise ValueError(
                f"declared runs that are not in this join: {sorted(unknown)}")
        chosen = set(declared)
        return ReplicateJoin(
            material=self.material,
            properties=self.properties,
            complete=tuple(r for r in self.complete if r.record_id in chosen),
            incomplete=tuple(r for r in self.incomplete if r.record_id in chosen),
            ambiguous=self.ambiguous,
            runs_declared=True,
        )

    @property
    def n(self) -> int:
        return len(self.complete)

    @property
    def records_seen(self) -> int:
        return len(self.complete) + len(self.incomplete) + len(self.ambiguous)


def join_on_record(pool: EvidencePool, engine, material_natural_key: str,
                   properties: Tuple[str, ...]) -> ReplicateJoin:
    """Join a material's observations on Record, outside the grouping.

    Deterministic and side-effect-free, on the same terms as `analyze`:
    it calls only public read API and never writes to the pool. It
    reaches each property through `analyze` so that retrieval, referent
    resolution and property matching stay in ONE place -- a second
    traversal written here would be a second definition of which
    observations belong to a material, and two definitions drift.
    """
    if len(properties) < 1:
        raise ValueError("a join needs at least one property to join on")

    referent: Optional[Referent] = None
    by_record: Dict[str, Dict[str, float]] = {}
    observations: Dict[str, Dict[str, str]] = {}
    ambiguous: set = set()

    for name in properties:
        answer = analyze(pool, engine,
                         MaterialQuestion(material_natural_key=material_natural_key,
                                          property=name))
        referent = answer.material
        for observation in answer.observed:
            for record_id in observation.record_ids:
                slot = by_record.setdefault(record_id, {})
                value = float(observation.content["value"])
                if name in slot and slot[name] != value:
                    # TWO DIFFERENT VALUES OF ONE PROPERTY ON ONE RECORD.
                    # The acquisition contract says one Record per RUN, so
                    # this Record is either two runs merged or a genuine
                    # re-read that disagrees with itself. Either way the
                    # join has no basis for choosing, and choosing would
                    # be inventing a run. The record is refused whole --
                    # never partially, since its other properties are
                    # equally suspect.
                    ambiguous.add(record_id)
                    continue
                slot[name] = value
                observations.setdefault(record_id, {})[name] = observation.id

    complete: List[PairedRun] = []
    incomplete: List[PairedRun] = []
    for record_id in sorted(by_record):
        if record_id in ambiguous:
            continue
        run = PairedRun(record_id=record_id, values=by_record[record_id],
                        observation_ids=observations.get(record_id, {}))
        (complete if run.complete_for(properties) else incomplete).append(run)

    return ReplicateJoin(
        material=referent,
        properties=tuple(properties),
        complete=tuple(complete),
        incomplete=tuple(incomplete),
        ambiguous=tuple(sorted(ambiguous)),
    )


def paired_values(join: ReplicateJoin, first: str,
                  second: str) -> Tuple[Tuple[float, float], ...]:
    """The pairs, in a STATED order -- by record id -- rather than an
    incidental one.

    Order is irrelevant to every statistic here, so this is not about
    correctness of the number. It is about the difference between an
    order that is chosen and an order that is inherited: the trap this
    module exists for is exactly an inherited order that looked like a
    chosen one."""
    for name in (first, second):
        if name not in join.properties:
            raise ValueError(f"{name!r} was not joined on; joined: {join.properties}")
    return tuple((run.values[first], run.values[second]) for run in join.complete)


def correlation(join: ReplicateJoin, first: str, second: str) -> Optional[float]:
    """Pearson rho over the RECOVERED pairing, or None where it is
    undefined.

    None is returned for the two DEFINITIONAL cases and no others:
    fewer than two pairs, and zero variance in either series. Those are
    not thresholds -- a correlation is not defined on one point or on a
    constant, and returning 0.0 or 1.0 for them would be inventing a
    result. No policy threshold on n is applied here, because choosing
    one is a decision about what evidence suffices, and this module
    measures rather than decides. The caller has `join.n`.

    IT REFUSES UNTIL THE CALLER HAS SAID WHAT THE PAIRS ARE. A
    correlation over replicate runs is a different object from a
    correlation over a set that happens to contain three summary rows,
    and the pool cannot tell them apart. Measured on a real replicate
    report's shape, the undeclared answer was n = 5 and rho = +0.9986
    where the truth is n = 2. That is the trap this module was written
    against, one layer up: a plausible recovery returning a confidently
    wrong number. So `declaring_runs` is required, and its absence
    raises rather than returning None -- None means "undefined on this
    data", and this is "you have not said what this data is".

    This says nothing about significance, and nothing about the
    material. It is a statistic over the pairs that were recovered.
    """
    if not join.runs_declared:
        raise UndeclaredRunsError(
            "correlation assumes its pairs are replicate runs, and nothing in "
            "the pool distinguishes a run from a transcribed Average or "
            "% RSD row. Call join.declaring_runs(record_ids) first")
    pairs = paired_values(join, first, second)
    if len(pairs) < 2:
        return None

    # NON-FINITE INPUT IS REFUSED BEFORE ANY ARITHMETIC, and this guard
    # exists because the clamp below made its absence dangerous rather
    # than merely untidy.
    #
    # An inf or NaN anywhere in the series propagates to a NaN quotient.
    # Unclamped that surfaced as `nan`, which is at least self-announcing
    # -- every comparison against it is False and a caller notices. But
    # `min(1.0, nan)` returns 1.0, because Python's min keeps its first
    # argument when the comparison is False. So the clamp silently
    # converted "this is not a number" into "these series are perfectly
    # correlated", which is the single most misleading value available.
    #
    # A bound that turns garbage into a confident answer is worse than
    # the out-of-range value it was added to fix. So the refusal comes
    # first, and the clamp only ever sees finite input.
    if any(not math.isfinite(value) for pair in pairs for value in pair):
        return None

    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    if variance_x == 0.0 or variance_y == 0.0:
        return None
    rho = numerator / math.sqrt(variance_x * variance_y)

    # CLAMPED TO [-1, 1], AND THIS IS NOT COSMETIC TIDYING.
    #
    # Pearson's rho is defined on [-1, 1], but the floating-point
    # quotient above is not confined to it. At n = 2 the correlation is
    # exactly +/-1 in exact arithmetic, so ANY rounding at all lands
    # outside the interval: measured here, |rho| > 1 in 15.4% of 200,000
    # random two-point draws (worst excess 4.44e-16). At n >= 3 it was
    # never observed in the same experiment.
    #
    # AND n = 2 IS THIS MODULE'S OWN CASE. The pairing this file exists
    # to recover is a replicate pair -- the docstring above records a
    # real report where "the truth is n = 2". So the one sample size the
    # defect touches is the one the module was written for.
    #
    # The excess is one ulp, but the consequence is not proportional to
    # its size: math.acos(rho), math.sqrt(1 - rho**2) and math.atanh(rho)
    # -- the angle between two series, a residual standard deviation, and
    # the Fisher z-transform used for every confidence interval on a
    # correlation -- all raise ValueError("math domain error") rather
    # than returning a slightly wrong number. A caller doing ordinary
    # statistics on this result gets a crash, not an inaccuracy.
    #
    # Clamping is sound BECAUSE the excess is bounded by rounding: this
    # returns the nearest representable value that is actually a
    # correlation. It is not masking a computational error -- the
    # two-pass form above is already the numerically stable one, and no
    # summation order removes this, since the true value IS the endpoint.
    return max(-1.0, min(1.0, rho))


def fragmentation(pool: EvidencePool, engine, material_natural_key: str,
                  property_name: str) -> Tuple[int, int]:
    """`(observations, comparison_groups)` for one property.

    WHAT THIS SURFACES AND WHY IT IS NOT A FIX. `_comparison_context`
    keeps every content key except `property` and the value key --
    `uncertainty` included. So replicates from an instrument that
    reports a per-run uncertainty, which is what a real one does, split
    into singleton groups: measured, five replicates whose uncertainty
    differs by 1 g/mol become FIVE groups of one, every disagreement
    None. Not an error, not a refusal, not a warning. Five groups of
    one.

    That rule is NOT changed here. Its docstring states the intent --
    absence is never treated as a match -- and differing VALUES
    splitting a group follows from the same rule rather than being a
    separate decision. Whether a per-run uncertainty belongs in a
    comparison context is a question about scientific semantics, which
    makes it a DECISION and not a measurement, and changing grouping
    semantics is a core-invariant change under bend_protocol. So the
    consequence is made VISIBLE instead: `observations > groups == 1`
    is a comparable set, and `groups == observations > 1` is the silent
    fragmentation, named.
    """
    answer = analyze(pool, engine,
                     MaterialQuestion(material_natural_key=material_natural_key,
                                      property=property_name))
    return len(answer.observed), len(answer.observed_comparison_groups)


def is_fragmented(pool: EvidencePool, engine, material_natural_key: str,
                  property_name: str) -> bool:
    """True when every observation landed in its own group, so no
    disagreement is computable anywhere -- the "five groups of one"
    condition, as a question that can be asked instead of a silence."""
    observations, groups = fragmentation(pool, engine, material_natural_key,
                                         property_name)
    return observations > 1 and groups == observations
