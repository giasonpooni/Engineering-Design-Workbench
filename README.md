# Notations Engineering Terminal

**A programmable workbench for scientific computing and game/simulation development.**

**Notations Engineering Terminal (NET)** is the terminal-first workbench from
**Notation Systems**. It runs supported models and analysis operations, retains
their inputs and results, and lets you inspect, compare and reopen an
investigation without silently running it again. Supported measurement and
apparatus integrations connect the same workflow to physical experiments.

The development direction is a practical **game and simulation development tool
around Blender, Godot and Bevy**: author a scenario or asset, run a selected
implementation, inspect its behaviour, change a parameter, and compare the result.
Blender remains the authoring application; Godot and Bevy remain independent
application/simulation runtimes. NET manages the investigation around them rather
than replacing their editors or owning their live worlds.

**Available now:** the scientific workflows and retained-result inspectors listed
below. **Integration targets:** broader Blender authoring, Godot gameplay capture
and Bevy simulation workflows. An existing Godot inspector is not evidence that
general game-runtime control is implemented. Scientific computation, measurement,
estimation and engineering design remain part of the workbench; this direction
extends them rather than replacing them.

An **investigation** connects a question to its models, observations, parameters,
assets, executions, results and checks. The goal is to retain why a change was
made and what it did, not just the latest project files or a final plot.

Notations Engineering Terminal extends the existing **Computational Instrumentation Workbench (CIW)**.
The Python package and terminal command remain `ciw`; this is not a second
runtime. The software works without a graphical viewer or an AI assistant.
Earlier documentation used **Notations Design Terminal** and **Parametric Design
Testbed**. These are historical project titles, not new operation, execution,
result or verification identities.

