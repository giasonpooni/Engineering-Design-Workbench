# Constraint-Based State Reconciliation

**Reconciliation of estimated states against declared constraints, with uncertainty
propagation and correction diagnostics.**

This describes the component's intended engineering responsibility.
**Current status: declarative specification only.** This repository contains an
invariant corpus and its citation. It does not contain an executable reconciliation
engine, numerical solver, uncertainty-propagation implementation, simulation,
adapter, or test suite.

## Scope and mandate

Within Notation Systems' computational instrumentation stack, this component
specifies how an estimated state may be reconciled with declared physical or
structural constraints. The repository name is method-neutral: covariance
weighting is one possible formulation, not the definition of the component.

The retained invariant states:

> projection enforces declared constraints. it does not invent them.

A constraint declaration must remain distinguishable from evidence supporting
that constraint. Satisfying a declared constraint alone does not establish
physical validity, measurement accuracy, or a stability certificate.

Uncertainty propagation and correction diagnostics belong to the intended
reconciliation interface; they are not capabilities implemented in this checkout.
The names `affine-exact-reconciliation`,
`affine-uncertain-reconciliation`, and
`nonlinear-local-reconciliation` are **proposed operation names only**.
They do not identify registered or executable operations here.

## Relationship to the instrumentation stack

These are responsibility boundaries, not claims that integrations are implemented.

| Component | Responsibility |
| --- | --- |
| [Provenance-Preserving Data Acquisition](https://github.com/giasonpooni/Provenance-Preserving-Data-Acquisition) | Acquire source material while retaining source identity, lineage, and explicit missingness. |
| [Evidence and State Management](https://github.com/giasonpooni/Evidence-and-State-Management) | Retain and govern evidence, versioned state, admission, and releases. |
| [Scientific Computation Runtime](https://github.com/giasonpooni/Scientific-Computation-Runtime) | Specify, dispatch, and record scientific computations. |
| Constraint-Based State Reconciliation | Specify correction of estimated states against declared constraints. |
| [State Estimation Evaluation Testbed](https://github.com/giasonpooni/State-Estimation-Evaluation-Testbed) | Evaluate state reconstruction and degradation scenarios. |
| [Geospatial State Visualization](https://github.com/giasonpooni/Geospatial-State-Visualization) | Present geographic and temporal state for inspection. |
| [Computational Instrumentation Workbench](https://github.com/giasonpooni/Computational-Instrumentation-Workbench) | Provide the environment for operating, inspecting, and replaying instruments. |

## Identity and compatibility

This repository was previously named **Lattice Calibration Module**
(`Lattice-Calibration-Module`). The descriptive name changes its presentation
and current repository location; it does not redefine retained scientific records.

The `invariant-corpus-v1` schema, `lattice.constraints` invariant,
`var.local-estimate` coordinate, and corpus citation are retained as declared.
Repository naming does not rewrite evidence identities, operation identities,
execution records, verification identities, or historical runtime pins.

## Repository contents

- [Invariant corpus](validation/invariant-corpus-v1.json)
- [Corpus citation and interpretation](docs/invariant-corpus-cite-v1.md)
- [License](LICENSE)
