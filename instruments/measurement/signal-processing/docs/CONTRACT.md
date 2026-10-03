# Executable contract: `stfe.window-mean.v1`

This version implements one bounded scalar window mean. It does not register an FFT, filter, arbitrary feature family, live acquisition service or estimator. `stfe.window_mean(dict)` and `python -m stfe` implement the same semantics. Unknown object fields are refused so an unsupported policy cannot be silently ignored.

## Request

The complete example is [`examples/window_mean.json`](../examples/window_mean.json).

| Field | Meaning and requirement |
| --- | --- |
| `operation_id` | Exactly `stfe.window-mean.v1` |
| `source_batch_ref` | Nonempty reference to the retained source batch |
| `source_batch_digest` | Lowercase `sha256:` plus 64 hexadecimal digits; canonical source JSON content digest supplied by the adapter |
| `samples` | Ordered list, at most 4096 presented records; exactly 1–32 consumed |
| `window` | Object with `start`, `end`, `received_by`, `decision_time`, `sample_period`, `max_lateness` |
| `channel_id`, `value_unit` | Nonempty scalar channel and unit; dimensionless must be explicit |
| `frame` | Named scalar source frame, or explicit `not_applicable` |
| `clock_basis` | Named common clock on which all numeric times are expressed in seconds |
| `clock_mapping_ref`, `frame_mapping_ref` | Named supplied mappings, including explicit identity mappings |
| `calibration_refs` | Ordered unique reference list; empty does not mean calibrated |
| `uncertainty` | Full covariance declaration described below |
| `execution_id` | Caller-assigned occurrence identity, distinct from evidence, operation, mapping and replay identities |
| `created_at` | Valid explicit UTC timestamp, up to six fractional digits |
| `implementation_revision` | Full 40-character lowercase Git revision, declared by the caller |
| `replay_ref` | Optional nonempty replay reference; absent or null when none |

Each sample has exactly `observation_ref`, `event_time`, `received_at`, `value`, `missing`. Consumed observation references are nonempty and unique. The batch reference must differ from individual observation references. Numeric inputs must be finite native JSON numbers; booleans, strings, implicit numeric conversions and integers not exactly representable in binary64 are refused. `missing` must be the boolean `false` for consumed samples.

The source digest and implementation revision are **declarations**, not cryptographic authentication or proof of consumed source bytes. A composing replay verifier must compare them to retained input content and a reviewed provider pin. STFE does not execute an input-supplied module, read an input-supplied path or fetch a reference.

## Time and window semantics

All time fields are seconds on the explicitly named common clock. The operation does not parse timestamps or perform clock/frame transformations; a separately named adapter maps source coordinates into this declaration.

- Support is the half-open interval `[start, end)`.
- `sample_period > 0`, `end > start`, `max_lateness >= 0`.
- `end <= received_by <= decision_time`; a partially elapsed window is unsupported.
- Exact rational arithmetic over represented binary64 times must establish `(end-start)/sample_period = N`, for integer `1 <= N <= 32`.
- The consumed event times are exactly `start + i*sample_period`, in presented order.
- Every consumed record satisfies `event_time <= received_at <= received_by` and `received_at-event_time <= max_lateness`.
- Receipt times are nondecreasing. Retrospective sorting, duplicate coalescing, padding and imputation are unsupported.
- Out-of-support records are not consumed. Their event time and record shape must be readable to establish exclusion; their value, receipt and missingness do not affect this window.

There is no implicit timestamp tolerance. For example, a supplied decimal grid may be refused when its represented binary64 values are not exactly regular. An integer-second or exactly representable binary-fraction grid avoids that ambiguity. A new operation version would be required to introduce a timing-tolerance or resampling policy.

All windows are stateless, rectangular and causal, with no detrending, padding, filter state, warm-up or automatic hopping. Each invocation declares one complete window. Overlap is permitted only through separately declared windows; covariance **between** output windows is not inferred by this scalar operation.

## Uncertainty

`uncertainty` has exactly four fields:

| Field | Values |
| --- | --- |
| `observation_refs` | Exact consumed observation reference order |
| `status` | `known` or `unknown` |
| `crosscov_policy` | `declared`, `declared_zero` or `unknown` |
| `matrix` | Complete `N × N` covariance, or null |

