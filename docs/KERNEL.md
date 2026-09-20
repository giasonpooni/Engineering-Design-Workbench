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
`uncertainty-budget-v1` retains declared sources, units, distributions,
sensitivities and correlations. Its Monte Carlo and Welch–Satterthwaite paths
have the limitations stated by their APIs and tests. Traceability defaults to
`none_claimed`; documentary declarations alone do not authenticate a reference.

Run `python -m pytest` from a development installation. The checked-in digests
validate deterministic host record encoding, not field accuracy or metrological
traceability. No firmware binary or on-device timing guarantee is provided.
