# Notations Engineering Terminal

**A programmable workbench for scientific computing and game/simulation development.**

[Portfolio](https://notation.systems) · [Quickstart](#quickstart) ·
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
| Role | Scientific and simulation-development workbench; portfolio category: **Tools**. |
| Author's work | Architecture, implementation, runtime interfaces, investigation workflows, instrumentation and tests. |
| Core identity | Python package and CLI **`ciw`**; existing session and record contracts remain unchanged. |
| Status | Active development with bounded scientific workflows and separately tracked native/interactive prototypes. |

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

Use `python scripts/superrepo.py list` to inspect the module registry,
`python scripts/superrepo.py audit` to verify source preservation, and
`python scripts/superrepo.py check --output-dir results/superrepo` to run the
independent public qualification lanes. The migration guide records exact
commands, selected snapshots, dependency requirements and qualification limits.

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
keep the same base. This overview updates portfolio positioning; it does not
promote planned integrations into implemented capabilities.

## Copyright and attribution

**© 2026 Giason Pooni, for original contributions.** Notation Systems is the
independent project umbrella, not a claim of ownership over third-party tools
or inherited code. Contributor and upstream copyright notices remain in force.

The existing [LICENSE](LICENSE), source notices and third-party terms continue
to govern the code and included materials. This documentation update does not
relicense the project, add a blanket “all rights reserved” restriction, or
change the rights already granted by those terms.
