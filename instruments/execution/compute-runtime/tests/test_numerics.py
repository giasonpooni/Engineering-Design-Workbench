"""Numerical locks on the statistics this project publishes.

WHY THESE ARE SEPARATE FROM THE BEHAVIOURAL SUITE. Every other test here
asks whether a function returns the value the design intends. These ask
whether that value is a real number of the kind it claims to be -- a
correlation inside [-1, 1], a variance that is the estimator its
docstring names. Those are different questions, and the second one is
invisible to the first: a correlation of 1.0000000000000002 satisfies
every assertion anyone would think to write about a perfect correlation,
and then raises ValueError inside the caller's `acos`.

WHAT THIS FOUND. `correlation` returned |rho| > 1 in 15.4% of random
two-point draws -- and n = 2 is the replicate pair the module was
written to recover, so the one sample size affected was its own case.
Not found by reading the formula, which is the textbook two-pass form
and is correct; found by running it 200,000 times and looking at the
range of the output.

MEASURED, NOT ASSUMED. The counts below are exact for their seeds. A
test that asserted "clamping happens" by reading the source would test
spelling; these drive the function over the inputs where the defect
actually lives.
"""

from __future__ import annotations

import math
import pathlib
import random
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evidence.types import make_referent  # noqa: E402
from materials.replicate_join import (  # noqa: E402
    PairedRun,
    ReplicateJoin,
    correlation,
)


def _join(pairs):
    runs = tuple(
        PairedRun(record_id=f"r{index}",
                  values={"a": x, "b": y},
                  observation_ids={"a": f"oa{index}", "b": f"ob{index}"})
        for index, (x, y) in enumerate(pairs))
    return ReplicateJoin(
        material=make_referent(natural_key="m", kind="material"),
        properties=("a", "b"), complete=runs, incomplete=(), ambiguous=(),
        runs_declared=True)


# ------------------------------------------- a correlation is bounded --


def test_rho_stays_inside_its_interval_at_the_size_that_broke_it():
    """n = 2, where rho is exactly +/-1 in exact arithmetic so ANY
    rounding lands outside. Before the clamp: 30,745 of 200,000 draws
    on this seed. The count is what makes this a measurement rather
    than a gesture -- a handful of samples would have missed it."""
    random.seed(11)
    outside = checked = 0
    for _ in range(20000):
        pairs = [(random.gauss(0, 1), random.gauss(0, 1)) for _ in range(2)]
        rho = correlation(_join(pairs), "a", "b")
        if rho is None:
            continue
        checked += 1
        if abs(rho) > 1.0:
            outside += 1
    assert checked > 15000, "too few defined results to be testing anything"
    assert outside == 0, f"{outside} of {checked} results were not correlations"


def test_rho_stays_inside_its_interval_at_larger_sizes_too():
    """n >= 3 never exhibited the defect, so this direction guards
    against a clamp that silently broke ordinary results while fixing
    the endpoint case."""
    random.seed(13)
    for size in (3, 5, 10):
        for _ in range(3000):
            pairs = [(random.gauss(0, 1), random.gauss(0, 1)) for _ in range(size)]
            rho = correlation(_join(pairs), "a", "b")
            assert rho is None or -1.0 <= rho <= 1.0


def test_the_clamped_result_survives_the_operations_that_used_to_crash():
    """THE POINT OF THE CLAMP. One ulp of excess is not a small error in
    consequence -- `acos` and `sqrt(1 - rho^2)` raise ValueError rather
    than returning a slightly wrong number, so a caller doing ordinary
    statistics got a crash instead of an inaccuracy.

    AND ONE OPERATION IS NOT RESCUED, WHICH IS CORRECT. The Fisher
    z-transform still raises at exactly +/-1, because atanh genuinely
    diverges there: the z of a perfect correlation is infinite, and no
    clamp can or should invent a finite value for it. The difference the
    fix makes is the REASON for the failure. Before, atanh refused a
    number that was not a correlation at all. Now it refuses a
    correlation that truly has no finite z -- a fact about the data,
    which the caller can handle, rather than an artefact of rounding,
    which they cannot."""
    pairs = [(-1.2158745995120142, -1.2928644508468463),
             (0.7059279025963143, 0.4740857132903602)]
    rho = correlation(_join(pairs), "a", "b")
    assert rho == 1.0
    assert math.acos(rho) == 0.0
    assert math.sqrt(1.0 - rho * rho) == 0.0

    with pytest.raises(ValueError):
        math.atanh(rho)

    # and z IS finite everywhere strictly inside, which is what makes
    # the endpoint a real boundary rather than a general breakage
    inside = correlation(_join([(0.0, 0.0), (1.0, 3.0), (2.0, 1.0), (3.0, 4.0)]), "a", "b")
    assert math.isfinite(math.atanh(inside))


