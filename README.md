# Notations Engineering Terminal

**Run an experiment. Change an input. Compare the results.**

Notations Engineering Terminal (**NET**) is a Python workbench for scientific
computing and simulation development from **Notation Systems**. It runs supported calculations and keeps
their inputs, settings and results together, so you can understand what changed
and return to an earlier experiment without starting over.

Use it to explore a model, compare design choices, inspect measurements or debug
a simulation. Its game-development integrations work **around Blender, Godot and
Bevy**, not in place of their editors or runtimes.

**Start here:** the built-in demo below needs Python, but no hardware, game engine
or external scientific provider. The newer authoring and fluid-inspection
workflows have tested implementations in review; [see their status](#interactive-simulation-development-direction)
before choosing a branch.

[Notation Systems](https://notations.io) · [Quickstart](#quickstart) · [What you can do](#current-scope) ·
[Game and simulation workflows](#interactive-simulation-development-direction) ·
[How the tools fit together](#architecture) · [Documentation](#documentation-map)

## Quickstart

From a checkout of this repository, use **Python 3.11 or newer**. The
[installation guide](docs/quickstart.md#install) covers virtual environments on
Windows, Linux and macOS. Run the commands below from the repository root.

**1. Install NET and generate an example recording.**

```sh
python -m pip install -e .
python -m ciw demo --output recordings/demo.json
```

The demo simulates a damped oscillator: a system that moves back and forth while
its motion gradually decreases. Its displacement is the channel named `q`.
These are synthetic data, not measurements from a physical device.

**2. Calculate statistics and a frequency spectrum.**

```sh
python -m ciw analyze stats --recording recordings/demo.json --channel q --start 2 --end 8 --output-dir results/stats
python -m ciw analyze spectrum --recording recordings/demo.json --channel q --start 0 --end 12 --output-dir results/spectrum
```

The first command summarizes displacement between 2 and 8 seconds. The second
calculates a periodogram power spectral density over the full recording: a view
of how the signal's power is distributed across frequencies, not a spectrogram.
Both commands return structured JSON and save their results.

**3. Inspect the saved experiment.**

```sh
python -m ciw inspect results/spectrum/workspace.json
```

Inspection reads the saved result; it does **not** rerun the calculation.
You will have:

```text
recordings/demo.json              example source data
results/stats/workspace.json      saved statistics experiment
results/spectrum/workspace.json   saved spectrum experiment
```

Each results directory also keeps its source recording and individual result
records. Use a different output directory for each experiment to preserve its
workspace snapshot.

**Next:** follow the [oscillator walkthrough](docs/OSCILLATOR_OPERATOR.md), try the
[worked RMS lesson](docs/LEARNING.md), or connect the optional Godot viewer using
the [shared-session guide](docs/quickstart.md#shared-terminal-and-viewport).
The terminal works without a viewer or an AI assistant.

<a id="current-scope"></a>
<a id="what-works-today"></a>
## What you can do

| Your task | Where to start |
| --- | --- |
| **Explore a model.** Run the oscillator, inspect equations, calculate statistics or a spectrum, and try supported what-if previews. | [Model exploration](docs/MODEL_EXPLORATION.md) |
| **Work with measurements.** Run supported calibration, telemetry and state-estimation workflows with their required providers. | [Workbench assembly](docs/WORKBENCH_ASSEMBLY.md) and [provider setup](docs/PROVIDER_AVAILABILITY.md) |
| **Compare engineering choices.** Run supported design, covariance and geometric-path calculations, keeping assumptions and checks with the outputs. | [Operation catalogue](docs/INSTRUMENTS.md) |
| **Return to earlier work.** Inspect saved results, reopen a session, or explicitly run a calculation again. | [Reopening a session](docs/quickstart.md#reopen-an-investigation) |
| **Inspect results visually.** Use optional Godot and geographic views, or export a supported inspection canvas to USDA. | [Integration coverage](docs/INTEGRATION_COVERAGE.md) |

Support depends on the selected operation and its inputs. The catalogue lists
commands; the coverage guide records what has been exercised and what remains
unsupported. Additional providers can require separately installed software and
exact source versions.

<details>
<summary>More specialized commands</summary>

The [catalogue](docs/INSTRUMENTS.md) also covers:

- Oscillator lessons: `ciw math work` for RMS, energy and velocity, and
  `ciw math learn oscillator-energy`.
- Language-binding inspection with `ciw bindings`; the Julia create path needs
  its documented `--julia` and `--runtime` bindings.
- Declared coordinate maps with `ciw chart identity|scale`, and inspection export
  with `ciw export usda --compare`; `--usd-bin` requires the documented USD tool.
- A single NVML energy reading with `ciw energy measure`, and retained-log replay.
- Read-only machine-configuration, supported geometry, stability and registered
  computation checks, each with its own input and provider requirements.

These are optional workflows, not prerequisites for the demo or general hardware
control. Follow each guide for exact syntax and limits.

</details>

<a id="what-the-testbed-does"></a>
<a id="one-investigation-several-control-surfaces"></a>
## How an investigation works

An **investigation** is a saved experiment: the question, inputs, settings,
calculations, results and checks that belong together.

```text
Choose a model or recording → Run a calculation → Inspect the result
                                                       |
                          Change an input ← Compare with an earlier run
```

For example, you can compare how two damping settings affect an oscillator while
keeping both results and the assumptions behind them. NET helps answer **“What
changed, and what did it do?”** rather than leaving you with only the latest plot.

**Inspect** means read an existing result. **Replay** means explicitly perform a
new execution and retain it separately. A failed calculation or refused input
also remains part of the record; it is not replaced with a successful-looking
empty result.

<a id="interactive-simulation-development-direction"></a>
## Game and simulation workflows

NET's development loop extends from scientific calculations to authored assets
and independent simulation runtimes:

```text
Author an asset → Run a scenario → Record observations → Compare → Revise
```

**Tested implementations in review — not yet merged into `main`:**

| Workflow | What the implemented example does | Guide and review |
| --- | --- | --- |
| **Blender → Godot or Bevy → NET** | Exports a simple projectile scene, runs each engine independently, compares trajectories, reproduces selected runs and detects an injected gravity error. | [Projectile guide](https://github.com/giasonpooni/Notations-Engineering-Terminal/blob/76075f9fa2235c109f800fd9d38a10cb6131c877/docs/INTERACTIVE_PROJECTILE.md) · [PR #45](https://github.com/giasonpooni/Notations-Engineering-Terminal/pull/45) |
| **Simulated observations → fluid-state estimation** | Passes a two-reservoir mass snapshot to the existing fluid estimator, preserving covariance, missing readings and held or refused outcomes. Simulator reference state stays separate. | [Simulated-fluid guide](https://github.com/giasonpooni/Notations-Engineering-Terminal/blob/297bf65cac98b28210c07972275c6adf715c497e/docs/SIMULATED_FSRT.md) · [PR #46](https://github.com/giasonpooni/Notations-Engineering-Terminal/pull/46) |
| **Saved fluid results → browser inspection** | Opens synthetic-source results in GSC's `/numerics` inspector without rerunning the engine or estimator; preserves the earlier RCI-backed view. The combined source also reruns the projectile regression campaign. | [Inspection guide](https://github.com/giasonpooni/Notations-Engineering-Terminal/blob/fd35fc091ea1d58be38e44cc5cf5c85249b541fa/docs/SYNTHETIC_FSRT_VIEW.md) · [NET #48](https://github.com/giasonpooni/Notations-Engineering-Terminal/pull/48) / [GSC #10](https://github.com/giasonpooni/Geospatial-Systems-Compiler/pull/10) |

The guide links point to tested source revisions and explain the required tools.
Use those instructions for the review implementations; installing `main` does
not install unmerged features. The PRs record test evidence and current status.

The projectile is a **headless, no-contact example**, not a test of an engine's
rigid-body solver or renderer. The fluid example is **one snapshot**, not a
general fluid simulation. Broader asset authoring, live player-input capture,
engine-owned pause/step control, checkpoint continuation and parameter-sweep
interfaces remain further work.

These tools support experimentation and debugging. They do not replace
playtesting or artistic judgement.

<a id="one-environment-separate-responsibilities"></a>
<a id="existing-runtime-same-substrate"></a>
## Architecture

**NET manages experiments; the connected tools keep doing their own jobs.**

- **Blender** authors assets. **Godot and Bevy** run their own applications and
  engine-owned worlds. A project can use either engine; no engine-to-engine
  chain is required.
- **Scientific providers** own their models and calculations: fluid estimation
  in FSRT, supported paths and sensitivity in CSR, and BIM estimation in CSE.
- **GSC and other viewers** present supported results. They do not change the
  scientific calculation by displaying it.
- **NET** selects supported operations and keeps the investigation history.
  Separately supported evidence review and release remain with ESM.

A **provider** is an implementation NET can call; an **adapter** connects its
inputs and outputs to NET. Each simulation declares who owns its state and clock.
Attaching a viewer does not change that ownership, and a visual mesh does not
by itself define a physical model or collision settings.

The Python package and command remain **`ciw`**. NET extends the existing
Computational Instrumentation Workbench (CIW), not a second runtime. Julia,
Rust, C++ and SCR serve selected numerical or execution tasks; no experiment
needs to use every language. Earlier project names include Notations Design
Terminal and Parametric Design Testbed.

<a id="composable-instruments-independent-scientific-authority"></a>
See the [systems catalogue](docs/SYSTEMS_CATALOG.md), [stack map](docs/STACK.md)
and [technical architecture](docs/ARCHITECTURE.md) for the full component map,
provider responsibilities and supported connections.

## The design language

**State. Variation. Invariance.** Three questions guide an experiment:

| Question | Oscillator example |
| --- | --- |
| What are we studying? | Position and velocity under a chosen motion model. |
| What are we changing? | The damping parameter. |
| What must remain true? | The requirements and checks declared for that model. |

<a id="computational-identity"></a>
A parameter change and a model change are different decisions. Keep the original
results rather than silently giving them a new meaning. The detailed sequence—
state, structure, transformation, computation and verification—is explained in
[contract foundations](docs/CONTRACT_FOUNDATIONS.md) and
[allowed transformations](docs/STATE_TRANSFORMATIONS.md).

<a id="evidence-boundaries"></a>
## Reading results correctly

NET keeps measurements, simulated observations, predictions, estimates and checks
distinct. A **residual** measures disagreement, such as prediction versus
observation. **Covariance** describes declared uncertainty and how quantities
vary together. Unsupported or missing uncertainty is not replaced with zero.

Inputs, operations, executions, results and verification records retain separate
identities. A successful calculation is not automatically a verified model,
formal proof or physical validation. Missing, inconclusive, held and refused
outcomes stay visible; a result does not grant equipment-control permission.
See [evidence classes](docs/WORKBENCH_OVERVIEW.md#evidence-classes) and
[record formats](docs/PROTOCOL.md) for the details.

<a id="base-pilot-the-programmable-computational-and-cyber-physical-laboratory"></a>
<a id="pilot-closure-not-unlimited-expansion"></a>
<a id="extension-rule"></a>
<a id="next-gates"></a>
## What comes next

Finish and verify assigned pilot work, preserve the existing scientific workflows,
and test new connections on their combined source revisions. The examples above
do not establish general hardware acquisition, hard real-time control or
platform-wide industrial readiness. Wider optional-provider checks still include
failures; a focused passing campaign does not waive them.

Further work includes broader interactive controls, input capture, asset workflows
and parameter studies. The proposed suspended-payload mechanic remains a future
example. Physical-validation claims require a separate held-out reference
measurement and its supporting records.

## Documentation map

| You need | Read |
| --- | --- |
| Installation, first run and shared viewer | [Quickstart](docs/quickstart.md) |
| Models, equation cards and worked examples | [Model exploration](docs/MODEL_EXPLORATION.md) · [Oscillator guide](docs/OSCILLATOR_OPERATOR.md) · [Learning](docs/LEARNING.md) |
| Commands, supported integrations and setup | [Instruments](docs/INSTRUMENTS.md) · [Coverage](docs/INTEGRATION_COVERAGE.md) · [Providers](docs/PROVIDER_AVAILABILITY.md) |
| Architecture, records and mathematical assumptions | [Architecture](docs/ARCHITECTURE.md) · [Protocol](docs/PROTOCOL.md) · [Research context](docs/RESEARCH_CONTEXT.md) · [Diagrams](docs/DIAGRAMS.md) |
| A shared service or deployment | [Workbench assembly](docs/WORKBENCH_ASSEMBLY.md) · [Deployment](deploy/README.md) |
| Contribution and test requirements | [Development guide](docs/DEVELOPMENT.md) |

The [full documentation index](docs/README.md) covers the remaining specialist
workflows. Consult each operation's guide and runtime requirements before using it.

## Development and validation

Install the development dependencies, then run the local checks:

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m compileall -q src
git diff --check
```

Provider-specific tests require their documented software, clean checkouts and
versions. Report unavailable or skipped checks explicitly. New workloads should
extend the current session and record formats, preserve existing commands and
verified invariants, and test failure cases alongside the working path.

Read [DEVELOPMENT.md](docs/DEVELOPMENT.md) before changing a contract or adding a
provider. Documentation edits alone do not qualify a numerical implementation.

## License

Copyright © 2026 Notation Systems.

PDT first-party application code is licensed under the GNU Affero General Public
License version 3 or, at your option, any later version (AGPL-3.0-or-later),
except where a component carries an explicit separate notice. Third-party
engines, libraries, runtimes, assets and standalone providers retain their
original licenses. See [LICENSE](LICENSE) and the
[platform licensing policy](docs/LICENSING.md).
