# Surface Path

**Explore paths on curved surfaces and how small changes alter their trajectories.**

[Portfolio](https://notation.systems) · [Technical reference](TECHNICAL_REFERENCE.md) ·
[Documentation](docs) · [Contribution guide](CONTRIBUTING.md) ·
[Copyright and licence](#copyright-and-attribution)

## NET micro-tool

| Identity | Value |
| --- | --- |
| User-facing name | **Surface Path** |
| Proposed NET operation | `geometry.surface_path` |
| Implementation repository | `Curved-Surface-Runtime` |
| Existing runtime | Curved Surface Runtime / CSR; `geodesic_testbed` |
| Current scope | Numerical trajectories, first-order variation and uncertainty experiments on supported surface models |

The friendly name describes the geometry capability to expose through
[Notations Engineering Terminal (NET)](https://github.com/giasonpooni/Notations-Engineering-Terminal).
The operation name is an interface target, **not a newly implemented command or
proof of an installed adapter**. Existing documented interfaces remain the
runnable entry points. Surface Path handles the declared curved-surface models;
**Mesh Path** is the separate tool name for intrinsic paths on supported meshes.

How does a small change in a path's initial position or heading propagate as
the path moves along a curved surface? CSR studies that question using declared
surface models, numerical trajectories and first-order variation.

![Surface Path: Curved Surface Runtime parametric-surface testbed](figures/surfaces-testbed-v1.png)

*Repository experiment figure; not gameplay footage or a physical measurement.*

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
| Role | Specialist geometry and path-sensitivity tool; portfolio categories: **Research** and **Simulation**. |
| Author's work | Mathematical formulation, computational implementation, transfer-map and covariance experiments, reference comparisons and diagnostics. |
| Runtime identity | Existing **`geodesic_testbed`** package and interfaces; the micro-tool name does not rename them. |
| Status | Research software with bounded supported surface models and explicitly documented numerical limits; NET alias registration is separate implementation work. |

## What this contributes

The project connects a supported surface and initial conditions to a path,
its sensitivity, and inspectable numerical checks. Its reference comparisons,
convergence studies and covariance assumptions remain part of the instrument's
scientific scope—not conclusions inferred from an attractive rendering.

In the wider workflow, NET can compose supported geometry operations while a
Godot or Bevy project owns its interactive state and Blender owns authored assets.
These are integration applications, not a claim that CSR already accepts any
Blender mesh or provides a universal game-navigation solver.

Evidence, operation specifications, execution attempts and verification records
remain distinct. This naming update changes no numerical contract, integration
availability, evidence-admission rule or release authority.

## Quickstart and technical reference

The complete existing installation instructions, experiments, equations,
validation scope and implementation notes are preserved **verbatim** in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md). Relative documentation and
figure links keep their original root base. Use the documented setup/profile
for the experiment being run; a recorded numerical check is not physical
validation or a cross-platform performance guarantee.

[NET](https://github.com/giasonpooni/Notations-Engineering-Terminal) remains the
workbench. This repository retains its own mathematics, tests and implementation.

## Copyright and attribution

**© 2026 Giason Pooni, for original contributions.** Notation Systems is the
independent project umbrella, not a claim of ownership over third-party tools
or inherited code. Contributor and upstream copyright notices remain in force.

The existing [LICENSE](LICENSE), source notices and third-party terms continue
to govern the code and included materials. This documentation update does not
relicense the project, add a blanket “all rights reserved” restriction, or
change the rights already granted by those terms.
