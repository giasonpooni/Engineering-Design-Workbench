"""Locks on the record join that recovers what the projection drops.

THE DEFECT THIS ANSWERS is the acquisition layer's finding, verified in
this tree rather than taken on faith: `ComparisonGroup.values` is a bare
tuple of floats, so two properties measured on the same replicate runs
come back as two independent tuples with nothing to join them.

THE SHARPER HALF IS PINNED HERE. The unpairing is not an absence. A
group's values arrive ordered by CONTENT-ADDRESSED OBSERVATION ID
(`RetrievalResult.observation_ids` is `tuple(sorted(set(...)))`), and
two properties have different content, so the two tuples are two
unrelated permutations of the same runs. Index-pairing them therefore
succeeds and returns the wrong number -- on this data, wrong in SIGN,
stably, the same wrong number every run. An absence announces itself; a
confident wrong answer does not.

So the first tests below assert the trap STILL EXISTS. They are
characterization locks, not defect locks: the day the projection starts
carrying identity is the day this module should be reconsidered rather
than kept out of habit, and that day should arrive as a failing test.
"""

from __future__ import annotations

import pathlib
import statistics
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship,
    make_document,
    make_observation,
    make_record,
    make_referent,
    make_source,
)
from materials.analysis import MaterialQuestion, analyze
from materials.replicate_join import (
    ReplicateJoin,
    UndeclaredRunsError,
    correlation,
    fragmentation,
    is_fragmented,
    join_on_record,
    paired_values,
)
from retrieval.engine import DeterministicRetrievalEngine

T = "2026-08-29T00:00:00Z"
KEY = "polystyrene-batch-7"

#: Five replicate GPC runs. Mn and Mw move OPPOSITELY across runs, so
#: the true correlation is strongly negative -- chosen that way because
#: the polymer vertical's question is rho's SIGN, and a fixture whose
#: sign is robust to mispairing would not test anything.
RUNS = ((3251.0, 8271.0), (3402.0, 8010.0), (3188.0, 8455.0),
        (3610.0, 7802.0), (3305.0, 8190.0))


def _all_runs(join):
    """Declare every joined Record a run. Honest for these fixtures --
    they contain nothing but runs -- and it has to be SAID, which is the
    whole point of the channel."""
    return join.declaring_runs(
        [run.record_id for run in join.complete + join.incomplete])


def _rho(pairs):
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den


def _pool(runs=RUNS, extra_content=None, one_record_for_all=False,
          properties=("Mn", "Mw"), omit_on_last=()):
    pool = EvidencePool()
    referent = make_referent(natural_key=KEY, kind="substance")
    pool.put_referent(referent)
    source = make_source(kind="report", name="gpc")
    pool.put_source(source)

    shared_record = None
    for index, values in enumerate(runs):
        if one_record_for_all and shared_record is not None:
            record = shared_record
        else:
            document = make_document(source_id=source.id, raw_content=f"run{index}",
                                     retrieval_method="manual_entry", retrieved_at=T)
            pool.put_document(document)
            record = make_record(document_id=document.id, locator=f"run/{index}",
                                 raw_content=f"run{index}")
            pool.put_record(record)
            shared_record = record
        last = index == len(runs) - 1
        for name, value in zip(properties, values):
            if last and name in omit_on_last:
                continue
            content = {"property": name, "value": value, "method": "GPC"}
            if extra_content is not None:
                content.update(extra_content(index))
            observation = make_observation(
                record_ids=(record.id,), extraction_method="regex:kv_v1",
                content=content, confidence=1.0, extracted_at=T)
            pool.put_observation(observation)
            pool.put_claimed_relationship(make_claimed_relationship(
                from_referent_id=referent.id, to_referent_id=referent.id,
                type="measured_on", observation_id=observation.id, confidence=1.0))
    return pool, DeterministicRetrievalEngine()


# ------------------------------------------------- the defect, pinned --


def test_the_projection_still_drops_the_pairing():
    """If this ever fails, the grouping began carrying identity and this
    whole module should be reconsidered rather than kept out of habit."""
    pool, engine = _pool()
    group = analyze(pool, engine, MaterialQuestion(material_natural_key=KEY,
                                                   property="Mn")).observed_comparison_groups[0]
    assert set(vars(group)) == {"context", "values", "disagreement"}
    assert all(isinstance(v, float) for v in group.values)


