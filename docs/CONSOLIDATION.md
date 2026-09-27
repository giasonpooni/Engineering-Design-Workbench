# Cross-system consolidation

This page describes how the existing Notation Systems components fit together.
It is an architecture map, not a new wire contract, operation catalogue, or
claim that every linked repository is already integrated.

## Roles and authority

    ESM governed evidence/state
       -> CIW/PDT investigation, execution and replay
       -> domain providers: models and bounded numerical claims
       -> ICRH/SCR: scoped conformance, execution and proof checks
       -> ESM review, admission and correction
       -> GSV geographic projection and OpenUSD local/asset view

| Layer | Current role | Authority boundary |
| --- | --- | --- |
| Evidence and State Management (ESM) | Evidence retention, state review, admission, correction, release and dependency impact | Workbench candidate capture remains UNADMITTED; admission is a separate ESM decision |
| CIW/PDT | Investigation inputs, operation selection, provider invocation, execution/result records, save/reopen/replay and terminal inspection | A successful computation is not canonical state, physical validation or actuation permission |
| Scientific providers | Domain equations, numerical methods, validity domains, diagnostics and refusals | The provider owns mathematical meaning; CIW does not generalize a provider's claim |
| ICRH | Independent, pinned conformance and replay inspection for supported exchange profiles | A conformance receipt has a declared scope and does not admit evidence or prove physical truth |
| SCR/SP1 | Selected workload execution and scoped proof/check paths | Execution or proof establishes only the registered statement and its commitments |
| GSV | Read-only geographic and temporal projection | It renders declared geographic state; it is not a solver, evidence store or admission service |
| OpenUSD | Local engineering/asset scene and exchange representation | A loadable scene is not geometry authority, calibration, or a scientific result |

The implemented identity boundary is evidence/source identity, operation identity,
execution identity, result identity and verification identity. See
[Architecture](ARCHITECTURE.md), [Diagrams](DIAGRAMS.md) and [Execution Responsibilities](EXECUTION_RESPONSIBILITIES.md).

## What is exercised now

The stack map and coverage matrix are authoritative for current pins and gates:
[Stack](STACK.md), [Integration Coverage](INTEGRATION_COVERAGE.md) and [Systems Catalog](SYSTEMS_CATALOG.md). They currently
describe, among other paths:

- CIW-native records and operation lifecycles with read-only reopen and explicit
  replay;
- pinned measurement, calibration, estimation, covariance, geometry, telemetry,
  design and stability providers with declared units, frames, timing and
  uncertainty limits;
- a quantity-only CSE adapter with QUANTITY_ONLY geometry authority, explicit
  frame declarations and no surveyed transform;
- a read-only GSV projection and a read-only ICRH exchange inspector;
- selected SCR integer/proof paths whose execution and proof scopes remain
  separate from ESM admission.

These are bounded paths. A repository link, provider capability, retained digest,
successful solve or visualization does not by itself create an integration.
The operating guides name the exact source/runtime pins, input/output fields,
refusals and replay evidence for each path.

## Proposed connective tissue

The next increment should fill structural gaps before adding another isolated
domain tool. The following are proposed design areas, not registered schemas:

1. **Data-only profile and capability registry.** Declare a domain/profile,
   typed inputs and outputs, validity envelope, evidence requirements and
   capabilities such as evaluate, advance, linearize, observe, optimize or
   check. Registration must not authorize an executable.
2. **Typed composition graph.** Represent observes, calibrates, constrains,
   derives-from, approximates, couples-to, validates, contradicts and
   supersedes relationships with explicit compatibility checks. Reuse the
   existing operation and record contracts while this is designed; do not
   invent a universal payload prematurely.
3. **Shared semantics.** Carry quantity dimension/unit/order, scalar/vector/tensor
   role, model/sensor/parameter status, coordinate frame, clock/time support,
   missingness, uncertainty and validity domain. Unknown uncertainty remains
   unknown; a covariance is not automatically a confidence region.
4. **Frame transformations.** Geographic, surveyed, BIM, machine and sensor
   frames require declared maps, units, applicability, uncertainty and source
   evidence. Co-location does not establish a transform. Cross-sensor and
   temporal dependence must survive uncertainty propagation; singularity and
   systematic error cannot be replaced by an invented independent covariance.
5. **Representation authority.** State whether an IFC quantity, mesh, point
   cloud, USD scene, surrogate or embedding is sufficient for the particular
   claim. Availability of a representation is not claim support.
6. **Candidate handoff and invalidation.** Map a PDT result and its dependencies
   to an ESM candidate for fresh review. Corrections should mark affected
   downstream records for re-evaluation without declaring them disproved.
7. **Coupling.** Describe explicit versus implicit coupling, operator splitting,
   shared time stepping, fixed-point iteration and convergence criteria before
   composing chemical/thermal, fluid/structure or plant/controller loops.

The existing [Contract Foundations](CONTRACT_FOUNDATIONS.md), [Covariance](COVARIANCE.md), [Exchange](EXCHANGE.md) and
[Workbench Assembly](WORKBENCH_ASSEMBLY.md) pages provide the current contract vocabulary. These
proposed areas must preserve their read-only evidence boundaries and separate
operation/execution/result identities. Event, acquisition, knowledge, simulation
and display times remain distinct. Missing, refused, inconclusive, superseded
and withdrawn states must retain their defined meanings rather than collapse
to zero or a generic false value.

## Two proposed extensions

**CSE measured-evidence loop.** CSE's SATISFIED, VIOLATED and UNRESOLVED
criterion states provide a useful domain example. An unresolved quantity can
feed experiment design: identify the missing or ambiguous measurement, rank a
declared next observation, acquire evidence, then recondition the CSE case.
This requires a surveyed/local frame chain and measurement authority; it is not
present in the quantity-only adapter.

**CSG design space.** The existing curved-path/geodesic sensitivity work can
be extended as a proposed design study over declared initial conditions,
surface/path parameters, constraints and local sensitivity responses. A study
may compare admissible candidates and expose a sensitivity atlas. It must retain
the model validity envelope and distinguish sampled design exploration from a
physical geometry, metrology or control claim. See
[Geodesic References](GEODESIC_REFERENCES.md) and [Curved Path Study](CURVED_PATH_STUDY.md).

The target is a universal investigation substrate, not universal science:
domain meaning stays with each provider while composition, evidence, frames,
uncertainty, validity and review become reusable structural rules.
