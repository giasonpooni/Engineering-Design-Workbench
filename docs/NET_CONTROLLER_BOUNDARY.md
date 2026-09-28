# NET scientific controller and instrument boundaries

**Architecture decision; not a declaration that every handoff below is implemented.**

Notations Engineering Terminal (NET) is the programmable scientific controller
for Notation Systems' investigations. Its existing Python package, command and
session remain `ciw`. A separate abstract Workbench does not sit above NET, and
this decision does not introduce another runtime, execution ledger or evidence
store. Specialist repositories retain their mathematics and implementations.

## Ownership

```text
                 Notations Engineering Terminal / ciw
          question -> plan -> execute -> compare -> inspect -> replay
                                |
          +---------------------+----------------------+
          |                     |                      |
          v                     v                      v
 Geospatial Systems       State Estimator       Curved Surface
 Compiler (GSC)           for BIM (CSE/gat)      Runtime (CSR)
 representation           BIM belief and        geodesic/Jacobi,
 compilation and          domain disposition    sensitivity, tolerance
 inspection                                     and covariance

 ESM: separate evidence/state admission and release authority where integrated.
```

The diagram shows control and ownership, not deployment topology or an already
qualified end-to-end workflow. GSC also supports provider-free inspection.
CSE and CSR remain usable standalone.

| Owner | Responsibility | Not delegated to it |
| --- | --- | --- |
| NET / `ciw` | Investigation/session state, typed composition, provider selection, operation dispatch, retained execution/result dependencies, comparison, inspection and explicit replay. | Redefining a specialist's scientific acceptance rule or admitting operational state on ESM's behalf. |
| GSC | Compile supplied source/result material into spatial, temporal, relational and visual representations; emit selection and variation intents. | Running scientific providers directly, changing posterior state, inventing covariance, admitting evidence or granting execution permission. |
| CSE / `gat` | Supported IFC interpretation, world/model identity, evidence conditioning, Gaussian belief, domain criteria, geometry authority and scoped disposition. | General solid reconstruction, machine control or construction approval inferred from `ACCEPT`. |
| CSR / `geodesic_testbed` | Supported surface/path computations, geodesic and Jacobi integration, transfer maps, validity diagnostics, tolerance and covariance propagation. | BIM interpretation, scan registration, arbitrary mesh solving or physical motion authorization. |
| ESM | Separately supported evidence retention, candidate-state review, admission and release. | Camera control or general numerical dispatch. |

**NET controls; specialist repositories compute; GSC represents; ESM governs
evidence.** This is a responsibility boundary, not a claim that every local
investigation requires ESM. Retention, verification, admission, release and
public publication remain different decisions. NET execution authority is
bounded by the deployment's permissions; it does not override ESM governance.

## Existing foundation and the extension point

The implementation map remains [ARCHITECTURE.md](ARCHITECTURE.md):

- `src/ciw/session.py` owns the shared session and retained dependencies.
- `src/ciw/operations/` owns versioned operation registration and retained
  execution/refusal/result handling.
- `src/ciw/adapters/` owns explicit manifests, registered adapters and bounded
  pinned subprocess paths.
- [PROTOCOL.md](PROTOCOL.md), [INSTRUMENTS.md](INSTRUMENTS.md) and
  [INTEGRATION_COVERAGE.md](INTEGRATION_COVERAGE.md) own current record formats,
  supported commands and exercised coverage.

Extend those components rather than moving them into a parallel `controller/`
implementation. A conceptual architecture tree is not an instruction to break
imports, rename wire records or reorganize every directory.

This document adds no parser, executable operation, provider registration,
scientific conversion, UI endpoint or runtime binding. It does not change an
existing schema, licence, scientific threshold or source pin.

## Algebra: one expression, explicit scientific types

Use the notation

```text
N = <S, Delta, T, C, I, E, Q, R>
```

as an investigation declaration:

| Symbol | Meaning |
| --- | --- |
| `S` | Explicit source/model/belief state references, not an unqualified claim about physical truth. |
| `Delta` | A typed requested change: parameter variation, observation, configuration or model choice. It is not universally vector addition. |
| `T` | Requested transformation with a declared domain and codomain. |
| `C` | Constraints, including the domain policy and numerical limits applicable to this operation. |
| `I` | Invariants to assess, together with the scoped checker or diagnostic required to assess them. |
| `E` | Evidence references and their status, applicability and provenance. |
| `Q` | Typed uncertainty and quality records, or explicit unavailable/unsupported status. |
| `R` | Requested representation, separate from the scientific result. |

