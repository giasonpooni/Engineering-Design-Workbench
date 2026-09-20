# Public instrument exchange

The adapter reads `notation.instrument.observation-batch.v1` and writes `notation.instrument.result-artifact.v1`. This is a conformance-tested connection to the workbench's **read-only exchange inspector**, not native CIW session import, an execution backend or a complete acquisition-to-control system.

## Exact source pins

| Component | Revision | Use |
| --- | --- | --- |
| State Estimation Evaluation Testbed | `542e672be512bf43b61253f2b2a43cd967cb3062` | Shared schema/numerical checker |
| Computational Instrumentation Workbench | `1ec11eb46bcf19ec57b40603dcd5921d284307ff` | Exercised CLI inspection |

The adapter loads only `state_estimation_testbed/contracts.py` with SHA-256 `2385537daa6147ef2475d17bd75c026fe187077b90841515a9e9378e0246ae54`, after CRLF-to-LF normalization. It executes the bytes it checked, without importing the checkout's package initializer. It performs no network access or implicit download. This pin identifies the approved source; it does not authenticate the local Python environment.

## Reproduce the handoff

From this project root after installing `.[dev]`, create explicit trusted source checkouts:

```sh
git clone https://github.com/giasonpooni/State-Estimation-Evaluation-Testbed.git ../gsie-set
git -C ../gsie-set checkout 542e672be512bf43b61253f2b2a43cd967cb3062
git clone https://github.com/giasonpooni/Computational-Instrumentation-Workbench.git ../gsie-ciw
git -C ../gsie-ciw checkout 1ec11eb46bcf19ec57b40603dcd5921d284307ff
python -m pip install 'websockets==16.0'
mkdir -p output
python examples/exchange_roundtrip.py --validator-repo ../gsie-set > output/result.json
PYTHONPATH=../gsie-ciw/src python -m ciw exchange inspect examples/exchange/observation.json output/result.json --validator-repo ../gsie-set
GSIE_SET_REPO=../gsie-set GSIE_CIW_REPO=../gsie-ciw python -m pytest -q
```

`PYTHONPATH`/environment assignment syntax above is POSIX shell syntax. The core estimator is independently usable on supported Python platforms. Without explicit checkout paths, cross-repository tests skip; the committed CI workflow supplies both pins so these checks run in CI. A workflow definition alone is not evidence of a successful hosted run.

The example imports two synthetic positions with full correlated measurement covariance, estimates position from a declared zero-mean unit-covariance prior, and exports the result. Each invocation assigns a new local execution reference and creation time; numerical results repeat, while result identity correctly changes with execution metadata. This execution reference is a declaration, not a native external-runtime execution commitment.

## Import contract

`import_observation_batch(artifact, *, epoch, variables, units, frame, validator_repo)` returns an `ImportedObservation`. Its `.observation` supplies the core numerical view; `.artifact` returns a fresh copy of the retained source snapshot.

- Ordered names/units and the complete frame declaration must match exactly. No reordering, dimensional selection, rescaling or coordinate conversion is implicit.
- Explicit measurement covariance is required. An `unknown` or `not_applicable` covariance may conform to the general exchange schema, but cannot drive this Kalman update.
- The source snapshot remains exact. The numerical core averages only asymmetry within its declared floating-point tolerance; it does not alter the retained observation artifact.
- Numerical time is elapsed seconds from the explicit UTC `epoch`; source `observed_at`, `received_at` and clock basis remain in the snapshot. Observation/epoch parsing accepts up to six fractional-second digits and refuses greater precision. This does not establish synchronization accuracy.
- At most 64 components and a 1 MiB canonical JSON artifact are accepted. The core is not a streaming acquisition service.

## Export contract

`export_result_artifact(estimate, *, source, variables, frame, execution_ref, created_at, applicability, validator_repo, calibration_refs=())` emits a detached JSON-native result.

The adapter retains the complete input snapshot, source content digest, prior/input/model references, full covariance, innovations, innovation covariance, posterior residual and NIS. It checks that the numerical observation agrees with the source snapshot. Names, full output frame semantics, model IDs and execution identity are caller declarations. Structural validation does not prove that an arbitrary caller-constructed Estimate was produced by the stated model.

Result identity is `sha256(schema UTF8 || NUL || canonical JSON)`, excluding `result_id` itself. Canonical JSON uses sorted keys, compact separators, UTF-8 and finite numbers. This is the encoding exercised by the existing CIW inspector.

Evidence references, `operation_ref`, external `execution_ref`, result content hash and independent verification identity have separate roles. Export never creates a verification artifact, admits evidence or authorizes action. Original admission and calibration claims remain unverified references.

The generic result includes model/prior references rather than complete matrices or prior contents. Preserve the corresponding configuration for replay; the shipped examples retain their full numerical models in source and fixtures. A result JSON by itself is not a complete replay bundle.

## Tested limits

The tests exercise the actual pinned SET checker and CIW CLI, check identity recomputation, preserve off-diagonal covariance and reject source drift, absent covariance, metadata mismatches and source/result substitution. The workbench must continue to report `may_authorize: false` and native workspace import `not_performed`.

There is no native workbench command, saved workspace/reopen integration, independent verification service, hardware calibration check, physical validation or actuator interface in this slice.
