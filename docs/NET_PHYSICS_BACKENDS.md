# Godot Physics / Jolt: controlled game-backend qualification

`net foundry physics run | inspect | report` extends the existing Foundry and Session.
It evaluates **GodotPhysics3D and Jolt Physics using the exact same accepted-workbench
1792 source**, without migrating the game, merging parallel branches, or changing its
colliders, movement, economic rules, save schema, tests or tolerances.

## Qualified profile, not a universal engine competition

The only installed profile is `1792.accepted-bench-backends.v1`, bound to game commit
`4869eac467288b99c32268df99d4a06e573fb28d` (1792 PR38) and its complete 121-file source
inventory. It uses the exact official Linux Godot4.5.1 executable, SHA256
`db07cae7de644278a1884d4552bdf2bca3f5d30131b18faf3a0c4d730080b199`.
A different snapshot or executable is refused rather than called an equivalent test.
No game code, GLB, copyrighted research or native executable is copied into NET.

The original game's project does not explicitly select a backend. The comparison
creates temporary full project copies and adds `override.cfg` with either
`physics/3d/physics_engine="GodotPhysics3D"` or `"Jolt Physics"`. Both use60Hz physics.
The only other temporary setting enables a passive observation autoload. The original
`project.godot`, tests, player/controller, collision shapes and workshop remain exact.
There is no permanent change of default, and no automatic promotion on a green result.

## Run from the existing terminal

```sh
python -m pip install -e '.[dev]'
net foundry physics run --game-root ../1792 \
  --godot /absolute/path/to/Godot_v4.5.1-stable_linux.x86_64 \
  --godot-sha256 sha256:db07cae7de644278a1884d4552bdf2bca3f5d30131b18faf3a0c4d730080b199 \
  --output-dir results/physics-production
net foundry physics inspect results/physics-production
net foundry physics report results/physics-production --output results/PHYSICS-COMPARISON.md
```

`--game-root` is the **repository root**, not its `game/` directory. The original
snapshot must be checked out deliberately (prefer a separate worktree rather than
switching an active development tree). Import caches and Git internals are excluded
by the existing packet inventory; an altered source or added source file changes its
identity and is refused. The known profile is not automatically rebased onto main.

## What executes

Four independent jobs use the original production controller:

1. Explicit GodotPhysics3D, first complete run.
2. Explicit Jolt Physics, first complete run.
3. Explicit GodotPhysics3D, fresh repeated complete run.
4. Explicit Jolt Physics, fresh repeated complete run.

There are no dependency edges hiding Jolt when a baseline fails, no retries and no
repair variants. Every available suite is run even after a different suite fails.
The max-operation budget must permit all four before dispatch. Each job executes an
import, a backend signature probe, fourteen unchanged game suites and the original
Python gameplay rechecker:16Godot processes+1Python process per complete job.
The fixed120-second per-process limit retains the original game suite limit. Engine
crashes and test failures retain logs and dispositions, not guessed PASS results.
An interrupted overall run has no completed production receipt; resume is not provided.

The fourteen suites cover command-story, house reporting, riding, companions, names,
childhood, aftermath, fixed interlude, household economy, remounts, settlement fabric,
town, smith's workshop and accepted-bench integration. Exact completion markers total
**2,096 assertions per complete pass**. Repeating those assertions four times is not
8,384 distinct tests or new content. Python unit fixtures are explicitly synthetic.

## Backend identity and save isolation

A passive autoload records the requested backend, the runtime-resolved setting,
registered backend choices, engine build, fixed timestep and all resolved `physics/`
settings at every suite startup. It marks clean tree shutdown but never moves an
actor or advances game time. All suites must report consistent settings.

The abstract `PhysicsServer3D.get_class()` does not identify the concrete solver in
this build. Therefore a **separate probe scene** corroborates the selected backend:
it ray-tests a fixed triangle-mesh box. Godot reports face index8; default Jolt
reports-1. Both must hit the same surface. The probe is version-specific and runs in
its own process, never adds test bodies to the game scene. This is corroboration under
an exact trusted binary/configuration, not cryptographic backend/host attestation.

