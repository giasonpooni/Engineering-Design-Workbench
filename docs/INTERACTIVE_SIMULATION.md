# Interactive simulation and computational authoring

**Godot, Bevy and Blender are first-class optional integration targets of NET,
not required dependencies or internal subsystems.** NET is the development
workbench around these tools: construct a scenario, request a supported run,
record what happened, change a parameter, compare and check the result.
It does not replace their editors, object models or simulation implementations.

This page records the extension direction and acceptance requirements. It does
not register new operations, schemas, commands or runtimes. The current source
baseline reviewed here is `177b8f000df791d33ec612d80c1b81c4f681e306`.
Source inspection is not a fresh engine build or qualification result; newer
implementation branches need their own evidence before their status is promoted.

## Workload and ownership

The workload families are scientific computation, engineering simulation, and
interactive simulation with computational authoring. They share investigations,
not a universal engine. Existing measurement, estimation, geometry, fluid,
thermal, design and verification workflows remain in place.

```text
                 NET / existing Python ciw session
          investigation, selected operations, retained history
                              |
           +------------------+------------------+
           |                  |                  |
     Blender adapter     Godot adapter      Bevy adapter
     authoring jobs      interactive app    ECS simulation
           |                  ^                  ^
           +-- retained assets + physical configuration --+
                              |
               observations, events and results
                              v
                    NET compare / inspect / check

Optional operation edges, not a compulsory execution chain:
  GSC representation | CSE/BIM estimation | CSR geometry | FSRT fluids
  registered Julia/Python models | SCR/native execution | selected checkers
```

| Target | Responsibility at its boundary | NET does not take ownership of |
| --- | --- | --- |
| Blender | Declared geometry generation, scene authoring, procedural operations, baking and export; retain generated artifacts and derivation. | Editable project data, dependency graph, modelling tools, authoring UI or a Blender simulation's internal state. |
| Godot | Interactive application/runtime, input and presentation; expose selected observations and supported experimental commands. | SceneTree, gameplay rules, animation, audio, UI or the evolving world of an engine-owned game. |
| Bevy | Rust/ECS runtime and declared systems; project selected components/resources into observations. | World, schedules, systems, component storage or arbitrary ECS serialization. |
| NET | Questions, scenarios, operation selection, execution history, comparison, inspection and separately scoped checks. | A second game loop, authoring editor or competing solver. |

`integration != ownership` applies per operation. In an engine-owned game,
Godot or Bevy advances its world and NET retains observations. In a
provider-owned scientific simulation, the existing provider and CIW commit
boundary remain authoritative and an engine is a client. Each simulation
instance declares one state owner and one clock owner. Adding a client never
silently transfers either. Independent Godot and Bevy runs have independent
worlds; they do not co-own one state.

NET is not a synchronous requirement on every gameplay tick. Live capture must
have bounded buffering, an explicit overflow policy and retained missingness.
Externally stepped experiments are a separate capability. A standalone game
must not require an installed NET, Blender, Julia or a proof service merely to
play. Authoring tools may be required for an explicitly selected build job.

## Integration matrix: audited source versus intended capability

Here **source present** means the referenced implementation exists; it does not
mean it was rebuilt or executed during this documentation update. **Pending**
means this audit establishes no qualified NET path for that capability. It is
not a claim that the upstream application lacks the capability. A standalone
schema, tool installation or architecture entry does not mean **available**.

| Target/profile | Adapter boundary | Run/control | Observe | Playback / reproduction | Headless | Generate |
| --- | --- | --- | --- | --- | --- | --- |
| Godot existing inspection client | Source present in `godot/` | Viewer/session interaction, not a general game launch/step contract | Retained views and supported shared-session displays | Retained inspection; no general game reproduction claim | Client import/protocol checks are documented; not simulation qualification | No authoring claim |
| Godot simulation adapter | Pending | Pending | Runtime tick telemetry pending | Input reproduction and checkpoint qualification pending | Simulation profile pending | Not required |
| Bevy existing projector | Source present in `tools/bevy-render-view` | Projector launch, not simulation control | Retained `*_render.json` projection | Retained display, not re-simulation | `--summary` path documented; not a physics run | No authoring claim |
| Bevy simulation adapter | Pending | Pending | Selected ECS observation projection pending | Input reproduction and checkpoint qualification pending | Simulation profile pending | Optional future workload |
| Blender authoring adapter | Pending | Declared job launch pending | Artifact/derivation capture pending | Regeneration is a fresh execution; not gameplay replay | Authoring-job qualification pending | Geometry/scene/bake/export pending |

