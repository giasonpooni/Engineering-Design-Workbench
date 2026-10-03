# Reductions, reassociation, and the test a GPU port would need

A note recorded **before** any GPU work, because it tells you what the
determinism test has to be, and that is cheaper to know now than to
discover from a kernel that disagrees with its CPU oracle.

## The claim

A parallel reduction computes a different **parenthesisation** than a
sequential fold. Invariance under reassociation requires associativity.
Floating-point addition is famously non-associative; less famously,
**`min`/`max` over NaN-capable data are neither associative nor
commutative**, and their failure is worse than addition's — it is not a
rounding difference but a different answer.

## Measured here, not cited

`g++ -O2`, x86-64, this container. Over `{NaN, 1, 2, 3}` with `std::min`:

| property | broken in |
|---|---|
| commutativity | **6 of 16** pairs |
| associativity | **3 of 64** triples |
| sequential fold vs pairwise tree | **2 of 24** orderings |

The witnesses matter more than the rates.

**Associativity.** `min(min(2, NaN), 1)` = **1**, but
`min(2, min(NaN, 1))` = **2**.

**Fold vs tree**, on the data `[2, 3, NaN, 1]`:

```
sequential fold  ->  1
pairwise tree    ->  2
```

Both answers are **finite and plausible**. No NaN reaches the output to
signal that anything happened. And it fails on roughly 8% of orderings,
so a casual test passes.

That is the dangerous shape: not a crash, not a NaN, not a tolerance
violation — a *different, believable number*, on a minority of inputs.

## Why `std::min` behaves this way

`std::min(a, b)` is `b < a ? b : a`. Every comparison with NaN is false,
so it returns **its first argument** whenever the comparison fails:

```
std::min(NaN, 2) -> NaN        std::min(2, NaN) -> 2
```

Order-dependent, which is precisely what a parallel reduction does not
preserve.

## The cross-backend hazard, shown without a GPU

Two definitions of "minimum" in the *same* standard library already
disagree:

| input | `std::min` | `fmin` (IEEE `minNum`-like) |
|---|---|---|
| `min(NaN, 2)` | `NaN` | **`2`** |
| `min(2, NaN)` | `2` | `2` |

Neither is a bug. They implement different, defensible semantics.

**Cited, not measured here:** PTX `min.f64` is reported to follow
`minNum` semantics — returning the non-NaN operand — which would put a
CUDA reduction on the `fmin` side of that table while a `std::min` host
path sits on the other. This container has no GPU and no CUDA toolkit
(`nvidia-smi` finds nothing), so **that half is unverified** and should
be checked against current PTX documentation before it is relied on.

The verified half is enough to establish the shape: two correct `min`
implementations can disagree on identical input, and **no tolerance
reconciles them, because they are computing different functions rather
than the same function to different precision.**

## What this means for a GPU port

For any engine that might reduce over belief blocks, covariance blocks or
clearance hypotheses on a GPU:

1. **A CPU/GPU agreement test with a tolerance is the wrong test.** The
   difference is not `1e-15`; it is `1` versus `2`. A tolerance either
   passes both or fails both, and says nothing.

2. **The test has to be exact equality over adversarial orderings** —
   the same multiset permuted, folded and tree-reduced, compared
   bit-for-bit. The rates above show why: at 2/24, a handful of fixed
   fixtures will not find it.

3. **Or eliminate the hazard rather than test for it:** refuse NaN at
   the boundary so the reduction never sees one. That is the cheaper
   fix, and it is the same rule as
   [`docs/NUMERICS.md`](NUMERICS.md) — where a clamp turned NaN into a
   confident `1.0` and the answer was to refuse non-finite input before
   any arithmetic, rather than to make the arithmetic clever.

Option 3 is the recommendation. A reduction that cannot receive a NaN
does not need to be associative over NaN.

## Locks

`tests/test_reduction_determinism.py` reproduces every measured number
above in Python, so a change in behaviour fails rather than drifts. The
C++ witnesses are recorded here as figures rather than run in CI: the
suite deliberately requires no compiler.
