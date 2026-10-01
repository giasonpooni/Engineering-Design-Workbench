# Notation Systems Terminal

**Research workbench for an invariant-preserving computational interlingua across heterogeneous scientific and engineering representations.**

[Mathematical problem](#mathematical-motivation) ·
[Review note and counterexample](docs/REPRESENTATION_PROBLEM.md) ·
[Research foundations](docs/RESEARCH_FOUNDATIONS.md) ·
[Architecture](docs/ARCHITECTURE.md) ·
[Research context](docs/RESEARCH_CONTEXT.md) ·
[Technical reference](TECHNICAL_REFERENCE.md) ·
[Documentation](docs) ·
[Quickstart](TECHNICAL_REFERENCE.md#quickstart)

> **Status discipline:** this repository contains a working Python/CLI workbench plus separately tracked research branches. A concept appearing in this README is not necessarily implemented on **main**. Implemented behavior is defined by executable contracts, tests, provider manifests and current documentation; draft PRs are identified explicitly.

## Abstract

The Notation Systems Terminal asks a narrow systems question with a broad scientific scope:

> **Can heterogeneous scientific and engineering systems be made easier to construct, inspect, perturb, compare and verify by separating underlying state from its representations, and by making transformations between those representations explicit, typed and provenance-bearing?**

The project treats scientific computation as an instrument rather than as a single solver or autonomous agent. The intended substrate connects retained evidence, admitted state, mathematical models, multiple representations, specialist execution engines, observations and verification while preserving the authority boundaries between them.

The working interaction loop is:

~~~text
program → model → generate → run → test → observe → needle
   ↑                                                   │
   └────────────── compare / revise / retain ──────────┘
~~~

The research program is deliberately additive. Existing qualified operations and evidence identities remain protected; new mathematical abstractions must demonstrate that they preserve the claims and operations they are introduced to support.

## Research premise

A complex scientific system rarely has one privileged representation. The same underlying state may be usefully projected as a graph, matrix, state-space model, spatial field, spectrum, parameter family, rendered scene or reduced control state.

The Terminal therefore distinguishes:

$$
\boxed{
\text{state}
\neq
\text{representation}
\neq
\text{execution}
\neq
\text{evidence}
\neq
\text{verification}
}
$$

The smallest research vocabulary currently under investigation is:

$$
\boxed{
\text{State}
+
\text{Representation}
+
\text{Morphism}
+
\text{Invariant}
}
$$

A bounded container or experiment supplies scope around those objects; it is not itself the source of scientific authority.

## Mathematical motivation

The first reviewable problem is **which queries and interventions survive a
change of representation**. Let $S$ be a declared mathematical state space,
$r_i:S\to A_i$ a representation, and $T_{ij}:A_i\to A_j$ an adapter.
$S$ describes a model; its correspondence to a physical system requires
separate evidence. Neither a schema nor a matching display establishes that
correspondence.

For observables $F_i:A_i\to Y$ and $F_j:A_j\to Y$ with compatible units,
frames and interpretation, exact preservation means

$$
F_j\circ T_{ij}=F_i
$$

on the declared admissible domain. This obligation concerns those observables,
not every property of either representation. If two composable maps preserve
the same observable through their intermediate representation, their composite
does too; the domains and preconditions must still match. Approximate
preservation requires an explicit metric, error bound and composition rule.

A family of queries $\mathcal Q$ defines an observational equivalence relation:

$$
s\sim_{\mathcal Q}s'
\quad\Longleftrightarrow\quad
q(s)=q(s')\quad\text{for every }q\in\mathcal Q.
$$

For a representation $r:S\to A$ and a query $q:S\to Y_q$, the query can be
recovered exactly from $r(s)$ if and only if it is constant on each fibre of
$r$. Equivalently, there is a function $\bar q:r(S)\to Y_q$ such that
$q=\bar q\circ r$. This elementary
factorization condition is settled; choosing the appropriate queries,
interventions and additional structure for a scientific workload remains a
project question. A representation can discard distinctions irrelevant to one
task while making another task impossible.

The project distinguishes the following guarantees:

| Notion | What must be specified or checked |
| --- | --- |
| Serialized equality | Identical bytes under a fixed encoding and schema. |
| Derived-output agreement | Equality of a specified calculation or aggregate under declared inputs. |
| Observational equivalence | Agreement for every query in a declared family, under a stated correspondence. |
| Statewise intervention preservation | $r\circ N=\bar N\circ r$ on every declared state. |
| Designated-invariant preservation | The named observable or property survives the map under its contract. |
| Structural equivalence | An isomorphism in a specified mathematical structure, when that stronger requirement is appropriate. |

These notions are not assumed to coincide. A transformation also carries its
assumptions, declared loss, uncertainty semantics and evidence references.
Here $N:S\to S$ is a fine intervention and $\bar N:r(S)\to r(S)$ its
proposed coarse counterpart.
Object identity across records is a separate binding claim; agreement of
observables does not by itself establish that two records identify the same
physical entity.

### A finite counterexample from the implementation

Draft/unmerged [PR #97](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/97)
contains a four-state synthetic fixture. The projection $r$ groups `cold-a`
and `cold-b` as `cold`, and `warm-a` and `warm-b` as `warm`. Each fine state has
probability $1/4$. In the negative case, $\bar N$ leaves the coarse labels
unchanged:

| Fine state $s$ | Fine intervention $N(s)$ | $r(N(s))$ | $\bar N(r(s))$ |
| --- | --- | --- | --- |
| `cold-a` | `warm-a` | `warm` | `cold` |
| `cold-b` | `cold-b` | `cold` | `cold` |
| `warm-a` | `cold-a` | `cold` | `warm` |
| `warm-b` | `warm-b` | `warm` | `warm` |

Both paths produce probability $1/2$ on each coarse label, yet the statewise
square fails at `cold-a` and `warm-a`. No deterministic coarse intervention can
represent this fine intervention exactly: states in the same source fibre
have different projected destinations. Equal output distributions therefore
do not establish intervention preservation.

The [mathematical review note](docs/REPRESENTATION_PROBLEM.md) states the
factorization criterion, the exact fixture and the commands for inspecting
its retained witnesses. The implementation checks every declared state,
including zero-probability states. These results concern a finite declared
model, not a general continuous system or physical validation.

### Open mathematical problems

1. **Task-relative equivalence:** which query family and intervention family
   capture the claims a workload actually needs? When is the induced quotient
   sufficient, and when must it retain additional distinctions?
2. **Additional structure:** what topology, measurable structure, algebraic
   relations or stochastic transition law must maps respect in a given domain?
   Sets and maps are the starting point, not a universal answer.
3. **Composition:** how should validity regions, uncertainty, error bounds and
   information loss compose without weakening downstream obligations?
4. **Identity continuity:** what evidence binds different representations to
   one modeled or physical entity as information is added, aggregated or lost?
5. **Beyond finite verification:** what regularity assumptions, error estimates
   or proofs connect a finite/discretized check to an infinite or continuous
   model? Passing a finite fixture alone supplies no such extension.

For mathematical review, the focused question is: **What is the weakest
structure that states this preservation problem correctly, and which
assumptions are missing for the intended workload?** Proposed answers can be
translated into new contracts and negative fixtures on the existing substrate.

### From mathematical statement to executable evidence

The development path is to specify spaces and maps, declare a preservation
obligation, bind a typed operation, execute a candidate, verify the claim, and
retain the witness or counterexample. AI may propose operations; the declared
contract and its checker determine what the verification supports. Execution,
verification and state admission retain separate identities and authority.

| Research increment | Implemented scope on its own draft branch |
| --- | --- |
| [#95: representation and morphism registry](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/95) | Representation/map declarations and exact registry bindings. |
| [#97: finite preservation](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/97) | Exact rational pushforwards, conditional expectations, statewise checks and retained counterexamples. |
| [#106: typed preservation contracts](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/106) | `PRESERVE`, `TRANSFORM`, `BOUND`, `FORGET`, a partial composition algebra and verification receipts; declarations still require evidence. |
| [#107: industrial semantic transitions](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/107) | Separate identity-continuity and preservation bindings with an admission-eligibility envelope. |
| [#108: interoperability ingress](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/108) | External profile/payload retention and evidence-backed qualification; no industrial format parser or mapping execution is implied. |

These increments are **draft/unmerged**, not capabilities installed by this
README's checkout. The general characterization of representation equivalence
remains open within the project. NET provides an executable setting for testing
specific formulations; it does not claim a universal mathematical theory of
representation. New formulations extend the existing workbench while protecting
previously verified contracts and evidence identities.

## Computational interlingua and the universal-adapter hypothesis

The broader architectural hypothesis is that heterogeneous scientific and engineering systems can share a **computational interlingua** without being forced into one universal domain model.

An ordinary adapter translates one interface or representation into another:

$$
R_A \rightarrow R_B
$$

The Terminal is investigating a stronger contract:

$$
\boxed{
\text{Object / State}
+
\text{Representation}
+
\text{Typed Morphism}
+
\text{Invariant or Variance Law}
+
\text{Evidence}
+
\text{Verification}
+
\text{Admission}
}
$$

A representation change is therefore not accepted merely because data can be transported or converted. The relevant question is whether the declared meaning of the operation survives the transformation, or changes only according to an explicit law.

That includes several distinct cases:

| Contract class | Required relation |
| --- | --- |
| **Invariant** | a declared property is unchanged by the transformation |
| **Equivariant** | the property changes consistently with a declared group/action law |
| **Contravariant** | direction or composition order reverses according to a declared law |
| **Commuting / path-preserving** | alternative valid computational paths agree exactly or within a declared tolerance |
| **Information-loss bounded** | a reduction or projection states what is discarded and which downstream operations remain valid |

The intended flow is:

~~~text
domain state
    ↓
declared representation
    ↓
typed transformation / computation
    ↓
candidate result
    ↓
preservation + lawful-variance checks
    ├── pass → eligible for the next declared admission step
    └── fail → retain the candidate and counterevidence; do not rewrite canonical truth
~~~

This is why **“universal adapter” is a useful shorthand but not yet a universality claim**. A new workload should be allowed to contribute its own objects, mathematical semantics, representations, morphisms, invariants, uncertainty model and validators. It should not have to collapse those semantics into NET, nor should it require a new evidence store, execution identity or verification authority merely because the domain is different.

The hypothesis is experimentally falsifiable:

> **As progressively different domains are attached, they should require new domain contracts rather than repeated redesign of the substrate's core state/evidence/execution/verification semantics.**

If each substantially different workload forces the core substrate to be conceptually rewritten, the universal-interlingua hypothesis has failed. If GIS, BIM/state estimation, fluid or thermal systems, mechanics, materials, simulation and other workloads can retain their specialist mathematics while composing through the same bounded transformation and verification grammar, the evidence for the hypothesis becomes stronger.

The objective is therefore not universal mathematics. It is a candidate **universal protocol for attaching heterogeneous computation while making preservation obligations explicit and executable**.

## Architecture thesis

The target architecture separates four planes.

~~~text
                    PHYSICAL / DIGITAL WORLD
                              │
                           observe
                              ▼
                     ┌────────────────┐
                     │ EVIDENCE PLANE │
                     └───────┬────────┘
                             │ admission
                             ▼
                    ┌─────────────────┐
                    │ CANONICAL STATE │
                    └────────┬────────┘
                             │ projections
              ┌──────────────┼───────────────┐
              ▼              ▼               ▼
           graph           matrix          spatial
           signal          spectral        rendered
              └──────────────┼───────────────┘
                             ▼
                    ┌─────────────────┐
                    │ EXPERIMENT /    │
                    │ EXECUTION PLANE │
                    └────────┬────────┘
                             │
                     observe / compare
                             ▼
                       VERIFICATION
                             │
                           retain

            ┌─────────────────────────────────┐
            │ SYSTEMIC CONTROL PLANE          │
            │ topology · parameters · agents  │
            │ scheduling · resources · models │
            └────────────────┬────────────────┘
                             │
                   configures execution,
                    never evidence truth
~~~

The current implementation already preserves distinct operation, execution, result and verification identities. The broader control-plane architecture is a research direction being developed through bounded increments, not a claim that a self-optimizing scientific system already exists.

## Typed morphisms

The project is converging on a language-neutral operation model. Candidate morphism classes include:

| Morphism | Scientific role |
| --- | --- |
| **observe** | latent/physical state → observation |
| **admit** | qualified evidence → canonical state |
| **project** | canonical state → representation |
| **transform** | one declared representation → another |
| **estimate** | observations + assumptions → candidate state |
| **simulate** | state at one index/time → predicted state |
| **coarsen / refine** | controlled movement between resolutions or model levels |
| **retrieve** | query + state/corpus → bounded relevant substate |
| **needle** | local candidate intervention with dependency propagation |
| **verify** | candidate/result + claim contract → accepted/rejected/unresolved |
| **render** | computational representation → human-observable projection |
| **rewrite** | candidate change to the computational/control graph |

A morphism should declare its domain, codomain, parameters, units, frame, scale, time semantics, validity region, uncertainty behavior, provenance and verification obligations. The implementation language is secondary to that contract.

Morphisms are not intended to be analyzed only one at a time. The research frame
also tracks **morphism families**: identity, composition, inverse/partial inverse,
dual or adjoint, representation-equivalent and commuting transformations whose
relations themselves become executable claims. Matrix algebra is used as the
first finite-dimensional reference model because it makes those relations
concrete through identity maps, composition, transpose/adjoint, kernels, images,
determinants, eigenstructure and change of basis.

See [Workbench research context](docs/RESEARCH_CONTEXT.md#morphism-frame-executable-change-with-preserved-meaning)
for the formal development frame and the distinction between invariance and
lawful variance.

## Needle: local intervention in a coupled system

**Needle** is the proposed interaction primitive for changing one bounded part of a larger coupled system without requiring the operator to mentally reconstruct every downstream relationship.

Conceptually:

$$
S \xrightarrow{N} \widetilde S
\xrightarrow{\text{run}} Y'
\xrightarrow{\text{compare}} \Delta Y
\xrightarrow{\text{verify}} S' \text{ or reject}
$$

The base state is not mutated in place. A candidate intervention should expose its dependency closure, predicted local sensitivity where available, actual recomputed consequences and verification result.

A representation is safe for a declared intervention only when the intervention is preserved exactly or within a declared tolerance. One useful research condition is:

$$
\pi\circ N \simeq \bar N\circ\pi
$$

where $\pi$ is a representation projection and $\bar N$ is the corresponding intervention in that representation.

Draft/unmerged [PR #90](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/90) is the first bounded implementation experiment for local intervention and selective recomputation.

## Parameterized scientific control

The scientific-controller direction treats a model as a family:

$$
M(x;\theta),\qquad \theta\in\Theta
$$

rather than as one fixed program. Parameter coordinates may be linear, logarithmic, angular, categorical, distributional, spatial or spectral. Model validity regions and scale transitions are intended to be explicit rather than implicit comments.

Draft/unmerged work currently includes:

- [PR #92](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/92) — parameterized typed System Board V1;
- [PR #93](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/93) — deterministic parameter programs over that board;
- [PR #89](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/89) — representation-reduction experiment;
- [PR #88](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/88) — backend-neutral Container / Experiment Calculus V1.

These branches are evidence of an active research program, not merged capabilities of this checkout.

## Polyglot execution

The Terminal is intentionally not a language monoculture.

The working division of responsibility is:

| Layer | Default role |
| --- | --- |
| **Python** | orchestration, adapters, agents, ecosystem integration and current authoritative workbench host |
| **Julia** | mathematical modeling, parameter-space exploration, numerical composition and scientific control experiments |
| **Rust** | bounded systems components, typed contracts and deterministic infrastructure where justified |
| **C++ / CUDA** | specialist native simulation and high-performance numerical kernels |

These are defaults rather than ownership claims. A scientific operation should remain semantically stable even when its backend changes.

## Research workloads

The architecture is tested through heterogeneous workloads rather than by claiming universality in advance.

Current and intended stress classes include:

- scientific computing and numerical methods;
- sensing, DSP, state estimation and uncertainty;
- geometry, GIS and reference-frame transformation;
- materials, thermodynamics and multiscale modeling;
- energy and thermal/fluid systems;
- manufacturing and robotics;
- simulation and game worlds as controllable synthetic laboratories;
- information retrieval, provenance and structured scientific corpora.

**Energy, GIS and simulation/game worlds are especially useful integration workloads** because they force several representations and scales to coexist. Domain-specific engines remain authoritative; the Terminal should compose them rather than absorb their mathematics.

## Research questions

The project currently treats the following as questions to be answered empirically, not slogans:

1. **Representation preservation:** which queries, interventions and invariants survive a projection or reduction?
2. **Operational completeness:** can a smaller independent coordinate set support a declared task without losing required intervention semantics?
3. **Cross-representation verification:** when two valid computational paths should agree, can their disagreement be measured and retained?
4. **Multiscale seams:** where do neighboring models overlap strongly enough to validate transformations between them?
5. **Architecture selection:** can alternative model/workflow structures be compared against explicit baselines without letting the optimizer weaken its own acceptance criteria?
6. **Human amplification:** can an expert manipulate a high-dimensional coupled system through a bounded board while the machine carries dependency, recomputation and provenance structure?

## Research lineage and attribution

The architecture is **informed by established mathematics and scientific-computing traditions; it is not presented as an invention of those underlying ideas**.

In particular, current research notes draw from:

- graph/matroid independence, circuit/cutset duality and hybrid network analysis;
- information theory, structural compression, universal modeling and minimax regret;
- ontology design patterns and competency-question-driven semantics;
- scientific provenance and reproducibility;
- state-space modeling, estimation, numerical stability and uncertainty;
- CALPHAD-style parameterized thermodynamic modeling and evidence/model separation;
- variational inference and bounded free-energy experiments where explicitly named.

The mapping from those sources into this architecture is annotated in [Research foundations and attribution](docs/RESEARCH_FOUNDATIONS.md). That document distinguishes **established result**, **architectural adaptation**, **project hypothesis** and **implemented evidence** so citations do not imply that a source author endorsed or implemented Notation Systems.

## Implementation boundary

On **main**, NET owns investigation state, operation selection and retained execution history. Specialist repositories retain their mathematics and implementations. Saved manifests do not authorize code execution. Reopening an investigation does not silently rerun it. Rendering is not admitted as calculation input. A successful numerical check does not establish physical validity.

See [Executable architecture](docs/ARCHITECTURE.md) for the exact implementation boundaries and [Technical reference](TECHNICAL_REFERENCE.md) for commands and qualification details.

## Reproducibility and quickstart

Use the [technical quickstart](TECHNICAL_REFERENCE.md#quickstart) for the exact installation and supported demonstrations.

The repository follows a conservative claim hierarchy:

~~~text
declared → executed → numerically checked → independently verified → physically validated
~~~

Later stages do not follow automatically from earlier ones.

## Notation Systems

Notation Systems is the public project umbrella for this research and the surrounding scientific/industrial tooling. The direction is toward reusable computational instrumentation, accessible research artifacts and collaboration with technical users and academic groups. This README does not assert a particular legal form or institutional partnership.

## Copyright and licence

**© 2026 Giason Pooni, for original contributions.**

Research citations acknowledge intellectual sources; they do not change ownership of the original implementation, grant endorsement, or claim ownership over third-party theories, software or datasets.

The existing [LICENSE](LICENSE), source notices and third-party terms govern the code and included materials.