Evidence owners: [Godot client](../godot/README.md),
[Bevy projector](../tools/bevy-render-view/README.md),
[visualization providers](VISUALIZATION_PROVIDERS.md),
[development checks](DEVELOPMENT.md) and
[integration coverage](INTEGRATION_COVERAGE.md).
The existing Godot 4.5.2 and Bevy source bindings are unchanged by this page.
The existing USDA inspect export also remains unchanged; the proposed glTF
asset handoff below is additive, not a replacement for retained inspect formats.

Keep discoverability, installed/runtime-bound, source-present and qualified
capability separate in any future provider display. Qualify each combination of
operation, adapter revision, runtime build, execution mode and platform. Do not
list all capabilities as available merely because a tool was found on PATH.
The console command remains `ciw`; no `net` command or new provider-inspection
CLI is introduced here.

## Contract requirements above the adapters

### Reuse the existing investigation and execution records

[PROTOCOL.md](PROTOCOL.md) and [ARCHITECTURE.md](ARCHITECTURE.md) continue to own
record semantics. Reuse `run.v1`, `ciw.execution.v1`,
`ciw.operation-result.v1`, existing manifests and retained view boundaries
where their actual contracts fit. Do not silently reinterpret old kinds.
Scenario, parameter set, input, observation, event, trace, metric, comparison,
geometry artifact and scene artifact are the required concepts; illustrative
names such as `simulation-trace.v1` are not registered wire formats.
Version a missing payload only after its operation and compatibility tests exist.

Retain model, scenario, assets, parameters, implementation, runtime, operation,
execution, result and verification identities separately. A simulation-instance
reference identifies a running lifetime; it does not replace the investigation
or execution. A new run, explicit reproduction, regenerated artifact or
counterfactual branch preserves its parent history and receives fresh applicable
execution/result identities. Viewing old results creates no fresh verification.

For engine-owned worlds, the adapter projects `P_runtime(W_t) -> O_t`.
The projection declares quantity order, units, frame, time basis, support and
missingness. It is not a reversible serialization of the world. Bind stable
scenario entity identities to runtime-local handles; raw ECS IDs or node paths
alone are not a cross-run correspondence. Synthetic truth, simulated sensor
observations, estimated belief and corrected candidates stay distinguishable.

### Separate artifact authoring from physics configuration

Use a retained bundle of authored/generated assets and an explicitly bound
physical configuration, rather than treating a visible mesh as a complete
physical model. Bind source project or generator, parameters, tool/exporter
revision, export settings and actual output bytes, including external buffers
and textures where present. Retain importer settings and derived runtime assets
as a separate transformation. A content digest checks bytes, not provenance
truth or physical correctness.

