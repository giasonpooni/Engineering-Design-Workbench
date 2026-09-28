# Stateful experiments: intervene, observe, branch, replay

NET can now control an explicitly attached, provider-owned simulation through its
**existing Python CIW Session**. The first runnable case is a small synthetic
Python model. It is not a new Godot, Bevy, SCR, Julia or C++ integration.

The design follows the same six operations for scientific and interactive work:
**configure → execute → intervene → observe → compare → reproduce**. A game is a
workload, not a special mode of the terminal.

## Try the complete experiment

From this feature branch, with the existing package installed:

```sh
python -m pip install -e '.[dev]'
net simulation demo --output-dir results/stateful-001
net simulation inspect results/stateful-001/workspace.json
net simulation check-replay results/stateful-001/replay.json
```

`python -m ciw.simulation_cli` provides the same commands. Use a new output
directory: the demo and its reports do not overwrite existing destinations.
`inspect` and `check-replay` are provider-free readers, **not fresh executions**.
The latter returns exit code 2 for a valid retained FAIL, 1 for invalid input,
and 0 for a valid retained PASS.

The demo creates one existing Session, attaches a reference motion provider,
queues an impulse, pauses at tick two and takes a checkpoint. It then executes
a baseline, restores a separate owner for an altered experiment, and restores
another owner to reproduce the baseline's eight accepted commands.

Expected observations for this synthetic case:

- World/debugger time is six seconds; the embodied observer's latest available
  position sample is from second four. Hidden velocity is not in that view.
- Changing the queued intervention yields a maximum position difference of
  eight metres. The zero-tolerance comparison correctly reports **FAIL**: that
  means the branches differ, not that the intended experiment failed.
- Baseline replay reports **PASS** for the eight compared commands. The parent
  state is unchanged by both children; each child has fresh instance, owner,
  execution and result identities.

`workspace.json` retains 32 ordinary execution/result pairs through the original
Session mechanism. `replay.json` is a derived evidence bundle, not another
execution ledger; `branch-comparison.json` uses the existing typed numerical
comparator. `summary.json` is a convenience summary, not the authority for any
check. The Session's original analytic oscillator recording is retained unchanged
as its existing host recording; its arrays are not used as this live model's
state, observations, or numerical reference. Motion samples declare their own
model, provider, entity, frame, time and provenance.

## The ownership boundary

| NET controls and retains | The explicitly attached provider owns |
| --- | --- |
| Instance/experiment identity and command ordering | Model state and simulation clock |
| Owner/revision fencing and command retry receipts | Numerical stepping and internal substeps |
| Intervention requests and retained outcomes | Whether an intervention is legal |
| Observer selection and typed observation checks | Visibility, delay and observation formation |
| Checkpoint references, branch lineage and replay checks | Complete continuation snapshots and restoration |

The controller does not integrate the model or mirror its state variables. Its
instance view contains configuration, provider identity, clock metadata and a
state hash. Opaque snapshot bytes are evidence on explicit checkpoint/restore
operations, not another authoritative live world. `SimulationInstance`, an
experiment label and a CIW execution/result occurrence remain different objects.

`SimulationControl(session)` registers one `simulation.control.v1` backend in
that Session's existing `OperationRegistry`. It neither replaces the registry nor
creates a second Session, Workbench, solver, workflow engine or mandatory dependency.
Existing `statistics.v1` executions can coexist without advancing the live model.

## Use an explicitly bound provider

```python
from pathlib import Path
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw.simulation_control import SimulationControl, completed
from ciw.simulation_records import observer
from ciw.simulation_reference import PROVIDER_ID, ReferenceMotion

session = Session(make_demo_run(), Path("results/python-stateful-001"))
control = SimulationControl(session)
world = control.attach(
    ReferenceMotion(seed=7),
    provider_id=PROVIDER_ID,
    experiment_id="observation-delay",
)
completed(world.command("start"))
completed(world.command("step", dt=1))
completed(world.command("pause"))
checkpoint = completed(world.command("checkpoint"))
player = observer("player", kind="embodied_agent", channels=["position"])
result = completed(world.command("observe", observer=player))
child, restore_receipt = control.branch(
    checkpoint, ReferenceMotion(seed=7), experiment_id="counterfactual"
)
completed(restore_receipt)
session.save_workspace(Path("results/python-stateful-001/workspace.json"))
```

The Python Session API retains its existing output-directory policy; use a fresh
operator-selected directory. Native adapters opt into `SimulationProvider` in
`simulation_control.py`: `identity`, `configuration`, `snapshot`, `restore`,
`lifecycle`, `step`, `intervene`, `observe_for`, plus the inherited checkpoint
protocol's `observe`. Attachment uses a trusted Python object, never an import
path, executable name or command extracted from a saved record.

