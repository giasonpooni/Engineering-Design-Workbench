# Implementation and validation plan

## Objective

Build the smallest executable path that can answer a concrete question:

> Can a bounded telemetry window be transformed into a deterministic,
> provenance-bearing feature record without future-data leakage or loss of the
> raw observation path?

The plan keeps the numerical engine, reference implementation, workbench
adapter and evaluation authority separate.

## Phase 1 — freeze the executable contract

Deliver:

- versioned C++ and Python data structures for the fields in `CONTRACT.md`;
- canonical serialization rules and content/result identity tests;
- explicit refusal cases for missing timebase, units, source references and
  unsupported missing-data policies; and
- a mapping fixture to `notation.instrument.result-artifact.v1` for an ordered
  scalar feature vector.

Acceptance:

- round-trip serialization preserves ordered fields and identities;
- unknown uncertainty survives as unknown;
- result, execution, input and verification identities cannot be conflated; and
- the State Estimation Evaluation Testbed accepts the mapped generic artifact.

## Phase 2 — deterministic window operator

Deliver a C++ operator that consumes timestamped samples and produces declared
windows with configurable length, hop, support convention and warm-up policy.

Acceptance fixtures:

- exact boundary timestamps;
- duplicate timestamps;
- missing and non-finite samples;
- jitter and out-of-order delivery;
- reset versus state continuation; and
- late samples arriving before and after the availability cutoff.

No spectral method is added until window identity and replay behavior pass.

## Phase 3 — reference spectral slice

Implement one deliberately small operation family:

1. detrend/center policy;
2. declared window function;
3. real-input FFT or STFT;
4. explicit amplitude/power normalization; and
5. frequency coordinates derived from declared sample spacing.

Provide a NumPy reference with the same contract. Cross-language tests compare
impulse, constant, bin-centered sinusoid, off-bin sinusoid, two-tone and seeded
noise inputs. Tolerances must be stated in relation to precision and transform
length; equality must not be claimed where only tolerance agreement is tested.

## Phase 4 — causality and replay proof obligations

For every operation labeled causal:

- append arbitrary future samples and prove prior emitted outputs are unchanged;
- perturb samples after the decision cutoff and prove prior outputs are
  unchanged;
- replay the same retained window and configuration and compare content
  identity; and
- verify filter-state continuation uses only the declared predecessor state.

Offline centered or zero-phase operations use separate identifiers and fixtures.
They must never pass a causal-operation test by relabeling timestamps.

## Phase 5 — quality diagnostics

Add diagnostic metrics only after their support and limitations are explicit.
Initial generic metrics may include:

- missing-sample fraction;
- late/out-of-order counts;
- clipping or saturation fraction;
- finite-sample count;
- spectral concentration or band-power summaries; and
- timestamp-spacing statistics.

Thresholded outputs remain `candidate_event` or `indeterminate`. Physical fault
labels require a domain-specific detector, calibration and evaluation corpus.

## Phase 6 — CIW adapter

Implement a Python provider that invokes a pinned C++ executable or library and
returns immutable output artifacts for inspection. The adapter must retain:

- provider repository and commit;
- operation/configuration identity;
- input references and supplied digests;
- execution environment and exit status;
- stdout/stderr or structured diagnostic references;
- output identities; and
- verification artifacts as separate records.

The first adapter is read-only with respect to evidence and canonical state.
CIW may save its own session record; that record does not become measurement
evidence or grant operational authority.

## Phase 7 — SET evaluation matrix

Exercise at least:

| Fixture | Primary property |
| --- | --- |
| Impulse | Window placement, leakage pattern and normalization |
| Bin-centered sinusoid | Frequency coordinate and amplitude scaling |
| Off-bin sinusoid | Leakage and window-function behavior |
| Linear drift | Detrending semantics |
| Dropout | Missingness policy and diagnostic honesty |
| Timestamp jitter | Timebase assumptions and refusal/handling behavior |
| Out-of-order samples | Buffer/reject/reorder policy |
| Step or discontinuity | Candidate-event timing and boundary effects |
| Stateful filter reset | Initial-state and warm-up handling |
| Future perturbation | Causal non-leakage |

Report numerical conformance, detector performance and physical applicability as
separate claims.

## Phase 8 — domain adapters

Only after the generic slice passes may domain adapters bind additional
semantics:

- GNSS/RTK observables and cycle-slip-like candidate features;
- IMU axes, vibration bands and bias diagnostics;
- industrial process channels and equipment metadata; or
- communications I/Q streams.

Each adapter owns its unit/frame mapping, calibration references, domain model
and applicability limits. Domain parameters must not be smuggled into the
generic engine as undocumented defaults.

## Release gates

A public release may claim an implemented capability only when:

- code and tests for that capability are present on the named revision;
- the README status table cites the executable path and limits;
- synthetic fixtures are reproducible;
- cross-language discrepancies are within declared tolerances;
- causal leakage tests pass where causality is claimed;
- source, operation, execution, result and verification identities remain
  distinct; and
- the central stack map and any CIW operating guide are updated together.

Hardware qualification, calibrated detector performance and production control
authority require separate experimental evidence and are never implied by a
software release.
