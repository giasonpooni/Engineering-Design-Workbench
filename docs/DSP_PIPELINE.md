# DSP conditioning and synthetic pump diagnostics

`net dsp pipeline` composes signal integrity checks, alignment, conditioning and
diagnostic features through the original NET Session and operation machinery.
The numerical provider is the optional `stfe_dsp` extension under
`instruments/measurement/signal-conditioning`. It depends on the original `stfe`
instrument under `instruments/measurement/signal-processing`, whose imported
source tree and bounded window-mean operator remain unchanged. NET binds
`signal.pipeline.v1`, retains its request and result, and provides inspection
and numerical replay.

This is an additive Python/SciPy pathway. The existing native
`net dsp run`, `net dsp demo` and `signal.filter.fir.v1` remain separate supported
interfaces; their native-provider build requirements are documented in
[DSP_INSTRUMENT.md](DSP_INSTRUMENT.md).

## Install and run

From the monorepo root, using Python 3.11 or newer:

```sh
python -m pip install ".[dev]" "./instruments/measurement/signal-processing" "./instruments/measurement/signal-conditioning[dsp]"
net dsp pipeline demo --seed 7 --output-dir results/pump-001
net dsp pipeline inspect results/pump-001
net dsp pipeline run --request results/pump-001/request.json --output-dir results/pump-002
net dsp pipeline replay results/pump-001 --output-dir results/pump-001-replay --atol 1e-10 --rtol 1e-9
```

Use a new output directory for each run or replay. Installing NET alone does not
install the DSP provider. The `dsp` extra supplies the pinned SciPy numerical
dependency. The extension is distributed as `streaming-telemetry-dsp-extension`
under MPL-2.0, independently of the unchanged imported
`streaming-telemetry-feature-extraction` package. This additive layout preserves
the monorepo's byte-identical imported-tree invariant. NET composition remains
under the repository's AGPL-3.0-or-later license.

`demo` creates and executes a seeded synthetic pump-and-pipe request. `run`
executes retained or operator-authored request JSON. `inspect` reads the saved
bundle and validates its retained bindings without performing fresh numerical
computation. `replay` executes the retained request again and writes both a fresh
bundle and `replay-verification.json` containing the numerical comparison.

## Input and processing contract

The numerical request uses schema `stfe.dsp-pipeline.v1`. Required fields are
`signals`, `steps` and `provenance`; optional `ground_truth` belongs to the
synthetic evidence declaration. Each named scalar signal declares `source_id`,
`unit`, `clock_id`, `sample_rate_hz`, `time_s` and `values`. Each step declares
`id`, `input`, `method` and `parameters`, with a `reference` for operations that
use a second signal. Downstream inputs can name earlier steps.

Numerical processing requires an explicit signal-quality stage. A successful
quality stage passes through the original samples; it is not a repair operation.
An integrity report does not authenticate a sensor, calibrate its units or
establish its physical validity. Missing samples are not implicitly zero-filled,
and irregular sample timing does not silently become a regular recording.

The bounded request admits at most eight input signals, 32 steps, 32,768 samples
per signal, 65,536 input samples in total and 4 MiB of request JSON. Results are
bounded to 10 MiB. These bounds constrain this reference workload; they are not a
throughput or real-time deadline claim.

Every operation retains effective parameters, source support, timing, numerical
mode and limitations. Signal outputs retain their unit and clock labels;
diagnostic units follow their source signals and recorded normalization. Scalar
features retain their source sample intervals so an event can be traced to the
recording that produced it. Original observations remain available alongside
derived outputs.

| Method | Implemented calculation and boundary |
| --- | --- |
| `quality` | Missing values, duplicate/backward/irregular timestamps, gaps, declared-bound clipping and constant-plateau candidates; no imputation |
| `clock_shift` | Declared additive timestamp correction into a named target clock |
| `detrend` | Constant or linear whole-record fit and subtraction |
| `filter` | Designed/custom FIR, Butterworth SOS IIR, or IIR notch; causal or offline zero-phase mode; coefficients and frequency response retained |
| `resample` | Rational polyphase resampling with a Kaiser anti-alias FIR and declared zero boundary extension |
| `delay` | Integer-lag positive cross-correlation peak on already aligned common-clock signals |
| `fractional_delay` | Offline finite windowed-sinc interpolation; fractional delay is approximate |
| `fft` | Windowed one-sided FFT, coherent-gain amplitude and PSD normalization |
| `welch` / `spectrogram` | One-sided density spectra with declared window, segment length, overlap, FFT size and detrending |
| `features` | RMS, absolute peak, crest factor, population Pearson kurtosis, optional band power and absolute-amplitude threshold events |
| `coherence` | Magnitude-squared coherence, complex cross-spectrum and H1 estimate of reference response / input signal |