def test_a_clamp_must_not_turn_garbage_into_a_perfect_correlation():
    """THE REGRESSION THE CLAMP INTRODUCED, and the reason the finite
    guard runs first.

    An inf or NaN in either series propagates to a NaN quotient.
    Unclamped that surfaced as `nan` -- self-announcing, since every
    comparison against it is False. But `min(1.0, nan)` returns 1.0,
    because Python's `min` keeps its first argument when the comparison
    is False. So the bound added to fix an out-of-range value silently
    converted "not a number" into "perfectly correlated", which is the
    most misleading value in the range.

    Found by pursuing a mutant that looked equivalent and was not."""
    infinity, not_a_number = float("inf"), float("nan")
    for pairs in ([(infinity, 1.0), (2.0, 3.0)],
                  [(1.0, not_a_number), (2.0, 3.0)],
                  [(infinity, infinity), (2.0, 3.0)],
                  [(1.0, 2.0), (3.0, -infinity)]):
        assert correlation(_join(pairs), "a", "b") is None, (
            f"non-finite input produced a correlation: {pairs}")

    # the guard must not have swallowed ordinary data with it
    assert correlation(_join([(0.0, 0.0), (1.0, 2.0), (2.0, 3.0)]), "a", "b") is not None


def test_rho_respects_the_lower_bound_as_well_as_the_upper():
    """A one-sided clamp passes every test that only ever drives rho
    toward +1. Anti-correlated pairs at n = 2 are where -1 is the exact
    answer, so any rounding lands BELOW the interval -- the mirror image
    of the defect that started this, and invisible to a `min(1.0, rho)`
    check."""
    random.seed(17)
    outside = checked = 0
    for _ in range(20000):
        x = random.gauss(0, 1)
        y = random.gauss(0, 1)
        # deliberately opposed, so the exact rho is -1
        pairs = [(x, -x * 1.7 + 0.3), (y, -y * 1.7 + 0.3)]
        rho = correlation(_join(pairs), "a", "b")
        if rho is None:
            continue
        checked += 1
        if rho < -1.0:
            outside += 1
    assert checked > 15000, "too few defined results to be testing anything"
    assert outside == 0, f"{outside} of {checked} results were below -1"
    assert correlation(_join([(0.0, 4.0), (1.0, 2.0)]), "a", "b") == -1.0


def test_the_clamp_did_not_flatten_real_correlations():
    """A clamp that returned 1.0 for everything would pass every test
    above. Anti-correlation, independence and partial correlation must
    still come back distinct and correctly signed."""
    perfect = correlation(_join([(0.0, 0.0), (1.0, 2.0), (2.0, 4.0)]), "a", "b")
    inverse = correlation(_join([(0.0, 4.0), (1.0, 2.0), (2.0, 0.0)]), "a", "b")
    partial = correlation(_join([(0.0, 0.0), (1.0, 3.0), (2.0, 1.0), (3.0, 4.0)]), "a", "b")

    assert perfect == 1.0
    assert inverse == -1.0
    assert -1.0 < partial < 1.0
    assert partial > 0.0
    assert len({perfect, inverse, partial}) == 3


def test_rho_is_undefined_rather_than_invented_where_it_has_no_value():
    """A constant series has no correlation, and returning 0.0 or 1.0
    would be inventing one. Both directions, and the too-few-points
    case."""
    assert correlation(_join([(1.0, 5.0)]), "a", "b") is None
    assert correlation(_join([(1.0, 5.0), (1.0, 9.0)]), "a", "b") is None
    assert correlation(_join([(1.0, 5.0), (4.0, 5.0)]), "a", "b") is None


def test_rho_is_unchanged_by_a_shift_that_would_wreck_a_naive_formula():
    """The two-pass form is the numerically stable one, and this is what
    keeps it. The single-pass E[xy] - E[x]E[y] identity loses all
    significance at this offset through catastrophic cancellation."""
    base = [(0.0, 0.0), (1.0, 2.0), (2.0, 3.0), (3.0, 7.0)]
    reference = correlation(_join(base), "a", "b")
    for offset in (1e6, 1e8, 1e10):
        shifted = [(x + offset, y + offset) for x, y in base]
        assert correlation(_join(shifted), "a", "b") == reference