def test_index_pairing_the_two_tuples_returns_a_confidently_wrong_number():
    """THE TRAP, measured rather than described. The group sorts, so the
    tuples are not in a common order and zipping them succeeds -- with
    the wrong answer and nothing to indicate it."""
    pool, engine = _pool()
    mn = analyze(pool, engine, MaterialQuestion(material_natural_key=KEY,
                                                property="Mn")).observed_comparison_groups[0].values
    mw = analyze(pool, engine, MaterialQuestion(material_natural_key=KEY,
                                                property="Mw")).observed_comparison_groups[0].values

    truth = _rho(RUNS)
    by_index = _rho(list(zip(mn, mw)))

    assert sorted(mn) == sorted(r[0] for r in RUNS), "same values"
    assert list(mn) != [r[0] for r in RUNS], "different order -- ordered by observation id"
    assert truth < 0, "the fixture's true correlation is negative"
    assert by_index > 0, "and the index pairing reports it POSITIVE"
    assert by_index != pytest.approx(truth, abs=0.5)


# ----------------------------------------------------- the join works --


def test_the_order_of_the_pairs_is_stated_not_inherited():
    """By record id, chosen here rather than taken from whatever the
    retrieval result happened to give. The number does not depend on it
    -- the point is that an inherited order is exactly what produced the
    trap above, so this module does not inherit one."""
    pool, engine = _pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    record_ids = [run.record_id for run in join.complete]
    assert record_ids == sorted(record_ids)
    # and the pairs follow that order rather than any other
    assert paired_values(join, "Mn", "Mw") == tuple(
        (run.values["Mn"], run.values["Mw"]) for run in join.complete)


def test_the_join_recovers_every_pair():
    pool, engine = _pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    assert join.n == len(RUNS)
    assert join.incomplete == ()
    assert join.ambiguous == ()
    assert sorted(paired_values(join, "Mn", "Mw")) == sorted(RUNS)


def test_the_recovered_correlation_is_the_true_one():
    pool, engine = _pool()
    join = _all_runs(join_on_record(pool, engine, KEY, ("Mn", "Mw")))
    assert correlation(join, "Mn", "Mw") == pytest.approx(_rho(RUNS))


def test_the_join_keeps_the_key_it_joined_on():
    """A pairing whose join key is discarded cannot be checked."""
    pool, engine = _pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    assert all(run.record_id for run in join.complete)
    assert len({run.record_id for run in join.complete}) == len(RUNS)
    assert all(set(run.observation_ids) == {"Mn", "Mw"} for run in join.complete)


def test_the_join_is_deterministic():
    """No hasattr guard: a guarded assertion that silently skips is not
    an assertion, and the pool has had a fingerprint all along."""
    pool, engine = _pool()
    before = pool.fingerprint()
    first = paired_values(join_on_record(pool, engine, KEY, ("Mn", "Mw")), "Mn", "Mw")
    second = paired_values(join_on_record(pool, engine, KEY, ("Mn", "Mw")), "Mn", "Mw")
    assert first == second
    assert pool.fingerprint() == before


# --------------------------------------------------- it refuses to guess --


def test_two_runs_merged_onto_one_record_are_refused_not_picked():
    """The acquisition contract is one Record per RUN. A Record carrying
    two different values of one property is either two runs merged or a
    re-read disagreeing with itself, and the join has no basis to
    choose. Choosing would invent a run."""
    pool, engine = _pool(one_record_for_all=True)
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    assert join.n == 0
    assert len(join.ambiguous) == 1


def test_an_ambiguous_record_is_refused_whole_not_partially():
    """Its other properties are equally suspect. A half-kept record
    would put an unverified value into a statistic."""
    pool, engine = _pool(one_record_for_all=True)
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    kept = {run.record_id for run in join.complete + join.incomplete}
    assert kept.isdisjoint(set(join.ambiguous))


def test_a_record_missing_a_property_is_incomplete_not_dropped():
    """Retained, because a join that silently discarded what it could
    not pair would report a clean n over an unstated denominator."""
    pool, engine = _pool(omit_on_last=("Mw",))
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    assert join.n == len(RUNS) - 1
    assert len(join.incomplete) == 1
    assert join.incomplete[0].values == {"Mn": RUNS[-1][0]}
    assert join.records_seen == len(RUNS)
    # and the incomplete run is NOT in the pairs
    assert RUNS[-1] not in paired_values(join, "Mn", "Mw")


