# Executable author / run / observe / reproduce / compare slice

This optional **source-checkout** workload uses the existing Python `ciw.Session`,
operation runner and workspace records. It adds three registered operations when
`ciw.interactive_simulation` is explicitly selected:

- `simulation.projectile-author.v1`: run the fixed Blender generation job and
  retain the GLB bytes, generator identity and author report.
- `simulation.projectile-run.v1`: run one explicitly bound Godot or Bevy adapter,
  retaining scenario, input events, tick observations and import report.
- `simulation.projectile-compare.v1`: retain per-runtime analytic errors and
  compatible-grid trajectory differences under an explicit numerical policy.

No engine is a dependency of a terminal-only installation or offline inspection.
This module does not replace `ciw.simulation`, `ciw.simulation_session`, SCR,
existing viewers or the separate persistent-oscillator work. The selected engine
owns the evolving state in this profile; Python owns the investigation.

## Model and runtime scope

The model is a point projectile in constant gravity, with optional prescribed
velocity increments before named transitions. There is **no drag or contact**.
Godot uses its real SceneTree, GLTFDocument importer and a GDScript semi-implicit
Euler update. Bevy uses its real ECS World and an ordered input/integrate/observe
schedule, with the same deliberately simple integration rule. Their states are
independent; no cross-engine state ownership or call chain exists.

The Bevy headless adapter imports actual GLB vertex coordinates with `gltf-rs`.
It does not qualify Bevy's renderer, GltfPlugin, graphics upload or materials.
Neither adapter claims to exercise an engine's rigid-body/contact solver.
The fixed Blender authoring job exports a radius-0.25 m sphere and unequal
one-, two- and three-metre axis markers. Both runtime import reports must match
those landmarks and the imported mesh bounds before a result is accepted.
Physical configuration remains separate from the authored mesh.

The default case starts at `(0,5,0) m` with velocity `(2,0,0) m/s`, gravity
`(0,-9.81,0) m/s^2`, and records 60 transitions at 120 Hz. Its analytic endpoint
at 0.5 s is `(1,3.77375,0) m`. Semi-implicit Euler has a nonzero timestep error;
comparison does not conceal it or require cross-engine bit equality.

The comparison policy is 0.1 m maximum position error and 0.0001 m/s maximum
velocity error against the analytic solution. These are declared demonstration
budgets, not empirical physical-accuracy certifications. Different grids are
incomparable for pointwise comparison; refinement gets its own reference check.
Missing observations remain missing and yield INCOMPLETE, never PASS or zero.

## Commands

Use Python 3.11+ from a source checkout. Provision explicit trusted binaries;
there is no PATH discovery or execution selected by saved records. The native
CI target is Godot Standard 4.5.2, Blender 4.5.3 and Rust 1.96.0, using the same
Bevy source revision as the existing projector. Its actual qualification status
must be read from the native workflow and retained report, not these version names.

```sh
python -m pip install -e .
cargo +1.96.0 build --release --manifest-path tools/interactive-simulation/bevy/Cargo.toml

python -m ciw.interactive_simulation run \
  --scenario examples/interactive-simulation/projectile.json \
  --blender /absolute/path/to/blender --runtime godot \
  --executable /absolute/path/to/godot --output-dir results/projectile-godot

python -m ciw.interactive_simulation candidate \
  results/projectile-godot/workspace.json --runtime bevy \
  --executable tools/interactive-simulation/bevy/target/release/ciw-bevy-projectile \
  --output-dir results/projectile-bevy

python -m ciw.interactive_simulation inspect results/projectile-bevy/workspace.json
```

`candidate --scenario FILE` makes an explicit changed candidate rather than
editing an old scenario. Each candidate retains the prior investigation history.
The special `--diagnostic-fault double-gravity` intentionally exercises regression
detection; it is not a silently changed physical model or a production feature.

Reproduction selects a specific completed execution ID printed by `inspect`:

```sh
python -m ciw.interactive_simulation replay results/projectile-bevy/workspace.json \
  --execution-id execution-<retained-id> --runtime bevy \
  --executable tools/interactive-simulation/bevy/target/release/ciw-bevy-projectile \
  --output-dir results/projectile-reproduced
```

The new execution, result and request nonce are distinct. The earlier execution
and its comparison remain retained. Original binary, adapter source, platform
and (for Bevy) Cargo manifest/lock identities must match. No replacement binary
is silently substituted. Preserve the generated Cargo.lock with the investigation;
initial dependency resolution is recorded, not claimed identical across dates.

## Records, failure and trust

The initial `run.v1` is explicitly classified as declared initial conditions,
not a simulated sensor measurement. Its one-second selection support is not the
simulation horizon. Simulation clocks live in the captured scenario and trace.
The source, author result, selected asset, runtime result and comparison retain
separate content and occurrence identities through existing CIW envelopes.
A successful comparison has no verification ID and grants no ESM admission.

Inputs are ordered by `(tick,id)`. Input tick k is applied at `(k-1)/Hz`, before
transition k, and appears in post-step sample k. Initial sample zero precedes
all inputs. Node handles and ECS entity indices are not cross-run identities.

The process runner bounds runtime and output, checks executable drift, snapshots
adapter script bytes, rejects overwrite of investigation destinations, and uses
no shell or executable paths from scenario/workspace content. It is **not an OS
sandbox**. Binary hashes and declared source hashes are not build attestations;
shared libraries and the whole machine are not captured. Workspaces prove
self-consistency, not authenticity against a party able to rewrite every hash.

Native process errors become retained refusals, not successful empty traces.
An interrupted process without a valid response remains refused; durable live
partial capture and recovery of a killed process are not implemented. A supplied
partial trace can be inspected but cannot pass the numerical comparison.
Inspection validates retained structure and dependency bindings without launching
an engine or rerunning the analytic reference. Use this module's `inspect` entry
point so its trusted payload validators are registered; the generic CLI is not
silently modified to import optional providers.

## Validation

```sh
python -m pytest -q tests/test_interactive_contract.py tests/test_interactive_session.py
python scripts/check_interactive_simulation.py \
  --blender /absolute/path/to/blender --godot /absolute/path/to/godot \
  --bevy tools/interactive-simulation/bevy/target/release/ciw-bevy-projectile \
  --output-dir results/interactive-native
```

The unit suite clearly labels synthetic trace and runtime doubles. Actual child
process tests qualify timeout/refusal plumbing, not engines. The native command
requires all three real tools, author/import checks, fresh reproduction in each
runtime, a detected and corrected gravity regression, timestep refinement,
tick-addressed input experiments, and provider/reference-free reopening.
Missing tools fail; no mock output or skipped engine gate counts as native evidence.

The implementation is a bounded headless development experiment. General live
subscriptions, windowed playtests, pause/step of running engine-owned worlds,
checkpoints, automated parameter-search UI, arbitrary assets, energy accounting,
GSC live views, CSE/CSR/FSRT application adapters and shipped games remain separate
extensions. None is implied by a passed projectile check. Specialist repositories,
licenses, current source pins and private implementations remain unchanged.