The lower-level numerical entry point is
`stfe_dsp.dsp.process(signal, method, parameters, reference=None)`; a full request is
executed with `stfe_dsp.pipeline.run_pipeline(request)`. Filter `chunks` records a
partition of the current input, and causal `state` accepts a preceding operation's
`contract.final_state`. This is a retained numerical state interface, not a live
acquisition service.

### Timing and alignment

Declared clock correction uses a `clock_shift` step with additive `offset_s`,
`target_clock_id` and `mapping_ref`. The original timestamps remain in the
retained source support. A mapping reference records the operator-supplied
mapping; it does not run ClockSync, estimate clock drift or certify that mapping.

Correlation-based delay estimates are model-dependent. Periodic signals can
produce ambiguous peaks, and an observed delay may combine transport delay,
filter phase, timing error and process dynamics. A declared correction and a
physical cause are different claims.

### Causality, boundary effects and uncertainty

Causal filtering operates only on present and past samples and must retain its
initialization and final state. Whole-record processing and chunked processing
must use compatible initialization to be comparable. Offline zero-phase
filtering uses future samples and cannot be represented as a live causal output.
The operation contract identifies the selected mode and boundary treatment.

Resampling is not a substitute for repairing unknown samples or clock drift.
Downsampling requires the declared anti-alias filter; an arbitrary FIR or a
sample-selection stride provides no general alias suppression guarantee.
Finite-record padding, filter settling and window support can influence the
edges even when central samples agree well.

The core `valid_sample_range` is local to each operation. Composition additionally
retains `pipeline_input_valid_sample_range`,
`pipeline_effective_valid_sample_range` and, for paired operations,
`pipeline_reference_valid_sample_range`. Finite-support FIR, resampling and
fractional-delay ranges are propagated conservatively; unknown IIR settling
extent remains unknown. Whole-record detrending can carry edge contamination
into the complete result because its fitted trend depends on all input samples.

The chain does not automatically crop data. Full-record spectra report
`includes_boundary_affected_samples`, while feature windows and threshold events
carry `pipeline_edge_support_valid`; `null` means unknown. Synthetic event
comparison excludes candidates with invalid or unknown support. The default pump
chain's FIR/resampling path has effective validity `[42, 2006)` out of 2,048
samples, and its full-record spectra explicitly include boundary-affected data.
Unknown settling extent or latency is never a zero-delay guarantee.

Filtering and overlapping windows change temporal noise correlation. This
release does not propagate full time-domain covariance through the new general
DSP chain or automatically update a downstream Kalman measurement model.
Unknown uncertainty remains unknown. The original bounded window-mean operator
retains its separate full-covariance contract.

## Evidence, operations, executions and verification

| Identity or record | Meaning |
| --- | --- |
| Source evidence identity | Binds the retained request and input observations |
| Operation identity | Names the declared `signal.pipeline.v1` operation |
| Execution identity | Identifies one actual processing occurrence |
| Result identity | Identifies the retained outcome of that occurrence |
| Replay verification identity | Identifies a fresh numerical comparison |

Repeated runs can share source evidence and operation identities while carrying
different execution and result identities. Inspection preserves these identities
and does not mint a fresh execution or numerical verification. Replay retains
fresh occurrence identities and reports the requested absolute and relative
tolerances together with the original and replayed result references.

A passing replay establishes numerical agreement within the declared comparison
scope. It does not provide an independent physical oracle, certify the source
sensor or admit state into the evidence ledger. The runtime-match field records
whether the compared execution declarations agree; source hashes are content
bindings, not an assertion that the implementation is correct.

The bundle contains `request.json` and `workspace.json`; replay additionally
contains `replay-verification.json`. CLI inspection explicitly reports
`fresh_execution: false`, `numerical_verification: "not_performed"` and
`state_admission: "not_performed"`. Numerical replay has its own comparison
status and verification identity.