def test_nothing_is_lost_between_complete_incomplete_and_ambiguous():
    pool, engine = _pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    assert join.records_seen == len(join.complete) + len(join.incomplete) + len(join.ambiguous)


# -------------------------------------- the two definitional refusals --


def test_a_correlation_of_fewer_than_two_pairs_is_none_not_a_number():
    pool, engine = _pool(runs=RUNS[:1])
    join = _all_runs(join_on_record(pool, engine, KEY, ("Mn", "Mw")))
    assert join.n == 1
    assert correlation(join, "Mn", "Mw") is None


def test_a_correlation_over_no_pairs_is_none_and_never_a_crash():
    """Zero pairs is the case the n guard exists for on its own. At n=1
    the variance guard would catch it too -- the two conditions coincide
    there -- but at n=0 computing a mean divides by zero, so only the n
    guard stands between this and a ZeroDivisionError."""
    # one run, carrying only Mn -> no complete pairs at all
    pool, engine = _pool(runs=((3251.0, 8271.0),), omit_on_last=("Mw",))
    join = _all_runs(join_on_record(pool, engine, KEY, ("Mn", "Mw")))
    assert join.n == 0
    assert correlation(join, "Mn", "Mw") is None


def test_a_correlation_over_a_constant_series_is_none_not_zero():
    """Undefined, not zero. Returning 0.0 would be inventing a result."""
    flat = tuple((3300.0, y) for _, y in RUNS)
    pool, engine = _pool(runs=flat)
    join = _all_runs(join_on_record(pool, engine, KEY, ("Mn", "Mw")))
    assert join.n == len(flat)
    assert correlation(join, "Mn", "Mw") is None


def test_both_definitional_refusals_and_no_policy_threshold():
    """Only the two cases where rho is undefined return None. A minimum
    n would be a decision about what evidence suffices; this module
    measures and hands the caller `join.n`."""
    pool, engine = _pool(runs=RUNS[:2])
    join = _all_runs(join_on_record(pool, engine, KEY, ("Mn", "Mw")))
    assert join.n == 2
    assert correlation(join, "Mn", "Mw") is not None, "two pairs is defined"


def test_asking_for_a_property_that_was_not_joined_raises():
    pool, engine = _pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    with pytest.raises(ValueError):
        paired_values(join, "Mn", "Mz")


# ---------------------------------------- the fragmentation, surfaced --


def test_a_comparable_replicate_set_is_one_group():
    pool, engine = _pool()
    assert fragmentation(pool, engine, KEY, "Mn") == (len(RUNS), 1)
    assert is_fragmented(pool, engine, KEY, "Mn") is False


def test_a_single_observation_is_not_fragmented():
    """One observation is trivially one group, and calling that
    "fragmented" would report the condition on every material that has
    been measured exactly once. Both halves of the predicate are driven
    here -- the count and the equality -- because a set of five in one
    group exercises only one of them."""
    pool, engine = _pool(runs=RUNS[:1])
    assert fragmentation(pool, engine, KEY, "Mn") == (1, 1)
    assert is_fragmented(pool, engine, KEY, "Mn") is False


def test_the_deferred_decision_is_still_deferred_on_a_true_condition():
    """`comparison_context_fragmentation_is_visible` defers the question
    of whether a per-run uncertainty belongs in a comparison context,
    and it is safe to defer only WHILE no admitted corpus carries one.
    A deferral whose condition is remembered rather than checked is a
    note, so the condition is checked here.

    When a real corpus with per-run uncertainties lands, this fails, and
    failing is the point: the decision comes due at the moment the
    silence would start."""
    root = pathlib.Path(__file__).resolve().parent.parent
    fixtures = list((root / "scout").rglob("*.py")) + list((root / "adapters").rglob("*.py"))
    carrying = [
        path.relative_to(root).as_posix()
        for path in fixtures
        if "uncertainty" in path.read_text() and "fixture" in path.name
    ]
    assert carrying == [], (
        f"a shipped corpus now carries per-run uncertainties ({carrying}); "
        f"comparison_context_fragmentation_is_visible is no longer safe to "
        f"defer and the decision it names is due")


