# Persistent Godot campaigns

The existing `SimulationControl` and campaign/replay APIs now have an optional
Godot-owned point-model adapter. The native process retains a Node3D position,
velocity, queued impulses, history and clock across requests. Python dispatches
operations and forms typed records; it does not advance the dynamics.

This is a bounded headless point model, not Godot rigid-body/contact physics,
an arbitrary scene/save-game loader, a renderer or a new simulation controller.
The older Blender/Godot/Bevy projectile, native oscillator and game-trace work
retain their own implementations and qualification. No engine pin is changed.

## Run the complete native experiment

Install this branch, provision the existing Godot 4.5.2 stable executable, and
compute the SHA256 of that exact executable (not the release ZIP):

```sh
python -m pip install -e '.[dev]'
python -c "import hashlib,pathlib; print('sha256:'+hashlib.sha256(pathlib.Path('/absolute/path/to/godot').read_bytes()).hexdigest())"
net simulation godot demo --godot /absolute/path/to/godot --godot-sha256 sha256:REPLACE_WITH_EXECUTABLE_HASH --output-dir results/native-001
```

The operator selects and trusts the executable. A file cannot request code
loading. Missing/mismatched binaries refuse; no Python fallback is substituted.
Godot is needed only for explicit native execution. Existing inspectors remain
provider-free. Native workers are included in the installed wheel.

The demo pauses at tick two with an impulse still queued for tick six. Four
branches restore that native snapshot and run a baseline and three additional
impulses at tick three. Each branch runs eight 1/64-second steps and compares
position-x observations through the existing typed comparator. The parent is
unchanged by those branches. An additional fresh owner reproduces the parent's
accepted suffix, including the queued event. A delayed embodied observation and
separate native-process diagnostics are retained.

Expected differences for the declared dyadic fixture are 0.25, 0.25 and 0.5 m.
These are test expectations, not physical accuracy claims. The generated records
and observed qualification, not this guide, establish what actually ran.

## Inspect and rerun

```sh
net simulation inspect results/native-001/workspace.json
net simulation campaign-check results/native-001/campaign.json
net simulation check-replay results/native-001/replay.json
net simulation godot campaign --godot /absolute/path/to/godot --godot-sha256 sha256:EXECUTABLE_HASH --workspace results/native-001/workspace.json --plan results/native-001/plan.json --output-dir results/native-002
```

Use fresh output paths. Export `campaign.json` with the existing `campaign-view`
command and an explicitly selected report-file digest; see
[Simulation campaigns](SIMULATION_CAMPAIGNS.md). That same observation-only
inspector works without changes. It embeds no native checkpoint bytes.

`campaign` freezes and validates the selected source workspace/plan in scratch
before creating the requested output. Once native execution starts, failures and
completed prefixes remain in the existing Session; a completed campaign report
is not fabricated. A repeated plan creates fresh instances/owners/executions,
not a second result with the original occurrence identity.

## Python integration

```python
from pathlib import Path
from ciw.godot_simulation import GodotProjectile, PROVIDER_ID
from ciw.simulation_control import SimulationControl, completed

# session is your existing CIW Session, not a new engine session.
control = SimulationControl(session)
with GodotProjectile(Path(godot_path), expected_sha256=godot_sha256) as native:
    world = control.attach(native, provider_id=PROVIDER_ID, experiment_id="native-point")
    completed(world.command("start"))
    completed(world.command("step", dt=1/64))
    completed(world.command("pause"))
    result = completed(world.command("checkpoint"))
    completed(world.command("stop"))
```

`stop` halts simulation; context exit separately closes the process. Always use a
context manager, including in provider factories (the CLI uses an `ExitStack`).
Godot, not Python, owns stepping, observation availability and snapshot restore.
Owner and process IDs are occurrence metadata, excluded from continuation bytes.
No reference world state is relabelled as measured evidence.

## Limits and failure semantics

The native pilot uses 64 Hz so every external time is exactly representable in
binary. It supports 128 ticks, 16 queued impulses, the existing 32 KiB snapshot
limit and at most 32 historical sample rows per observation. Debuggers can request
position/velocity components. Embodied/sensor observations are delayed two ticks
and exclude velocity; retrospective narrators get current position without
transferring knowledge. These labels are not user authentication.

The point model uses Godot Vector3 float32 arithmetic and semi-implicit Euler.
Analytical discrete checks account for that integration rule; continuous
trajectory error is not hidden. No covariance or physical calibration is inferred.
Snapshots use bounded native Variant bytes, validated shapes and disabled object
deserialization. They contain the queue and retained history, not merely a seed.

The request transport uses a four-byte little-endian size followed by UTF-8 JSON.
Responses are bounded lines with matching request nonce, action and native PID.
The deadline covers both pipe writes and reads. Unexpected replies, native
refusal, oversized output, process death and timeout close the adapter; the
existing control gate quarantines a touched instance instead of assuming rollback.
A process context closes child resources on both success and failure. This is
not an OS sandbox, a distributed lease or power-loss-tested transaction system.
Binary/source hashes bind selected content, not shared-library closure or signer
authenticity. Saved evidence never silently reattaches a native owner.

## Qualification

The dedicated workflow runs the new real-OS-pipe host tests with the unchanged
stateful/campaign/control suites on Linux and Windows, then repeats the provider
and stateful tests from an installed wheel outside source imports. Its Linux
profile downloads the existing checksum-pinned official Godot 4.5.2 archive and
executes the actual native campaign, fresh replay, queued-event restoration,
independent dyadic/non-dyadic numerical checks, missing/delayed observations,
stale-owner/retry controls, real process death and provider-free reopening.

Host protocol doubles are explicitly labelled and are not engine qualification.
Windows host tests do not qualify a Windows Godot binary. Native/rendering,
physical, wider-repository and merge qualification remain separate. Observed
results and any failure/fix history belong to PR #59.

Upstream interface references (Godot 4.5 documentation):
- OS `read_buffer_from_stdin`: https://docs.godotengine.org/en/4.5/classes/class_os.html
- `--headless`/`--script`: https://docs.godotengine.org/en/4.5/tutorials/editor/command_line_tutorial.html
- `var_to_bytes`/`bytes_to_var` (without objects): https://docs.godotengine.org/en/4.5/classes/class_@globalscope.html
