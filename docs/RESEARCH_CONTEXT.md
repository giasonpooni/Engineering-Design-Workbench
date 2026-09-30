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

