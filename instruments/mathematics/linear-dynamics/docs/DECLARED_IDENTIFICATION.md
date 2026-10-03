# Declared identification for integration sessions

`sidt.identify_declared(payload, execution_ref=...)` implements
`sidt.declared-lti-identification.v1`. It extends the existing `fit_lti` API with
retained evidence, timing, coordinate frames, a conditioning gate, and replay.
This bounded operation fits only `A` and `B`; the original `fit_lti` API still
supports optional `C` and `D`.

Run `python examples/declared.py` for an analytical synthetic example. Its
declared rows obey `x[k+1] = 0.5*x[k] + 2*u[k]`.

## Input contract

| Required field | Contract |
| --- | --- |
| `schema` | `sidt.declared-identification-input.v1` |
| `model_id` | Caller-declared model identity, distinct from evidence and executions |
| `clock_frame` | Common reference clock for all supplied sample times |
| `state_frame` | Explicit state-coordinate frame; distinct in meaning from the clock frame |
| `sample_interval` | Finite positive seconds |
| `state_names`, `state_units` | Ordered unique coordinate names and nonempty unit labels |
| `input_names`, `input_units` | Ordered unique input names and nonempty unit labels |
| `condition_limit` | Finite maximum permitted spectral condition number, at least one |
| `training` | Object with `states`, `inputs`, `sample_times`, `sample_refs`, `evidence_refs` |

`rcond`, `conditioning_reference`, and `holdout` are optional. Unknown keys are
refused. Numeric arrays are explicit finite JSON sample-row matrices. Training
has `N+1` state rows and `N` transition-input rows. Autonomous models use empty
input rows and empty input labels, as in `fit_lti`.

Every state row has one reference time and one unique `sample_ref`. Times must
increase by the declared interval, within absolute tolerance
`sample_interval * 1e-9` seconds. This tolerance concerns numeric representation,
not estimated time uncertainty. Epochs that lose the interval's precision are
refused. Sample times, their integer differences, the sample interval, and
numeric policy scalars must be exactly representable as float64 before any
conversion; a large integer cannot silently become a neighboring float. A
supplied floating-point fraction retains its declared binary64 value and the
bounded interval tolerance above. SIDT does not alter timestamps, interpolate, supply absent clock maps,
or prove calibration applicability. Upstream time/calibration records belong in
the retained evidence references and must be validated by the consuming session.

`evidence_refs` is a nonempty unique list. An optional holdout has the same five
data fields plus `independence: "declared_disjoint"`. State/input widths must
agree. Training and holdout references and time intervals must be disjoint.
These checks catch declared overlap; they do not authenticate observations or
establish physical independence between correlated experiments. A parent source
may be retained externally, while each partition receives its own evidence
reference. No holdout is silently created by splitting training data.

## Result and conditioning gate

| `numerical_result.status` | Meaning |
| --- | --- |
| `identified` | Full regressor rank and finite condition number no greater than the declared limit; candidate `A` and `B` are retained |
| `nonidentifiable` | Deficient regressor rank; no candidate |
| `ill_conditioned` | Full rank but condition is above the limit or not finite; no candidate |
| `unresolved` | Numerical SVD did not converge; no candidate |

Malformed declarations or nonfinite computed values raise `ValueError`.
`numerical_result.diagnostics` retains rank, singular values, relative cutoff,
sample/regressor counts, degrees of freedom, condition number and limit, plus
available training residuals and component sums of squares. An undefined or
nonfinite condition is JSON `null`, never a fabricated finite value. The
condition measure is the spectral 2-norm of the regressor matrix in the declared
coordinates. It changes with coordinate units and scaling; SIDT does not
silently whiten or rescale mixed physical quantities.

Only `identified` exposes `numerical_result.candidate`, containing `A`, `B`,
the original candidate digest, and ordered `fit_lti` metadata. Optional
`holdout_evaluation` contains component residuals and RMSE. It is explicitly
caller-declared evidence, not independent verification. Full rank of the
identification design and observability of a future measurement configuration
are separate gates.

Parameter covariance always remains
`{"status": "unknown", "matrix": null, ...}`. Residual covariance and a perfect
fit cannot establish coefficient uncertainty when noisy observed regressors
and error correlations are not modeled. Any downstream uncertainty forecast
using `A` and `B` must declare that it is **conditional on these fixed candidate
matrices**, preserve this unknown parameter covariance, and source its state,
process, measurement, and cross-covariance assumptions separately. The result
does not certify physical dynamics, stability, conservation, or model adoption.

## Identity and replay

The result uses schema `sidt.declared-identification-result.v1` and retains the
complete request in `inputs`. Canonical JSON has sorted keys, compact
separators, ASCII escaping, and no nonfinite numbers.

| Field | Bound content |
| --- | --- |
| `input_digest` | `sha256:` plus SHA-256 of the complete input declaration |
| `numerical_id` | `sidt:numerical:sha256:` plus SHA-256 of `numerical_result` |
| `execution_ref` | Caller-assigned occurrence identity |
| `result_id` | `sidt:result:sha256:` plus SHA-256 of all result fields except `result_id`, including execution and inputs |
| `verification_refs` | Initially empty; no verification identity is invented |

`replay_identification(result, execution_ref=...)` recomputes the retained
inputs and compares the complete original result with strict JSON identity. An
edited result is refused even if its hashes were recomputed. It then returns a
fresh occurrence: equal inputs and mathematical content retain their input and
numerical identities, while execution and result identities change. A reused
execution reference is refused. This is same-implementation replay in the same
numerical environment; it is not an independent verifier, cross-platform bitwise
promise, or evidence authentication.

CIW owns source-pinned provider execution and session construction; SET and ICRH
own their respective exchange and conformance checks. SIDT retains candidate
evidence and makes no canonical-state or ESM admission decision.
