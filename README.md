# State Estimation Evaluation Testbed

**Specification-stage evaluation of state reconstruction under degraded observations.**

This repository defines the state-estimation evaluation responsibility within
Notation Systems' computational instrumentation stack. Its scope covers
reconstruction under noise, missing observations, latency, and other measurement
degradation, with the plant and measurement model declared explicitly.

## Status and implemented contents

**Specification stage.** This checkout contains a declarative invariant corpus
and its citation. It has no executable estimator, evaluation runner, numerical
solver, simulation, benchmark results, or test suite. The repository name
describes its responsibility; it does not establish an implemented capability.

The existing corpus declares:

- `plant.declared`: estimation requires a declared plant and measurement model.
- `var.x`: the state coordinate requires `declared-H`.
- `claim_scope: computational-integrity-only`.

These declarations do not establish physical validity, estimator accuracy,
observability, or a stability certificate. Noise, missingness, and latency are
evaluation concerns, not implemented perturbation generators in this checkout.

## Technical responsibility

The testbed's responsibility is to evaluate state reconstruction against a
declared model and explicitly characterized observations. Estimator
implementations retain their own identities and mathematical assumptions; this
repository is not the authoritative implementation of every estimator.

A reported evaluation must distinguish its source observations, model
declarations, estimator operation and version, execution attempt, computed
result, and verification evidence. Declaring an invariant is separate from
executing an evaluation or verifying its result.

## Relationship to the instrumentation stack

These are component responsibilities, not claims of working integrations in
this specification-stage repository.

| Component | Responsibility |
| --- | --- |
| **State Estimation Evaluation Testbed** | Evaluation of reconstruction under declared observation degradation. |
| [Provenance-Preserving Data Acquisition](https://github.com/giasonpooni/Provenance-Preserving-Data-Acquisition) | Source acquisition, observations, extraction lineage, and explicit missingness. |
| [Evidence and State Management](https://github.com/giasonpooni/Evidence-and-State-Management) | Evidence retention, versioned state, admission, and release management. |
| [Scientific Computation Runtime](https://github.com/giasonpooni/Scientific-Computation-Runtime) | Declared scientific computations and provenance-bearing execution. |
| [Constraint-Based State Reconciliation](https://github.com/giasonpooni/Constraint-Based-State-Reconciliation) | Reconciliation against declared physical or structural constraints. |
| [Geospatial State Visualization](https://github.com/giasonpooni/Geospatial-State-Visualization) | Read-only presentation of geographic and temporal state. |
| [Computational Instrumentation Workbench](https://github.com/giasonpooni/Computational-Instrumentation-Workbench) | Instrument sessions, adapters, inspection, and replay. |

Evaluation, reconciliation, execution, information governance, and visualization
remain separate responsibilities. A display or evaluation result does not grant
authority to change retained evidence or operational state.

## Repository identity and compatibility

The repository was renamed from `State-Estimation-Testbed` to
`State-Estimation-Evaluation-Testbed`. Use the current repository name and
location for documentation and new references.

This naming change preserves the existing `invariant-corpus-v1` schema,
invariant IDs, state-coordinate ID, declared claim scope, and historical
`cites` value. It does not rewrite operation identities, evidence, execution
records, or historical runtime pins.

## Repository contents

- [Invariant corpus](validation/invariant-corpus-v1.json)
- [Corpus citation and claim boundary](docs/invariant-corpus-cite-v1.md)
- [License](LICENSE)
