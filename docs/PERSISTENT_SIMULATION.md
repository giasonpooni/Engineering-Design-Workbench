# One persistent simulation, two clients

The existing Python `ciw` Session remains the programmable laboratory. This
optional extension attaches one authoritative simulation controller to that
Session and uses the existing WebSocket server. Julia computes motion through
SCR's existing native host; C++ computes force, acceleration and energy. Godot
is an optional client, never a second integrator. GSC and domain repositories
are not rewritten or absorbed into this increment.

## What is implemented

The first model is the already-qualified synthetic damped oscillator:

    dq/dt = v
    dv/dt = -2 gamma v - omega_0^2 q
    E = mass (v^2 + omega_0^2 q^2) / 2

It is not a polymer model, bead-chain implementation or chemistry engine.
Using this existing model exercises persistent execution and ownership before
introducing another numerical model. The default parameters are mass 1 kg,
omega_0 2 rad/s and gamma 0.1/s, with initial q=1 m and v=0 m/s.

The reusable implementation consists of:

- `ciw.persistent_native`: pinned binary/source snapshots, a retained handshake,
  multiple framed requests per host, bounded IO, timeout and process cleanup.
- `ciw.simulation`: sole writer of q/v, integer simulation ticks, immutable
  commands/results, checkpoint and explicit restart with fresh owner identity.
- `ciw.simulation_session`: an optional subclass of the existing Session,
  retaining its protocol checks, Workbench, selection and other operations.
- `godot/simulation.tscn`: an additional scene in the existing Godot project,
  with numerical snapshots, returned-trajectory playback, bounded advance,
  impulse, checkpoint and reconnect controls.

The old one-shot native workflow is unchanged, including its fresh reproduction.
Live steps reuse the exact existing native step/result schemas and validation
functions. A live step runs the existing independent analytical/reference check,
but does not claim the one-shot bundle's second native reproduction. This is
explicit in the new outer authority fields. No proof or state-admission status
is upgraded by a successful calculation.

## State ownership and clocks

NET alone commits {tick, q_m, v_m_s}. Providers return proposals and observables;
they never maintain a second authoritative q/v. A mutation requires an exact
owner_id, expected_revision, at_tick and command_id. The controller refuses a
stale owner, stale revision/time, or concurrent mutation. Repeating an accepted
command ID with identical content returns its retained response without
re-execution; different content with that ID refuses. After restart, any command
ID from the retained earlier history refuses, even when given the new owner ID.

There are 120 declared observation ticks per simulated second. One advance
requests 1..120 ticks. Julia may use adaptive internal integration steps; those
are NOT claimed to equal the observation ticks. Simulation time is tick/120,
not wall time and not Godot's frame clock.

Godot plays the returned samples on a presentation cursor. This cursor never
writes simulation state. The numeric labels show the authoritative final tick;
the picture labels its playback tick separately. The application does not use
RigidBody physics or independently predict the next position. Client disconnect
has no close/advance effect on the backend. This slice is bounded on-demand
simulation, not an autonomous real-time scheduler or a 60 FPS performance claim.

## Persistence, restart and failure

One Julia host/worker and one C++ host stay alive across batches. They are the
unchanged approved SCR implementation. Each request has a unique occurrence;
the accepted host/child identities stay fixed within a stream. Frames and
responses remain request-bound, runtime-bound and retained. Stdout is framed;
stderr is a bounded cumulative diagnostic prefix, not attributed to a specific
request. Cancellation remains unsupported: timeout or failure kills/reaps the
owned stream, and the controller cannot silently restart it.

A failed Julia/C++ stage leaves the previous committed state unchanged. When
possible, a separate failure artifact retains completed stages and the rejected
command. If storage itself is unavailable, memory remains at the previous state
and the exception is surfaced; durability of the failure report cannot be
promised in that case. Event publication is create-only and atomic on the same
filesystem, preceding visibility of its state. This is not a power-loss-tested
multi-file transactional database.

