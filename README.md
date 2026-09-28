# Notations Engineering Terminal

**Develop scientific and interactive simulations as reproducible investigations.**

**Notations Engineering Terminal** is a terminal-first scientific computing and
cyber-physical design workbench from **Notation Systems**. It runs supported
models and analysis operations, saves their inputs and results, and lets you
inspect or reopen a study without running it again. Supported sensing and
apparatus integrations extend the same investigation into physical experiments.
For supported workflows, you can vary model parameters, compare the responses,
and inspect uncertainty, residuals and other checks. The same investigation model
is being extended toward interactive simulation development: author a declared
scenario, run it in a specialist runtime, capture selected state and events,
compare candidate changes, and keep runtime and artifact identities attached to
the result.

An **investigation** is the question together with the models, observations,
settings, calculations and checks used to answer it. Notations keeps these connected
rather than saving only a final number or plot. Engineering design is the main
use: change a permitted input, calculate the response, check the result and
compare candidates.

Notations Engineering Terminal extends the existing **Computational Instrumentation Workbench (CIW)**.
The Python package and terminal command remain `ciw`; this is not a second
runtime. The software works without a graphical viewer or an AI assistant.
Earlier documentation used **Notations Design Terminal** and **Parametric Design
Testbed**. These are historical project titles, not new operation, execution,
result or verification identities.

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

The existing workflows remain in place:

