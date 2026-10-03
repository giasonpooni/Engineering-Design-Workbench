# Constraint Based State Reconciliation in the instrumentation stack

Notation Systems develops computational instrumentation and evidence infrastructure for industrial and cyber-physical systems.
This component owns **reconciliation under declared constraints**, with one bounded executable exact-affine operation. The [stack map](https://github.com/giasonpooni/Computational-Instrumentation-Workbench/blob/main/docs/STACK.md) locates all public components and distinguishes implemented paths from specifications and scaffolds.

## Current boundary

| Property | Scope |
| --- | --- |
| Implementation | `cbsr.affine-exact.v1`, standard-library Python, bounded exact rational arithmetic over binary64 inputs |
| Workbench connection | JSON stdin CLI and Python API; receipt retains request and optional source-result binding; consumer must verify replay/admission |
| Inputs | Ordered estimate and full covariance, frame and unit declarations, exact affine law, evidence refs, distinct execution identity, hold threshold |
| Outputs | Accepted / held / refused receipt; raw candidate, corrected state/covariance when accepted, pre/post residuals, conditioning and feasibility |

FSRT and GTE retain their scoped domain engines. CBSR's exact-affine operation does not replace their domain laws, discover constraints, estimate a plant, or turn a local tangent into a global nonlinear law. Live pinned-provider tests cover the explicitly shared affine cases only. Unknown cross-covariance and uncertain constraint coefficients are refused by this operation.

## Interoperability

Integrations use the component's documented contract and an explicit adapter. They preserve source observations, ordered quantities, units, coordinate/frame meaning, time semantics, missingness and declared uncertainty where applicable. An unimplemented field or conversion must be reported as unsupported rather than silently inferred.

Evidence identity names the source record; operation identity names the versioned computation; execution identity names an invocation; result identity names its output; verification identity names a scoped check. These are integration requirements, not a claim that every standalone repository already implements all five record types.

Display names and repository locations do not rename packages, schemas, operation IDs, retained corpus keys or historical runtime pins. CIW integrations use the exact source revisions named in its runtime manifests and operating guides; a provider's current default branch is not a substitute for that binding. Published numerical records retain their original run scope.

## Technical references

- [Overview and runnable instructions](../README.md)
- [docs/invariant-corpus-cite-v1.md](invariant-corpus-cite-v1.md)
- [Exact-affine contract](AFFINE_EXACT.md)

Private customer state, deployment configuration and calibration knowledge are outside this public component description. Applicable repository licenses and source-data rights remain controlling; a shared stack identity is not a license grant or a change of repository visibility.