A checkpoint contains the model, configuration, original state, native runtime,
initial observable evaluation and full accepted event chain. Opening it checks
identities, original native records, sequence and state/output bindings, without
launching providers or rerunning reference solvers. Explicit restart requires an
independently selected checkpoint_id and the original runtime. It preserves
model_id, simulation_id and the selected physical state; a new owner_id fences
old client commands and a restore event binds the selected checkpoint.

The checkpoint_id hashes canonical checkpoint content without its own ID field;
it is not the SHA-256 of the outer file. A self-declared hash does not authenticate
a source. The expected ID must come from the operator's retained-artifact record.

A restore is a new execution incarnation from an explicitly selected checkpoint.
Stop the previous owner before restoring. Ownership is enforced inside this
Session and against reusing its output directory; this is not a distributed
lease service preventing copies on another machine. Restoring an earlier
checkpoint starts a new continuation from that retained history, not an
in-place rewrite of a later run.

The Julia process and runtime remain persistent, but the existing Tsit5 profile
starts a new ODE solve for each bounded batch. Its adaptive caches/internal solver
state are not serialized. Restart/partition agreement is checked numerically;
bitwise-equivalent adaptive trajectories are not claimed.

## Run headlessly and attach Godot

Provision approved runtimes as in [native interoperability](NATIVE_INTEROP.md).
No saved command can supply executable paths, packages, source code or a new
provider. The binding file is operator configuration only.

Start the existing server with the optional simulation Session extension:

```sh
python -m ciw.simulation_session serve --binding runtime.json --output-dir live-run
```

No GUI is required. In another terminal, inspect or change that same instance:

```sh
python -m ciw.simulation_session status
python -m ciw.simulation_session advance --ticks 12
python -m ciw.simulation_session impulse --impulse-n-s 0.2
python -m ciw.simulation_session checkpoint
```

Attach the optional scene (Godot Standard 4.5.2 is the existing tested target):

```sh
godot --path godot res://simulation.tscn
```

The server binds loopback only. It retains the existing origin restrictions;
this is a local trusted-operator interface, not a public execution endpoint.
The legacy Session recording remains an independent synthetic reference;
simulation snapshots are not silently substituted for observation evidence.

For a finite process-only run, then explicit restart into the interactive server:

```sh
python -m ciw.simulation_session headless --binding runtime.json --output-dir batch-run --batches 4
python -m ciw.simulation_session inspect batch-run/simulation/checkpoint-<id>.json
python -m ciw.simulation_session serve --binding runtime.json --output-dir restarted-run \
  --checkpoint batch-run/simulation/checkpoint-<id>.json --expected-checkpoint-id sha256:<id>
```

Use the filename and checkpoint_id returned by the command. Checkpoints and
simulation events live beside, not inside, the unchanged legacy workspace
format. Ordinary workspace reopening does not start or restore a simulation.
The extension explicitly checkpoints on normal shutdown. SIGKILL/power-loss
recovery is only from an already published, selected checkpoint; orphan event
scanning/recovery is not implemented.

## Budgets and validation

The existing native numerical bounds remain intact. Each stream accepts at most
240 execution requests, below SCR's 256-frame budget. The whole retained lineage
allows at most 200 events and a 32 MiB checkpoint. These are prototype bounds,
not limits claimed for a future sparse/particle/PDE family. Exhaustion refuses;
there is no hidden provider rotation, truncation or loss of old events.

```sh
python -m unittest discover -s tests -p 'test_persistent*.py' -v
python scripts/check_persistent_simulation.py --binding runtime.json \
  --godot /path/to/godot --output-dir native-simulation-evidence
```

The unit/controller tests use explicitly labelled reference doubles. Pipe tests
run actual bounded OS child processes but do not qualify scientific kernels.
The second command requires real Julia and C++ through SCR and the actual Godot
scene. It checks persistent native occurrences, analytical trajectory agreement,
checkpoint/restart, stale-owner fencing, uninterrupted/restored agreement,
provider-free inspection, client reconnect and dead-provider state preservation.
Missing runtimes fail rather than skip.

No covariance, material calibration, chemistry mechanism, physical validation,
SP1 proof, hardware authority, automatic model promotion, distributed ownership,
real-time deadline guarantee, or public deployment is added by this slice.
