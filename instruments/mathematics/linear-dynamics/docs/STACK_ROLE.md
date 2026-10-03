# Instrument boundary

SIDT computes candidate dynamics from explicitly supplied, fully observed state and input trajectories. It extends the instrument collection with an empirical check on dynamics assumptions.

| Neighbor | Handoff | Boundary |
| --- | --- | --- |
| Provenance-Preserving Data Acquisition (PPDA) | Observations and acquisition references | Source identity and evidence remain upstream |
| Stream and Temporal Feature Engine (STFE) | Aligned/conditioned state, input, and output rows plus conditioning reference | SIDT does not silently filter, resample, fill gaps, or reinterpret coordinates |
| Geometric State Inference Engine (GSIE) | Candidate `A`, `B`, declared interval, coordinates, units, and fit diagnostics | Estimator consumption requires explicit model selection; identification does not retune or adopt a model |
| Observability and Identifiability Testbed (OIT) | Declared `A`, optional `C`, numerical policy and metadata | State observability and regression rank are distinct questions |
| State Estimation Testbed (SET) | Candidate identity and separately defined experimental cases | Estimation performance and independent model evaluation remain explicit results |
| Scientific Computation Runtime (SCR) | Declared bounded operation and execution record | Runtime execution identity is separate from candidate identity |
| Computational Instrument Workbench (CIW) | Candidate/diagnostic inspection and verification records | Workspace sessions and instrument binding remain external |
| Evidence and State Management (ESM) | Evidence, result, execution, and verification references if admitted by its own policy | SIDT makes no admission decision and writes no canonical state |

The current repository implements local fit and one-step evaluation APIs plus
the [declared identification operation](DECLARED_IDENTIFICATION.md) for external
integration sessions. CIW owns provider invocation and session construction.
SIDT does not implement signed evidence bindings, ingestion services, or
operational execution.

Private acquisition profiles, real telemetry, calibration details, experiment records, operating thresholds, and adoption policies are not required for the public synthetic example. Public documentation describes the instrument interface and its limits. No customer-specific data or control-plane implementation is included.

Neither the candidate matrices nor their digest carry authority to act. A model can fit a dataset while being inappropriate for an observer, unobservable through an intended sensor configuration, or unstable outside the tested domain. Preserve these questions and their verification records separately.
