# Stateful simulation studies

A runnable extension of the existing NET/CIW workbench, not a new runtime.

The current profile develops a **persistent damped oscillator** through the
already implemented `Simulation` / `SimulationSession` and approved SCR providers.
Julia computes motion; C++ computes force/energy; the existing NET controller alone
commits the state. This change adds observer projections, explicit intervention
receipts, sequential counterfactual branches, numerical reproduction, and an
observer-scoped HTML view. No old solver, provider pin or Session format changes.

## Why this is a game/simulation development instrument

The same development questions recur: what changed, who could observe it, which
input caused it, and does replay reproduce it? This slice makes those questions
executable on an existing model before extending other engine providers.

| Requested primitive | Implemented boundary |
| --- | --- |
| Persistent instance / state | Existing oscillator `simulation_id` lineage and `owner_id` occurrence, not another generic state store. |
| Step and intervention | Existing bounded advance (1..120 ticks) and impulse (-1..1 N s), with owner/revision/tick fencing. |
| Pause / resume | Session command gate; `step` works while paused. Resume does not start a background clock. |
| Observer | Selected quantities, integer sampling cadence and delivery delay; source state is not embedded. |
| Checkpoint | Existing native checkpoint bytes wrapped in the existing `ciw.checkpoint.v1` envelope. |
| Branch | Close parent, restore its exact checkpoint through the original constructor, one fresh owner per sequential branch. |
| Reproduce | Explicit new study and native executions with the same plan/runtime, compared numerically. Not bitwise replay. |
| Compare | Unchanged `control_checks.compare` checks quantity, unit, frame, model, time grid and shape before values. |
| Render / inspect | Offline, script-free HTML showing only the chosen observer's streams. No hidden diagnostic stream embedded. |
| Multirate | Observation downsampling only, not coupled solver scheduling or multiple evolving world clocks. |

Godot/Bevy/Blender, GSC and OpenUSD integrations remain separate. This does not
checkpoint an arbitrary game world, simulate factions or authorize equipment.
The earlier detached spatial inspector and original live Godot oscillator client
are not replaced or claimed to consume the new study automatically.

## Run

Use the feature branch and Python 3.11+. The core package's dependencies are
unchanged. Actual runs additionally require the **existing, explicitly provisioned
SCR host / Julia binding file** described in `PERSISTENT_SIMULATION.md` / the
existing native interoperability guides. Runtime paths are operator inputs; a
saved observation or plan cannot choose executable code.

```sh
python -m pip install -e '.[dev]'
net simulate describe
net simulate plan --output plans/oscillator-study.json
net simulate run --plan plans/oscillator-study.json --binding /absolute/runtime.json --output-dir results/study-001
net simulate inspect results/study-001
net simulate view results/study-001 --observer observer:position --output results/position.html
```

`python -m ciw.simulation_study` is the same optional command surface.
`describe`, `plan`, `inspect`, `inspect-reproduction` and `view` never launch a
native provider. Fresh output paths are required; completion is published only
after the retained study validates. There is no silent reference fallback when
native dependencies are missing.

The shipped plan reaches tick 24, captures a parent, then advances two branches
to tick 144 (1.2 s). The baseline receives no impulse; the candidate receives
+0.25 N s before continuing. Both retain the same model/parent lineage but have
different owner occurrences. Their difference is an expected counterfactual,
not an execution failure.

## Observations and partial knowledge

A position observer receives only q, sampled every 12 ticks and delayed by 24.
A diagnostic observer receives q, v and energy at the same sampling interval
without delay. For example, at tick 144 the delayed view contains samples through
tick 120, with separate sampling and available-at ticks. Before the first delivery,
the stream is empty, not a fabricated zero or an inferred measurement.

The original checkpoint retains every event. The observer policy explicitly
selects the **latest committed value at each sampled tick**. Same-tick impulses
remain distinct in that original history; older observer snapshots remain bound
to their original checkpoint and do not change retroactively. This is not a
networked messaging model or observer memory/authentication service. Anyone with
developer access to the full checkpoint can still inspect that checkpoint.

Individual typed observation records leave `execution_id` null because a series
spans several native executions. The enclosing checkpoint digest binds all the
original execution/result IDs. No synthetic execution is fabricated to fit the
comparison API. Values are declared simulated; covariance remains undeclared.

## Interventions and identity

Each planned action declares an actor label, but the label is not authenticated
identity. The study saves an intent before dispatch; the receipt binds it to the
actual accepted existing event, revision and tick. The existing controller owns
command deduplication, stale owner rejection, failure retention and native state
commit. A failed action has retained intent/native failure but no accepted receipt.

Study, model, simulation lineage, owner, branch, native execution/result,
checkpoint, observer and comparison IDs remain distinct. Branch metadata refers
to the original restore event, rather than rewriting its simulation lineage.
Sequential branches do not establish a distributed lease or permission to leave
the previous owner running elsewhere.

## Reproduction and offline recheck

```sh
net simulate reproduce results/study-001 --expected-report-digest sha256:REPORT_DIGEST --binding /absolute/runtime.json --output-dir results/study-002
net simulate inspect-reproduction results/study-001 results/study-002
```

Use the exact `record_digest` returned by the selected original study. This binds
the operator's selected content, not independent source authenticity. The binding
must match the original native runtime closure. A reproduction uses new study,
simulation and owner occurrences, new commands and native executions. Its report
compares corresponding observer streams under the original absolute-plus-relative
policy. It does not claim cross-platform bitwise determinism or restoration of
adaptive solver caches. The existing Julia solver initializes each bounded batch.

Offline reopening validates existing native records without recomputing numerical
references, then derives observation/comparison displays from retained values.
It does not create a verification occurrence, authenticate the entire historical
record, or promote simulated evidence to physical validation or admitted state.

## Bounds and tests

Plans contain 2..8 branches, at most 64 prefix and 64 per-branch actions, 1..8
observer policies and at most 4096 records per observer view. Existing native
model, timestep, state and checkpoint limits still apply. No arbitrary code,
provider paths, stochastic state or parameter mutation is accepted in the plan.

`tests/test_simulation_study.py` uses the unchanged real controller with clearly
labelled reference doubles for the native pair. The focused public CI runs these
contracts, prior control/scientific/math regressions and installed-wheel tests.
It does **not** claim actual SCR execution. The separate own-repository SCR native
workflow runs `scripts/check_simulation_study_native.py` with actual Rust/C++/Julia,
retaining private numerical evidence without exporting provider source or binaries.
A workflow definition is not a successful native campaign; consult its reports.

The copied existing `simulation.py`, `simulation_session.py` and
`persistent_native.py` are byte-identical to NET PR49 revision
`f11a5f96685f6965d878641f30066e58774660da`. This composes the already-tested persistent
slice with PR51's controls; neither original branch is changed. The current PR51
projectile additions are retained at their existing revision.

## Next qualified adapters

Exercise this observer/intervention/checkpoint/comparison workflow with an
engine-owned provider that declares complete restoration support. Keep local
player observations, retrospective narration and developer truth separate.
Add stochastic replay only with captured RNG state/order and explicit numerical
policies. Add multirate coupling only with declared clock ownership, exchange
boundaries and interpolation/error policy. Those remain future work, not claims
made by the oscillator demonstration.
