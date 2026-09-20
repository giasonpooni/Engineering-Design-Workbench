# Draft telemetry feature exchange contract

## Status and claim boundary

This document is a **proposed v1 domain contract**, not an implemented schema or
registered operation. It defines the minimum information an implementation must
retain before the component can be integrated into the Computational
Instrumentation Workbench.

Contract conformance would establish structural eligibility and replay
sufficiency within the checks actually implemented. It would not establish
sensor truth, calibration validity, physical applicability, anomaly existence,
model adequacy or independent verification.

## Record separation

The domain boundary uses three conceptual records:

| Record | Purpose | May assert |
| --- | --- | --- |
| `TelemetryWindow` | Binds a bounded view over retained samples | Which samples, times, channels and policies define the window |
| `TelemetryFeatureRecord` | Records deterministic or declared derived quantities | What the named execution computed from the referenced window |
| `StreamQualityDiagnostic` | Reports stream condition or candidate events | What diagnostic values and thresholds were produced, not that a physical fault is verified |

These records do not replace the stack's evidence, execution, result or
verification artifacts. A production serialization must map each record to
those existing identities explicitly.

## `TelemetryWindow`

Required information:

| Field | Requirement |
| --- | --- |
| `window_id` | Stable identity for this window declaration; distinct from source artifact identities |
| `source_observation_refs` | Non-empty ordered or explicitly indexed references to retained observations |
| `channel_id` | Stable channel identity |
| `value_unit` | Unit of input samples; dimensionless must be explicit |
| `frame` | Frame/axis declaration when applicable; otherwise explicit `not_applicable` semantics |
| `event_time_start`, `event_time_end` | Closed/open support convention must be declared |
| `received_by` | Availability cutoff used for causal evaluation |
| `clock_basis` | Clock/timebase identity and mapping reference where needed |
| `sample_order` | Rule used to order equal or ambiguous timestamps |
| `sample_count` | Count presented to the operation before padding or imputation |
| `missingness` | Missing count/mask/reference and its interpretation |
| `late_data_policy` | Reject, revise, buffer or another versioned policy |
| `out_of_order_policy` | Reject, reorder within a bound or another versioned policy |
| `calibration_refs` | Ordered list; empty is allowed and not equivalent to calibrated |

The window must not embed corrected values as though they were the original
observations. If a transformation creates replacement sample values, those
values are a derived artifact with their own identity and source references.

## Operation specification

An execution request must bind the full transformation, including:

- operation identifier and semantic version;
- implementation revision and numeric backend;
- `causal` or `offline` mode;
- window length and units;
- hop/stride and overlap convention;
- boundary/padding policy;
- detrending and centering policy;
- window function and its parameters;
- transform type, length, normalization and frequency-coordinate convention;
- filter coefficients or a content-addressed filter specification;
- initial filter-state identity and reset/continuation rule;
- missing-sample and non-finite-value policy;
- floating-point precision and deterministic-mode declaration; and
- any feature definitions, thresholds and output ordering.

A change to any result-affecting field creates a different operation
configuration or execution identity. Human-readable labels are not sufficient
identity.

## `TelemetryFeatureRecord`

Required information:

| Field | Requirement |
| --- | --- |
| `feature_record_id` | Identity distinct from operation, execution and input identities |
| `window_ref` | Exact `TelemetryWindow` consumed |
| `operation_ref` | Declared operation semantics |
| `execution_ref` | This invocation/attempt |
| `created_at` | Processing timestamp with explicit UTC form |
| `mode` | `causal` or `offline` |
| `features` | Ordered named values or arrays with units and coordinates |
| `frequency_axis` | Values, unit, ordering and one-/two-sided convention when spectral output exists |
| `quality_ref` | Associated diagnostic identity, if emitted |
| `uncertainty` | Reported, estimated, propagated, unknown or not applicable; missing is not zero |
| `filter_state_in_ref`, `filter_state_out_ref` | Required for stateful continuation; reset must be explicit |
| `warmup_status` | Whether all, part or none of the output is in transient/warm-up state |
| `source_observation_refs` | Retained directly or transitively with a testable resolution path |
| `replay_ref` | Replay fixture/session identity when produced under replay |

Feature arrays must declare their coordinates and ordering. A bare numeric array
is ineligible because consumers cannot safely infer bins, units, sidedness,
channel order or frame.

## `StreamQualityDiagnostic`

Required information:

- diagnostic identity and subject feature/window reference;
- named metric, value, unit and applicability;
- method/threshold specification reference;
- status such as `nominal`, `degraded`, `indeterminate` or `candidate_event`;
- sample support and any excluded samples;
- limitations and uncertainty status; and
- operation and execution references.

`candidate_event` is intentionally not `verified_anomaly`. A later verification
artifact must identify the diagnostic as its subject, state the checks performed
and keep internal versus independent verification explicit.

## Time and causality rules

For a causal execution with decision time \(t_d\), every consumed sample and
state artifact must have been available by the declared availability cutoff:

\[
\forall o_i \in W,\qquad \operatorname{receivedAt}(o_i) \le t_d.
\]

The output support interval alone does not prove causality. Replay validation
must perturb or append future samples and show that already emitted causal
results remain unchanged. Zero-phase filtering, centered windows that reach
beyond the decision time and retrospective reordering are offline operations
unless an explicit bounded-delay contract proves otherwise.

## Failure and refusal behavior

An implementation must fail closed or emit an explicit ineligible/indeterminate
result when required identity, unit, timebase, ordering or configuration is
missing. It must not silently:

- treat absent samples as zeros;
- coerce non-finite values;
- infer a calibration or frame;
- repair timestamps without recording the transformation;
- average duplicate samples without a declared policy;
- fabricate covariance; or
- convert a diagnostic into a verified condition.

## Mapping to existing instrument exchange

When a scalar ordered feature vector is exported through
`notation.instrument.result-artifact.v1`:

- `result_id` maps to `feature_record_id`;
- `execution_ref` remains the feature execution identity;
- `input_refs` include the window and/or source observation batch references;
- `model_refs` include the operation/filter specification;
- `components` preserve feature order, numeric value and unit;
- covariance uses `feature_space` frame semantics and an explicit status; and
- calibration references are retained at both required levels.

This projection loses domain information unless the window, frequency axis,
filter state and quality diagnostic remain available as referenced companion
artifacts. The mapping is therefore explicit and testable, not assumed.

## Compatibility policy

Repository renames and documentation revisions do not change record identity.
Once contract identifiers and operation IDs are implemented, incompatible field
or semantic changes require a new version. Recorded executions retain the
contract and implementation versions under which they ran.
