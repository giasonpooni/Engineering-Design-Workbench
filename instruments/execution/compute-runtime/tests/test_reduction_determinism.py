"""Reductions over NaN-capable data, and why a tolerance is the wrong test.

RECORDED BEFORE ANY GPU WORK. A parallel reduction computes a different
parenthesisation than a sequential fold, and invariance under
reassociation requires associativity. `min`/`max` over NaN-capable data
have neither associativity nor commutativity, and the failure is not a
rounding difference -- it is a DIFFERENT, PLAUSIBLE, FINITE ANSWER.

These reproduce in Python the numbers measured in C++ and recorded in
docs/REDUCTION_DETERMINISM.md, so a change in behaviour fails here
rather than drifting in prose. The suite requires no compiler.

WHY IT MATTERS TO THIS PROJECT rather than only to a future GPU port:
the same class already appeared in `correlation`, where a clamp turned
NaN into a confident 1.0. The answer there was to REFUSE non-finite
input before any arithmetic rather than make the arithmetic clever. The
same answer applies to a reduction: one that cannot receive a NaN does
not need to be associative over NaN.
"""

from __future__ import annotations

import functools
import itertools
import math

NAN = float("nan")


def cpp_min(a: float, b: float) -> float:
    """`std::min(a, b)` is `b < a ? b : a`.

    Every comparison with NaN is false, so it returns its FIRST argument
    whenever the comparison fails. Spelled out rather than using
    Python's `min`, whose NaN behaviour is its own and not the point.
    """
    return b if b < a else a


def _same(x: float, y: float) -> bool:
    return (math.isnan(x) and math.isnan(y)) or x == y


VALUES = (NAN, 1.0, 2.0, 3.0)


def test_the_min_used_in_reductions_returns_its_first_argument():
    assert math.isnan(cpp_min(NAN, 2.0))
    assert cpp_min(2.0, NAN) == 2.0


def test_commutativity_fails_on_exactly_the_measured_fraction():
    broken = sum(1 for a, b in itertools.product(VALUES, repeat=2)
                 if not _same(cpp_min(a, b), cpp_min(b, a)))
    assert broken == 6, f"commutativity broken in {broken}/16, measured 6"


def test_associativity_fails_on_exactly_the_measured_fraction():
    broken = sum(1 for a, b, c in itertools.product(VALUES, repeat=3)
                 if not _same(cpp_min(cpp_min(a, b), c),
                              cpp_min(a, cpp_min(b, c))))
    assert broken == 3, f"associativity broken in {broken}/64, measured 3"


def test_the_witness_returns_two_different_finite_numbers():
    """The rates matter less than this. Neither answer is NaN, so
    nothing in the output signals that anything went wrong."""
    left = cpp_min(cpp_min(2.0, NAN), 1.0)
    right = cpp_min(2.0, cpp_min(NAN, 1.0))
    assert left == 1.0
    assert right == 2.0
    assert not math.isnan(left) and not math.isnan(right)


def test_a_sequential_fold_and_a_pairwise_tree_disagree():
    """THE GPU-SHAPED CASE. A parallel reduction is the tree; the CPU
    reference is the fold. On `[2, 3, NaN, 1]` they return 1 and 2."""
    data = [2.0, 3.0, NAN, 1.0]
    fold = functools.reduce(cpp_min, data)
    tree = cpp_min(cpp_min(data[0], data[1]), cpp_min(data[2], data[3]))
    assert fold == 1.0
    assert tree == 2.0

    disagreeing = sum(
        1 for order in itertools.permutations(data)
        if not _same(functools.reduce(cpp_min, order),
                     cpp_min(cpp_min(order[0], order[1]),
                             cpp_min(order[2], order[3]))))
    assert disagreeing == 2, (
        f"{disagreeing}/24 orderings disagree, measured 2 -- and 2/24 is "
        f"why a handful of fixed fixtures would not find this")


def test_a_tolerance_cannot_distinguish_the_failure():
    """Why the obvious CPU/GPU agreement test is the wrong test: the
    difference is 1 versus 2, so any tolerance either accepts both or
    rejects both, and reports nothing about reassociation."""
    fold, tree = 1.0, 2.0
    for tolerance in (1e-12, 1e-6, 1e-3):
        assert abs(fold - tree) > tolerance      # a tight tolerance rejects
    assert abs(fold - tree) < 10.0               # a loose one accepts
    # neither outcome is evidence about associativity


def test_refusing_non_finite_input_removes_the_hazard_entirely():
    """The recommendation, driven. With NaN excluded at the boundary,
    fold and tree agree on every ordering -- so the reduction does not
    need to be associative over a value it can never receive."""
    clean = [2.0, 3.0, 5.0, 1.0]
    assert all(math.isfinite(v) for v in clean)
    for order in itertools.permutations(clean):
        fold = functools.reduce(cpp_min, order)
        tree = cpp_min(cpp_min(order[0], order[1]), cpp_min(order[2], order[3]))
        assert fold == tree == 1.0
