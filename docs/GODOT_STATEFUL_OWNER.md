# An engine-owned simulation in the workbench

This adds a real, persistent **Godot 4.5.2 Standard** provider behind the existing
`SimulationControl` / `CheckpointProvider` interfaces. Godot owns the state,
logical clock, RNG, queue and observation history. NET retains the investigation
using its existing Session, operation registry, execution/result ledger,
checkpoint envelopes, observation contracts and replay checker.

The previous `net simulate` oscillator study is unchanged. `net simulation`
retains the Python reference workload and adds the optional `godot` route.
No mandatory engine dependency, provider source pin or scientific solver changes.

## Use

Install this branch, or its wheel. Explicitly supply an operator-verified Godot
binary and SHA-256. No executable path is read from saved observations.

```sh
net simulation godot demo --godot /absolute/path/to/godot --godot-sha256 sha256:HEX --output-dir results/godot-study-001
net simulation godot inspect results/godot-study-001
net simulation inspect results/godot-study-001/workspace.json
net simulation check-replay results/godot-study-001/replay.json
```

`python -m ciw.godot_motion_study` exposes the same demo/inspect commands. Inspection
and replay-report checking do not launch Godot. The demo runs a real engine or
refuses; there is no Python model substituted when Godot is unavailable. Output
directories are create-only. Engine templates are packaged with the wheel.

The native demo composes one parent, one counterfactual and one reproduction
inside the same Session. All source records remain in `workspace.json`.
`replay.json` links the original accepted suffix to fresh engine execution/result
occurrences. `branch-comparison.json` uses the unchanged typed comparator.
`study.json` is written only after all retained components validate. Transport
information in `engine-processes.json` is diagnostic, not scientific verification.

## What the model does

This is the existing **synthetic-integer-motion.v1** reference workload, ported
to GDScript for a genuine engine-owned implementation, not a rigid-body physics
solver. At each requested one-second logical tick:

1. Advance the declared 31-bit toy linear-congruential random state.
2. Apply its bounded velocity perturbation, then queued impulses in stored order.
3. Advance position, revision and history; update the engine's `Node3D` display copy.

The toy PRNG is explicit and has no security purpose. Motion values are synthetic;
metre/second labels describe the demonstration, not physical calibration. No
state advances on rendering frames, idle wall time, lifecycle commands or reads.
A single native OS process remains alive per provider across requests.

The parent pauses at tick 2 with an impulse pending for tick 4. One branch
continues unchanged. Another queues an additional impulse at tick 3. A fresh
Godot process restores the original checkpoint and executes its accepted suffix.
The checkpoint contains **configuration binding, tick, state revision, position,
velocity, full RNG state, pending queue and observation history**. Lifecycle and
owner/process identities are excluded intentionally: restoration creates a fresh,
paused owner, while the original model/continuation bytes stay intact.

Complete checkpoint here means complete for this small declared model. It does
not mean arbitrary Godot scenes, contacts, animations, timers, navigation agents,
external resources or network sessions can already be saved/restored.

## Observation policy

A debugger may receive position and velocity without delay. An embodied or sensor
observer receives only position, delayed two logical ticks. A retrospective
narrator may receive the undelayed position history, but not hidden velocity.
All policies return at most eight historical samples per channel.

Godot applies this policy before returning sample data. The Python adapter wraps
those engine-selected samples in the existing typed observation records. An
unavailable observation is an empty stream, not a zero. Narrator observation does
not alter the engine snapshot or automatically transfer knowledge to the player.

This is a workload-specific visibility policy, not an authentication boundary.
Developer access to the complete checkpoint still permits developer inspection.
No historical character or title-specific game content is embedded in NET.

## Reuse and identity

This branch composes PR58's unchanged oscillator study with the existing PR59
lifecycle implementation at `c2c2112916720546de1622ce24d0404f97bab4c4`.
`simulation_control.py`, `simulation_records.py`, `simulation_reference.py` and
`simulation_replay.py` are reused byte-for-byte. The existing CLI receives only
additive routing. No replacement controller, integrator or hidden Session is made.

Each engine exposes an owner occurrence distinct from instance, experiment,
model, simulation lineage, native process, checkpoint and operation-result IDs.
Replay allocates fresh owners and CIW execution/result IDs, while comparing the
captured continuation state and observations. The runtime identity includes
engine version/platform, operator-selected binary hash, adapter source hash and
packaged worker hashes. It is not an attestation of the binary's build or all
shared libraries. Engine/runtime binds must match before checkpoint restoration.

## Failure and resource boundaries

The trusted-process adapter uses atomic request/response files in its private
working directory, with one request in flight, sequence numbers and fresh nonces.
Requests/responses are capped at 128 KiB, snapshots at the existing 32 KiB limit,
logs at 64 KiB, the channel at 4,096 requests, and each exchange has a deadline.
Timeout, malformed response, identity mismatch, engine/script error or process
death kills/reaps the channel; it cannot then be reused.

The existing control gate quarantines a provider failure as
`refused / unknown_after_failure`. It does not invent rollback or claim the cached
pre-failure state is still the live state. Stop is retained as a lifecycle event;
explicit `close()` disposes of native resources afterward. This is process-local
coordination, not distributed leasing, durable exactly-once execution or an OS
sandbox. The binary is hashed before launch, not authenticated by a signature.

## Qualification

`tests/test_godot_motion.py` checks host validation and an actual subprocess
mailbox. Its subprocess fixtures explicitly test transport only, not Godot or
scientific output. The previous 62 lifecycle and 54 oscillator-study tests run
alongside the new tests; the oversized-byte case has bounded pytest IDs to
avoid the Windows environment-variable length limit, without changing assertions; original numerical/control tests also run.

The native workflow provisions the fixed official Godot release, checks its
archive digest, installs NET outside the checkout, and runs the actual engine.
The campaign covers checkpoint restoration, nine-command replay, delayed and
restricted observations, queued-event continuation, three-seed agreement with
the independent Python reference, uninterrupted/restored continuation, and actual
engine death/refusal handling. Native results must be read from completed CI and
its retained artifacts; a workflow definition does not establish success.

This is a **headless** acceptance target. Rendering, live GUI controls, broad
asset/world restore, Bevy lifecycle integration, cross-platform determinism and
physical validation are separate. OpenUSD and the prior detached viewers remain
separate representations, not substitutes for the continuation checkpoint.

Primary engine API references:
- https://docs.godotengine.org/en/4.5/classes/class_mainloop.html
- https://docs.godotengine.org/en/4.5/classes/class_json.html
- https://docs.godotengine.org/en/4.5/classes/class_fileaccess.html
