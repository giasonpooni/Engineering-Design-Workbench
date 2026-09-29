# Notations Systems Terminal

**Compose scientific instruments, models and simulations into inspectable engineering workflows.**

[Run the existing workbench](TECHNICAL_REFERENCE.md#quickstart) · [Technical reference](TECHNICAL_REFERENCE.md) · [Development record](DEVELOPMENT_REFERENCE.md) · [Research programme](RESEARCH_PROGRAMME.md) · [Notation Systems](PUBLIC_POSITIONING.md) · [Documentation](docs)

Notations Terminal connects a question, its inputs, declared operations, results and checks in a retained investigation. It is a programmable workbench and coordination layer—not a replacement for the scientific libraries, applications or machines it connects.

```text
question / model / annotation
            ↓
declared inputs → supported operations → results and observations
            ↑                                ↓
      revised investigation ← comparison and review
```

## Use the tools without rebuilding the workflow

A scientific programmer can compare numerical results. An engineer can inspect a supported measurement or estimation operation. A simulation developer can retain and compare application traces. Each workflow uses the providers and contracts actually available in its checkout; a shared interface does not make every combination valid.

NET owns investigation/session state, composition and execution history. Specialist repositories own their mathematical implementations. Godot and other applications retain their own live state and clocks. The evidence/state service retains its separate admission and release authority.

**Existing `NET`, `net` and `ciw` identities remain.** Start with the [technical quickstart](TECHNICAL_REFERENCE.md#quickstart), which records installation, runnable commands, optional providers and limitations. Reading retained results must not silently rerun an experiment.

## What is implemented, and where?

The default workbench and the following development increments are different source identities. Links are not claims that a branch is installed, merged or released. Status below is a documentation snapshot of 29 September 2026; consult the linked PR before running it.

| Surface | Evidence and boundary |
| --- | --- |
| Scientific workbench | Existing CIW sessions, declared operations, results and comparisons; use the technical reference for this checkout. |
| Native language interoperability | [NET #71](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/71) and [Compute Runtime #11](https://github.com/giasonpooni/Notations-Compute-Runtime/pull/11): bounded FIR work using one C++ kernel and multiple language clients. Bindings to one kernel are not independent numerical implementations. |
| Game-production experiments | [#76](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/76): a measured, human-operated coding/vision revision through a native build and review workflow. It is not an unattended studio or a measured productivity multiplier. |
| Typed workflow algebra | [#79](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/79): a bounded composition vocabulary and checked lowering into existing workcells. Parallel syntax does not imply a parallel executor or a universal compiler. |
| Scientific instrument packaging | [ClockSync #3](https://github.com/giasonpooni/Notations-ClockSync/pull/3): a separately tracked instrument manifest, specimen and report surface. It does not register every instrument in NET. |
| NISE and mathematical authoring | Related projects and research directions; query-conditioned schematics, general notation frontends and minimum-representation guarantees must not be inferred from their names. |

The [preserved development overview](DEVELOPMENT_REFERENCE.md) retains earlier case studies, exact source references, Game Foundry scope and acceptance boundaries. Its dated PR snapshots remain historical records, not an aggregate feature claim for this checkout.

## One substrate, specialist implementations

Python, Julia, Rust and C++ are implementation choices, not four compulsory layers for every operation. A provider declares its inputs, units, frames, time basis, algorithm, arithmetic, environment, outputs and effects where applicable. CUDA/GPU execution belongs to specific provisioned providers; language choice alone guarantees neither precision, determinism, proof nor acceleration.

The intended common interface is a **typed operation contract**, not arbitrary source-to-source translation. Existing model representations, sessions, provider registries and retained records are extended rather than replaced. A new model notation or engine must enter through an explicit, tested adapter.

LLMs may help interpret intent, retrieve context and propose work. They do not acquire numerical authority, permission to operate a machine or the right to accept their own output by generating a plausible plan.

## Build useful tools; study what makes them useful

The research programme develops working instruments and creative workloads while testing their representation, composition and computational cost. Candidate questions include uncertainty-preserving measurement chains, task-conditioned retrieval, cross-provider agreement, incremental reuse and expert effort required for accepted output.

Performance, token savings, minimality and cross-domain generality are **hypotheses to measure**, not properties established by this README. [RESEARCH_PROGRAMME.md](RESEARCH_PROGRAMME.md) defines comparison conditions, negative cases and reporting expectations. It adds no executor, universal schema or automatic telemetry collection.

## Notation Systems and Cartesian Graphics

**Notation Systems — Frontier Tooling and Instrumentation for Digital Futures.** We develop computational instruments and operational tooling that connect scientific methods, specialist computation and human expertise.

**Cartesian Graphics — Interactive Worlds, Simulation Technology and Digital IP.** Its games and production work are creative projects in their own right and can also test shared tooling. 1792 remains the primary project; Hero of the Two Worlds is secondary. Creative direction and game-release decisions remain with the game projects.

PAYLOAD, Caravan, LANDSHARK, TRADEWIND, PayloadOS and Dossier Services retain their distinct operational/domain responsibilities. No new public product room, licence grant, legal entity, nonprofit status or ownership transfer is created here. See [public positioning and profile copy](PUBLIC_POSITIONING.md).

The public organization site stays a thin, read-only shell, with the globe explicitly labelled `synthetic:demo`. Hosted Terminal access at `notations.io` is a product direction, not a deployment claim. Public source or a navigation link does not grant access to private data, live feeds, workers or machine controls.

## Trust and compatibility

Evidence, annotations, models, operation specifications, execution attempts, results, verification and release decisions remain distinguishable. Numerical agreement is not physical validation; a passing build is not artistic or historical approval. Preserve failed attempts and unresolved results. No silent covariance repair, invented benchmark, retrospective relabelling of evidence or automatic release is authorized by this documentation.

## Copyright and licence

**© 2026 Giason Pooni, for original contributions.** Existing contributor and upstream notices remain in force. The [LICENSE](LICENSE), source notices and third-party terms are unchanged. Neither the public-interest direction nor Cartesian Graphics' IP focus transfers rights or reclassifies existing material.

The previous README is retained byte-for-byte as [DEVELOPMENT_REFERENCE.md](DEVELOPMENT_REFERENCE.md), using its original Git blob at the same repository-root base. Existing technical documents, code, tests, workflow definitions and historical pins are unchanged.
