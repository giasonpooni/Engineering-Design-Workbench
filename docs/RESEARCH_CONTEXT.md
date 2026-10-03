# Workbench research context

The workbench treats applied mathematics as structured variation over state
space. Its smallest useful description is:

\[
\boxed{\mathcal S + \Delta\mathcal S + \mathcal I}
\]

where:

- `\(\mathcal S\)` is the admissible state space;
- `\(\Delta\mathcal S\)` is an allowable variation or change; and
- `\(\mathcal I\)` is invariant structure that must survive the relevant
  transformation.

This is a research organizing principle, not a claim that every physical
system has already been identified or that every invariant is automatically
verified. A workload must still declare its state variables, domains, change
rule, and evidence for any invariant it reports.

## Derived mathematical structure

Within this vocabulary:

| Concept | Interpretation |
| --- | --- |
| Transformation | A rule that produces a state variation. |
| Constraint | A restriction on admissible states or variations. |
| Dynamics | Structured variation indexed by time, path length, iteration, or another declared parameter. |
| Observation | A partial or noisy representation of state. |
| Estimation | A transformation from observations and prior assumptions to a candidate state. |
| Invariant | A declared property whose preservation is checked within a stated scope. |
| Evidence | The records that support what was supplied, computed, checked, or left unresolved. |

The existing [state-space transformation contract](STATE_TRANSFORMATIONS.md)
implements the operational tuple around this idea: typed input and output
spaces, a transformation, constraints, invariants, and evidence. It validates
the declaration and its content identity; it does not execute the operation or
turn a declaration into proof.

## Research lineage and abstraction discipline

The project separates a cited mathematical result from the architectural
abstraction built on top of it. Detailed references and attribution rules are in
[Research foundations and attribution](RESEARCH_FOUNDATIONS.md).

Current lineages include:

- **Novak and Gibbons / matroid and hybrid-network theory** — representation
  independence, dual circuit/cutset structure, independence/exchange, and
  topologically complete variable sets. NET's cross-domain representation
  registry and "operationally complete coordinates" are architectural
  adaptations, not direct restatements of those theorems.
- **Shannon / Rissanen / universal modeling** — explicit source/model families,
  redundancy and regret relative to comparators. NET adapts this discipline to
  model/workflow comparison; coding regret is not asserted to be a universal
  engineering loss.
- **Hitzler, Gangemi, Janowicz, Krisnadhi, Presutti and the ontology-pattern
  community** — reusable semantic patterns, competency questions and explicit
  applicability limits. NET adapts this to typed semantic sockets and
  domain-extensible instrument contracts.
- **CALPHAD / Kaufman-Bernstein lineage** — evidence-informed parameterized
  model families over declared state domains. NET uses this as a strong domain
  pattern for ModelFamily, ParameterSpace and ValidityRegion abstractions.
- **State-space, estimation and numerical-analysis traditions** — explicit
  state, observation, dynamics, residuals, covariance and stability conditions.
  NET binds those ordinary mathematical objects to provenance and execution
  identities rather than claiming a new underlying mathematics.

The documentation uses the progression:

\[
\text{source result}
\rightarrow
\text{architectural adaptation}
\rightarrow
\text{project hypothesis}
\rightarrow
\text{bounded implementation}
\rightarrow
\text{evidence}.
\]

A citation supports only the stages it actually establishes.

## Morphism frame: executable change with preserved meaning

The research vocabulary can be sharpened by treating a **morphism** as the
smallest explicit unit of lawful change between identified objects or state
spaces:

\[
f:X\rightarrow Y.
\]

In this project, the word does not by itself assert a category-theoretic
implementation. It is an architectural contract: the domain, codomain,
representation assumptions, transformation law, evidence inputs and
verification obligations must be explicit.

A useful morphism record has the form

\[
\boxed{
\mathfrak M
=
(X,Y,f,\rho_X,\rho_Y,\mathcal L,\mathcal I,\mathcal E,\mathcal V)
}
\]

where:

- \(X,Y\) are identified source and target spaces;
- \(f\) is the declared transformation;
- \(\rho_X,\rho_Y\) are the representations in which it is realized;
- \(\mathcal L\) is the lawful-variance or composition law;
- \(\mathcal I\) is the set of invariants or protected relations;
- \(\mathcal E\) identifies supporting evidence; and
- \(\mathcal V\) identifies the checks that can support or reject the claim.

### Morphisms should be studied in families, not isolation

A transformation becomes scientifically useful when its relation to other
transformations is explicit. The important object is often not one function
but a **morphism family** connected by one or more of the following relations:

| Relation | Research question |
| --- | --- |
| **Identity** | What counts as no change on this object? |
| **Composition** | Which transformations may be sequenced, and in what order? |
| **Inverse / partial inverse** | Which information is recoverable after the transformation? |
| **Dual / adjoint** | How does the action transfer across a declared pairing? |
| **Representation change** | How does the same underlying operation appear in another basis, frame or model? |
| **Commutation** | Do two valid paths produce the same semantic result? |
| **Invariant restriction** | Which subspace, quantity or relation survives the transformation? |
| **Reduction / quotient** | What information is intentionally discarded, and which operations remain valid afterward? |

This supplies a stronger interpretation of a cross-representation adapter.
Suppose \(\pi:R_X\rightarrow R_Y\) changes representation and a declared
operation has realizations \(f_X\) and \(f_Y\). The preservation question is
not merely whether both programs run. It is whether the diagram commutes within
the declared exact or approximate policy:

\[
\boxed{
\pi\circ f_X
\simeq
f_Y\circ\pi
}
\]

where \(\simeq\) must be bound to a specific equality, tolerance, statistical
criterion or other verification contract.

A failure of this relation is retained as evidence that the representation
change is not adequate for that operation under the tested conditions.

### Matrix algebra as the first finite-dimensional reference model

Linear algebra provides a compact executable laboratory for this morphism
frame. Let

\[
A:V\rightarrow W.
\]

Once bases are chosen, \(A\) has a matrix representation, but the matrix is
not identified with the underlying map.

The basic structures then become:

| Linear-algebra object | Morphism interpretation |
| --- | --- |
| \(I_V\) | identity morphism; the reference for unchanged state |
| \(BA\) | composition of compatible transformations |
| \(A^{-1}\) | inverse when the transformation is bijective |
| \(A^*\) | dual/adjoint action across a declared pairing |
| \(P^{-1}AP\) | the same endomorphism under a change of basis |
| \(\ker A\) | state distinctions destroyed or made unobservable |
| \(\operatorname{im}A\) | reachable output subspace |
| \(\det A\) | compositional volume/orientation summary for an endomorphism, relative to the usual finite-dimensional assumptions |
| \(Av=\lambda v\) | invariant one-dimensional subspace and its internal action |
| \(\det(A-\lambda I)=0\) | condition under which \(A\) agrees with the scalar action \(\lambda I\) along a nonzero direction |

The familiar transpose is therefore treated as a coordinate realization of a
dual or adjoint operation under declared finite-dimensional pairings and bases,
not as an intrinsically meaningful array flip in every setting.

For a time-indexed linear map \(A(t)\), the representation also exposes a
kinematic preservation law:

\[
\frac{d}{dt}A(t)^T
=
\left(\frac{dA}{dt}\right)^T,
\]

so differentiation and transpose commute in this setting. For a rotation
\(R(t)\in SO(3)\),

\[
R^TR=I,
\qquad
R^T\dot R\in\mathfrak{so}(3),
\]

which demonstrates how identity, transpose/adjoint, dynamics and invariant
structure meet in one executable example.

### Development consequence

The implementation target is not a universal `morphism` class that erases
domain semantics. The target is a common **contract grammar** through which
domain-specific transformations can declare:

1. source and target identity;
2. admissible representations;
3. composition compatibility;
4. protected invariants;
5. lawful variance;
6. information loss;
7. evidence requirements; and
8. verification procedures.

A new domain should normally extend the vocabulary by adding domain morphisms,
invariants and validators rather than by changing the identity of evidence,
execution, result or verification records.

This gives the project a concrete research test for the proposed computational
interlingua: whether increasingly heterogeneous transformations can be attached
through the same contract grammar while their specialist mathematics remains
outside the substrate.

## Educational use

The same representation gives learners a stable way to compare mathematical
objects:

1. Identify the state variables and their units, frame, clock, and validity
   domain.
2. Describe the permitted variation and the parameter that indexes it.
3. Predict which properties should remain unchanged or change in a specified
   way.
4. Run a bounded model preview or sensitivity sweep.
5. Compare the resulting trajectory, residual, covariance, or energy trace
   with the declared invariant and record what the experiment actually tests.

For the oscillator, position and velocity form the state, damping changes the
trajectory, and the declared mechanical energy is conserved only in the
undamped case. A preview can demonstrate that relationship; it cannot establish
that a physical device follows the model.

## Research boundary

Higher-level machinery such as category-theoretic composition, observers,
optimizers, geometric transport, or learned surrogates is treated as derived
structure until a workload shows that another primitive is required. This
keeps the workbench extensible without making a mathematical label stand in
for an implementation or an evidence claim.

Every future instrument should therefore answer four questions:

- What is the admissible state space?
- What variation is being applied or considered?
- Which invariants and constraints are relevant, and over what domain?
- Which evidence establishes the transformation and which limits remain?

Those questions guide model education, augmented previews, provider adapters,
and eventual physical calibration while preserving the separation between a
declared possibility and a retained result.