The launcher sets a disposable child HOME/XDG/APPDATA environment before Godot starts;
it does not modify the parent's environment. The actual engine user directory is
checked to lie in that job's private temporary home. Existing `user://` saves are
never read from or written into the user's real1792 directory. Each backend/repetition
starts with its own home and project import cache. A game save is never transferred
between backends. Existing in-process F5/F9 behavior is tested as authored; fresh
repeated whole journeys do not constitute cross-process campaign save-resume proof.
Cross-backend save migration remains unimplemented, not silently declared compatible.

## Evidence and unchanged acceptance

The original game tests and original `tools/check_bench_artifact.py` execute without
modification. A separate NET gate rechecks imported geometry, four physical capsule
contacts, blocked-pickup atomicity, produced/carried/delivered custody, cash and stock,
600-tick production, trace continuity and two explicit restore epochs. Actual native
logs, observations, settings and game checker output are retained with byte hashes.
Large JSON traces are split into Unicode-safe text chunks to preserve exact UTF-8
bytes **within the existing Session64KiB scalar limit**. No core limit is weakened.

Reinspection uses the original production history and recomputes gates without starting
Godot or Python child processes. It checks worker, script, executable, source and matrix
bindings. Results, executions, production receipts, original source identity and derived
comparison records remain distinct. Signatures, hostile-host authenticity and evidence
admission into ESM are not implied by a matching content hash.

Same-backend repeats compare full recorded trace/stage/geometry projections. Cross-backend
comparison reports exact trace agreement or the first discrepancy and final-resource
agreement. A maximum positional delta is emitted only where ticks, epochs and phases
align; it does not misleadingly compare different moments of two routes. Equality of
all resolved physics settings except backend is reported. Cross-backend bitwise trajectory
agreement is **not** an acceptance requirement; each must satisfy the same game contract.

Process wall times are retained as diagnostic observations. They include startup/import,
GDScript, filesystem work and host scheduling noise. They are **not** physics-frame costs,
GPU profiling, input latency, hardware scalability or evidence that Jolt is faster. No
engine is ranked using these run times. Human feel and target-hardware budgets still need
separate evidence.

## What remains outside this gate

This snapshot includes its existing riding/companion/town systems, but not the separately
developed movement-foundation/course, funded-service, later anthology or other branches.
They are neither merged nor jointly qualified by this result. No additional crowd, cloth,
destruction, dynamic-prop stress test or GPU benchmark is claimed. No game scene is rendered
by this native matrix; the earlier workshop screenshots do not become Jolt render evidence.

Native Linux only is currently qualified. Python contract and installed-wheel checks run
on Linux and Windows; that does not qualify Windows native game physics. Temporary folders
and bounded execution are not a security sandbox. The exact runtime is operator-trusted;
shared libraries, OS, network access and all external reads are not attested. Inspect only
trusted retained bundles and use original source/executable pins.

## Qualification commands

```sh
python -m pytest -q tests/test_foundry_physics.py
python scripts/check_foundry_physics.py --game-root ../1792 --godot /path/to/godot \
  --output-dir results/physics-native
```

The dedicated workflow retains source and installed-wheel tests on two operating systems,
then actual four-job native qualification. It retains the exact candidate NET source,
game revision, original production/Session records, environment and comparison. The native
qualification script also alters eight copies of actual observations and verifies that
mislabelled backends, missing observers, failed tests, a wrong backend signature, teleport,
invented money, changed source and unmarked rewinds cannot qualify. Source/gameplay output
remains intact. A workflow definition is not proof of a successful hosted run.

## Primary engine references

- Godot4.5 ProjectSettings: explicit backend selection, override files and user paths:
  https://docs.godotengine.org/en/4.5/classes/class_projectsettings.html
- Godot4.5 Jolt integration: margins, face-index reporting and behavioral differences:
  https://docs.godotengine.org/en/4.5/tutorials/physics/using_jolt_physics.html
- Pinned engine initialization, including fallback when a backend is unavailable:
  https://github.com/godotengine/godot/blob/4.5.1-stable/main/main.cpp

These explain API behavior, not why a given game should migrate. The executable signature
probe was added because observing the configured setting alone cannot prove no fallback.