[notations.io](https://notations.io) · [Quickstart](#quickstart) · [What works today](#current-scope) ·
[Game and simulation workflow](#interactive-simulation-development-direction) ·
[Architecture](#architecture) · [Development priorities](#next-gates) ·
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
| Inspect model equations and make bounded what-if previews. | Equation cards and offline previews associated with the oscillator workflow. |
| Follow a retained RMS lesson through the existing statistics operation. | [One worked investigation](docs/LEARNING.md), with a separate Decimal comparison and explicit replay. |
| Evaluate a recorded machine configuration. | Read-only encoder/gearbox/leadscrew reference workflow, with configuration, inputs and results retained together; no firmware loading or actuation. |
| Run selected stability and computation checks. | PLSR and registered SCR/SP1 operations have separate requirements and scopes; they do not verify every calculation or physical model. |
| Inspect results in optional graphical clients. | Godot Experiments and read-only geographic views use retained `ciw.experiment-view.v1` records. Coordinate, strip and mesh panels that carry `ciw.panel-render.v1` are drawn as detached copies (`connect: false`, canvas id distinct from frame). Neither client changes the scientific result. |
| Export a retained inspect canvas to ASCII USDA. | `ciw export usda --compare` matches retained points. `--usd-bin` opens the copy with a pinned usdcat/usdview; a missing pin is refused. |
| Inspect registered language bindings. | `ciw bindings` inspects without launching. `ciw bindings julia-oscillator --create` runs create only with pinned `--julia` and `--runtime`. |
| Report GPU energy availability. | `ciw energy measure` is one NVML read, measurement only. `replay-log` recomputes a retained log. No actuation. |
| Read oscillator lessons. | `ciw math work` accepts oscillator-rms, oscillator-energy and oscillator-velocity. Three lessons, not a curriculum engine. |
| Apply a declared design chart. | `ciw chart identity|scale` maps finite coordinates between named frames. A chart is not a manifold runtime or state admission. |
| Read a second oscillator lesson. | `ciw math learn oscillator-energy` is a second lesson on the same recording. It is not a curriculum engine. |

Current support does **not** establish general-purpose hardware acquisition,
equipment control or platform-wide industrial qualification.

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

The existing scientific workflows remain in place:

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
| **Notations Engineering Terminal / CIW** | Manage the investigation, selected operations, saved history, inspection and explicit replay. The existing Python session remains authoritative for these records, not an engine's live world. |
| **Scientific providers** | Supply domain models and calculations through adapters with explicit source/runtime versions. Each repository retains its own scientific contract, tests and licence. |
| **Native execution / SCR** | Supply selected native execution adapters where a profile registers them. It remains the shared execution foundation, not a new game engine or a replacement for the Python session. |
| **Checkers / ICRH, PLSR and selected SP1 paths** | Check the numerical, contract, stability or registered-computation claims they actually support. A computation does not certify itself. |
| **Evidence handoff / ESM** | Handle separately supported retention, review and release of evidence or candidate state. An inspect copy and a `render` descriptor are not modeling inputs and do not admit corpus state. |
| [Geospatial Systems Compiler (GSC)](https://github.com/giasonpooni/Geospatial-Systems-Compiler) | Compile admitted state into spatial, temporal and relational representations. `spatial.map` is the interface target; NET does not absorb the compiler or its specialist mathematics. |
| **GSV** | Project released snapshots read-only. No computation, evidence admission or state release; NET does not replace or bypass this viewer. |
| [Curved Surface Runtime (CSR)](https://github.com/giasonpooni/Curved-Surface-Runtime) | Optional specialist for its supported curved-surface paths, sensitivities and numerical diagnostics. A Blender mesh does not automatically become a supported CSR surface or navigation model. |
| [State Estimator for BIM](https://github.com/giasonpooni/State-Estimator-for-BIM) | BIM-specific evidence-to-decision instrument. It retains its domain semantics; general game perception or rover sensor fusion requires a separately qualified estimator, not a relabelled BIM adapter. |
| **Inspection clients** | Display numerical, temporal, spectral, geographic or local 2D/3D views of retained inspect records. Closing a viewer does not stop the backend or change retained records. |
| **Blender, Godot and Bevy integrations** | Optional authoring/runtime adapters described below. Their native project formats, editors and application state remain independent of NET. |

The model, calculation and supporting evidence are related but separate records:
what is being studied, what ran, and why its conclusion should be trusted.
[GIS/remote-sensing requests](docs/GIS_RS_WORKBENCH.md) are optional workbench operations, not a fourth firm domain or an embedded GIS engine.

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

## Interactive simulation development direction

**Use NET during development, not only to display the finished result.** The
target is one repeatable loop around authoring, gameplay and scientific tools:

```text
author -> build -> run -> observe -> fix -> compare -> verify -> continue
```

This is a workload family of the existing workbench. The following architecture
is a target integration, not a claim that these adapters are all implemented:

```text
Blender -- versioned assets --> Godot OR Bevy
   ^                                ^ |
   | authoring jobs                 | | selected observations
   |                         runs / | v
   +-------------------------- NET / CIW
                                  |    |
                 declared compute |    +--> retained views --> GSC / inspectors
                                  v
                       specialist providers / SCR
```

Blender supplies authored/generated assets; it is not underneath either engine
in a shared runtime. Godot and Bevy are alternatives or separate implementations,
not a mandatory engine-to-engine chain. A project need not use all three.

### Tool roles and integration status

| Tool | Work it should make easier through NET | Status and ownership boundary |
| --- | --- | --- |
| **Blender** | Generate parameterized geometry, bake/export assets, and retain source parameters, export settings and artifact identities. | Authoring-adapter target. Existing USDA inspect export does not establish a Blender integration. Blender owns its files, objects, modifiers, rigs and authoring state. |
| **Godot** | Launch declared scenarios, capture playtests, inspect telemetry, and request supported pause/step or re-simulation operations. | Retained-result inspection is documented above; gameplay/runtime control is a target. Godot owns its SceneTree, input, game state, physics, animation, audio and UI. |
| **Bevy** | Run ECS-based simulations interactively or headlessly, perform parameter studies, and expose selected component/resource observations. | Simulation-adapter target; no Bevy execution is demonstrated by the current quickstart. Bevy owns its World, schedules, systems, resources and components. |

Each adapter must declare its actual capabilities and pinned versions. Launch,
observe, pause, step, restore and re-simulate are separate capabilities, not a
universal promise. The existing Godot inspector remains a detached, read-only
scientific view; a future game-runtime adapter is a separate explicit control
path and must not turn inspection records into writable game state.

### What changes in the development workflow

These are intended outcomes to qualify with working integrations:

| Development task | Intended workflow | What the investigation retains |
| --- | --- | --- |
| **Asset iteration** | Change a Blender parameter, export a candidate, load it in one runtime and rerun the affected scenario. | Source/build identity, parameters, export settings, artifact digest, unit/frame conversion and import configuration. |
| **Physics tuning** | Run a declared parameter sweep, compare responses, then playtest useful candidates in the chosen engine. | Initial conditions, input sequence, runtime/solver settings, trajectories, metrics and the selected change. |
| **Bug reproduction** | Capture a failure, replay recorded observations for inspection, then attempt a new execution against a candidate fix. | Original build, assets, seeds or RNG state where supported, timing, inputs, events and any missing reproduction state. |
| **Regression testing** | Run the same bounded scenarios after a code, model or asset change. | Baseline/candidate executions, numerical tolerances, invariant checks and measured performance conditions. |
| **Procedural content** | Generate candidate worlds, check declared geometric/playability constraints, and playtest the survivors. | Generator configuration, rejected cases, evaluation results and human feedback. |

A concrete first case is a **suspended-payload mechanic**. Author a simple trolley
and load in Blender, run the mechanic in Godot **or** Bevy, retain its control
inputs and motion, then compare two damping settings in NET. Measure swing angle,
settling behaviour and runtime cost; use playtesting to assess control feel.
This is a proposed end-to-end case, not an additional runnable quickstart.

Only add a second engine after the first path works. Reuse the declared scenario
where its semantics apply, but keep each engine, physics implementation and
execution distinct. Agreement or disagreement is something to investigate, not
an equivalence guaranteed by sharing an asset or configuration file.

### Contracts that make the workflow reliable

**Reuse the current session and records.** Bind scenario, model, asset, parameter,
implementation and runtime identities to existing operation/execution/result
records. Add versioned payloads through the existing protocol only when a concrete
integration needs them; do not create a parallel simulation runtime or evidence
store. A Blender object, Godot node and Bevy entity need not share a universal
object model. Adapters expose declared observations and stable project-level
identifiers without assuming engine-local IDs survive another execution.

**Keep assets separate from physics.** An exported visual mesh does not by itself
define collision geometry, mass, joints, friction or a material model. Retain those
choices separately, together with unit/frame conventions and import settings.
CSR calculations require a supported surface/chart and an explicit relationship
to displayed geometry; an arbitrary mesh export is not a numerical validation.

**Distinguish playback from re-simulation.** Reopening or playing back retained
observations must not execute a provider. Re-simulation is a new execution with
its own identity, linked to the original inputs and observations. A seed and
input log alone do not establish reproducibility: record the state, timing,
build and environment required by the profile, and report missing information.
Declare whether comparison expects exact equality, numerical tolerance or only
specified behavioural checks. Do not promise cross-engine determinism.

**Do not put NET on the frame-critical path.** Runtime adapters should buffer or
sample observations within declared budgets and report dropped data. Simulation
time, physics ticks and wall-clock performance measurements stay distinguishable.
Loss of an inspection client must not silently stop or mutate the running world;
any pause, parameter change or restart uses an explicit supported control request.

### Python, Julia, Rust and C++

The language stack serves these workflows; it is not a requirement that every
project execute every language.

| Layer | Role |
| --- | --- |
| **Python / `ciw`** | Existing investigation/session authority, operation dispatch, retained records, analysis and comparisons. |
| **Julia** | Registered numerical providers and reference experiments within their documented scope; further comparisons require their own qualification. |
| **Rust / Bevy** | Target ECS application/simulation runtime and native systems components where selected. |
| **C++ / native providers** | Specialist geometry, physics or numerical kernels where a supported library or measured bottleneck justifies them. |

SCR remains the shared execution foundation for its registered native profiles;
specialist repositories keep their mathematics. A reference must be independently
justified and scoped: using another language alone does not make it an independent
check. Human playtesting and artistic judgement are also retained inputs, not
quantities automatically replaced by an optimization score.

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

Use the existing oscillator/thermal, measurement-chain and curved-path foundations
to close a shared investigation workflow, not a set of disconnected demos.
Interactive simulation extends this foundation only after existing gates remain
intact; new runtime adapters must not weaken retained evidence, replay identity,
provider boundaries or headless operation.
These are acceptance requirements, not gates claimed passed by this README:

| Gate | Required demonstration |
| --- | --- |
| Compose | Bind a named model and all inputs; check quantities, units, frames, clocks, representations and dependencies before execution. |
| Execute and compare | Run actual registered providers and compare against independent references under declared numerical policies. |
| Investigate | Retain baseline/candidate changes, assumptions, responses, uncertainty status and checks, including invalid or unresolved cases. |
| Reopen and replay | Read saved records without executing providers; explicitly replay with new execution identities and preserved history/version bindings. |
| Challenge and recover | Reject altered bindings and incompatible inputs; retain bounded failures, recover without losing results and identify affected dependencies. |
| Inspect and hand off | Keep headless use working; test each inspect client against retained `ciw.experiment-view.v1` records. |
| Physical apparatus | For each supported device, bind configuration and authorization; test disconnects, duplicate requests, stale plans and uncertain outcomes. |
| Qualify claims | Retain actual evidence for each numerical, proof or physical claim. Report startup, transfer, computation and checking costs separately. |
| Interactive simulation slice | Exercise one small mechanic in one engine: optional parameterized Blender artifact -> declared run -> input/event/state capture -> NET inspection -> candidate comparison -> explicit re-simulation. Test missing assets, incompatible frames, incomplete traces and disconnection; retain every outcome without overwriting the original run. Add a second engine only after this path works. |

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

Build and audit each increment together: exercise the working path and its
failure cases before expanding it. Documentation changes do not implement an
adapter, create a record type or pass an integration gate.

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
| Game/simulation tool roles, target workflows and boundaries | [Interactive simulation development](#interactive-simulation-development-direction) |
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

PDT first-party application code is licensed under the GNU Affero General Public
License version 3 or, at your option, any later version (AGPL-3.0-or-later),
except where a component carries an explicit separate notice. Third-party
engines, libraries, runtimes, assets and standalone providers retain their
original licenses. See [LICENSE](LICENSE) and the
[platform licensing policy](docs/LICENSING.md).
