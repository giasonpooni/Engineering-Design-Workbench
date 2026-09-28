# Notations Engineering Terminal in the Notation Systems stack

The public repository is [Notations-Engineering-Terminal](https://github.com/giasonpooni/Notations-Engineering-Terminal).
Its distribution package is `computational-instrumentation-workbench`, its
Python import is `ciw`, and its command-line entry point is `ciw`.
**Notations Engineering Terminal (NET)** is the programmable scientific
controller; **Computational Instrumentation Workbench (CIW)** names its existing
execution substrate, not a separate controller above NET.

Notation Systems develops computational instrumentation and evidence infrastructure for industrial and cyber-physical systems.
This component owns **investigation composition, operation dispatch, inspection
and explicit replay**. The [stack map](STACK.md) locates the components and
distinguishes implemented paths from specifications and scaffolds. The
[NET controller decision](NET_CONTROLLER_BOUNDARY.md) defines the target
cross-project hierarchy and its remaining acceptance gates.

## Controller and instrument ownership

| Component | Authority in the target hierarchy |
| --- | --- |
| NET / `ciw` | Investigation/session state, typed planning, operation resolution and dispatch, retained provenance/dependencies, comparison, inspection and explicit replay. |
| [Geospatial Systems Compiler](https://github.com/giasonpooni/Geospatial-Systems-Compiler) | Representation compilation and inspection; selections and variation intents return to NET rather than invoking scientific providers directly. |
| [State Estimator for BIM](https://github.com/giasonpooni/State-Estimator-for-BIM) | Supported IFC world interpretation, evidence conditioning, posterior belief, geometry authority and scoped BIM disposition. |
| [Curved Surface Runtime](https://github.com/giasonpooni/Curved-Surface-Runtime) | Supported geodesic/Jacobi calculations, path sensitivity, tolerance, covariance and validity diagnostics. |
| [Fluid State Reconstruction Testbed](https://github.com/giasonpooni/Fluid-State-Reconstruction-Testbed) | Supported fluid-state estimation, balance residuals, guarded reconciliation, covariance and operation-specific fault distinguishability; `set_lcm` remains its package namespace. |
| [Evidence and State Management](https://github.com/giasonpooni/Evidence-and-State-Management) | Separately supported evidence/state review, admission and release; NET does not supersede this authority. |

**NET controls; specialist repositories compute; GSC represents; ESM governs evidence.**
The named specialist repositories remain independent implementations, not
modules copied wholesale into NET. Standalone use remains possible. This
ownership map is not evidence that every cross-project path already executes.
It extends the provider catalogue rather than replacing RCI, JSPT or other
existing instruments.

FSRT's `fsrt.tank-reconstruct.v1` and `.v2` already use the pinned Python
subprocess path. The [adapter guide](ADAPTERS.md) and
[covariance guide](COVARIANCE.md) describe the bounded RCI -> FSRT -> JSPT
workflow. Its one simultaneous two-reservoir snapshot is not a generic
fluid-network or temporal-fusion operation. Physical disagreement may hold
correction despite successful computation; retained outcomes must preserve
that status. The [FSRT extension](NET_CONTROLLER_BOUNDARY.md#fsrt-extend-the-existing-fluid-instrument-not-a-second-estimator)
separates those existing capabilities from new algebra, GSC and domain-model
handoffs that still need qualification.

## Current boundary

| Property | Scope |
| --- | --- |
| Implementation | Executable prototype; consult the operation catalogue and integration coverage for exercised capabilities. |
| License | First-party PDT code: GNU Affero General Public License v3.0 or later (`AGPL-3.0-or-later`); see [LICENSE](../LICENSE) and [component boundaries](LICENSING.md). |
| Workbench connection | Host: the existing Python session, operation and adapter registries remain the implementation. |
| Inputs | Retained scientific records, explicit selections, operation parameters and bound runtime manifests. |
| Outputs | Saved investigations, execution and result records, terminal analysis and supported optional inspection views. |

A session coordinates instruments; it does not replace their numerical engines
or infer verification from a view. An instrument catalogue must index the
existing trusted registry, not create a parallel runtime. The typed algebra,
cross-project planner and GSC intent protocol in the controller decision are
extension targets, not capabilities implemented by this documentation edit.

## Interoperability

Integrations use the component's documented contract and an explicit adapter. They preserve source observations, ordered quantities, units, coordinate/frame meaning, time semantics, missingness and declared uncertainty where applicable. An unimplemented field or conversion must be reported as unsupported rather than silently inferred.

Evidence identity names the source record; operation identity names the versioned computation; execution identity names an invocation; result identity names its output; verification identity names a scoped check. These are integration requirements, not a claim that every standalone repository already implements all five record types.

Display names and repository locations do not rename packages, schemas, operation IDs, retained corpus keys or historical runtime pins. CIW integrations use the exact source revisions named in its runtime manifests and operating guides; a provider's current default branch is not a substitute for that binding. Published numerical records retain their original run scope.

## Technical references

- [Overview and runnable instructions](../README.md)
- [NET controller and specialist boundaries](NET_CONTROLLER_BOUNDARY.md)
- [docs/PROTOCOL.md](PROTOCOL.md)
- [docs/INSTRUMENTS.md](INSTRUMENTS.md)
- [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- [docs/INTEGRATION_COVERAGE.md](INTEGRATION_COVERAGE.md)

Private customer state, deployment configuration and calibration knowledge are outside this public component description. Applicable repository licenses and source-data rights remain controlling; a shared stack identity is not a license grant or a change of repository visibility.

## Read-only exchange path

CIW's [instrument-exchange inspector](EXCHANGE.md)
checks supported `notation.instrument.*.v1` acquisition/runtime artifacts with
an explicitly pinned State Estimation Evaluation Testbed validator. It retains
full or explicitly unknown covariance and reports content/reference checks.
This is read-only conformance inspection: it does not import a native workspace,
run a scientific provider, admit source evidence or authenticate verification.
The operating guide records the producer/checker revisions and exact limits.
