# Notations Engineering Terminal

**A programmable workbench for scientific computing and game/simulation development.**

[Portfolio](https://notation.systems) · [Quickstart](#quickstart) ·
[Technical reference](TECHNICAL_REFERENCE.md) · [Documentation](docs) ·
[Copyright and licence](#copyright-and-attribution)

NET connects models, declared runs, observations and comparisons in a retained
investigation. It supports the development loop around a system without
replacing the application that owns that system's live state.

[Scientific system composition](docs/SYSTEM_COMPOSITION.md) adds typed
configuration compilation, coupled polymer reference models and separately
retained numerical verification: `ciw system demo --output-dir results/system-demo`.

```text
author → run → observe → compare → modify → check
                └──────── retained investigation ────────┘
```

## Organization

**Notation Systems Inc.** is the parent company in the owner-declared
parent/child company hierarchy. It is a scientific computing and systems
engineering company developing computational instruments, software and
interactive environments for understanding and building physical and virtual
systems.

Its development direction connects measurement, state estimation and sensor
fusion, scientific modelling, simulation and execution, from materials and
machines to interactive worlds. Each repository's implemented capabilities and
qualification limits remain those documented for that component.

The owner identifies the following child companies:

| Child company | Focus |
| --- | --- |
| **Notations Gaming** | Games, graphics, world building, interactive environments and gameplay simulation. |
| **Notation Manufacturing** | Design, machinery integration, process development, fabrication and production systems. |
| **Notations Laboratories** | Research and experimental validation in scientific computing, measurement, physics and chemistry modelling, materials and simulation. |

NET is shared scientific and engineering infrastructure across these companies.
Its existing Session, controller and operation registries compose investigations,
dispatch declared operations and retain execution history. Specialist providers
retain their implementations, and applications retain their live state.

Evidence, operation, execution and verification identities remain separate.
Game and simulation state do not acquire industrial evidence or canonical-state
authority through shared tooling. Cross-company handoffs use explicit contracts
and the existing admission, execution and release boundaries.

Scientific and industrial applications require calibration, uncertainty,
repeatability, validation and documented operating envelopes appropriate to the
application. Simulation alone does not validate a physical model or authorize
machinery control. Gaming prioritizes interaction, visual quality and play;
reusable simulations do not make gameplay state scientific evidence.

Notation Systems Inc. remains the declared rights holder for project-owned
original material. A company name or group relationship alone does not transfer
rights or confer signing authority. Each signed grant identifies its actual
legal licensor, rights and authorized signer; see the
[asset permission policy](docs/licensing/ORIGINAL_ASSETS.md).

[notation.systems](https://notation.systems) presents the organization's work.
Each repository retains its implementation, status and applicable licence.
Website publication and repository availability are separate; a project link
does not imply that a hosted demo or released game exists.

## Role, contribution and status

| Field | This project |
| --- | --- |
| Role | Scientific and simulation-development workbench; portfolio category: **Tools**. |
| Author's work | Architecture, implementation, runtime interfaces, investigation workflows, instrumentation and tests. |
| Core identity | Python package and CLI **`ciw`**; existing session and record contracts remain unchanged. |
| Status | Active development with bounded scientific workflows and separately tracked native/interactive prototypes. |

Use the [integration coverage matrix](docs/INTEGRATION_COVERAGE.md) to distinguish
callable operations, required provider bindings and remaining qualification.
The [2026-10-03 concerns audit](docs/CONCERNS_AUDIT_2026-10-03.md) checks the broader
platform narrative against merged source. The [retained correction loop](docs/CORRECTION_LOOP.md)
demonstrates local dependency review with preserved history and fresh results;
its synthetic reference establishes workflow behavior, not physical calibration.

## Architecture

NET owns investigation state, operation selection and retained execution
history. Specialist modules retain their mathematics and implementations.
SCR remains the shared native-execution foundation where registered; evidence
handoff and verification retain their separate authority.

**Blender** authors assets. **Godot** and **Bevy** own their respective application
worlds. NET requests supported operations and inspects explicit observations;
it does not impose one universal scene tree or ECS model on those applications.
A project does not have to use every tool.

The [engineering superrepo](docs/MONOREPO.md) co-locates 21 public modules
across composition, execution, measurement, inference, mathematics, domain
tools, representations and resources. Each keeps its package, original source
history, tests, licence and release boundary. The root Terminal package retains
its existing interfaces; declared provider revisions remain explicit.

The [Geospatial Systems Compiler](https://github.com/atomtrapping/Notations-FrameMapper-RunTime),
[Curved Surface Runtime](https://github.com/atomtrapping/Notations-Surface-RunTime), and
[State Estimator for BIM](https://github.com/atomtrapping/Notations-Estimator-for-BIM)
retain their scientific and representation responsibilities within the shared
repository. NET composes their declared interfaces.

Use `python scripts/superrepo.py list` to inspect the module registry,
`python scripts/superrepo.py audit` to verify source preservation, and
`python scripts/superrepo.py check --output-dir results/superrepo` to run the
independent public qualification lanes. The migration guide records exact
commands, selected snapshots, dependency requirements and qualification limits.

## Explore the work

| Case study | Implementation and evidence |
| --- | --- |
| Blender-authored Godot / Bevy experiment | [PR #45](https://github.com/atomtrapping/Notations-Systems-Terminal/pull/45): bounded, headless projectile work; not a released game. |
| Julia-authored native oscillator | [PR #47](https://github.com/atomtrapping/Notations-Systems-Terminal/pull/47): checked C export with Python/Rust consumers. |
| C++ and Godot native consumers | [PR #50](https://github.com/atomtrapping/Notations-Systems-Terminal/pull/50): native-interface and headless numerical qualification. |

These links identify separate development increments. Consult each PR's current
branch and status rather than assuming its implementation has been merged into
this checkout. Recorded qualification is scoped to its exact configuration;
visual agreement, numerical agreement and physical validation are different claims.

## Bounded atmospheric model

`net atmosphere` retains a declared dry hydrostatic column with temperature,
pressure, density, sound speed, viscosity and constant local ENU wind.
Independent hydrostatic quadrature and typed preservation receipts qualify the
numerical profile; exact-sample handoffs retain evidence identities and require
fresh verification. [Atmospheric engine](docs/ATMOSPHERIC_ENGINE.md) documents
the validity domain and expansion routes. Weather forecasting, measured physical
validation and receiving-provider dynamics remain unestablished.

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
keep the same base. This overview updates portfolio positioning; it does not
promote planned integrations into implemented capabilities.

## Copyright and attribution

**© 2026 Giason Pooni, for original contributions.** Notation Systems Inc. is
the parent organization. Existing creator attribution does not claim ownership
of third-party tools or inherited code. Contributor and upstream copyright
notices remain in force.

The existing [LICENSE](LICENSE), source notices and third-party terms continue
to govern the code and included materials. This documentation update does not
relicense the project, add a blanket “all rights reserved” restriction, or
change the rights already granted by those terms.
