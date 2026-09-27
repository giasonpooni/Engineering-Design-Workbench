# Notations Design Terminal

**Run scientific calculations, compare changes, and keep a checkable record.**

**Notations Design Terminal** is a terminal-first scientific computing and
cyber-physical design workbench from **Notation Systems**. It runs supported
models and analysis operations, saves their inputs and results, and lets you
inspect or reopen a study without running it again. Supported sensing and
apparatus integrations extend the same investigation into physical experiments.
For supported workflows, you can vary model parameters, compare the responses,
and inspect uncertainty, residuals and other checks.

An **investigation** is the question together with the models, observations,
settings, calculations and checks used to answer it. Notations keeps these connected
rather than saving only a final number or plot. Engineering design is the main
use: change a permitted input, calculate the response, check the result and
compare candidates.

Notations Design Terminal extends the existing **Computational Instrumentation Workbench (CIW)**.
The Python package and terminal command remain `ciw`; this is not a second
runtime. The software works without a graphical viewer or an AI assistant.

[notations.io](https://notations.io) · [Quickstart](#quickstart) · [What works today](#current-scope) ·
[How it works](#how-an-investigation-works) · [Development priorities](#next-gates) ·
[Documentation](docs/README.md)

<a id="current-scope"></a>
## What works today

Support is specific to each operation. The [operation catalogue](docs/INSTRUMENTS.md)
contains the commands; [integration coverage](docs/INTEGRATION_COVERAGE.md)
records exercised paths, independent checks and remaining gaps.

| You can | Scope and requirements |
| --- | --- |
| Generate a synthetic oscillator recording and calculate statistics or a spectrum. | Built-in example; no external scientific provider or hardware required. |
| Save, inspect, reopen and explicitly replay investigations. | Reopening reads retained inputs and results without recomputing them. Replay is a new execution with its own identity. |
| Run supported measurement, telemetry, calibration, estimation and design workflows. | Uses the exact provider versions and input assumptions listed in the integration guides; not a generic live sensor-fusion service. |
| Evaluate supported covariance and geometric-path calculations. | Bounded matrix, mesh, translation-flow, flat-torus and curved-path operations; each has its own numerical limits. |
| Inspect model equations and make bounded what-if previews. | Equation cards and offline previews associated with the oscillator workflow; the full learning curriculum is not implemented. |
| Follow a retained RMS lesson through the existing statistics operation. | [One worked investigation](docs/LEARNING.md), with a separate Decimal comparison and explicit replay; no new curriculum engine or proof claim. |
| Evaluate a recorded machine configuration. | Read-only encoder/gearbox/leadscrew reference workflow, with configuration, inputs and results retained together; no firmware loading or actuation. |
| Run selected stability and computation checks. | PLSR and registered SCR/SP1 operations have separate requirements and scopes; they do not verify every calculation or physical model. |
| Capture and compare GPU energy-to-accuracy measurements. | Explicit host capture requires a supported NVIDIA device and its NVML interface. Shared-session analysis uses retained logs. |
| Inspect results in optional graphical clients. | Godot views and read-only geographic inspection use retained records; neither changes the scientific result. |

The broader laboratory integration is still being completed. Current support
does **not** establish general-purpose hardware acquisition, equipment control,
a complete mathematics curriculum or platform-wide industrial qualification.

## Quickstart

Run these commands from the repository root with **Python 3.11 or newer**.
The [installation guide](docs/quickstart.md#install) includes virtual-environment
instructions for Windows, Linux and macOS.

```sh
python -m pip install -e .
python -m ciw demo --output recordings/demo.json
python -m ciw analyze stats --recording recordings/demo.json --channel q --start 2 --end 8 --output-dir results/stats
python -m ciw analyze spectrum --recording recordings/demo.json --channel q --start 0 --end 12 --output-dir results/spectrum
python -m ciw inspect results/spectrum/workspace.json
```

This generates a **synthetic damped-oscillator recording**, calculates statistics
and a spectrum for its displacement (`q`) channel, and inspects the saved spectrum workspace.
The spectrum is a periodogram power spectral density, not a spectrogram.

The named outputs are:

```text
recordings/demo.json              generated source recording
results/stats/workspace.json      saved statistics investigation
results/spectrum/workspace.json   saved spectrum investigation
```

Each analysis directory also retains its source recording and result records.
Use separate output directories to keep distinct workspace snapshots. Inspecting
or reopening a workspace does not rerun the calculations; additional execution
requires an explicit request. This demo is not a physical experiment or a
calibration result.

For a shared terminal/viewer session, use the [full quickstart](docs/quickstart.md).
For additional scientific providers, use [workbench assembly](docs/WORKBENCH_ASSEMBLY.md)
and [provider setup](docs/PROVIDER_AVAILABILITY.md). See the
[oscillator walkthrough](docs/OSCILLATOR_OPERATOR.md) and
[deployment guide](deploy/README.md) for further operating instructions.

<a id="what-the-testbed-does"></a>
<a id="one-investigation-several-control-surfaces"></a>
## How an investigation works

```text
Model or recorded observations
             |
             v
Choose a supported calculation and declare its inputs
             |
             v
Run the selected implementation
             |
             v
Inspect the result, uncertainty and available checks
             |
             v
Save inputs, settings, result and checks together
             |
             +----> reopen without computing
             +----> compare a candidate change
             +----> explicitly replay as a new execution
```

A **residual** measures disagreement, for example between a predicted and an
observed quantity. An uncertainty estimate describes what the selected model
and assumptions support. Neither is silently supplied when unavailable, and a
small residual alone is not proof that a model is correct.

The existing workflows remain in place:

| Workflow | What it does |
| --- | --- |
| Measurement and estimation | Align observations, apply supported calibration and uncertainty calculations, estimate quantities, evaluate constraints and retain diagnostics. |
| Design studies | Declare a model and allowed changes, run candidate configurations, compare responses and checks, and retain the basis for revising the design. |
| Numerical geometry | Evaluate supported paths, coordinate descriptions and sensitivities without treating a displayed shape as a measurement. |
| Inspection and replay | Read retained records, inspect dependencies and repeat an operation explicitly while preserving its original history. |

A failed or refused operation remains part of the investigation. Original
observations remain distinct from predictions, estimates and corrected values.
The question, assumptions, objectives and standard of evidence are chosen by
the operator, not inferred from a successful calculation.

<a id="one-environment-separate-responsibilities"></a>
<a id="existing-runtime-same-substrate"></a>
## Architecture

Notations coordinates existing scientific software rather than replacing its equations
or solvers. A **provider** is a registered implementation of a supported
calculation. A **profile** describes the particular model, inputs, assumptions
and checks a workflow supports.

| Component | Responsibility |
| --- | --- |
| **Notations / CIW** | Manage the investigation, selected operations, saved history, inspection and explicit replay. The existing Python session remains authoritative for these records. |
| **Scientific providers** | Supply domain models and calculations through adapters with explicit source/runtime versions. Each repository retains its own scientific contract, tests and licence. |
| **Native execution / SCR** | Supply supported native execution services and runtime bindings. Python, Julia and C/C++ implementations connect through the applicable registered boundary; no mandatory language chain is imposed. |
| **Checkers / ICRH, PLSR and selected SP1 paths** | Check the numerical, contract, stability or registered-computation claims they actually support. A computation does not certify itself. |
| **Evidence handoff / ESM** | Handle separately supported retention, review and release of evidence or candidate state. Producing a result does not approve it as authoritative state. |
| **Inspection clients** | Display numerical, temporal, spectral, geographic or local 2D/3D views. Closing a viewer does not stop the backend or change retained records. |

The model, calculation and supporting evidence are related but separate records:
what is being studied, what ran, and why its conclusion should be trusted.
Unimplemented handoffs must remain explicit. Supported local investigations do
not require a proof service or an external evidence-governance service.

Every operation must state what it accepts, what it produces, which assumptions
apply and what information must be preserved. The
[state transformation contract](docs/STATE_TRANSFORMATIONS.md) records such a
declaration; validating it does not execute a calculation, prove an invariant
or authorize equipment. See [architecture](docs/ARCHITECTURE.md),
[record formats](docs/PROTOCOL.md) and [contract foundations](docs/CONTRACT_FOUNDATIONS.md)
for the implementation details.

<a id="composable-instruments-independent-scientific-authority"></a>
The [systems catalogue](docs/SYSTEMS_CATALOG.md) distinguishes native operations,
pinned adapters, contracts and pending integrations. A repository link means
that a project can be found, not that its integration has been exercised.
[Provider availability](docs/PROVIDER_AVAILABILITY.md) documents setup;
the [stack map](docs/STACK.md) records the detailed division of responsibilities.

## The design language

**State. Variation. Invariance.** These are questions about a calculation, not
additional software components:

| Question | Meaning |
| --- | --- |
| What are we studying? | The system, its state and the selected model. |
| What are we changing? | A permitted parameter, input, configuration or model choice. |
| What must remain true? | The requirements and checks applicable to that particular change. |

For an oscillator, position and velocity are state variables; damping is a
parameter. Changing damping changes the predicted response. Choosing a different
model is a different kind of change and must not silently reinterpret old
results. Discrete choices and continuous parameter changes require their own
supported operations.

<a id="computational-identity"></a>
The more detailed reasoning sequence is:

```text
State -> Structure -> Transformation -> Computation -> Verification
```

In plain language: identify the object, state its rules and assumptions, define
the change, run a method, and inspect the evidence for the answer. A mathematical
operation, its algorithm, its implementation and its checks remain distinct.

<a id="unified-mathematical-reasoning-and-learning-layer"></a>
<a id="one-substrate-two-complementary-uses"></a>
<a id="proposed-terminal-surfaces"></a>
### Learning and reasoning direction

**Planned extension after the currently assigned pilot work is completed and
verified.** The existing equation cards and previews are a starting point, not
an implemented universal tutor or theorem prover.

The aim is to teach the same mathematics that users execute in the workbench,
with a concept retaining its identity across explanations, worked examples,
calculations and checks. The proposed surfaces are:

| Surface | Purpose |
| --- | --- |
| `history` | Explain the problems, stories and contributions behind mathematical ideas. |
| `learn` | Develop a concept through examples, mechanism, notation, calculation and verification. |
| `explore` | Inspect, derive, connect and generalize concepts. |
| `work` | Use supported calculations through the existing operation system. |
| `verify` | Inspect the specific checks, bounds or proofs supporting a claim. |

These are **interface proposals**, not commands added by this README. Existing
`ciw` commands remain the operating interface.

<a id="historical-prologue-and-capability-map"></a>
The built-in curriculum is intended to start with a substantial historical
prologue covering the development and roles of mathematical fields, followed by
the shared pedagogy:

```text
Historical problem -> example -> mechanism -> mathematical structure
                   -> notation -> computation -> verification -> generalization
```

Users should be able to move between concrete, geometric, symbolic, structural,
formal, computational and research explanations without changing systems.
Learning remains optional for users who simply need to work. A first executable
lesson must reuse the same concept and operation records as its calculation and
checks; it must not introduce a second session, evidence store or execution engine.

<a id="applied-reasoning-and-natural-philosophy-boundary"></a>
This also supports the broader inquiry discussed as **natural philosophy**:
observation, questions, theories, predictions, experiments and revision. The
workbench assists formalization, computation and comparison; it does not replace
human judgment about questions, experiments or what the evidence establishes.
Mathematical proof and empirical validation remain different activities.

## Physical integration direction

**General instrument and equipment integration remains delivery work.** The
longer-term laboratory combines computational studies with supported sensors,
data-acquisition equipment and local controllers. The bounded GPU measurement
path above is not evidence of a general hardware gateway.

A physical workflow must separate:

```text
proposed action -> authorization -> device request -> controller outcome
                                                    -> measured result
```

Each supported device path must bind identity, configuration, units, coordinate
frames, clocks, operating limits and authorization. Local controllers retain
time-critical execution and equipment protections. A recommendation, command
acknowledgement or display update is not proof of a physical outcome.

An optional assistant or future MCP interface may propose work through the same
boundaries; neither receives independent equipment-control or approval authority.
Current CIW scientific operations remain read-only with respect to external
actuators. The target authority modes are Explore, Observe, Prepare and Operate,
not a claim that all four are implemented.

<a id="a-testbed-for-parametric-design-and-representation"></a>
## Research and integration directions

The research question is whether a shared description makes investigations
easier to connect and compare **without losing required meaning, results or
evidence**. Compare a conventional formulation with the shared representation
on the same inputs, independent references and declared tolerances. Include
invalid and held-out cases, and measure representation size, integration effort,
error and execution/checking costs separately.

This is a research programme, not a demonstrated universal compiler or a measured
compression advantage. Broader physics, chemistry/materials, biology, agriculture,
AEC, logistics, manufacturing, robotics and social-modelling coverage requires
separately supported models, providers and validation. The learning benefit also
needs to be tested rather than inferred from the architecture.

<a id="kernel-architecture"></a>
<a id="computational-kernel-families"></a>
<a id="language-boundaries"></a>
<a id="sensor-fusion"></a>
<a id="qualification-and-next-executable-slice"></a>
### Extending calculations and sensor fusion

A **computational kernel** performs one bounded mathematical operation. The
existing and proposed work is organized into six families: numerical algebra and
local response; dynamics and geometry; inference and sensor fusion; constraint
reconciliation; design and experiment selection; and claim/certificate checking.
These are responsibilities, not six new services or a completed universal library.

Extensions reuse existing providers and the CIW/SCR interfaces. Python remains
responsible for the shared session and records; Julia and C/C++ supply selected
scientific calculations; Rust supplies supported native execution and checks.
JuMP and JuliaControl remain candidate extensions. SP1 applies only to selected
registered computations, not automatically to Julia output or physical truth.
See [Julia/SP1 contracts](docs/JULIA_SP1.md) and [integration coverage](docs/INTEGRATION_COVERAGE.md).

The next numerical extension starts with an actual bounded linear-response or
oscillator request, an independent reference comparison and retained results.
A subsequent two-sensor case must preserve clock/frame mappings, shared errors,
full required covariance, pre-update predictions and innovations. Duplicate
observations must not add information twice; missing and late data need explicit
handling. The [covariance guide](docs/COVARIANCE.md) records current limits.

<a id="kernel-contracts"></a>
<details>
<summary>Implementation requirements for numerical extensions</summary>

- Declare input/output order, units, frames, clocks, sample support, model identity,
  allowed changes and validity domain. Linearization must name its base point;
  vector subtraction is not assumed valid for every state space.
- Record arithmetic, tolerances, algorithm/runtime versions, resource limits,
  and any random-stream and replay policy. Distinguish exact, approximate and
  stochastic claims; matching software versions do not guarantee bitwise equality.
- Preserve dependencies and the uncertainty representation a model requires.
  Unknown uncertainty is not zero; covariance is not appropriate for every model.
  Keep original observations and pre-correction residuals when computing corrections.
- Keep numerical routines separate from storage, policy and device I/O. Use bounded
  process messages where isolation is needed; in-process bindings require tested
  ownership, buffer layout, endianness, version and error-handling rules.
- Retain transport bytes and any canonical semantic representation separately.
  Saved data must not select arbitrary imports, code or executable paths; worker
  failure must not become an empty successful result.
- Challenge duplicate, dropout, late-data, shared-error and stale-binding cases.
  Unsupported cross-covariance or rank-deficient inference must be explicit.
  A satisfied balance constraint alone does not identify a faulty sensor.
- Exercise real providers, bounded failure recovery, provider-free reopening and
  fresh replay. Proof-enabled paths require genuine proof production, independent
  verification and rejection of corrupted or mismatched claims. Skipped checks
  are not passes.

</details>

<a id="testbed-framework-and-design-spaces"></a>
### Advanced descriptions of design spaces

A smooth family of designs may use local coordinates and a manifold description;
other designs may be discrete or mix both. **Parametric design manifolds** name
that specialized research case, not every investigation. Equivalence-based model
descriptions, topology and category-theoretic composition are tools to use where
a workload requires them, not prerequisites for running Notations.

Changing coordinates, reducing a model, losing information in an encoding and
coupling two physical models are different operations. A change of domain is not
automatically a new chart on the same manifold. Required calculation inputs must
survive a representation change; preserving one invariant alone is insufficient.
The existing [research context](docs/RESEARCH_CONTEXT.md) and
[state transformation contract](docs/STATE_TRANSFORMATIONS.md) describe this work.

## OpenUSD scene interchange

**Selected direction; implementation pending.** OpenUSD is intended to export
supported geometry and trajectories for inspection alongside the existing
scientific records. It does not replace the investigation, model or evidence
formats. Godot, geographic inspection and terminal-only use remain independent
of an OpenUSD installation.

Start with a read-only `.usda` export of one retained oscillator trajectory.
Reopen it with a pinned OpenUSD runtime and compare geometry, units, time mapping
and links to the original result. Challenge missing or altered dependencies
before claiming that export supported. Binary `.usdc`, packaged `.usdz` and
scene import are later, separately tested extensions.

<details>
<summary>Scene-export requirements</summary>

Use the upstream C++ API or Python bindings behind a registered adapter, rather
than inventing another scene format. Prims and transforms describe supported
assets and spatial outputs; layers and references compose scene assets; variant
sets expose selected configurations; time samples display trajectories; metadata
links them to separately retained model and result identities.

Preserve explicit `metersPerUnit`, `upAxis`, coordinate/frame mappings and
`timeCodesPerSecond` where relevant. Keep source clocks, epochs, offsets, sample
support and interpolation policy separate; interpolated display values are not
new observations. Mixed-unit assets require explicit corrective transforms.

Keep Notations investigation and result identifiers separate from scene paths. Bind contributing asset/layer
digests, layer order, selected variants and exporter/runtime identity; hashing
only the root file does not bind an externally referenced scene. Declare any
supported schema subset, tessellation, decimation or precision loss.

Missing references or unsupported geometry must not be silently approximated.
Only configured, bounded assets and host-controlled plugins/resolvers may be
used. Loading a scene cannot authorize network access, arbitrary execution,
scientific operations or equipment control. Future scene edits/imports enter as
new candidate evidence and require domain checks, never silent source replacement.
Retain original domain files, including IFC, chemistry mechanisms and numerical
arrays. Appearance materials are not validated physical properties.

Scene composition and scientific-operation composition remain separate. Keep
provider-free scientific reopening separate from optional scene inspection.
Upstream references: [OpenUSD introduction](https://openusd.org/release/intro.html),
[units](https://openusd.org/release/api/group___usd_geom_linear_units__group.html),
[stage/time APIs](https://openusd.org/release/api/class_usd_stage.html) and
[Python tutorials](https://openusd.org/release/tut_usd_tutorials.html).

</details>

## Evidence boundaries

A saved investigation distinguishes what was supplied, measured, predicted,
estimated, corrected and checked. The classification is maintained in the
[workbench overview](docs/WORKBENCH_OVERVIEW.md#evidence-classes).

Keep these distinctions explicit:

```text
mathematical object       != its representation
mathematical operation    != algorithm != implementation
execution result          != verified result
numerical agreement       != physical validation
supporting evidence       != formal proof
physical state            != belief about that state
model                     != observation
approximation             != exact object
requested action          != controller outcome != measured outcome
```

Evidence, operation, execution, result and verification identities remain
separate. Invariants, residuals, reference comparisons, error bounds, statistical
checks and proofs support different claims. No single passing check establishes
everything about a result, and no calculation grants permission to use it on
equipment. Unavailable, inconclusive, refused and failed checks remain visible.

<a id="base-pilot-the-programmable-computational-and-cyber-physical-laboratory"></a>
<a id="pilot-closure-not-unlimited-expansion"></a>
<a id="extension-rule"></a>
## Next gates

**Finish and verify the currently assigned work first.** The agreed initial
end-to-end demonstration (the **base pilot**) remains the development priority.
The learning layer, new providers and broader research directions extend that
work; they do not replace it, reset its queue or justify speculative rewrites.

Use the existing oscillator/thermal, measurement-chain and curved-path foundations
to close a shared investigation workflow, not a set of disconnected demos.
These are acceptance requirements, not gates claimed passed by this README:

| Gate | Required demonstration |
| --- | --- |
| Compose | Bind a named model and all inputs; check quantities, units, frames, clocks, representations and dependencies before execution. |
| Execute and compare | Run actual registered providers and compare against independent references under declared numerical policies. |
| Investigate | Retain baseline/candidate changes, assumptions, responses, uncertainty status and checks, including invalid or unresolved cases. |
| Reopen and replay | Read saved records without executing providers; explicitly replay with new execution identities and preserved history/version bindings. |
| Challenge and recover | Reject altered bindings and incompatible inputs; retain bounded failures, recover without losing results and identify affected dependencies. |
| Inspect and hand off | Keep headless use working; test each client, export and evidence handoff separately. OpenUSD must pass its export/reload gate. |
| Physical apparatus | For each supported device, bind configuration and authorization; test disconnects, duplicate requests, stale plans and uncertain outcomes. |
| Qualify claims | Retain actual evidence for each numerical, proof or physical claim. Report startup, transfer, computation and checking costs separately. |

The next physical-claim milestone remains a held-out reference measurement with
a replayable evidence bundle and explicit limitations. Pilot completion does not
establish physical validation of all models, production multi-user readiness,
hard real-time control or platform-wide industrial certification. Each workload
and deployment needs its own numerical, physical, security, recovery and timing
evidence. Proof generation and exploration stay outside deadline-critical control.

## Development and validation

Read [DEVELOPMENT.md](docs/DEVELOPMENT.md) before changing a contract or adding a
provider. Preserve existing commands, saved records, numerical references and
verified invariants. New workloads must reuse the current session and record
formats rather than introduce a parallel runtime or evidence store.

```text
finish assigned work -> run -> observe -> fix -> verify -> audit -> extend
```

The normal local checks are:

```sh
python -m pytest -q
python -m compileall -q src
git diff --check
```

Provider-specific checks need the exact clean checkouts and environments listed
in [provider availability](docs/PROVIDER_AVAILABILITY.md) and the operating guides.
Report unavailable or skipped checks explicitly. Documentation edits do not
constitute a new numerical validation result.

## Documentation map

| Need | Guide |
| --- | --- |
| Installation and the first run | [Quickstart](docs/quickstart.md) |
| Model exploration and equation cards | [Model exploration](docs/MODEL_EXPLORATION.md) |
| Oscillator commands and reopening | [Oscillator operator guide](docs/OSCILLATOR_OPERATOR.md) |
| Investigation scope and evidence classes | [Workbench overview](docs/WORKBENCH_OVERVIEW.md) |
| Supported operations and exact commands | [Instruments](docs/INSTRUMENTS.md) |
| Exercised integrations and remaining gaps | [Integration coverage](docs/INTEGRATION_COVERAGE.md) |
| Scientific providers and responsibilities | [Systems catalogue](docs/SYSTEMS_CATALOG.md) and [stack map](docs/STACK.md) |
| Shared session and deployment | [Workbench assembly](docs/WORKBENCH_ASSEMBLY.md) and [deployment](deploy/README.md) |
| Runtime architecture and record formats | [Architecture](docs/ARCHITECTURE.md) and [protocol](docs/PROTOCOL.md) |
| Typed inputs, models and machine configuration | [Contract foundations](docs/CONTRACT_FOUNDATIONS.md) |
| Allowed changes and mathematical assumptions | [State transformation contract](docs/STATE_TRANSFORMATIONS.md) and [research context](docs/RESEARCH_CONTEXT.md) |
| Tests and contribution requirements | [Development guide](docs/DEVELOPMENT.md) |
| Architecture diagrams | [Diagram atlas](docs/DIAGRAMS.md) |

The [full index](docs/README.md) points to the document that owns each detail.
Historical audits provide context but do not override the current operation
catalogue, integration matrix or provider manifests.

## License

Copyright © 2026 Notation Systems.

Licensed under the GNU Affero General Public License v3.0 only
(AGPL-3.0-only). See [LICENSE](LICENSE).
