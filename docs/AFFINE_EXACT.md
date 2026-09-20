# `cbsr.affine-exact.v1`

This operation enforces a caller-declared exact affine law `C x = d`. It does not
invent that law, infer its physical truth, perform sensor fusion, or admit evidence.

## Mathematical operation

Given candidate `x`, symmetric positive-semidefinite full covariance `P`, and
declared exact `C,d`:

```math
r = Cx-d,\quad S=CPC^\top,\quad T=r^\top S^+r,
```

```math
x_* = x-PC^\top S^+r,\quad P_*=P-PC^\top S^+CP.
```

The implementation solves exact linear systems rather than numerically forming
a pseudoinverse. Dependent rows are retained in diagnostics; residual rank comes
from an exact PSD Schur test. If `r` is outside the range of `S`, the declaration
conflicts with an exact deterministic direction and is refused. A zero residual
in an exact zero-variance direction is a supported no-op, not an inferred sensor
agreement or a statistical coverage claim.

If `T > max_normalized_residual`, the receipt is held with the original candidate
retained and no corrected state. The positive finite threshold is supplied by
the caller; CBSR does not invent a confidence level or diagnose a unique fault.
Its chi-square interpretation would require a justified Gaussian model and a
correct declared law; neither is established by a numerical receipt.

## Request

The complete example is [affine_exact.json](../examples/affine_exact.json).
Unknown fields are rejected, including unsupported uncertainty fields.

| Field | Meaning |
| --- | --- |
| `state_id` | Incoming candidate identity; never reused as accepted output-state identity |
| `estimate`, `covariance` | Ordered finite binary64 vector and full square matrix; no inferred block diagonals |
| `state_labels`, `state_units`, `frame_ref` | Explicit coordinate order, units and frame; no conversion is performed |
| `constraints.constraint_id` | Identity of the caller's declaration, separate from evidence supporting it |
| `constraints.coefficients`, `rhs`, `row_units` | Full `C`, `d`, row units; coefficient dimensions are declared row-unit/state-unit ratios |
| `constraints.coefficient_policy` | Must be `declared_exact`; coefficients **and right-hand sides** are fixed exact declarations |
| `crosscov_policy` | `declared`: all entries supplied; `declared_zero`: all off-diagonal entries must actually be zero; `unknown`: refused |
| `max_normalized_residual` | Positive finite maximum allowed `T`; equality passes |
| `evidence_refs` | Nonempty caller-supplied evidence references; no source bytes are fetched or authenticated |
| `execution_id` | Occurrence identity; must not alias state, evidence, operation, constraint, or source-result identity |
| `source_result_id`, `source_result_digest` | Optional pair linking an upstream result and SHA-256; retained assertion, verified by the caller's replay layer |

State and constraint sizes are each 1..16. Lists are required. Numeric strings,
booleans, complex values, NaN, infinity, integers not exactly representable in
binary64, and implicit numeric coercions are rejected. The CLI also rejects
duplicate JSON keys and requests over 1 MiB. Units are explicit labels, not a
dimensional-analysis engine; the caller remains responsible for a meaningful law.
Decimal JSON literals that overflow or turn a nonzero mantissa into binary64 zero
are rejected during parsing, before that information can be lost. A genuine zero
such as `0e-999` remains valid.

## Numerical guarantees and refusals

Arithmetic uses Python `Fraction` over the exact supplied binary64 values. There
is no tolerance-based symmetry repair, eigenvalue clipping, jitter, rank cutoff,
or silent independence assumption. Input and internal covariance must be exactly
PSD in this representation. This is intentionally conservative: a matrix accepted
by another instrument under a roundoff tolerance may be refused here.

`condition_inf_independent_rows` describes the first independent principal block
of `S` in the declared row coordinates; values above `1e12` are refused. This
coordinate-dependent diagnostic is not a claim of coordinate-invariant model
quality. A caller may explicitly rescale a declaration, producing a new retained
request, rather than having CBSR silently change it.

Output uses nearest binary64 encoding. Any nonzero number becoming zero or any
overflow is refused. Rounded covariance must remain exactly PSD and may not lose
a positive direction relative to the rational posterior. Some legitimate systems
cannot meet this conservative finite-output contract and will be refused instead
of returned with false certainty.

An exact rational solution may have no exact binary64 state representation:
`3*x=1` is a simple example. Therefore:

- `rational_constraint_residual_zero` concerns the internal rational solution.
- `output_constraint_residual_zero` concerns the actual delivered binary64 state.
- `residual_post` is recomputed exactly from the delivered state before encoding.
- `residual_covariance_post` is recomputed from the delivered covariance.

For `3*x=1`, the operation can accept with a nonzero reported output residual; it
does not claim the encoded state exactly satisfies the law. A downstream operation
requiring exact encoded closure must additionally require
`output_constraint_residual_zero`, or explicitly budget the reported rounding
residual. Accepted means the defined bounded numerical operation completed, not
that a physical or admission claim is established.

## Receipt and replay identities

`candidate` retains raw numeric input. `reconciled` and `output_state_id` exist
only for accepted results; held/refused receipts never promote a corrected state.
Every receipt retains the entire request, request digest, input-state and
constraint IDs, explicit evidence references, diagnostics, status and reason.

| Identity | Scope |
| --- | --- |
| `operation_id` | Versioned mathematical operation, fixed `cbsr.affine-exact.v1` |
| `execution_id` | Caller-supplied invocation occurrence |
| `numerical_result_id` | SHA-256 over operation, normalized mathematical input and scientific output; excludes occurrence, evidence, input-state, constraint-declaration label and upstream-result identities |
| `output_state_id` | SHA-256 over parent-state identity and numerical-result identity; distinct from incoming state even on an accepted no-op |
| `result_id` | SHA-256 of the complete receipt before adding `result_id`; binds the retained request, source assertions, evidence refs and execution |

Hash canonicalization is Python JSON with sorted keys, compact separators, ASCII
escaping and no nonfinite values. The numerical identity normalizes equivalent
integer/float encodings and signed zero. Receipt identity retains those input
distinctions. These are local operation contracts, not a new stack-wide protocol.

`source_binding_verification` is `caller_assertion_only`: a hash reference alone
is not proof that a supplied candidate came from that result. The workbench must
verify exact source bytes, derivation, pinned operation and replay equivalence
before presenting a bound verification record to ESM. CBSR issues no verification
or admission identity and all physical-validity/fault-isolation/admission/stability
claims remain false.

## Validation boundaries

Analytic tests cover equal and unequal uncertainty, correlated camera/gauge
agreement with retained common-reference uncertainty, dependent/inconsistent
rows, exact nullspaces, hold policy, and identity separation. Adversarial cases
cover mixed scales, symmetry, false-zero cancellation/underflow, unsupported
uncertainty, coercion, conditioning, and output rounding.

Four optional live-provider tests check exact revisions and fixture hashes in
[cross-instrument-pins.json](../validation/cross-instrument-pins.json). FSRT is
compared only on its declared-exact mass balance and common-level camera/gauge
system. GTE is compared at an on-circle tangent basepoint, with a separate negative
case proving that tangent reconciliation is not nonlinear circle projection.
These are tested mathematical overlaps, not imports of a domain plant into CBSR,
not a claim that FSRT's whole test suite is green, and not an uncertain-row solver.