An invariant declaration is not proof that it holds. A covariance's meaning
includes ordered variables, units, coordinate frame, linearization point and
model/source bindings; it is not merely a matrix field in a generic quality
object. Unknown uncertainty does not become zero. Shared evidence and
cross-covariance must not be silently replaced by an independence assumption.

Proposed lowering sequence:

```text
expression -> typed AST -> validated operation plan
           -> existing registered providers -> retained result graph
           -> requested GSC representations
```

The AST and cross-instrument compiler are extension targets, not an executable
language delivered by this document. Human-facing algebra may hide repository
boundaries; retained provenance may not.

## Three graphs, not one overloaded registry

The **instrument catalogue** describes owners and capabilities. The
**execution graph** describes a particular plan's operation dependencies. The
**investigation graph** retains sources, hypotheses, variations, plans,
executions, results, checks and comparisons across time.

Build the catalogue as an index over the existing trusted operation/adapter
registries. It must not become a second source of executable registration.
For each capability, bind its owner, exact registered operation/version,
input/output contracts, supported models, runtime/source requirements,
availability and qualification evidence. A listed capability is not proof of
availability or numerical qualification.

```text
resolve(requested_transform, typed_inputs, explicit_bindings)
    -> one instrument + one registered operation + compatible contracts
```

Unknown, unavailable, incompatible or ambiguous resolution is explicit. Do not
select the first approximate match, silently upgrade a source pin or let a
saved manifest import executable code. Algebraic aliases are not automatically
new operation IDs. Reuse actual registered identities; add/version operations
only through their existing registration and contract process.

A compiled plan must validate dependencies before dispatch and be acyclic at
the orchestration level. Iterative scientific algorithms belong inside their
bounded operations, or in an explicitly bounded future control construct,
rather than accidental dependency cycles. Preserve the original plan when a
variation creates a new plan. Invalidated downstream results remain historical
records, not inputs silently treated as current.

## Typed BIM -> path -> representation chain

The following is **design pseudocode**, not supported CLI syntax or a list of
currently registered operation IDs:

```text
world = BIM.load(ifc_source)
belief = BIM.condition(world, evidence)
surface_problem = supported_surface_adapter(
    belief, geometry_source, frame_binding, path_specification)
path_result = CSR.integrate_and_assess(surface_problem)
view = GSC.compile(belief, path_result, requested_views)
```

The explicit `supported_surface_adapter` is essential. A BIM posterior is not
a parametric surface, and an IFC entity ID is not a registered path. The
current documented CSE adapter supports quantities and placements rather than
general solids; CSR's parametric/path boundaries do not make it a generic
triangle-mesh solver. A fixture linked to a BIM entity is still a fixture.

The handoff must preserve the world/result identity, geometry producer and
revision, units, frame/registration evidence, chart/surface definition,
initial data, path interval, method and uncertainty assumptions required by
the selected CSR operation. A mapping digest binds a declared mapping; it
does not establish spatial registration. Unsupported geometry, conversion or
missing registration remains an explicit limitation or refusal according to
the receiving contract, not invented surface data.

CSE retains ownership of posterior meaning, covariance, diagnostics and
disposition. NET retains the cross-system dependencies. CSR retains ownership
of transfer/sensitivity calculations and their validity envelope. GSC consumes
explicit representations; display meshes are not fed back as scientific input.
A later scientific use of exported geometry needs a separately qualified
geometry contract, not a viewer-selection shortcut.

For CSR's documented transverse Jacobi system,

```text
j''(s) + K(gamma(s)) j(s) = 0
Phi(s) = [[a(s), b(s)], [a'(s), b'(s)]]
Phi(0) = identity
```

`det(Phi(s)) = 1` is the exact-system invariant in those coordinates. A
numerical integrator reports its drift and tolerance; NET does not overwrite
the determinant with one or generalize this invariant to arbitrary Jacobians.
Deterministic tolerance boxes, first-order covariance, integration error and
physical model validity remain different objects.