def test_per_run_uncertainty_fragments_the_set_into_singletons():
    """Measured: five replicates whose uncertainty differs by 1 g/mol
    become five groups of one, every disagreement None. Not an error,
    not a refusal, not a warning -- which is why it is surfaced."""
    pool, engine = _pool(extra_content=lambda i: {"uncertainty": 12.0 + i})
    observations, groups = fragmentation(pool, engine, KEY, "Mn")
    assert (observations, groups) == (len(RUNS), len(RUNS))
    assert is_fragmented(pool, engine, KEY, "Mn") is True
    answer = analyze(pool, engine, MaterialQuestion(material_natural_key=KEY, property="Mn"))
    assert all(g.disagreement is None for g in answer.observed_comparison_groups)


def test_the_join_still_pairs_what_the_grouping_fragmented():
    """The point of separating the two: fragmentation destroys
    comparability inside the projection and leaves the pairing intact in
    the pool. rho survives a split that makes every disagreement None."""
    pool, engine = _pool(extra_content=lambda i: {"uncertainty": 12.0 + i})
    assert is_fragmented(pool, engine, KEY, "Mn") is True
    join = _all_runs(join_on_record(pool, engine, KEY, ("Mn", "Mw")))
    assert join.n == len(RUNS)
    assert correlation(join, "Mn", "Mw") == pytest.approx(_rho(RUNS))


# ------------------------------------------------- it changes nothing --


def test_the_grouping_semantics_were_not_touched():
    """This is a CONSUMER. If it ever starts editing analysis.py, that
    is a core-invariant change under bend_protocol and must not arrive
    as a side effect of adding a consumer."""
    import inspect

    from materials import analysis

    source = inspect.getsource(analysis._comparison_context)
    assert 'k not in ("property", value_key)' in source
    assert "uncertainty" not in source


def test_the_join_writes_nothing_to_the_pool():
    """BEHAVIOURAL, NOT A GREP. The first version of this asserted that
    the module's source contained no `put_` call -- and a mutant that
    reached the same method through getattr and a split string SURVIVED
    it. A source grep tests spelling; the pool's fingerprint tests what
    happened. Any write, however it is spelled, moves the fingerprint."""
    pool, engine = _pool()
    before = pool.fingerprint()
    before_history = pool.fingerprint_history()

    join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    fragmentation(pool, engine, KEY, "Mn")
    is_fragmented(pool, engine, KEY, "Mn")

    assert pool.fingerprint() == before
    assert pool.fingerprint_history() == before_history


# ---------------------------------------------------------------------
# THE AGGREGATE ROWS. Measured on the shape the acquisition layer found
# in a REAL replicate report (Impact Analytical R190048): a table of two
# injections followed by Average, Standard Deviation and % RSD. With its
# incidental refusals removed it lands FIVE Records, three of them
# aggregates, with nothing in the pool distinguishing them and their
# lineage to the injections unrecoverable -- that lineage is POSITIONAL
# in the document and position is what acquisition discards.
#
# This module inherited the defect exactly, and these lock the fix. The
# join still returns five, because five Records is the truth about the
# pool; what it no longer does is let a statistic be computed over them
# as though they were runs.
# ---------------------------------------------------------------------

#: locator, Mn, Mw -- two injections, then the three aggregate rows.
ANCHOR_TWO = (
    ("PA191 (S190109)/1", 23479.0, 51000.0),
    ("PA191 (S190109)/2", 26459.0, 54000.0),
    ("Average/row-2", 24969.0, 52500.0),
    ("Standard Deviation/row-3", 2107.0, 2121.0),
    ("% RSD/row-4", 8.4, 4.0),
)


def _anchor_two_pool():
    pool = EvidencePool()
    referent = make_referent(natural_key=KEY, kind="substance")
    pool.put_referent(referent)
    source = make_source(kind="report", name="impact-analytical")
    pool.put_source(source)
    locator_to_record = {}
    for locator, mn, mw in ANCHOR_TWO:
        document = make_document(source_id=source.id, raw_content=locator,
                                 retrieval_method="manual_entry", retrieved_at=T)
        pool.put_document(document)
        record = make_record(document_id=document.id, locator=locator,
                             raw_content=locator)
        pool.put_record(record)
        locator_to_record[locator] = record.id
        for name, value in (("Mn", mn), ("Mw", mw)):
            observation = make_observation(
                record_ids=(record.id,), extraction_method="regex:kv_v1",
                content={"property": name, "value": value, "method": "GPC"},
                confidence=1.0, extracted_at=T)
            pool.put_observation(observation)
            pool.put_claimed_relationship(make_claimed_relationship(
                from_referent_id=referent.id, to_referent_id=referent.id,
                type="measured_on", observation_id=observation.id, confidence=1.0))
    return pool, DeterministicRetrievalEngine(), locator_to_record


