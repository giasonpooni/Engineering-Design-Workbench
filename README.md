# Notations Engineering Terminal

**A programmable workbench for scientific computing, simulation and evidence-backed game production.**

[Portfolio](https://notation.systems) · [Premise](#premise-build-the-game-and-the-production-system) ·
[Game Foundry](#game-production-foundry) · [Engineering experiment](#engineering-experiment-and-evaluation) ·
[Quickstart](#quickstart) ·
[Technical reference](TECHNICAL_REFERENCE.md) · [Documentation](docs) ·
[Copyright and licence](#copyright-and-attribution)

NET connects models, declared runs, observations and comparisons in a retained
investigation. It supports the development loop around a system without
replacing the application that owns that system's live state.

```text
author → run → observe → compare → modify → check
                └──────── retained investigation ────────┘
```

## Notation Systems

[notation.systems](https://notation.systems) is the portfolio umbrella for
independent computational systems, simulation and interactive-software projects
by **[Giason Pooni](https://github.com/giasonpooni)**. The website presents the
work; each repository retains its own implementation, status and licence.

Portfolio areas: **Games & Interactive · Simulation · Tools · Research · About**.
Website publication and repository availability are separate; a project link
does not imply that a hosted demo or released game exists.

## Role, contribution and status

| Field | This project |
| --- | --- |
| Role | Scientific, simulation and game-production workbench; portfolio category: **Tools**, with a coupled engineering experiment. |
| Author's work | Architecture, implementation, runtime interfaces, investigation workflows, instrumentation and tests. |
| Core identity | Python package and CLI **`ciw`**; existing session and record contracts remain unchanged. |
| Status | Active development; bounded scientific workflows and separately tracked native/production prototypes. Industrial-scale agentic production remains an experimental goal. |

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

**Status snapshot: September 29, 2026.** Scope and implementation are separate.
The existing workbench remains the foundation; development increments on other
branches must not be assumed present in this checkout.

| Layer | Evidence and limit |
| --- | --- |
| Existing workbench | Retained investigations, declared operations and scoped scientific workflows; see the [technical reference](TECHNICAL_REFERENCE.md). |
| Bounded production prototype | [PR #65](https://github.com/giasonpooni/Notations-Engineering-Terminal/pull/65), draft and unmerged at this snapshot, extends the PR #51/#57 controller and game-trace work with work orders, fixed acceptance checks, retained attempts and predeclared parameter repairs. |
| Native reference workload | The cited prototype attaches a synthetic Godot courier scenario, **not 1792 or Blender asset production**. It is a local sequential controller, not autonomous source rewriting or a distributed agent farm. |
| Next integration | One game-owned 1792 scenario or asset operation with an explicit contract and retained output, followed by a separately provisioned coding-agent worker. |
| Larger Foundry scope | Parallel workers, durable recovery, token/currency budgets and broader content pipelines are development goals, not capabilities established by the cited prototype. |

Read the [production guide at the inspected PR #65 revision](https://github.com/giasonpooni/Notations-Engineering-Terminal/blob/98386f4dfa621f6340670755603abd229be4684f/docs/NET_PRODUCTION.md)
for exact commands and limits. Its operation-count budget is not a money budget;
its logical worker lanes are not running AI agents. A passing acceptance check is
not state admission or release approval. This README neither merges that branch
nor expands any execution permissions.

The first game attachment should retain both a baseline and a deliberately failing
candidate, enforce the same contract through repair, preserve original failure
records, and make missing evidence hold dependent work. Inspection must not
restart the engine. The accepted result must then be demonstrated in a playable
build and reviewed for its actual gameplay or visual effect.

## Engineering experiment and evaluation

The research question is practical: **can bounded agentic workflows increase
accepted, integrated game production per human hour without degrading quality or
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
| Useful throughput | Matched-scope work accepted **and integrated** into a tested playable build; do not equate unlike artifacts or count unused generation. |
| Human effort | Specification, tool development, supervision, review, integration and repair time; report setup investment separately from recurring work. |
| Cost and latency | Provider/compute spend, elapsed time, retries and blocked time per accepted work package. |
| Quality and rework | First-pass acceptance, regressions, integration conflicts, discarded work and human playtesting/visual review. |
| Reuse and scaling | Net benefit on a new task after adaptation cost; compare sequential and bounded parallel execution before increasing worker count. |

Begin with bounded Gujranwala content and gameplay, then test the workflow on
unseen task types. Later reuse in
[Hero of the Two Worlds](https://github.com/giasonpooni/Hero-of-the-Two-Worlds)
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
| Blender-authored Godot / Bevy experiment | [PR #45](https://github.com/giasonpooni/Notations-Engineering-Terminal/pull/45): bounded, headless projectile work; not a released game. |
| Julia-authored native oscillator | [PR #47](https://github.com/giasonpooni/Notations-Engineering-Terminal/pull/47): checked C export with Python/Rust consumers. |
| C++ and Godot native consumers | [PR #50](https://github.com/giasonpooni/Notations-Engineering-Terminal/pull/50): native-interface and headless numerical qualification. |

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

The complete previous README is preserved **verbatim** in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md), including setup, available
workflows, assumptions, limits, compatibility notes and development gates.
It remains in the repository root so its relative documentation and asset links
keep the same base. This overview updates scope and portfolio positioning; it does not
promote planned integrations into implemented capabilities.

## Copyright and attribution

**© 2026 Giason Pooni, for original contributions.** Notation Systems is the
independent project umbrella, not a claim of ownership over third-party tools
or inherited code. Contributor and upstream copyright notices remain in force.

The existing [LICENSE](LICENSE), source notices and third-party terms continue
to govern the code and included materials. This documentation update does not
relicense the project, add a blanket “all rights reserved” restriction, or
change the rights already granted by those terms.
