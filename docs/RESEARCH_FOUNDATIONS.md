# Research foundations and attribution

This document records the mathematical and scientific lineages that inform the
Notation Systems Terminal research program.

It is deliberately stricter than a conventional "inspired by" page. A citation
here does **not** mean that the cited author proposed Notation Systems, endorsed
this architecture, or that their theorem automatically applies to a NET
workload. The purpose is to make the path from source material to architectural
abstraction inspectable.

## Annotation vocabulary

Research-facing documentation should use the following labels when a source is
material to an architectural claim.

| Label | Meaning |
| --- | --- |
| **Established result** | A result, definition or method supported directly by the cited source within its stated assumptions. |
| **Architectural adaptation** | A NET design decision motivated by, generalized from or structurally analogous to established work. |
| **Project hypothesis** | A claim that must be tested experimentally; citation supplies context, not proof. |
| **Implemented evidence** | Behavior exercised by code/tests in this repository or an explicitly linked draft PR. |
| **Conceptual inspiration** | A useful way of thinking that is not yet a formal dependency of the implementation. |

A document should not silently move from **established result** to **architectural
adaptation**. When the step is ours, it should say so.

## 1. Graphs, matroids, graphoids and representation independence

### Source lineage

**Ladislav Novak and Alan Gibbons, _Hybrid Graph Theory and Network Analysis_,
Cambridge University Press, 1999.**  
Cambridge book DOI family: <https://doi.org/10.1017/CBO9780511666391>.

The monograph develops a vertex-independent perspective based on the dual
circuit and cutset structures of a graph, relates them to dual matroids, defines
graphoids, independence structures, basoids, hybrid rank, principal partitions
and hybrid network analysis.

Important antecedents named in that literature include **Hassler Whitney** for
2-isomorphism and abstract linear dependence/matroids, **W. T. Tutte** for
matroid theory, **Gustav Kirchhoff** for electrical-network constraints, and
later network/matroid researchers including Minty, Iri, Fujishige, Kishi,
Kajitani, Chua and others.

### Established results used as references

- A graph contains interdependent circuit and cutset structures.
- Circuit and cut spaces are dual/orthogonal in the stated binary setting.
- Graphs related by the appropriate 2-isomorphism can share the same deeper
  circuit/cutset structure.
- Maximal independent sets, rank/corank and exchange operations provide a
  language for nonredundant structural coordinates.
- Hybrid network analysis can choose mixed independent variables and seeks
  topologically complete sets of small cardinality.
- Double-independent sets/basoids and hybrid rank provide a distinct notion
  from ordinary graph rank.

### Architectural adaptations in NET

NET generalizes the **representation-independence lesson**, not the graphoid
theorems themselves:

\[
\text{canonical scientific state}
\neq
\text{graph projection}
\neq
\text{matrix projection}
\neq
\text{rendering}
\]

The proposed representation registry therefore treats graphs, matrices,
spatial fields, spectra, state-space forms and renderings as projections of a
separately identified state.

The hybrid-network idea also motivates the project hypothesis of an
**operationally complete coordinate set**: a task-specific set of coordinates
small enough for control or inspection while preserving declared queries,
interventions and validation conditions. This term is project terminology; it
is not asserted to be identical to hybrid rank outside the mathematical
conditions of the cited theory.

### Research tests suggested

- Can two representations be proven or tested to preserve the same declared
  intervention?
- Can a smaller coordinate set preserve a workload's required operations?
- Can a dual or independent representation expose invalid transformations?

## 2. Information theory, compression and universal modeling

### Source lineage

The project draws from the Shannon source-coding tradition and later universal
coding/modeling work, especially **Jorma Rissanen** and the literature on
minimax redundancy and regret.

A source used in current study notes is the Cambridge chapter:

**"Minimax Redundancy and Regret"**  
<https://doi.org/10.1017/9781108565462.010>,

together with adjoining chapters on structural compression, universal
memoryless sources, Markov sources and renewal processes.

### Established results used as references

- Description length depends on a coding/model class and a declared source
  family.
- Universal modeling compares a candidate code/model against a comparator
  class through redundancy or regret.
- Structural information can differ from instance labeling information.
- Memoryless, finite-order Markov and unbounded-memory source classes require
  different assumptions and exhibit different redundancy behavior.

### Architectural adaptations in NET

NET distinguishes four operations that should not be conflated:

\[
\text{lossless encoding},
\quad
\text{structural quotient},
\quad
\text{model reduction},
\quad
\text{control-state projection}.
\]

A smaller object is not assumed to be equally useful. Every reduction should
declare which operations and queries remain valid and which information must be
retrievable before a stronger intervention.

Minimax regret motivates a second project rule:

> an architecture or model change should be evaluated against an explicit
> comparator and loss function rather than declared "better" because it is more
> elaborate.

This does not make coding regret a universal engineering objective.

## 3. Ontology design patterns and semantic contracts

### Source lineage

**Pascal Hitzler, Aldo Gangemi, Krzysztof Janowicz, Adila Krisnadhi and
Valentina Presutti (eds.), _Ontology Engineering with Ontology Design Patterns:
Foundations and Applications_, 2016.**

The book situates ontology design patterns as reusable semantic building blocks,
emphasizes competency questions, alternatives, applicability limits,
modularization and domain-specific extension. It also traces the design-pattern
lineage back through **Christopher Alexander** and software/workflow patterns.

### Architectural adaptations in NET

The scientific board should have **semantic sockets**, not merely data types.
Candidate core patterns include:

- Identity
- Quantity
- Observation
- State
- Event
- Parameter
- Model
- CoordinateFrame
- Scale
- Transformation
- Constraint
- Uncertainty
- Evidence
- Experiment
- Verification

Domain vocabularies for chemistry, materials, energy, GIS, robotics or games
should extend these patterns rather than forcing all domains into one ontology.

Every semantic pattern should be justified by competency questions such as:

- Which observation established this quantity?
- In what unit, frame, scale and validity interval?
- Which model produced this candidate state?
- Which downstream results depend on this assumption?

## 4. Provenance, identity and reproducibility

### Source lineage

Current study material includes work on dataset provenance and compliance that
defines provenance around the origin, ownership and evolution of an artifact,
including transformations and software acting on it. The Terminal also draws on
the wider scientific provenance and reproducibility tradition.

A currently studied example is the dataset-compliance/provenance paper retained
in the project research corpus (including discussion of C2PA-style provenance).

### Architectural adaptations in NET

The strongest resulting invariant is:

\[
\text{evidence identity}
\neq
\text{operation identity}
\neq
\text{execution identity}
\neq
\text{result identity}
\neq
\text{verification identity}.
\]

A replay is a new occurrence. A digest proves content identity, not physical
truth. A valid transformation record proves lineage, not scientific adequacy.

These distinctions are already reflected in the executable architecture and
should remain protected as the control plane becomes more capable.

## 5. Thermodynamics, CALPHAD and scientific model families

### Source lineage

The current materials corpus includes:

**"Experimental data for thermodynamic modeling"**  
<https://doi.org/10.1017/CBO9781139018265.004>

and

**"CALPHAD modeling of thermodynamics"**  
<https://doi.org/10.1017/CBO9781139018265.006>.

The CALPHAD tradition is associated with **Larry Kaufman**, **Harold
Bernstein** and subsequent thermodynamic-modeling communities.

### Established pattern used as a reference

CALPHAD combines thermodynamic and phase-equilibrium evidence to parameterize
phase Gibbs-energy models across temperature, pressure and composition, and
uses those models to compute phase stability and driving forces. First-principles
calculations can provide information where experiments are missing or
inaccessible.

### Architectural adaptation in NET

CALPHAD supplies a strong domain example of the generic scientific loop:

\[
\text{evidence}
\rightarrow
\text{model family}
\rightarrow
\text{parameterization}
\rightarrow
\text{validity domain}
\rightarrow
\text{computed state}
\rightarrow
\text{experiment/revision}.
\]

NET should therefore treat **ModelFamily**, **ParameterSpace** and
**ValidityRegion** as first-class research objects rather than assuming every
provider is one fixed function.

A change to a foundational parameter may invalidate downstream derived models;
that motivates explicit dependency and invalidation graphs.

## 6. State-space models, control and numerical stability

The project uses standard dynamical-systems and control notation such as

\[
\dot x=f(x,u,\theta),\qquad y=h(x)+\epsilon,
\]

and local linearizations

\[
\delta\dot x=A\delta x+B\delta u+E\delta\theta.
\]

