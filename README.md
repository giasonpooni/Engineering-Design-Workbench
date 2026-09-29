# Notation Systems Terminal

**Research workbench and executable instrument architecture for explicit state, representation, transformation, experiment and verification.**

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

\[
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
\]

The smallest research vocabulary currently under investigation is:

\[
\boxed{
\text{State}
+
\text{Representation}
+
\text{Morphism}
+
\text{Invariant}
}
\]

A bounded container or experiment supplies scope around those objects; it is not itself the source of scientific authority.

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

## Needle: local intervention in a coupled system

**Needle** is the proposed interaction primitive for changing one bounded part of a larger coupled system without requiring the operator to mentally reconstruct every downstream relationship.

Conceptually:

\[
S \xrightarrow{N} \widetilde S
\xrightarrow{\text{run}} Y'
\xrightarrow{\text{compare}} \Delta Y
\xrightarrow{\text{verify}} S' \text{ or reject}
\]

The base state is not mutated in place. A candidate intervention should expose its dependency closure, predicted local sensitivity where available, actual recomputed consequences and verification result.

A representation is safe for a declared intervention only when the intervention is preserved exactly or within a declared tolerance. One useful research condition is:

\[
\pi\circ N \simeq \bar N\circ\pi
\]

where \(\pi\) is a representation projection and \(\bar N\) is the corresponding intervention in that representation.

Draft/unmerged [PR #90](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/90) is the first bounded implementation experiment for local intervention and selective recomputation.

## Parameterized scientific control

The scientific-controller direction treats a model as a family:

\[
M(x;\theta),\qquad \theta\in\Theta
\]

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