Snapshot bytes must include RNG state, queued external events, integration memory,
agent memory and other continuation state the provider actually needs. They must
exclude ephemeral owner/process handles. A seed alone is insufficient. Providers
must not advance state/time during identity, snapshot, observation or lifecycle
calls. A step reaches the requested boundary; intervention advances state revision
without silently advancing time. Providers remain free to refuse unsupported
step sizes or operations.

The reference provider deliberately supports only integer one-second ticks,
a toy PRNG, queued velocity changes and up to 128 ticks. Its units describe a
synthetic model, not physically calibrated motion. It contains the equations;
the controller contains none of them.

## Observation is not world truth

Observers carry an identity, kind, selected channels, data-only policy and an
explicit `player_knowledge_transfer` declaration. Batches separate acquisition
sample time from `available_at` time. Empty batches mean no available samples;
they are not fabricated zeros. Existing numeric observations retain quantity,
unit, frame, model/entity identity, full optional uncertainty and provenance.

The reference embodied/sensor view is delayed by two ticks and cannot request
velocity. Its debugger can receive both channels. The retrospective narrator can
receive current position without any automatic transfer to an embodied agent.
These are executable reference policies, not historical claims or a general
knowledge engine. Generic policy enforcement remains the provider's duty. The
observer declaration is **not authentication or an adversarial access-control
boundary**; trusted operators can explicitly request checkpoints containing the
whole state. Inner samples are linked to their enclosing execution by
`projected_samples`, without rewriting the original samples.

## Failures and replay are explicit

Each request carries the expected owner, control revision and provider-state
revision. Identical retries return the original receipt while this controller
lives; reuse of a command ID with different data refuses. A per-instance lock
covers dispatch and Session publication, not only the provider call. Raw calls
to the registered operation cannot bypass that gate. Pre-dispatch stale/lifecycle
refusals retain failed executions without touching or quarantining the owner.

Once a provider has been invoked, unexpected failure, malformed output, external
state drift or publication failure quarantines the instance as `refused` with
`state_status: unknown_after_failure`. Previously captured metadata is not passed
off as current truth. No rollback is assumed. Stop resource use explicitly with
`discard()` on the refused handle; it does not manufacture a successful retained
stop. Cancellation and process termination are not transactional recovery.

Branches require matching declared runtime/model/simulation lineage/configuration,
a fresh owner and initial provider revision zero. They restore into a separate
instance, start paused, and retain both the checkpoint content reference and the
selected source execution/result reference. The original owner is untouched.

`simulation_replay.replay(...)` executes a supplied fresh provider against a
contiguous accepted suffix of 1–128 commands after a **paused** checkpoint. It
compares captured state bytes, provider clock/revision and returned observations,
not merely the final displayed number. New executions are required. Mismatch
produces a retained **FAIL**, with first divergence and all mismatching indices;
a provider refusal stops execution and remains in the original Session, without
emitting a successful replay report. A completed-prefix report is not advertised
as complete reproduction.

All checks remain `not_verified`, with no verification occurrence or state
admission. Content hashes detect consistency changes; a malicious author can
reseal fabricated records. Provider runtime declarations are not full build
attestations or signatures. Passing this suffix is not proof of universal,
cross-platform or future deterministic behavior.

## Deliberately bounded first implementation

The pilot permits 64 attached handles per controller, 1,024 cached command IDs per
instance and opaque snapshots up to **32 KiB**. Pre/post snapshots check every
command: this is on-demand experimentation, not a per-frame performance design.
Stopped handles are not recycled. Use another Session for a new bounded campaign.
Ownership and retry receipts are process-local, not distributed leases or durable
exactly-once recovery. Reopening workspaces never resurrects live owners.

Existing persistent SCR oscillator work and the Blender/Godot/Bevy projectile
adapters retain their own interfaces and qualifications. This increment does not
silently generalize or wrap them. Native lifecycle adapters, large snapshots,
multi-rate scheduling, live GUI subscriptions, capture of image/video/audio,
campaign search and OpenUSD world composition remain separate extensions.
OpenUSD/engine scenes remain representations; NET retains the investigation.

## Qualification

`tests/test_simulation_control.py` exercises the actual Python reference model
through the original Session: lifecycle, fencing, retry/concurrency, provider and
publication failures, explicit observers, checkpoint restoration, independent
branches, RNG/queued-event continuation, corrupted/resealed records, injected
replay divergence, provider-free inspection and existing statistics coexistence.
The dedicated `stateful-simulation.yml` workflow requires every new test, repeats
them from an installed wheel outside the checkout, and retains source/evidence.

Local test results and environment are recorded in the pull request. A workflow
file is not evidence that CI has passed. Native engines, physical validation,
repository-wide green CI and Windows/macOS runtime acceptance are not implied by
these reference tests. Existing qualification gates are unchanged.
