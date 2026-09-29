# ClockSync 0.1 JSON and CLI contract

## Request

One request contains `source_frame`, `reference_frame`, `observation`, `model`, and `joint_covariance`. Optional top-level fields are `expected_reference` and `require_synchronization_evidence` (default `false`). Unknown fields are refused at every object boundary; this format has no arbitrary extension-data field.

A frame has required nonempty `clock_id` and `time_scale` strings and optional `unit`, which defaults to `s` and must equal `s`. The top-level source and reference bind the observation and model together. Independent, contradictory nested frame declarations are not silently overwritten: they are unknown fields and refused. Use the typed API when observation and model arrive as independently framed records.

`observation` contains finite numeric `device_time`, nonempty `evidence_id`, and optional `received_at` / `known_at`. Each optional time point is `null` or an object with `value` and `frame`. These instants remain metadata and do not enter the clock calculation.

`model` contains `model_id`, `device_origin`, `reference_origin`, positive `skew`, `offset`, and inclusive two-element `valid_device_interval`. Optional `synchronization_evidence_ids` is an array of distinct nonempty strings. Evidence-presence policy can require at least one ID; this does not authenticate that evidence.

`joint_covariance` is a finite, exactly symmetric, positive-semidefinite 3 by 3 matrix ordered `[device_time, skew, offset]`. Zero variances are allowed under the core covariance constraints. Entries must be numbers, not booleans or numeric strings. No symmetrization, diagonalization, regularization or unit conversion is implicit.

`expected_reference`, when supplied, must match the top-level reference frame exactly. When omitted, the top-level reference is the requested destination. `require_synchronization_evidence` must be a JSON boolean; strings such as `"false"` are not accepted.

## Result

All existing draft CLI result fields remain: `observation`, `model`, `event_time_delta`, `variance`, `jacobian`, `joint_covariance`, `propagation`, `operation_id`, `reference_origin`, `event_time`, and `standard_uncertainty`.

`request_options` is an additive transport record containing the resolved `expected_reference` and the actual boolean `require_synchronization_evidence`. It is not evidence, an execution receipt or a verification record. Arrays in JSON correspond to the retained tuple values in the Python numerical result. The result does not contain the original lexical JSON bytes; retain those upstream when needed.

## Commands

| Command | Behavior |
|---|---|
| `clocksync request.json` | Reconcile one request and emit result JSON. |
| `clocksync -` | Read one request from standard input. |
| `clocksync --example offset` | Emit a synthetic request bundled in the wheel. |
| `clocksync --example drift` | Emit a synthetic positive-skew drift request. |
| `clocksync --example correlated` | Emit a request with covariance cross-terms and distinct receipt/knowledge times. |
| `clocksync --version` | Read the installed distribution version. An uninstalled checkout identifies itself as such. |
| `python -m tbrt ...` | Same parser, computation and output contract. |

`--compact` changes JSON formatting only. Exactly one input path/stdin or `--example` may be selected. Generated examples are explicitly synthetic and provide no synchronization evidence about physical devices.

The text reader accepts UTF-8 and at most 1,048,576 decoded characters. It rejects duplicate keys at any nesting depth, non-finite constants, malformed JSON and oversized input. It is a local single-request tool, not a hardened multitenant network service.

Exit code 0 means successful command completion; 2 means usage/input/I/O rejection; 1 is used for a broken output pipe. Errors go to stderr. JSON is serialized completely before writing so validation failures do not emit a partial numerical result. An I/O failure while writing is different: the destination may already contain a prefix.

## Scope of replay

Retain the original request and output together. `clocksync` consumes request JSON, not its own result JSON. `replay_reconciliation` in the typed API checks a retained typed result against deterministic recomputation; it does not establish the authenticity of the observation, model or evidence IDs.
