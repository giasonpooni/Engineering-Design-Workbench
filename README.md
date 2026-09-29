# Notations Systems Terminal

**A programmable workbench and unified control plane for scientific computing, simulation and bounded expertise-to-artifact workflows.**

[Notation Systems](#notation-systems) · [Expertise amplification](#expertise-amplification) ·
[Domain composition](#one-control-plane-bounded-domain-workloads) ·
[Game Foundry](#game-production-foundry) · [Engineering experiment](#engineering-experiment-and-evaluation) ·
[Quickstart](#quickstart) · [Technical reference](TECHNICAL_REFERENCE.md) ·
[Documentation](docs) · [Copyright and licence](#copyright-and-attribution)

NET connects models, declared runs, observations and comparisons in a retained
investigation. It supports the development loop around a system without
replacing the application that owns that system's live state. The repository is
**Notations-Systems-Terminal**; existing **NET**, **`net`** and **`ciw`** identities
are retained. The firm is **Notation Systems**.

```text
author → run → observe → compare → modify → check
                └──────── retained investigation ────────┘
```

## Notation Systems

[**Notation Systems**](https://notation.systems) develops evidence-backed
industrial intelligence, computational instrumentation and tooling for physical
systems. Its purpose is to connect domain expertise, observations and declared
models to inspectable computation, justified decisions and bounded production
work. The service direction remains **verify → refresh → reconstruct** for a
defined scope, not generic AI output or an assumed universal digital twin.

| Identity | Responsibility |
| --- | --- |
| **PAYLOAD** | Physical-economy and operational context: organizations, facilities, materials, shipments, custody and network dependencies. Existing **Caravan** movement/logistics interfaces retain their identity. |
| **LANDSHARK** | Parcels, sites, ownership/use, access, development and spatial constraints. |
| **TRADEWIND** | Contracts, prices, commitments, exposure and physical-economic/market analysis. |
| **PayloadOS** | The governed industrial evidence/state and service substrate; not replaced by this workbench. |
| **Dossier Services** | Scoped service delivery and compilation of permitted dossiers, reports and other customer-facing releases. |
| **NET** | The shared programmable workbench/control plane for investigations, typed operations, execution history and comparisons. It is not a second canonical industrial ledger. |
| **Cartesian Graphics** | Notation Systems' games, graphics, physics and simulation studio/label. This organizational description does not assert a separately incorporated subsidiary. |

Manufacturing, robotics, materials/chemistry, GIS/remote sensing, DSP, scientific
computing and analytics are **engineering workload families** that can extend
this shared architecture. They are not extra public product rooms, nor claims
that every corresponding adapter or industrial service is deployed. PAYLOAD,
LANDSHARK and TRADEWIND retain their distinct domain identities.

```text
Notation Systems
├── Industrial intelligence: PAYLOAD / LANDSHARK / TRADEWIND
├── PayloadOS and governed service delivery through Dossier Services
├── Shared computational instrumentation and the NET workbench
└── Cartesian Graphics
    ├── Physics, simulation, graphics and world systems
    ├── 1792 — primary historical-biographical game
    ├── Hero of the Two Worlds — secondary, gradual development
    └── Geronimo — on hold
```

Cartesian Graphics' layered worlds motivate research into physics engines,
coupled physical and multi-agent dynamics, and multirate simulation. These are
development directions, not a claim that a general-purpose multiphysics engine
or every planned world system is implemented. NET remains the shared workbench;
Game Foundry is a workload on that substrate, not a new studio-specific engine.

**Shared primitives; separate state authority.** Specialist repositories retain
their mathematics, implementations and licences. ESM retains industrial evidence,
admission and release authority; game repositories retain their live state,
clocks, creative direction and game-release approval. Evidence, operation,
execution and verification identities remain distinct. Reusing a numerical model
or simulation does not make its output admitted industrial evidence.

The work is by **[Giason Pooni](https://github.com/giasonpooni)**, with contributor
and upstream attribution retained. The public website presents organization and
project information; each repository retains its own scope, status and licence.
The public organization shell remains read-only, with GSV's interactive globe
explicitly labelled **synthetic:demo**; GSC is a repository link, not a compiler
server exposed through that shell. Credentials, NET execution, industrial state
writes and live-provider access do not belong in that public bundle. Website
publication and repository availability are separate: a project link does not
imply that a hosted operational service or released game exists.

## Role, contribution and status

| Field | This project |
| --- | --- |
| Role | Scientific, simulation and production workbench; a shared control plane, not a universal domain model or replacement engine. |
| Author's work | Architecture, implementation, runtime interfaces, investigation workflows, instrumentation and tests. |
| Core identity | Existing **NET / `net` / `ciw`** interfaces; session and record contracts remain unchanged by this documentation. |
| Status | Active development; bounded scientific workflows and separately tracked native/production prototypes. Cross-domain expertise compilation and industrial-scale agentic production remain experimental goals. |

## Expertise amplification

The general problem is **expertise amplification rather than expertise
substitution**: help a domain expert turn knowledge, corrections and decisions
into inspectable production work. A historian, mechanic, chemist, architect or
game designer may know what matters without having a complete formal
specification. Capture must retain that distinction instead of manufacturing
certainty or treating fluency as evidence.

```text
expert statement + sources + constraints
                 ↓
retained capture: claims / observations / heuristics / variants / questions
                 ↓
reviewed, domain-scoped specification — not automatic evidence admission
                 ↓
typed dependency graph and bounded work orders
                 ↓
registered tools / solvers / agents in explicitly provisioned workspaces
                 ↓
candidate artifacts + execution observations
                 ↓
independent checks + required expert review
                 ↓
accepted work → separately authorized integration / release
                 ↑
      retained failures and bounded repairs
```

**This is the target workflow, not a newly installed universal compiler.** The
`expertise.capture`, `expertise.formalize` and similar names discussed during
design are proposed vocabulary, not commands advertised as available in this
checkout. Existing commands are documented in their implementation-specific
guides and branch snapshots.

Capture should distinguish observations, attributed claims, interpretations,
procedures, heuristics, preferences, exceptions, conflicting accounts and open
questions. Preserve raw input and its provenance; a reviewed specification can
select an interpretation for a game without asserting it as historical fact.
Industrial canonical admission remains a separate authorized decision under its
own evidence policy. One expert's correction does not automatically overwrite
another domain's accepted state.

The design objective is for recurring human work to concentrate on **novel,
consequential decisions**, rather than manual repetition across artifacts.
This does not eliminate elicitation, research, review, measurement or integration
cost. The workbench should first attempt authorized machine-resolvable work,
then present unresolved decisions with supporting evidence, alternatives,
uncertainty and the affected scope. Mandatory human gates remain mandatory even
when a model reports high confidence.

## One control plane, bounded domain workloads

NET owns the reusable coordination machinery. A domain owns its models, evidence
policy, state semantics, specialist operations and release criteria. A workload
binds those responsibilities for one declared task. New workloads extend the
existing Session, registries and retained record contracts rather than starting
another control plane, monorepo, canonical store or game engine.

| Proposed workload contract | Required distinction |
| --- | --- |
| Typed inputs and outputs | Schema/version, units, frames, clocks, provenance and uncertainty must be explicit where relevant. Compatible filenames or language bindings are not sufficient. |
| State and evidence references | Raw observations, estimates, simulations, source claims and accepted domain state remain distinguishable. |
| Operations and executors | Operation identity is separate from the selected agent/tool, invocation, environment and execution attempt. |
| Capability envelope | Explicit readable inputs, writable candidate paths, permitted tools/network access, budgets and stop conditions; never permissions inferred from a plan. |
| Observation and verification | Keep measured traces, computed results, checks, unresolved conditions and verifier identity. Workers cannot silently redefine their acceptance criteria or approve their own release. |
| Promotion and repair | Acceptance, evidence admission, integration, release, dispatch and reconciliation retain separate authorization and records. Preserve rejected attempts. |

A **domain container** first means a bounded semantic/authority contract. It is
**not, by itself, an OS security sandbox**. Running untrusted workers requires
separately implemented and tested process/container isolation, credential and
network restrictions, resource limits and an appropriate threat model. An MCP
connection exposes a tool interface; it does not automatically supply isolation,
trust, permission to actuate equipment or independent verification.

The categorical direction is **typed composition**: operations compose when
their input/output contracts and domain conditions agree. This is not a claim of
a proved category-theoretic implementation, a universal ontology, or automatic
translation of arbitrary Python, Julia, Rust and C++ programs. Specialist
repositories remain usable independently, with explicit adapters where supported.

### Change propagation and transfer: validation targets

A changed claim, parameter or accepted specification should identify the affected
dependency closure, mark derived candidates stale, and schedule only the
necessary rebuilds and checks. This is a **development target**: sound incremental
rebuilds require declared dependencies, versioned tools, external inputs and
cache semantics. An undeclared dependency can invalidate any minimal-rebuild
claim. Existing released artifacts remain immutable and separately superseded;
they are not silently rewritten or republished.

The first generalization experiment is one actual 1792 episode/work package,
followed by a bounded sensor/DSP or materials task using the same control-plane
contracts. Domain schemas and validators may differ. Success requires accepted,
integrated output on the second task with measured adaptation cost and unchanged
protected session/authority semantics—not merely two similar diagrams or more
generated files. Physical conclusions additionally need appropriate empirical
validation; game simulation and software tests cannot supply it by analogy.

## Premise: build the game and the production system

[**1792**](https://github.com/giasonpooni/1792) is the first major reference
workload: an ambitious historical open-world biography, developed outward from
Buddh Singh's childhood in Gujranwala toward the full Ranjit Singh narrative.
The game is a product in its own right, not merely a demonstration of AI tooling.
Its scope motivates a coupled engineering problem: how to turn a small team's
creative direction into coherent, integrated game production.

**The engineering experiment is to industrialize agentic development, not simply
to generate more code.** NET is being extended to test whether explicit work
contracts, reusable operations, bounded machine labor and independent acceptance
gates can increase useful production without making supervision, rework and
integration the new bottleneck. This is a hypothesis to measure, not an assertion
that an autonomous studio or large-studio-equivalent output already exists.

| Coupled deliverable | What must improve |
| --- | --- |
| **1792: the game** | Playable, visually coherent environments, mechanics and narrative, with source-aware historical reconstruction. |
| **NET: the production workbench** | Repeatable ways to specify, execute, inspect, compare and integrate work while preserving existing scientific workflows. |
| **The engineering experiment** | Evidence about throughput, human effort, cost, failure modes and transfer to new tasks—not agent counts or generated-file totals. |

Game requirements expose production bottlenecks; bounded workflow improvements
are then tested on actual game work. Tooling must earn its place through better
playable increments rather than becoming a second project detached from the game.

## Game Production Foundry

**Notations Game Foundry (working name: NGF)** names the game-production workload
being developed **on NET**, not a replacement for NET, a separate game engine, or
a newly released package. Scientific computing, GIS/remote sensing and simulation
remain part of the broader workbench. Existing package names and interfaces are
not renamed by this scope statement.

The intended production model is a graph of **typed transformations**. Agents,
Python scripts, procedural generators and native tools are candidate executors
of declared operations, not competing authorities over the whole project.

```text
human direction + source evidence
                ↓
reviewed specification + dependency graph + acceptance contract
                ↓
bounded work orders → explicitly bound tools / agents
                ↓
candidate code / assets / scenes / narrative
                ↓
checks + human review where required → controlled integration → playable build
                ↑                                               ↓
                └──── retained failures, observations and repairs ┘
```

This diagram describes the target workflow, not a claim that every stage is
implemented or autonomous. Development-time AI does not require live model calls
in the shipped game.

| Production area | Intended reusable operations |
| --- | --- |
| Research and world specification | Source retrieval, dated claims, conflicting accounts, uncertainty and reviewed reconstruction briefs. |
| Environment and assets | Terrain preparation, modular architecture, materials, collision, navigation and asset-budget checks. |
| Gameplay and simulation | Bounded code changes, engine-owned scenarios, trace capture, regression and performance checks. |
| Narrative and presentation | Attributed oral accounts, mission dependencies, dialogue, animation, audio and visual review. |
| Integration and delivery | Isolated workspaces, artifact manifests, dependency-aware scheduling, candidate builds and explicit promotion gates. |

The initial integration priority is one repeatable 1792 workload, not all of these
production areas at once. A visually attractive asset that breaks traversal, a
passing test with an altered requirement, or a generated scene that never reaches
the game is not accepted production.

## Architecture

NET owns investigation state, operation selection and retained execution
history. Specialist repositories retain their mathematics and implementations.
SCR remains the shared native-execution foundation where registered; evidence
handoff and verification retain their separate authority.

**Blender** authors assets. **Godot** and **Bevy** own their respective application
worlds. NET requests supported operations and inspects explicit observations;
it does not impose one universal scene tree or ECS model on those applications.
A project does not have to use every tool.

The [Geospatial Systems Compiler](https://github.com/giasonpooni/Geospatial-Systems-Compiler),
[Curved Surface Runtime](https://github.com/giasonpooni/Curved-Surface-Runtime), and
[State Estimator for BIM](https://github.com/giasonpooni/State-Estimator-for-BIM)
remain independently scoped projects, not capabilities absorbed into NET.

The shared **C++–Rust–Python–Julia** direction is a set of optional, explicitly
bound execution paths, not a requirement that every project run four runtimes.
Game repositories retain their story, art direction, gameplay rules, saves and
live clocks. NET orchestrates development operations around those authorities.

Evidence, specification, operation, execution, artifact, verification and release
identities remain distinct. Retained execution history is not a second canonical
evidence store. Workers must not silently rewrite their acceptance policy, admit
evidence, approve their own release, or acquire broader permissions through a
plan. Human authors retain creative direction and approval of sensitive source,
rights and presentation decisions. Ordinary checks do not become formal proof or
historical truth; content hashes establish byte integrity, not authenticity.

## Current implementation and next boundary

**Documentation status snapshot: September 29, 2026.** Scope and implementation
are separate. The existing workbench remains the foundation; increments on
other branches must not be assumed present in this README-only checkout.

| Layer | Evidence and limit |
| --- | --- |
| Existing workbench | Retained investigations, declared operations and scoped scientific workflows; see the [technical reference](TECHNICAL_REFERENCE.md). |
| Earlier bounded production prototype | [PR #65](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/65), inspected at `98386f4dfa621f6340670755603abd229be4684f`, uses work orders, fixed checks, retained attempts and predeclared repairs around a synthetic Godot courier. This historical snapshot is not the whole subsequent Foundry scope. |
| Game-owned Foundry increment | [PR #68](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/68), currently draft/unmerged, separately tracks the 1792 water-round attachment with [1792 PR #30](https://github.com/giasonpooni/1792/pull/30). Its recorded qualification is revision-scoped; its changing head must not be treated as identical to the tested revision named in its body. This is not an autonomous studio or playable-build generator. |
| Historical-perspective increment | [PR #70](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/70), draft/unmerged at `e1fa85f89ff3f39db84ee9b157929133de49b72c`, separately tracks received-information boundaries and annotation audits. It does not implement free-form expertise extraction, historical authentication or live game integration. |
| Larger cross-domain scope | General expertise capture, dependency-aware rebuilds, secured untrusted agent containers, distributed workers and broader industrial adapters remain development/qualification targets. No universal interoperability or cross-domain productivity gain is asserted. |

Read the [production guide at the inspected PR #65 revision](https://github.com/giasonpooni/Notations-Systems-Terminal/blob/98386f4dfa621f6340670755603abd229be4684f/docs/NET_PRODUCTION.md)
for that prototype's exact commands and limits. Its operation-count budget is not
a money budget; its logical worker lanes are not running AI agents. A passing
acceptance check is not state admission or release approval. This README does
not merge those branches or expand any execution permissions.

Game attachments should retain both a baseline and a deliberately failing
candidate, enforce the same contract through repair, preserve original failure
records, and make missing evidence hold dependent work. Inspection must not
restart the engine. Accepted results must then be demonstrated in a playable
build and reviewed for their actual gameplay or visual effect; a headless
contract check is not a substitute for that review.

## Engineering experiment and evaluation

The research question is practical: **can bounded agentic workflows increase
accepted, integrated production per human hour without degrading quality or
letting coordination and rework erase the gain?** General-purpose autonomy and
studio-scale equivalence are not assumed prerequisites or established results.

Evaluate comparable work packages under direct human-led development, a single
agent with the same tools, and the orchestrated workflow. Freeze the brief and
acceptance criteria before each comparison. Record revisions, tool/model versions,
inputs, environment and budgets; report repeated trials and failures rather than
only a favorable run. Retained inputs and traces support auditability, not a
promise that stochastic generation is byte-for-byte reproducible.

| Measure | What to record |
| --- | --- |
| Useful throughput | Matched-scope work accepted **and integrated** into a tested system; for games, a playable build. Do not equate unlike artifacts or count unused generation. |
| Human effort | Elicitation, specification, tool development, supervision, review, integration and repair time; report setup investment separately from recurring work. |
| Cost and latency | Provider/compute spend, elapsed time, retries and blocked time per accepted work package; report money and time separately rather than adding incompatible units. |
| Quality and rework | First-pass acceptance, regressions, integration conflicts, discarded work and appropriate human/empirical review. |
| Reuse and scaling | Net benefit on a new task after adaptation cost; compare sequential and bounded parallel execution before increasing worker count. |
| Expertise amplification | Accepted, integrated matched-scope downstream work per consequential expert decision, alongside total human effort and quality. Fewer questions alone is not an improvement if errors are hidden. |

Begin with bounded Gujranwala content and gameplay, then test the workflow on
unseen task types. Later reuse in
[Hero of the Two Worlds](https://github.com/giasonpooni/Hero-of-Two-Worlds)
and [Geronimo](https://github.com/giasonpooni/Geronimo) is a transfer hypothesis,
not evidence already obtained or a reason to begin their full production now.
1792's childhood-to-Lahore development remains first; the full Ranjit Singh
narrative precedes historical-character DLC production.

Build and audit together: **build → run → observe → fix → audit → continue**.
Increase concurrency only when accepted throughput improves at comparable quality
and within the human/compute budget. Where overhead dominates, reduce work in
progress, repair the contract or keep the task human-led. Automated checks cannot
by themselves establish historical accuracy, artistic coherence or enjoyable play.

## Explore the work

| Case study | Implementation and evidence |
| --- | --- |
| Blender-authored Godot / Bevy experiment | [PR #45](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/45): bounded, headless projectile work; not a released game. |
| Julia-authored native oscillator | [PR #47](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/47): checked C export with Python/Rust consumers. |
| C++ and Godot native consumers | [PR #50](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/50): native-interface and headless numerical qualification. |

These links identify separate development increments. Consult each PR's current
branch and status rather than assuming its implementation has been merged into
this checkout. Recorded qualification is scoped to its exact configuration;
visual agreement, numerical agreement and physical validation are different claims.

## Quickstart

Use the [existing quickstart](TECHNICAL_REFERENCE.md#quickstart) for the exact
installation, demonstration, analysis and replay commands. Scientific provider
and engine dependencies remain optional and explicitly bound. Reading retained
results must not silently launch a runtime or rerun an experiment.

## Technical reference

The complete previous technical README is preserved in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md), including setup, available
workflows, assumptions, limits, compatibility notes and development gates.
That file is unchanged by this update and remains in the repository root so its
relative documentation and asset links keep the same base. This overview extends
scope and organizational positioning; it does not promote planned integrations
into implemented capabilities.

## Copyright and attribution

**© 2026 Giason Pooni, for original contributions.** The Notation Systems parent
and Cartesian Graphics studio relationship does not claim ownership over
third-party tools or inherited code. Contributor and upstream copyright notices
remain in force.

The existing [LICENSE](LICENSE), source notices and third-party terms continue
to govern the code and included materials. This documentation update does not
relicense the project, add a blanket “all rights reserved” restriction, or
change the rights already granted by those terms.
