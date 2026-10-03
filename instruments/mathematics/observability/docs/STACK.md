# Instrument foundations in the existing stack
[System diagram atlas](https://github.com/giasonpooni/Computational-Instrumentation-Workbench/blob/main/docs/DIAGRAMS.md) gives the shared topology and authority boundaries. The local README, numerical contract, and operation contract explain this instrument's implemented mechanism; stack relationships do not imply a native execution adapter.


These six standalone Python instruments extend Notation Systems' computational
instrumentation and evidence infrastructure. Each has a bounded numerical API,
synthetic examples, tests, and an explicit exporter for the existing
`notation.instrument.result-artifact.v1` format. Export conformance is not a
native Computational Instrumentation Workbench execution adapter.

| Instrument | Implemented numerical foundation | Relationship to existing components |
| --- | --- | --- |
| [Time Base Reconciliation Runtime](https://github.com/giasonpooni/Time-Base-Reconciliation-Runtime) | Supplied affine clock mapping and correlated first-order time uncertainty | Derives event-time coordinates while PPDA retains source timestamps; consumers must explicitly select the derived coordinate |
| [Observability and Identifiability Testbed](https://github.com/giasonpooni/Observability-Identifiability-Testbed) | Finite-horizon linear observability and local sensitivity/Fisher diagnostics | Diagnoses declared GSIE models and supplied JSPT sensitivities; SET retains evaluation responsibility |
| [Metrological Calibration and Uncertainty Runtime](https://github.com/giasonpooni/Metrological-Calibration-Uncertainty-Runtime) | Applicable affine calibration and full correlated first-order uncertainty | Complements RCI's measurement-chain boundary; does not replace its existing calibration operation or pins |
| [System Identification and Dynamics Testbed](https://github.com/giasonpooni/System-Identification-Dynamics-Testbed) | Fully observed discrete linear least squares and one-step evaluation | Produces candidate dynamics; model selection and use by GSIE remain explicit caller decisions |
| [Fault Detection and Isolation Runtime](https://github.com/giasonpooni/Fault-Detection-Isolation-Runtime) | Innovation NIS/whitening and deterministic CUSUM transitions | Interprets supplied residuals statistically; SET retains offline benchmarking; physical fault isolation is not implemented |
| [Experiment Design and Sensor Placement Testbed](https://github.com/giasonpooni/Experiment-Design-Sensor-Placement-Testbed) | Finite candidate information ranking with D- and A-optimal criteria | Consumes declared sensitivities and noise models; outputs advisory rankings without commanding acquisition |

## Preserved ownership

| Existing component | Retained authority |
| --- | --- |
| [PPDA](https://github.com/giasonpooni/Provenance-Preserving-Data-Acquisition) | Source bytes, extraction lineage, observation identity and missingness |
| [STFE](https://github.com/giasonpooni/Streaming-Telemetry-Feature-Extraction) | Signal conditioning, windows, spectral/temporal features and quality |
| [GTE](https://github.com/giasonpooni/Geometric-Telemetry-Engine) | Declared geometry and coordinate operations |
| [GSIE](https://github.com/giasonpooni/Geometric-State-Inference-Engine) | State estimation and model-conditional covariance |
| [JSPT](https://github.com/giasonpooni/Jacobian-Sensitivity-Propagation-Testbed) | General sensitivity and covariance transport |
| [CBSR](https://github.com/giasonpooni/Constraint-Based-State-Reconciliation) | Declared constraint reconciliation |
| [SET](https://github.com/giasonpooni/State-Estimation-Evaluation-Testbed) | Existing exchange validation and estimator evaluation boundary |
| [CIW](https://github.com/giasonpooni/Computational-Instrumentation-Workbench) | Source-pinned operation binding, sessions, inspection and replay |
| [SCR](https://github.com/giasonpooni/Scientific-Computation-Runtime) | Declared execution and separate verification records |
| [ESM](https://github.com/giasonpooni/Evidence-and-State-Management) | Evidence admission, state transitions, history and release |

The new packages neither import private operating state nor create a canonical
write path. Numerical validation stays local to each bounded method. No seventh
numerical-substrate repository or universal replacement protocol is introduced.

## Exchange and identity

Each optional exporter calls SET's validator, pinned in the `exchange` dependency
to commit `bd261a765281a95312f7c91a3857233476294c5b`. It retains explicitly mapped
input payloads and numerical outputs alongside ordered components, covariance,
model/calibration references, operation identity and caller-supplied execution
identity. A supplied Git revision is labelled unattested. Export neither checks
out that revision nor proves it produced the values.

The input digest identifies JSON content; the result digest includes the
execution reference. A new execution reference therefore produces a new result
identity. Verification references start empty. No digest, successful calculation,
or passing conformance check is promoted to independent verification, calibrated
measurement truth, admitted evidence, or actuation permission.

Results are deterministic within the declared numerical environment; NumPy/BLAS
or platform changes may affect floating-point values and result digests. The
examples are synthetic computational checks, not device qualification or physical
validation. Detailed methods and refusal conditions are owned by each package's
numerical contract.
