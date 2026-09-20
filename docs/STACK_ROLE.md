# Scientific Computation Runtime in the instrumentation stack

Notation Systems develops computational instrumentation and evidence infrastructure for industrial and cyber-physical systems.
This component owns **scientific workload execution and verification records**. The [stack map](https://github.com/giasonpooni/Computational-Instrumentation-Workbench/blob/main/docs/STACK.md) locates all public components and distinguishes implemented paths from specifications and scaffolds.

## Current boundary

| Property | Scope |
| --- | --- |
| Implementation | Executable runtime and state/evidence packages; backend-specific prerequisites |
| Workbench connection | No CIW runtime adapter |
| Inputs | Versioned scientific state, declared computation specifications, explicit inputs and engine bindings. |
| Outputs | Computed artifacts, execution traces and verification artifacts for supported workload/backend combinations. |

Execution, proof verification and physical validity are different claims. Existing state packages keep their admission boundary; the runtime is not a universal owner of other repositories' state.

## Interoperability

Integrations use the component's documented contract and an explicit adapter. They preserve source observations, ordered quantities, units, coordinate/frame meaning, time semantics, missingness and declared uncertainty where applicable. An unimplemented field or conversion must be reported as unsupported rather than silently inferred.

Evidence identity names the source record; operation identity names the versioned computation; execution identity names an invocation; result identity names its output; verification identity names a scoped check. These are integration requirements, not a claim that every standalone repository already implements all five record types.

Display names and repository locations do not rename packages, schemas, operation IDs, retained corpus keys or historical runtime pins. CIW integrations use the exact source revisions named in its runtime manifests and operating guides; a provider's current default branch is not a substitute for that binding. Published numerical records retain their original run scope.

## Technical references

- [Overview and runnable instructions](../README.md)
- [docs/README.md](README.md)
- [docs/ENGINE_SEAM.md](ENGINE_SEAM.md)
- [docs/ARCHITECTURE.md](ARCHITECTURE.md)

Private customer state, deployment configuration and calibration knowledge are outside this public component description. Applicable repository licenses and source-data rights remain controlling; a shared stack identity is not a license grant or a change of repository visibility.
