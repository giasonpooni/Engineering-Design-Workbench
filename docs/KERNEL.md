# Measurement records and validation invariants

The implemented Python package records a declared measurement chain. It keeps
raw observations, indicated values, quality dimensions and delivery metadata
distinct. The included example is simulated and does not establish a physical
calibration, certified device or safety integrity level.

## Components

| Component | Implemented declaration |
| --- | --- |
| Board profile | Board identity and declared peripherals/pins |
| Measurement interface | Description of the raw signal source |
| Instrument profile | Quantity, units, range and declared uncertainty |
| Installation binding | The assembly's mounting or observed asset/region |
| Calibration | Versioned conversion, units, applicable range and citation |

Changing a calibration or installation does not rewrite historical observations.
A board pin label alone does not establish electrical compatibility.

## Observation and delivery identity

An observation uses the acquisition session and sequence for its identity.
Transport packet identity and delivery attempts are separate. A retry is another
delivery of the same observation, not another physical sample. Delivery metadata
is excluded from the observation's canonical SHA-256 commitment.

Missing raw input remains unavailable. No last-value hold or fabricated zero
stands in for a measurement. Unknown uncertainty is not treated as zero.
Device ticks retain their declared timestamp meaning; they are not an inferred
UTC observation time.

## Quality dimensions

| Dimension | Represented status |
| --- | --- |
| Acquisition | Received, unavailable, overrange, corrupt |
| Timing | Device clock, readout-only time, unknown |
| Calibration | Applicable, unsupported range, changed installation, none |
| Inference | Not run, updated, prediction only, outside model |

The host example does not run an observer. A status label or digest is not a
proof of the underlying physical quantity.

## Numerical validation

Numerical methods require checks against independent closed-form or published
reference values; reproducing a method's own earlier output is insufficient.
`uncertainty-budget-v2` retains declared sources, units, distributions,
sensitivities and correlations. Its Monte Carlo and Welch–Satterthwaite paths
have the limitations stated by their APIs and tests. Traceability defaults to
`none_claimed`; documentary declarations alone do not authenticate a reference.

Component deviations and widths must be finite and nonnegative, sensitivities
finite, sample counts integral and at least two, and divisors positive. Only
positive infinite degrees of freedom have an explicit special meaning. The
complete dimensionless correlation matrix must be symmetric and PSD; coefficients
must lie in [-1, 1], self-correlations equal one, and reverse declarations agree.
Duplicate record pairs are refused. Mutable budgets are revalidated at use.

PSD validation permits only eigenvalue roundoff within
`64 * float64_epsilon * dimension * max(1, spectral_radius)`. Singular models are
supported without jitter or matrix repair. The quadratic variance is summed
exactly over the validated float64 weighted contributions using rational
arithmetic; an 80-digit decimal square root is converted back to float64. This
preserves tiny independent uncertainties after large correlated cancellation.
Any negative quadratic variance is refused, including a numerically ambiguous
one within the PSD check's tolerance. Nonfinite or underflowed component products
and unrepresentable outputs are refused. These routines target small metrology
budgets, not large streaming covariance matrices.

Compatibility: version 0.2 emits `uncertainty-budget-v2` because the
`contributions().variance_share` field is now nullable: zero total uncertainty
makes the ratio undefined, so it is `None`/JSON `null`, not zero. For nonzero
totals this remains the diagonal ratio `(c_i*u_i)^2/u_c^2`; it excludes cross
terms, can exceed one, and is not an additive attribution for correlated inputs.
The v1 declaration reader remains supported and does not alter received records.
Re-serialization emits v2. Observation, assembly and evidence schemas/digests
are unchanged; consumers of budget records must handle null ratios explicitly.

Monte Carlo remains restricted to independent components and its declared
distributions; finite draws are checked before reporting, not treated as a
physical validation. Its existing Type A Student-t scale convention is unchanged:
the scale is `u`, not the Student-t population standard deviation. Welch–
Satterthwaite remains an uncorrelated-budget calculation.

Run `python -m pytest` from a development installation. The checked-in digests
validate deterministic host record encoding, not field accuracy or metrological
traceability. No firmware binary or on-device timing guarantee is provided.