`known` requires a complete finite matrix and either `declared` or `declared_zero`. `declared_zero` asserts zero **off-diagonal** cross-covariance, not zero variance; every off-diagonal must actually be zero. `unknown` requires both `crosscov_policy: unknown` and `matrix: null`. A partial diagonal covariance with unknown cross-covariance must therefore remain unknown; STFE does not fabricate a unique uncertainty estimate.

Both matrix triangles must agree exactly. Exact rational symmetric elimination verifies PSD of the represented matrix, including zero-pivot coupling. No negative pivot is clamped, no jitter is added and no approximate matrix is substituted.

For `w_i=1/N`, the operation computes `mean = wᵀy` and `variance = wᵀRw` by exact accumulation over the supplied binary64 values and a single final binary64 rounding. Overflow or nonzero-to-zero underflow refuses the operation. A mathematically exact zero for the represented inputs is permitted. Unknown uncertainty produces the mean with null covariance and `status: unknown`, never an empirical scatter estimate or a zero matrix.

## Receipt and exchange mapping

The top-level `notation.stfe.window-mean-receipt.v1` object contains:

| Field | Content |
| --- | --- |
| `operation_id` | Versioned law |
| `window` | Consumed raw values and references, source digest, time/window declaration, calibration and uncertainty |
| `quality` | Sample count, complete warm-up, zero missing count and `nominal_under_declared_grid`; not physical validity |
| `execution` | Caller-declared occurrence, configuration reference, revision, Python version and creation time |
| `numerical_result` | Numerical inputs, operation configuration, mean and variance, independent of execution occurrence |
| `numerical_result_id` | Content identity of that numerical equivalence record |
| `result_artifact` | Existing `notation.instrument.result-artifact.v1` projection |

The generic result has one component named `<channel_id>.mean`, with the source value unit. Covariance uses `feature_space` semantics, a named frame derived from the source frame and an explicit one-element basis. Input references retain the source batch, window and individual observations. Model references retain the operation, configuration and clock/frame mappings. Calibration references occur at artifact and covariance levels.

The companion window is required to recover timing, full input covariance, raw values and policy. The generic scalar artifact alone is not a replay bundle. No verification record is minted here.

## Identity and canonicalization

Canonical JSON uses sorted keys, compact separators, unescaped Unicode and no NaN/Infinity, encoded as UTF-8. Negative numerical zero is normalized to `0.0`; numerical input integers become exact binary64 numbers only after the exact-representability check.

- Generic `result_id`: `sha256(schema + NUL + canonical artifact without result_id)`, prefixed `sha256:`. This is the existing SET/CIW exchange convention.
- `window_id`, `quality_id`: SHA-256 of each canonical companion before its identity field is added, prefixed `stfe-window:` or `stfe-quality:`.
- `operation_config_ref`: SHA-256 of canonical configuration, prefixed `stfe-config:`.
- `numerical_result_id`: SHA-256 of canonical `numerical_result`, prefixed `stfe-numerical:`.

The numerical identity includes numerical values, covariance, grid and operation configuration. It excludes evidence references, source-batch digest, calibration references, implementation Git revision, execution ID and creation time. Thus a numerical-equivalent replay can have a new occurrence and new provenance identity. Numerical identity is not source equivalence, authentication, execution verification or scientific equivalence beyond this exact record.

The window identity includes the source-batch digest and references. Appending future source bytes can change that provenance identity while leaving the numerical result unchanged. Future noninterference tests explicitly distinguish these two properties.

## Refusal and bounds

The CLI accepts at most 1 MiB of UTF-8 JSON, rejects duplicate keys and nonfinite constants, emits one JSON receipt to stdout on success, or a JSON refusal to stderr with exit code 2. The callable validates bounded record counts, text lengths, strict numeric types and versioned field sets. It returns detached JSON-native values and does not mutate the request.

A successful receipt establishes only the implemented calculation under supplied declarations. It does not establish calibration validity, physical applicability, unique sensor-fault isolability, authenticated source bytes, an SCR execution commitment, an independent verification or ESM admission. A future incompatible policy requires a new operation version.