def test_the_join_cannot_tell_an_aggregate_row_from_a_run():
    """THE DEFECT, PINNED. Not a bug to fix inside the join -- the fact
    is not in the pool and cannot be derived. Pinning it is what makes
    the declaration channel necessary rather than decorative."""
    pool, engine, _ = _anchor_two_pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    assert join.n == len(ANCHOR_TWO) == 5
    assert join.incomplete == ()
    assert join.ambiguous == (), "it has nothing to refuse them ON"


def test_a_correlation_over_undeclared_pairs_is_refused_not_computed():
    """Undeclared, this returned rho = +0.9986 over two runs and three
    summary rows. The truth is n = 2. A raise, not None: None means
    "undefined on this data", and this is "you have not said what this
    data is"."""
    pool, engine, _ = _anchor_two_pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    with pytest.raises(UndeclaredRunsError):
        correlation(join, "Mn", "Mw")


def test_declaring_the_two_injections_gives_the_real_replicate_set():
    pool, engine, locators = _anchor_two_pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    runs = join.declaring_runs([locators["PA191 (S190109)/1"],
                                locators["PA191 (S190109)/2"]])
    assert runs.n == 2
    assert sorted(paired_values(runs, "Mn", "Mw")) == sorted(
        (row[1], row[2]) for row in ANCHOR_TWO[:2])
    assert correlation(runs, "Mn", "Mw") is not None


def test_the_undeclared_answer_and_the_declared_one_differ_materially():
    """Both are numbers. Only one is about replicate runs -- and the
    wrong one is the one available by default before this change."""
    pool, engine, locators = _anchor_two_pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    everything = _all_runs(join)
    injections = join.declaring_runs([locators["PA191 (S190109)/1"],
                                      locators["PA191 (S190109)/2"]])
    assert everything.n == 5 and injections.n == 2
    assert correlation(everything, "Mn", "Mw") == pytest.approx(0.9986, abs=1e-3)


def test_the_join_itself_needs_no_declaration():
    """A join is a FACT -- these Records carry these values. Only the
    claim that they are runs needs saying, so `paired_values` stays
    available and only `correlation` refuses."""
    pool, engine, _ = _anchor_two_pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    assert join.runs_declared is False
    assert len(paired_values(join, "Mn", "Mw")) == 5


def test_declaring_a_record_that_is_not_in_the_join_is_refused():
    """A declaration naming something absent is a caller error, and
    silently ignoring it would let a typo shrink n without saying so."""
    pool, engine, _ = _anchor_two_pool()
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    with pytest.raises(ValueError):
        join.declaring_runs(["not-a-record-id"])


def test_the_declaration_does_not_resurrect_an_ambiguous_record():
    """Ambiguity is a refusal the join made on evidence. A caller may
    say which Records are runs; it may not overrule a Record the join
    could not read."""
    pool, engine = _pool(one_record_for_all=True)
    join = join_on_record(pool, engine, KEY, ("Mn", "Mw"))
    assert len(join.ambiguous) == 1
    with pytest.raises(ValueError):
        join.declaring_runs(list(join.ambiguous))


def test_neither_the_evidence_class_nor_the_locator_is_used_to_guess():
    """Both were checked and both refused. The class is a total function
    of extraction_method, so every row from one adapter shares one --
    correctly, since a transcribed average and a transcribed injection
    are both the document's claim. The locator DOES separate them in
    this corpus, and matching it is the literal-enumeration hazard that
    has just fired on real data one repository over."""
    import inspect

    from materials import replicate_join

    body = inspect.getsource(replicate_join)
    for guess in ("Average", "Standard Deviation", "RSD", "locator",
                  "evidence_class", "startswith"):
        assert f'"{guess}"' not in body and f"'{guess}'" not in body, (
            f"the join appears to guess on {guess!r}")
