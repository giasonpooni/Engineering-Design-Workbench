# Notations Systems Terminal

**A programmable computational instrument for composing scientific tools, models and simulations into inspectable workflows.**

[Run the existing workbench](TECHNICAL_REFERENCE.md#quickstart) · [Technical reference](TECHNICAL_REFERENCE.md) · [Development record](DEVELOPMENT_REFERENCE.md) · [Research programme](RESEARCH_PROGRAMME.md) · [Institutional positioning](PUBLIC_POSITIONING.md) · [Documentation](docs)

Notations Terminal connects a question, its inputs, declared operations, results and checks in a retained investigation. It is a workbench and coordination layer—not a replacement for the scientific libraries, applications or machines it connects.

```text
question / model / annotation
            ↓
declared inputs → supported operations → results and observations
            ↑                                ↓
      revised investigation ← comparison and review
```

## Notation Systems: scientific instrumentation commons

Notation Systems is being developed as a **public-interest computational instrumentation programme**: accessible scientific tools for representing, measuring, simulating and investigating physical systems.

The architecture favors **domain-independent instruments beneath domain-specific workloads**. State estimation, DSP, frame transforms, graphs, uncertainty, conservation, verification and projection should be reusable across manufacturing, materials, agriculture, robotics, energy, GIS and simulation wherever their scientific contracts actually match.

A useful provisional grammar is:

```text
Acquire → State → Retrieve / Transform / Simulate → Verify → Project
```

Energy, geospatial computation and games/simulation are cross-domain testbeds, not merely vertical products: they stress physical flow, place/reference frames and executable synthetic worlds respectively. This is a research architecture, not a claim that every operator or adapter is implemented.

## Use the tools without rebuilding the workflow

A scientific programmer can compare numerical results. An engineer can inspect a supported measurement or estimation operation. A simulation developer can retain and compare application traces. Each workflow uses the providers and contracts actually available in its checkout; a shared interface does not make every combination valid.

NET owns investigation/session state, composition and execution history. Specialist repositories own their mathematical implementations. Godot and other applications retain their own live state and clocks. The evidence/state service retains separate admission and release authority.

**Existing `NET`, `net` and `ciw` identities remain.** Start with the [technical quickstart](TECHNICAL_REFERENCE.md#quickstart). Reading retained results must not silently rerun an experiment.

## What is implemented, and where?

The default workbench and the following development increments are different source identities. Links do not imply that a branch is installed, merged or released.

| Surface | Evidence and boundary |
| --- | --- |
| Scientific workbench | Existing CIW sessions, declared operations, results and comparisons; use the technical reference for this checkout. |
| Native language interoperability | [NET #71](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/71) and [Compute Runtime #11](https://github.com/giasonpooni/Notations-Compute-Runtime/pull/11): bounded FIR work using one C++ kernel and multiple language clients. Bindings to one kernel are not independent numerical implementations. |
| Game-production experiments | [#76](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/76): a measured, human-operated coding/vision revision through a native build/review workflow. It is not an unattended studio or measured productivity multiplier. |
| Typed workflow algebra | [#79](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/79): bounded composition vocabulary and checked lowering into existing workcells. |
| Scientific instrument packaging | [ClockSync #3](https://github.com/giasonpooni/Notations-ClockSync/pull/3): separately tracked manifest/specimen/report surface. |
| NISE and mathematical authoring | Related projects/research directions; general semantic compilation and minimum-representation guarantees must not be inferred from their names. |

The [preserved development overview](DEVELOPMENT_REFERENCE.md) retains earlier case studies and exact source references.

## One substrate, specialist implementations

Python, Julia, Rust and C++ are implementation choices, not four compulsory layers. A provider declares inputs, units, frames, time basis, algorithm, arithmetic, environment, outputs and effects where applicable. CUDA/GPU execution belongs to specific provisioned providers.

The intended common interface is a **typed operation contract**, not arbitrary source-to-source translation. New notation or engines enter through explicit tested adapters.

LLMs may interpret intent, retrieve context and propose work. They do not acquire numerical authority, permission to operate machinery or the right to accept their own output.

## Build useful tools; study what makes them useful

The research programme develops working instruments and demanding workloads while testing representation, composition, uncertainty and computational cost. Candidate questions include uncertainty-preserving measurement chains, task-conditioned retrieval, transformation fidelity, cross-provider agreement, projection fidelity, incremental reuse and expert effort required for accepted output.

Performance, token savings, minimality, simulation-to-reality transfer and cross-domain generality are **hypotheses to measure**. [RESEARCH_PROGRAMME.md](RESEARCH_PROGRAMME.md) defines comparison conditions and negative cases.

## Cartesian Graphics: proposed private ownership/commercialization layer

The institutional framing is being inverted: **Cartesian Graphics is the intended private creative/commercial ownership layer; Notation Systems is the scientific instrumentation commons.**

That is a **conceptual governance direction, not a claim that a legal parent/subsidiary relationship, nonprofit, charity, IP assignment or corporate restructuring has already been completed**.

Cartesian Graphics develops interactive worlds, simulation technology and commercial/project-specific IP. 1792 remains the primary game; Hero of the Two Worlds is secondary. Cartesian can consume the same public scientific instruments as universities, researchers and industry while retaining private worlds, assets, production pipelines and other project-specific IP.

PAYLOAD, Caravan, LANDSHARK and TRADEWIND are better understood as application consumers of instrumentation rather than definitions of Notation Systems itself. Their eventual legal/commercial placement remains unresolved. See [institutional positioning](PUBLIC_POSITIONING.md).

## Trust and compatibility

Evidence, annotations, models, operation specifications, execution attempts, results, verification and release decisions remain distinguishable. Numerical agreement is not physical validation; simulated ground truth is not field validation; a passing build is not artistic or historical approval.

No silent covariance repair, invented benchmark, retrospective evidence relabelling or automatic release is authorized here.

## Copyright and licence

**© 2026 Giason Pooni, for original contributions.** Existing contributor/upstream notices remain in force. The [LICENSE](LICENSE), source notices and third-party terms are unchanged. The proposed institutional inversion transfers no rights and reclassifies no existing repository.

The previous README is retained byte-for-byte as [DEVELOPMENT_REFERENCE.md](DEVELOPMENT_REFERENCE.md). Existing technical documents, code, tests, workflows and historical pins are unchanged.
