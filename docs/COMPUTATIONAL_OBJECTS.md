# Computational Objects and Surgical Selection

NET treats source code as one representation of a computation, not as the computation's entire identity.

`ciw.computational-object.v1` is an additive, descriptive contract that binds a bounded source span to an operation identity, mathematical domain/codomain, assumptions, relations, invariants, retained evidence and experiments. It does **not** execute a provider, authorize an edit, verify a result or admit state.

## Inspect -> perturb -> compare

A selection can request views of source, state, algebra, graph, geometry, topology, composition, evidence and experiments. Its edit envelope is deliberately narrower than repository authority: v1 can name only the selected object's bound source path and still requires separate human/executor authorization.

A context package is suitable for a coding agent because it carries the selected object plus only direct dependencies, consumers, evidence, experiments and invariants. This gives an agent a bounded semantic neighborhood without claiming that the package is complete repository context.

Perturbations are inert records. They declare one dimension (input, parameter, implementation, precision, solver, backend or representation), the proposed change, and the observations that a later authorized executor should retain. Comparison can summarize finite numerical differences, but remains `not_verified`; invariant assessment and scientific verification stay separate.

## Mathematical lenses

The contract intentionally supports multiple projections of the same object:

- state-space: `x_(t+1) = F(x_t, u_t, theta)`
- algebra: `f : X -> Y`
- graph: dependencies, consumers and compositions
- topology/geometry: neighborhoods, continuity, configuration spaces and trajectories
- composition: alternate paths may later be tested for exact or tolerance-bounded commutativity

Category-theoretic language is therefore used where composition is real; it is not imposed on every source function.

## Boundary

Specialist repositories still own their mathematics and implementations. Existing NET Session, Workbench, provider registry, operation identities, execution records and verification identities remain authoritative in their existing roles. This contract is a navigation and experiment-description layer over those objects, not a replacement substrate.

The first implementation is intentionally library-level. UI/source-index adapters can project AST/LSP/tree-sitter spans into this contract later without changing its authority boundary.