## GSC -> NET: intent, not scientific execution

```text
NET -> GSC: permitted retained state/result/view material and exact bindings
GSC -> NET: selection, requested variation or explicit replay intent
NET -> GSC: accepted/rejected/stale/unavailable outcome and permitted results
```

These are intended interactions, not new protocol status constants. Local
camera, styling and layout changes may remain entirely inside GSC. Display
reprojection and rendering are representation operations, not scientific
provider execution. Shared investigation selections belong to NET; a temporal
cursor must identify its time basis, units/epoch where applicable, and whether
it selects event time or knowledge time. A cursor value alone does not
reconstruct historical state.

A proposed computation-affecting intent must include a versioned contract,
request identity, investigation/session identity, expected revision, exact
source/result binding and typed target/value. The following is an illustrative
payload shape only; `ciw.control-intent.v1` is **not registered by this change**:

```json
{
  "schema": "ciw.control-intent.v1",
  "request_id": "example-request-001",
  "investigation_id": "example-investigation",
  "expected_session_revision": 12,
  "intent": "propose_variation",
  "base_state": {
    "result_id": "example-bim-result",
    "state_digest": "<exact retained state digest>"
  },
  "target": {
    "entity_id": "<exact entity identity>",
    "quantity": "ClearHeight"
  },
  "proposed_value": {"value": 3.45, "unit": "m"}
}
```

The browser's claim to an investigation or digest is not authorization. NET's
adapter must validate identity, permissions, revision, target and quantity
compatibility before planning; then use the existing execution path only for
an explicit execution request. A preview/selection does not run a provider.
Require idempotency for accepted requests and a defined outcome for duplicate,
stale and interrupted requests. A process failure is not a successful result.
Retain admitted execution failures according to the existing runner contract;
malformed requests rejected before execution do not acquire fake execution IDs.

GSC cannot choose executable paths, register providers, change source pins or
call CSE/CSR/SCR directly. A public portfolio uses deliberately published
artifacts; sharing a UX does not grant access to a private session. Existing
write-capable freight routes in GSC are legacy application surfaces and are
not reclassified as read-only by this architecture decision.

## Python, Rust, Julia and C++

Python/`ciw` remains the scientific controller and owner of investigation
records. Selected native operations can use the existing SCR/Rust supervision
path with explicitly bound Julia **or** C++ providers. This is not a mandatory
four-language pipeline and does not imply that the complete CSE or CSR solver
has been ported. GSC remains a TypeScript representation client. Language
bindings never transfer domain or evidence authority.

The independently developed bounded linear-map and BIM/CSR inspection slices
must be assessed through their own changes and qualification evidence. A mean
response without propagated covariance is labelled as such, not promoted to a
full posterior or path-uncertainty workflow.

## Acceptance gates and development order

Finish and verify already assigned pilot work first. Then extend the existing
registration/session path in bounded increments:

| Gate | Required evidence before claiming completion |
| --- | --- |
| Catalogue and resolution | Tests for exact version/type/model selection; unknown, ambiguous, unavailable and unqualified providers remain distinguishable. |
| Typed composition | A real CSE result accepted by a specifically supported surface/path adapter; refusal of unsupported geometry, units, frames and stale bindings. |
| Execution | Real owning providers, not mock results; preserved source/runtime identities and per-step execution/result/refusal records. |
| Uncertainty | Declared coordinate order and assumptions, retained covariance/unknown status, explicit treatment of shared uncertainty and domain validity. |
| View intents | Selection/preview causes no scientific execution; stale/duplicate/tampered requests are tested; only the NET execution boundary can launch providers. |
| Inspection and replay | Provider-free reopen; explicit replay with fresh execution IDs; old history retained; unavailable historical runtime is not replaced by latest. |
| End-to-end | One qualified BIM -> supported surface/path -> CSR -> GSC investigation, including a failing candidate and traceable limitations. |

A mock, parsed fixture, passing schema test or README diagram cannot satisfy the
real-provider gate. Numerical checks do not establish field validation,
equipment authorization or platform-wide industrial qualification. This
architecture change does not merge active branches, waive release/protection
gates, publish private configuration or alter repository visibility.