# --------------------------------------- the variance names its form --


def test_the_predictive_variance_is_the_unbiased_estimator():
    """THE DIVISOR CHANGED, and the docstrings that disagreed about it
    were the thing that surfaced the question.

    The module called this `population variance` in two places and
    `sample variance` in three others -- different estimators, since the
    latter conventionally carries Bessel's correction. It computed the
    former. It now computes and names the latter, because divisor n is
    biased low by (n-1)/n and that factor varies with n, so it did not
    cancel when ranking cells with different sample counts.

    Pinned by arithmetic a reader can do by hand, so this test can
    disagree with the implementation rather than echo it."""
    values = (80.0, 90.0, 100.0)
    mean = 90.0
    unbiased = sum((v - mean) ** 2 for v in values) / 2        # 100.0
    plug_in = sum((v - mean) ** 2 for v in values) / 3         # 66.66...

    variance = _predict_variance(values)

    assert variance == unbiased == 100.0
    assert variance != plug_in


def test_the_estimator_is_unbiased_where_the_old_one_was_not():
    """The property the change was made FOR, measured rather than
    asserted. Divisor n recovered a true variance of 100 as roughly 50
    at n = 2; the unbiased form recovers it. Averaged over enough draws
    that the difference cannot be sampling noise."""
    random.seed(23)
    true_variance = 100.0
    for size, tolerance in ((2, 3.0), (5, 1.5)):
        total = 0.0
        trials = 60000
        for _ in range(trials):
            drawn = tuple(random.gauss(0.0, 10.0) for _ in range(size))
            total += _predict_variance(drawn)
        estimated = total / trials
        assert abs(estimated - true_variance) < tolerance, (
            f"n={size}: recovered {estimated:.2f}, expected ~{true_variance}")


def _predict_variance(values):
    """Build a real cell and read the variance THROUGH `predict`.

    An earlier version of this helper recomputed the formula here
    instead of calling the function -- and a mutation battery caught it
    immediately: swapping the shipped divisor to `n - 1` left this test
    green, because the test was checking its own arithmetic rather than
    the code's. That is this project's own mirror rule appearing inside
    its verification: a copy that agrees with the source proves nothing
    about the source, and byte-identity is what makes it convincing.

    So the cell is constructed and `predict` is invoked, which also
    means the state key resolution is exercised on the same path a
    caller would use."""
    from materials.candidates import ActionCandidate
    from materials.model_state import make_model_state, predict, resolve_model_state_key, Sample

    formulation = make_referent(natural_key="f", kind="formulation")
    context = {"temperature_c": 25}
    key = resolve_model_state_key(formulation.id, "melting_point", context)
    state = make_model_state({
        key: tuple(Sample(value=v, observation_id=f"o{i}")
                   for i, v in enumerate(values))})
    candidate = ActionCandidate(
        id="c1", action_class="measure", requirement_ids=("req-1",),
        formulation=formulation, property="melting_point", role="primary",
        target_context=context, existing_evidence_ids=())
    return predict(state, candidate).uncertainty


def test_one_sample_yields_no_uncertainty_rather_than_zero():
    """With divisor n - 1 this is DEFINITIONAL: one sample gives 0/0, so
    `None` is the only available answer.

    Under the previous divisor it was a judgement call, and the right
    one -- zero would have asserted certainty from a single observation.
    The two conventions agree about n = 1 for different reasons, and
    this one needs no argument."""
    assert _predict_variance((42.0,)) is None
    # and two samples DO yield one, so the refusal is about the count
    # rather than about never producing a variance at all
    assert _predict_variance((42.0, 44.0)) == 2.0


def test_the_module_names_one_estimator_and_not_two():
    """The contradiction this replaced was five docstrings in one file
    naming two different estimators. A reader deciding whether to trust
    the number has to be able to find out which it is."""
    source = (ROOT / "materials" / "model_state.py").read_text()
    assert "sample variance" in source
    assert "divisor n - 1" in source
    # `population variance` may appear only in the recorded explanation
    # of what the divisor USED to be, never as a name for what it is
    for line in source.splitlines():
        stripped = line.strip()
        if "population variance" in stripped and not stripped.startswith("#"):
            raise AssertionError(
                f"`population variance` names the estimator again: {stripped!r}")