The proposed first asset route is Blender -> glTF/GLB -> each runtime.
Godot documents glTF import and Blender-to-glTF conversion; Bevy exposes glTF
loading behind an optional feature. These upstream facilities do not establish
a tested NET asset pipeline. For the standalone runtime, consume exported
artifacts rather than make Blender's presence an implicit launch requirement.
See [Godot's format/import guide](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html)
and [Bevy's glTF module](https://docs.rs/bevy/latest/bevy/gltf/index.html).

The baseline must separately declare mass, inertia when applicable, collision
shape, contact/material model, gravity, initial conditions, constraints, solver
and timestep. Do not infer friction from a rendered material or accept an
exported animation as a dynamics calculation. Support for any physics-specific
asset extension needs an explicit exporter/importer profile and tests; neither
ignore it silently nor assume identical semantics in both engines.

Declare source/export/runtime transforms, length scale, axes, handedness and
rotation conventions. The [glTF specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)
defines its own coordinate/units convention; verify the full conversion with
asymmetric landmarks and a known length. Exact export-byte regeneration and
geometric equivalence are different checks. Missing inputs, unsupported
extensions and invalid transforms must remain visible failures.

A validated authored geometry input is distinct from a retained render copy.
The existing rule that inspect/render geometry is not a scientific input is not
relaxed. A computational geometry operation needs its own accepted input shape,
precision, topology and provenance contract.

### Lifecycle, timing and observation

Capability descriptions should distinguish describe/bind, author/generate,
launch, observe, submit input, pause, externally advance, stop and supported
checkpoint operations. A capability absent from a profile must not be emulated
by silently changing its meaning. Inspection must not import or launch engines.
Trusted deployment configuration chooses approved tools and resource limits;
saved data cannot select executable paths, scripts or extend an allowlist.

Bind requested and applied input tick, sequence, initial state, RNG state or
seed policy, physics backend/integrator, precision, solver settings, build and
relevant platform information. Record tick state after the declared update
phase, not an interpolated render transform. Distinguish simulation time,
wall time, capture/arrival time and display time. Declare whether the initial
sample is tick zero and whether the observation is pre- or post-step.

Headless is an execution mode, not a fourth engine. Windowed/headless and
realtime/external stepping/batch are independent properties. Bevy's
[MinimalPlugins](https://docs.rs/bevy/latest/bevy/struct.MinimalPlugins.html)
provides a schedule runner without a window event loop; it does not by itself
supply exact-tick control or all glTF/asset plugins. Its
[FixedUpdate](https://docs.rs/bevy/latest/bevy/app/struct.FixedUpdate.html)
schedule is distinct from per-frame update. The actual pinned adapter must
qualify its chosen schedule and asset-loading path.

Preserve bounded cancellation, disconnect behavior, retained partial traces,
state revision checks and explicit reset history. Duplicate input requests must
have a declared idempotency policy. Do not repeatedly launch a native worker
per tick where a qualified persistent provider already owns the instance.
Python orchestration, analysis and proof generation stay outside deadline-critical
loops; no real-time guarantee follows from the choice of language.

### Playback, reproduction and comparison

Playback reads retained observations without executing a provider. Reproduction
runs the scenario and retained inputs as a new execution. Checkpoint restoration
requires a complete profile-specific continuation state, not just positions and
velocities. Counterfactual continuation additionally records the intervention.
A seed and fixed timestep alone do not establish reproducibility; qualify the
actual runtime/configuration and declared numerical policy.

Compare stable entity correspondences, compatible quantities, frames and clocks.
Align simulation times explicitly, retaining any interpolation rule. Do not
subtract whole heterogeneous state vectors or compare mismatched timesteps by
array index. Report position, velocity, orientation and event differences with
their own metrics and units, or use explicitly scaled dimensionless metrics.
Unsupported correspondence yields an incomparable result, not a passing check.

Two engines running a named model are distinct implementations/executions.
Numerical agreement, behavioral change, invariant checks, performance budgets
and physical validation are separate outcomes. Bind the comparison policy,
tolerances and any independent reference. A missing reference is not zero error.
Preserve full covariance/correlation when supplied; never invent independent
uncertainty from a trajectory difference. Report startup, simulation, capture,
transport, rendering and analysis cost separately under declared hardware and
measurement conditions. A headless timing is not a rendering benchmark.

## Optional specialist providers and execution foundation

These are optional operations composed by NET, not a mandatory layer between
every game tick and its engine. Their repositories and scientific contracts
remain authoritative; no merge, rename or generic solver port is implied.

| Specialist | Potential interactive-simulation use | Boundary to preserve |
| --- | --- | --- |
| [GSC](https://github.com/giasonpooni/Geospatial-Systems-Compiler) | Spatial/temporal/relational inspection, world layers and comparison views. | Representation compiler, not numerical truth, game-state owner or state-admission authority; qualify the selected retained-result handoff. |
| [CSE / State Estimator for BIM](https://github.com/giasonpooni/State-Estimator-for-BIM) | Supported built-asset belief/quantity investigations; an example of evidence-to-estimate composition. | Do not turn BIM semantics into a universal NPC, IMU/GNSS or robotics estimator. A different state-estimation provider needs its own model and qualification. |
| [CSR / Curved Surface Runtime](https://github.com/giasonpooni/Curved-Surface-Runtime) | Supported curved paths, transfer maps and sensitivity investigations. | Not arbitrary-world locomotion, a collision engine or a universal navigation solver; each new surface/application has separate assumptions and gates. |
| [FSRT](https://github.com/giasonpooni/Fluid-State-Reconstruction-Testbed) | Supported fluid-state, balance and uncertainty investigations in simulated plant scenarios. | Existing RCI/FSRT/JSPT profiles remain bounded; no general CFD, universal sensor fusion or physical-acceptance claim. |

The [systems catalog](SYSTEMS_CATALOG.md), [integration coverage](INTEGRATION_COVERAGE.md)
and provider-specific operating guides own existing qualification. Retain ESM
admission/release as a separate optional boundary. A game result, authored asset
or GSC inspect copy does not authorize equipment or admit canonical state.

Keep the [existing execution allocation](EXECUTION_RESPONSIBILITIES.md): Python
`ciw` coordinates and retains records; SCR supplies registered execution paths;
Julia/Python may provide selected numerical references; Rust and C++ provide
runtime systems or qualified kernels where useful. Bevy's Rust World is not
SCR and does not replace it. An operation need not traverse every language.
Keep all existing pins, licenses and private-source boundaries unchanged.

## First all-three acceptance case

Finish and verify currently assigned pilot/persistent-instance work first.
Then use all three external targets minimally in one investigation, rather than
require three complete new platforms or another game implemented twice.

**Case: an authored projectile scene, compared before any collision.** Blender
generates a simple sphere and a reference scene with asymmetric markers and
exports retained GLB assets. NET binds an explicit physical configuration.
Godot and Bevy each import the artifacts and execute a declared constant-gravity,
no-drag, no-contact trajectory. Each run owns its own state and reports position,
velocity, applied input/tick data and relevant metrics to the same investigation.
Their physics backends or handwritten integrators must be identified explicitly.

One proposed configuration is `p0 = (0, 5, 0) m`, `v0 = (2, 0, 0) m/s`,
`a = (0, -9.81, 0) m/s^2`, `m = 1 kg`, on `0 <= t <= 0.5 s`.
The endpoint remains above the reference plane. Declare the timestep rather than
copy a runtime default. The analytic reference is
`p(t) = p0 + v0*t + a*t^2/2`, `v(t) = v0 + a*t`.
It permits an independent numerical check from the start; a Julia reference
implementation can be added later without changing scenario identity.
The chosen implementation's discretization error is measured, not concealed.

| Gate | Required retained evidence |
| --- | --- |
| Author and import | Real Blender output, tool/source/export bindings and both runtime import reports; known length, asymmetric frame markers and physics configuration checked. |
| Execute | Real Godot and Bevy runs over the declared interval, stable entity mapping and separate execution/runtime identities. No test double counts as engine qualification. |
| Observe | Full-resolution tick observations with units, frames, clock/phase, ordering and explicit completeness. A rendered animation alone fails this gate. |
| Reopen and reproduce | Provider-free inspection with tools unavailable; explicit fresh same-runtime reproduction under a declared tolerance. Claim checkpoint continuation only when separately exercised. |
| Compare | Per-runtime analytic errors, cross-runtime differences and comparison policy retained. Include a timestep refinement and distinguish agreement from physical validation. |
| Challenge and recover | Altered asset/parameter binding, unsupported capability, wrong units/frame, dropped trace data, duplicate/stale input and interrupted execution produce the documented failure or partial outcome. |
| Demonstrate developer value | Capture one deliberately introduced regression, identify the changed configuration or implementation, correct it and retain the before/after comparison. |
| Preserve the base | Existing scientific and viewer paths still pass their relevant gates; no new dependency for a terminal-only install or provider-free reopening. |

These are open acceptance requirements, not completed results. The initial case
qualifies a small authoring/import/execution/observation/comparison chain, not
contact physics, checkpoint completeness, broad engine interchangeability,
physical calibration or industrial readiness. A ramp/rolling-body case can
extend it with declared inertia, friction and contact assumptions; a rover case
can add independently qualified geometry and state-estimation operations later.
