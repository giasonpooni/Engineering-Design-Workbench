# Scalar linearization requirement

The optional `intervals` provider extends the existing `native-interop` workflow
and `ciw.native-interop.v1` operation with `scalar-square-interval.v1`. It reuses
the shared source, operation, execution, result, verification and workspace
records. It creates no parallel evidence store or admission path.

For the declared model `f(x)=x²`, the linear approximation at `x` is
`x²+2xu`. The polynomial identity leaves the exact remainder `u²`. This profile
asks whether `u²-error_limit ≤ 0` throughout a declared closed interval of `u`.
The identity is code-owned and independently tested; it is not a formal proof
or a statement about arbitrary nonlinear models.

| Returned enclosure `[lo, hi]` | Requirement outcome |
| --- | --- |
| `hi ≤ 0` | `holds_throughout` |
| `lo > 0` | `fails_throughout` |
| Otherwise | `inconclusive` |

These are conclusions about the declared enclosure. A valid inconclusive result
is a successful calculation. A malformed request, unavailable runtime or invalid
enclosure is a refusal. A result saying the requirement fails is also a valid
scientific result, not a failed process.

## Exact inputs and retained arithmetic

The payload has exactly `model`, `x`, `variation_lower`, `variation_upper` and
`error_limit`. The model is `scalar-square.v1`; each numeric field is a reduced
`{"numerator": integer, "denominator": positive_integer}`. Numerator magnitude
and denominator are at most 1,000,000. Zero is `0/1`. No floats, booleans, implicit
decimal parsing, expressions or program paths are accepted.

The anchor and the entire changed-state interval must stay within `[-100,100]`;
variations are within `[-200,200]`, ordered, and the error limit is in `[0,40000]`.
Quantities are dimensionless, the frame is `dimensionless-cartesian`, and the
clock is `not_applicable`. There are no observations, covariance or calibration
claims in this mathematical profile.

Julia constructs guaranteed Float64 intervals directly from exact rationals,
sets `rounding=:correct` and `power=:slow`, and evaluates `u²-error_limit`.
The error limit is also explicitly constructed as an interval. Only finite,
ordered, common (`com`), guaranteed output is accepted. Every endpoint is retained
as its 16-digit IEEE754 binary64 bit pattern in network-order hexadecimal,
avoiding a second decimal conversion. Construction and rounding configuration
are retained with the output.

These choices follow the upstream [construction](https://juliaintervals.github.io/IntervalArithmetic.jl/stable/manual/construction/)
and [configuration](https://juliaintervals.github.io/IntervalArithmetic.jl/stable/manual/configuration/)
interfaces. The version actually exercised is recorded by the locked runtime
and [qualification report](INTERVAL_REQUIREMENT_VALIDATION.md).

After execution, a separate Python `Fraction` reference computes the exact
minimum/maximum of the polynomial over the original rational interval. Returned
binary endpoints are interpreted as exact rationals and must contain both
extrema, with **no tolerance**. A one-ULP inward bound fails this check. A wider
enclosure can legitimately remain inconclusive even if the exact reference
would decide the requirement. The shared check's `max_abs_discrepancy=0` denotes
no containment violation, not equality of enclosure and exact extrema.

## Execution and replay

The framed worker accepts only the fixed profile. SCR supervises its process,
request/output/diagnostic budgets and byte commitments. Operator configuration
selects the runtime; untrusted payloads cannot choose an executable. Qualification
binds the exact SCR revision/tree, Julia executable and worker/project/manifest
bytes, plus the declared package identity. Source-to-binary and complete depot
attestation remain unestablished.

Reopening validates retained structure, commitments, metadata and sign-derived
classification without loading Julia or evaluating the exact oracle. It is
inspection of historical evidence, not a fresh enclosure check. Replay requires
the original qualified runtime and creates new execution/result occurrences.
Byte identity and reference containment remain distinct checks. Coherent local
record fabrication is not ruled out by unsigned hashes.

Provision the locked Julia environment once, then run the optional gate with
an installed CIW wheel and an operator binding containing `scr`, `host`,
`host_sha256`, `provider: "intervals"`, `executable`, `runtime` and `depot`:

```powershell
julia --startup-file=no --project=runtimes/interval-requirement -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'
python scripts/check_interval_requirement.py run --binding interval-binding.json --fixtures examples/interval-requirement/fixtures.json --output interval-evidence
python scripts/check_interval_requirement.py inspect --workspace interval-evidence/workspace.json --artifacts interval-reopened
```

Use the Julia version and exact closure from the runtime manifest; the command
does not qualify whichever `julia` happens to be on PATH. Provider execution is
offline after provisioning. The gate retains source fixtures, outcomes,
execution costs, complete workspace history and explicit fresh replay. The
general [native operation API](NATIVE_INTEROP.md) also accepts this profile.

An enclosure establishes a bounded numerical claim about this supplied model
and interval. It does not establish the physical validity of either, a confidence
level, SP1 verification, ESM admission, or equipment authorization.