| Workflow | What it does |
| --- | --- |
| Measurement and estimation | Align observations, apply supported calibration and uncertainty calculations, estimate quantities, evaluate constraints and retain diagnostics. |
| Design studies | Declare a model and allowed changes, run candidate configurations, compare responses and checks, and retain the basis for revising the design. |
| Numerical geometry | Evaluate supported paths, coordinate descriptions and sensitivities without treating a displayed shape as a measurement. |
| Inspection and replay | Read retained records, inspect dependencies and repeat an operation explicitly while preserving its original history. |
| Interactive simulation development | Target workflow for declared scenarios executed in independent Godot or Bevy runtimes, with selected telemetry returned for inspection, comparison and regression work. This is an integration direction, not a claim of general engine control today. |
| Computational authoring | Target workflow for parameterized Blender geometry/scene generation whose exported artifacts retain source parameters and identity before use by a runtime. Blender remains the authoring authority. |

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
| **Notations Engineering Terminal / CIW** | Manage the investigation, selected operations, saved history, inspection and explicit replay. The existing Python session remains authoritative for these records. |
| **Scientific providers** | Supply domain models and calculations through adapters with explicit source/runtime versions. Each repository retains its own scientific contract, tests and licence. |
| **Native execution / SCR** | Supply selected native execution adapters where a profile registers them. The Python session remains authoritative. |
| **Checkers / ICRH, PLSR and selected SP1 paths** | Check the numerical, contract, stability or registered-computation claims they actually support. A computation does not certify itself. |
| **Evidence handoff / ESM** | Handle separately supported retention, review and release of evidence or candidate state. An inspect copy and a `render` descriptor are not modeling inputs and do not admit corpus state. |
| [Geospatial Systems Compiler (GSC)](https://github.com/giasonpooni/Geospatial-Systems-Compiler) | Separately maintained browser presentation and visualization project, formerly Payload Terminal V0. Its ESM read-only projection and workbench handoff are integration targets, not a second workbench or execution authority. |
| **Inspection clients** | Display numerical, temporal, spectral, geographic or local 2D/3D views of retained inspect records. Closing a viewer does not stop the backend or change retained records. |
| **Godot** | Interactive application and gameplay runtime target: scenes, input, animation, UI, audio and engine-owned simulation state. NET may request declared runs and consume selected observations; it does not own the SceneTree or silently rewrite game state. |
| **Bevy** | Rust/ECS simulation-runtime target for systems-heavy, procedural and headless workloads. A Bevy adapter may project selected ECS state into NET records; NET does not impose a universal component model on the Bevy World. |
| **Blender** | Computational-authoring target for geometry, assets, animation, procedural generation, baking and scene export. Generated artifacts may be bound to investigations, but NET does not replace Blender's editing or artistic workflows. |
| [Curved Surface Runtime (CSR)](https://github.com/giasonpooni/Curved-Surface-Runtime) | Specialist authority for its supported curved-surface path and sensitivity calculations; useful to interactive simulations through explicit provider operations rather than copied mathematics. |
| [State Estimator for BIM](https://github.com/giasonpooni/State-Estimator-for-BIM) | BIM-specific evidence-to-decision instrument. Its state-estimation patterns can inform simulation work, but BIM semantics remain with that repository; any general simulation estimator requires its own declared provider contract. |

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

## Interactive simulation development direction

Interactive simulation is a **workload family of the existing workbench**, not a
second NET runtime and not a replacement for an engine or DCC application. The
target development loop is:

```text
author -> run -> observe -> compare -> modify -> verify
  ^                                           |
  +-------------------------------------------+
```

NET should retain the investigation that connects those steps. Godot, Bevy and
Blender retain authority over their own native state and project formats.

```text
                         NET / CIW
             investigation + experiment history
                           |
          scenario / run / trace / comparison
                           |
       +-------------------+-------------------+
       |                   |                   |
    Blender              Godot               Bevy
 authoring/DCC      interactive runtime   Rust/ECS runtime
       |                   |                   |
 geometry/assets      gameplay/state       systems/state
       +-------------------+-------------------+
                           |
                 specialist providers
              GSC / CSR / estimators / SCR
```

The intended integrations solve different development problems:

| System | NET-facing role | Native authority retained by |
| --- | --- | --- |
| **Blender** | Parameterized geometry/scene generation, artifact identity and export provenance. | Blender files, objects, modifiers, rigs, animation and authoring state. |
| **Godot** | Interactive scenarios, playtest capture, selected telemetry and explicit replay requests. | SceneTree, gameplay state, input, physics, animation, UI and presentation. |
| **Bevy** | ECS-heavy and headless simulation, benchmark scenarios, selected component/resource projections and traces. | Bevy World, schedules, systems, resources and components. |
| **GSC** | Spatial, temporal and relational inspection of explicitly published simulation projections. | Its representation/view configuration; it does not become simulation authority. |
| **CSR** | Supported curved-surface paths, sensitivities and numerical diagnostics. | Its mathematical contracts, solver scope and tests. |
| **State-estimation providers** | Estimate latent state from declared observations where a workload explicitly registers such a model. | The provider's domain semantics, assumptions and uncertainty contract. |

A shared interface should describe **experiments and observations**, not pretend
that a Blender object, Godot node and Bevy entity are the same object. Candidate
record families include `simulation-scenario`, `simulation-run`, `simulation-input`,
`simulation-observation`, `simulation-event`, `simulation-trace`,
`simulation-comparison`, `geometry-artifact` and `scene-artifact`. These names
remain design targets until they are registered in the protocol and exercised by
tests; documentation alone does not create a supported record type.

The useful boundary is:

```text
engine/DCC-native state
        |
        | explicit adapter / projection
        v
NET observation or artifact record
        |
        +--> inspect
        +--> compare
        +--> parameter study
        +--> regression check
        +--> explicit replay request
```

A replay is always a new execution. A retained trace remains an observation of
the original execution. Reopening either must not silently rerun an engine.

### Intended game and simulation workflow

For an interactive physical system, NET should make it possible to bind a
scenario, runtime/build identity, parameter set, asset identities, initial state,
seed where applicable and declared input stream. The runtime then executes the
system and emits only the observations it has agreed to expose.

This enables workflows such as:

- reproduce a gameplay or simulation failure from a retained scenario and input trace;
- run headless Bevy parameter sweeps before selecting candidates for human playtesting;
- capture Godot playtest telemetry without making NET the game-state authority;
- generate parameterized Blender artifacts and bind their exact source parameters to downstream runs;
- compare trajectories, events, performance and declared invariants across candidate implementations;
- compare a runtime trajectory with an independent Julia/Python/native reference where a provider explicitly supports that comparison;
- publish selected spatial or temporal projections to GSC without promoting a visualization into canonical simulation state.

Quantitative experiments narrow and explain the design space; they do not decide
whether a mechanic is enjoyable. Human playtesting and artistic judgement remain
first-class inputs to game development.

### Integration invariant

```text
integration != ownership
model != runtime representation
artifact != simulation state
recorded replay input != original execution
visual agreement != numerical equivalence
numerical agreement != gameplay quality
```

Godot, Bevy and Blender therefore remain independently usable. A project may use
Blender + Godot, Blender + Bevy, Bevy headless, Godot alone, or another registered
composition. No workload is required to traverse every tool merely because the
integration exists.

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
| Interactive simulation slice | Exercise one small scenario end to end: parameterized Blender artifact where useful -> Godot or Bevy execution -> selected trace/event capture -> NET inspection -> explicit comparison/replay, with runtime and artifact identities retained. A later cross-runtime case may compare Godot and Bevy without assuming numerical equivalence. |

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

PDT first-party application code is licensed under the GNU Affero General Public
License version 3 or, at your option, any later version (AGPL-3.0-or-later),
except where a component carries an explicit separate notice. Third-party
engines, libraries, runtimes, assets and standalone providers retain their
original licenses. See [LICENSE](LICENSE) and the
[platform licensing policy](docs/LICENSING.md).