## Synthetic diagnostic scope

The pump example is a reproducible synthetic signal-model exercise. Its
pressure, flow and vibration channels, disturbances, clock offsets and noise
are generated observations with retained synthetic ground truth. The example
demonstrates processing and traceability across channels; it does not model a
validated physical pump installation.

The default fixture generates eight seconds at 512 Hz per channel: a 24 Hz pump
component, its 48 Hz harmonic and a tapered 80 Hz disturbance between 40% and
60% of the record duration. The three clock offsets are intentionally known.
The 18-stage workload checks each channel, applies the declared inverse clock
offset, applies an offline zero-phase 100 Hz FIR low-pass, decimates by two with
anti-alias filtering, and computes Welch PSD. It additionally computes a vibration
spectrogram, windowed vibration features/events and pressure-vibration coherence.

The amplitude event threshold is fixed independently of the truth annotation.
The post-processing diagnostic compares candidate event intervals with declared
synthetic intervals on the same clock, excluding candidates whose inherited edge
support is invalid or unknown. An event record is one contiguous threshold
excursion; an oscillating disturbance can produce many excursions inside one
injected interval. The comparison reports temporal overlap, not a calibrated
probability, detection sensitivity, specificity or count of physical failures.

Candidate events are anomalies under the declared processing and signal model.
They are not identified physical leaks. Physical leak identification requires
separate experimental records that distinguish leakage from valve changes,
pump operating-point changes, cavitation, coupling changes and sensor faults.
Synthetic event agreement is reported only against the synthetic construction.

## Qualification and current limits

Local qualification for this increment used Linux/Python 3.12, NumPy 2.4.3
and SciPy 1.17.0. The 106 new numerical, retained-contract and integration tests
passed with no skips. The original window-mean gate passed 93 tests (two existing
adjacent-repository exchange tests excluded), and 155 Session/operation/control
and catalog regression tests passed. The isolated three-wheel journey passed
`demo`, `inspect`, `run` and `replay` with all 18 pump stages and unchanged
original bundle files. These results do not qualify other platforms or physical
equipment; the hosted matrix remains a separate gate.

Run the focused source gates:

```sh
python -m pytest -q tests/test_dsp_pipeline.py tests/test_dsp_pipeline_numerics.py tests/test_dsp_pipeline_contract.py
python -m pytest -q instruments/measurement/signal-processing/tests/test_window.py -k "not set_exchange_projection and not ciw_exchange_inspection"
```

The DSP CI workflow runs the new numerical/retention tests and the original
window-mean tests as separate suites on Linux and Windows, with Python 3.12 and
3.13. The two original adjacent-repository exchange checks are explicitly
excluded from this local DSP gate; their existing separate qualification remains
independent. The executed DSP suites must report no skips, errors or failures.

The installed gate builds independent NET, STFE and DSP-extension wheels, creates a fresh
virtual environment and runs the CLI from a temporary directory outside the
checkout with source import overrides removed. It checks installed module
locations, executes `demo`, `inspect`, `run` and `replay`, checks fresh occurrence
identities and passing numerical comparison, and verifies that inspection and
replay leave the original bundle unchanged:

```sh
python -m pip wheel --no-deps . --wheel-dir dist/dsp-pipeline
python -m pip wheel --no-deps ./instruments/measurement/signal-processing --wheel-dir dist/dsp-pipeline
python -m pip wheel --no-deps ./instruments/measurement/signal-conditioning --wheel-dir dist/dsp-pipeline
python scripts/check_dsp_pipeline.py --wheel-dir dist/dsp-pipeline --output-dir results/dsp-installed
```

JUnit reports, wheels, CLI logs, retained runs and `qualification.json` are CI
artifacts. The presence of the workflow is not evidence that a hosted run has
passed; qualification claims must refer to actual executed reports and revisions.

This increment does not implement a browser dashboard, live acquisition,
hard-real-time scheduling, automatic state admission, physical leak validation,
tachometer order tracking, synchronous averaging, adaptive LMS/RLS cancellation
or general wavelet/change-point analysis. RDFLib graph export and semantic
queries are also deferred. Relationships are currently represented by explicit
retained JSON identities and step references.