These are established mathematical tools. The NET-specific adaptation is to
bind them to typed state, evidence, validity, covariance and execution records,
and to compare predicted local response against actual recomputation after a
**Needle** intervention.

A dependency graph answers **where influence may propagate**; a Jacobian or
sensitivity operator estimates **how strongly it propagates locally**; retained
execution measures **what happened in the declared model**. Those claims remain
distinct.

## 7. Variational inference and free-energy experiments

The current bounded workflow is documented separately in
[VARIATIONAL_FREE_ENERGY.md](VARIATIONAL_FREE_ENERGY.md).

That document attributes its mathematical sources directly, including
**Karl Friston** for the broader variational-free-energy context,
**Baltieri and Isomura** for the filtering comparison, and **Blei,
Kucukelbir and McAuliffe** for the variational-inference decomposition.

This line of work is **not** the foundation of the whole Terminal. It is an
experimental workload. The repository explicitly does not infer physical
correctness, biological active inference, or universal architectural optimality
from minimization of the bounded numerical free-energy objective.

## 8. Manufacturing decision analysis

### Source lineage

**Venkata Rao, _Decision Making in the Manufacturing Environment Using Graph
Theory and Fuzzy Multiple Attribute Decision Making Methods_, Springer, 2013.**  
<https://doi.org/10.1007/978-1-4471-4375-8>

### Architectural adaptation in NET

Decision analysis belongs downstream of scientific state and model outputs.
Alternatives, attributes, weights and measured performance form a decision
projection; they do not become canonical evidence.

\[
\text{evidence}
\rightarrow
\text{state/model}
\rightarrow
\text{candidate alternatives}
\rightarrow
\text{decision analysis}.
\]

This separation is important in industrial deployments because changing a
weight or ranking method must not rewrite measurements or model evidence.

## 9. Scale, transformed coordinates and multiscale seams

The current mathematical study corpus includes Mellin-transform material whose
scaling law gives a precise example of multiplicative scale becoming simple in
a transformed representation:

\[
\mathcal M[f(ar)](s)=a^{-s}\mathcal M[f](s).
\]

The architectural adaptation is to make coordinate choice explicit. A positive
parameter may be represented linearly or logarithmically; frequency and spatial
coordinates may have separate transforms; a model can declare the region in
which its representation is valid.

This should not be confused with physical coarse-graining. Molecular →
mesoscale → continuum mappings require domain-specific mathematics and
validation.

## 10. Conceptual inspirations not yet formal dependencies

The following ideas are useful research lenses but are **not current
implementation foundations**.

### Moduli spaces — Riemann, Teichmüller, Grothendieck, Mumford, Mirzakhani

The useful conceptual move is to study a **space of admissible structures** rather
than only one structure. NET currently implements ordinary parameter and
configuration spaces. It should use "moduli space" only when an actual
equivalence relation and quotient structure have been defined.

### Category theory — Eilenberg and Mac Lane and later applied/compositional work

Category theory supplies useful language for objects, morphisms, composition
and commuting diagrams. NET currently treats it as a possible specification and
verification language. A diagrammatic resemblance is not itself a categorical
implementation.

### Musical instruments and scientific instruments

The instrument analogy is project language: a bounded interface exposes a large
compositional space while rapid observation lets expertise compound. This is a
design objective, not a mathematical theorem.

## 11. How architecture documents should cite research

When a source materially shapes a design choice, use a short annotation near the
claim and link here for detail.

Example:

> **Research annotation — architectural adaptation.** Representation identity
> is kept separate from canonical-state identity, motivated in part by the
> graph/graphoid distinction in Novak and Gibbons; NET generalizes that lesson
> beyond the theorem's graph-theoretic domain.

Do not write:

> "Novak and Gibbons prove the NET canonical-state architecture."

They do not.

Likewise, do not write:

> "Mirzakhani's moduli spaces justify the parameter board."

They do not. The relationship is conceptual unless the required mathematical
structure is constructed.

## 12. Research-to-implementation rule

The documentation should preserve this sequence:

\[
\boxed{
\text{source result}
\rightarrow
\text{architectural adaptation}
\rightarrow
\text{testable hypothesis}
\rightarrow
\text{bounded implementation}
\rightarrow
\text{evidence}
}
\]

A source citation can justify the first arrow and motivate the second. Only
experiments in the repository can support the final two.

This document should evolve as additional mathematical machinery becomes an
actual dependency of implemented work.
