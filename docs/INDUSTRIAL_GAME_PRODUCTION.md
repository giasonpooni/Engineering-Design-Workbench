# Industrial game production: first real-title worker

The existing production controller now consumes a pinned, game-owned Godot domain
slice. An agent can submit candidate parameter assignments, batch-expand a finite
space, execute through the original NET Session, and read exact failed-rule/action
feedback. The first workload is 1792's ORIGINAL household water-round state,
clock, validation and save/load implementation, not another synthetic courier.

NET's graph runner, ParameterSpace, Session, operation/result identities,
three-valued game checker, comparator and production receipts are reused. No
second scheduler, game-state owner, numerical water model or evidence store is
introduced. Existing production, scientific, courier and agent/MCP interfaces stay
unchanged. This branch is stacked on production PR #65; it does not merge or
replace the independent agent/MCP branch.

## What runs and what does not

The title supplies an explicit 11-script source closure, a game-owned capture
entrypoint, fixed scenario/checks and a bounded parameter space. The operator
pins the exact profile bytes and extracted Godot binary. Each operation snapshots
those scripts into a NEW temporary minimal Godot project. Saved plans cannot
select executables, file paths, imports, credentials or shell commands. The
operator must trust the selected scripts: this is **not an OS sandbox**.

The workload calls actual title state methods. Its initial post-inquiry state and
endpoint positioning are explicit fixtures. It does not render the full scene,
walk the avatar, qualify collisions or prove that an earlier childhood was played.
The game clock advances 420 original physics ticks. Observations have a declared
six-tick cadence and assignment-relative origin; original game ticks are also
retained. The game itself performs a disk save/load roundtrip and then continues
on the restored owner. No player save slot or live checkout is modified.

This remains a LOCAL SEQUENTIAL worker. The batch is not 18 parallel agents. No
model API, autonomous source rewriting, token/currency-budget service, distributed
leases, automatic merge, release approval, historical truth scoring, live GIS
acquisition or Blender asset factory is claimed.

## Setup: two checkouts, separate licences

Use this NET feature branch and the companion 1792 branch
`feat/net-water-production-v1-20260929`, initially pinned at
`70fcc477fb3783847fea56fa0ccaa5868413226f`.

```sh
python -m pip install -e '.[dev]'
python /absolute/path/1792/tools/check_net_profile.py
```

The generic adapter is in NET. The harness and title code remain in 1792 under
Cartesian Graphics' existing terms. A profile grants local workload access, not
permission to redistribute proprietary source as AGPL NET code. Game play does
not depend on NET being installed.

## Batch 18 real game-state scenarios

The following commands are run from NET. Replace filesystem paths with local
operator choices. The profile digest below is the exact companion profile; the
engine digest must be for the EXTRACTED Godot 4.5.1 executable, not the ZIP.

```sh
net production project grid \
  --profile /absolute/path/1792/tools/net/water-round.profile.json \
  --profile-sha256 sha256:513a3316187fc981857c2f000bf614ee87e17ee123a4be2e7a00a6d5f7bf38e9 \
  --output-dir results/water-orders

net production project run \
  --profile /absolute/path/1792/tools/net/water-round.profile.json \
  --profile-sha256 sha256:513a3316187fc981857c2f000bf614ee87e17ee123a4be2e7a00a6d5f7bf38e9 \
  --plan results/water-orders/plan.json --source results/water-orders/source.json \
  --source-root /absolute/path/1792/game \
  --godot /absolute/path/godot --godot-sha256 sha256:EXTRACTED_BINARY_DIGEST \
  --max-operations 18 --output-dir results/water-run

net production project feedback results/water-run --output results/water-feedback.json
```

`python -m ciw.game_project_workflow` is equivalent. `grid` only declares work;
it never starts Godot. The grid covers first deposit 29/30/31, second deposit
60/61/62 and save/load checkpoint 15/45. Each number is a capture interval, not a
physics tick or historical time. The correct baseline is 30/61/15.

The authored expectation is eight accepted and ten rejected schedules. Actual
qualification must establish this, not the existence of this guide. Rejected
candidates are expected diagnostic data: exit 2 means a valid incomplete campaign,
not a crashed tool. Exit 0 means declared/completed work and exit 1 is malformed or
refused input. Each execution and output file requires a new destination.

## Agent-facing work orders

Agents submit inert JSON, for example `orders.json`:

```json
[
  {
    "job_id": "water-schedule",
    "attempts": [
      {"first_deposit_tick": 29, "second_deposit_tick": 61, "checkpoint_tick": 15},
      {"first_deposit_tick": 30, "second_deposit_tick": 61, "checkpoint_tick": 15}
    ],
    "depends_on": []
  },
  {
    "job_id": "regression",
    "attempts": [
      {"first_deposit_tick": 30, "second_deposit_tick": 61, "checkpoint_tick": 15}
    ],
    "depends_on": ["water-schedule"]
  }
]
```

Use `net production project declare --orders orders.json` with the same operator
profile, digest and new output directory as `grid`. It compiles these assignments
into the ORIGINAL production plan; models, routes, check policies and source files
are not agent-editable fields. Preflight validates every possible attempt before
execution or destination creation. Existing 64-job/three-attempt limits and the
operator's worst-case operation budget remain in force.

The first failed candidate stays retained; a predeclared passing correction can
unblock regression. Unknown/missing observations hold and do not consume a repair.
Runtime failure retains an original refused execution without inventing a result.
A new model-generated correction beyond the declared alternatives requires a new
work order, not a silent modification of old history.

Feedback exposes job counts, every attempt, original execution/result IDs,
parameter assignments, failed rule IDs/status/reasons, and refused game actions
with original game ticks, checkpoint mismatch fields, and runtime refusal reasons.
It first freezes bounded exact bytes, then runs the
original provider-free production inspector and recomputes acceptance. It never
launches Godot. A coding/MCP host can use this JSON as the next agent's input;
this increment does not claim an actual paid/model-driven agent ran.

## Fixed acceptance and evidence scope

Nine checks cover transfer conservation, currency invariance, original state
validity, zero refused actions, final storage/carried/remaining quantities,
checkpoint roundtrip and original tick advancement. Six water units are authored
gameplay quantities, not litres or physical metrology. Passing means these checks
passed, not that the scene is historically accurate, fun, performant or released.
Ordinary checks have no formal verification occurrence and perform no admission.

Profile and binary hashes detect byte drift, not authenticity or full library
closure. `source_revision` is contextual; explicit file digests bind the actual
slice. Unlisted files are not copied. The snapshot does not later follow edits to
the live game checkout. New source edits require a newly reviewed profile/binding.
Bounded trusted native operations keep the original 30-second process deadline;
this is not an overall token or money budget. Provider-free feedback caps one
record at 8 MiB and the frozen campaign at 64 MiB.

## Qualification

Run `python -m pytest -q tests/test_game_project.py` for labelled non-native
boundary tests. `.github/workflows/game-project-production.yml` additionally tests
the existing production/game/control suites and the installed wheel on Linux and
Windows, then loads the pinned title checkout in actual Godot 4.5.1 on Linux.

`scripts/check_game_project.py` retains the 18-case grid, failed/corrected candidate
and dependent regression, missing-evidence hold, and an explicitly substituted
failing native harness. The unchanged comparator compares the corrected PRIMARY
candidate to the matching baseline. Actual source archives, runtime identity,
checks and original records are retained. Dedicated passing results do not waive
unrelated private-provider or repository-wide integration gates.

## Native finding and game-owned correction

The first actual 18-case batch retained four accepted and fourteen rejected cases,
not the predicted eight/ten. All late checkpoints exposed one floating-point step
of JSON reload drift in `state.game_time.hour` at original tick 274. Added native
diagnostics retained `before=7.00126851851851839` and
`after=7.0012685185185175`. The fixed whole-state equality check was not relaxed.

The title-owned correction in companion commit `70fcc477` recomputes its derived
day/hour on restore from the already authoritative integer tick, using the same
mapping as `advance`, AFTER unchanged input validation. It does not advance time,
change the clock tolerance or alter water rules. Twenty-eight added native title
assertions cover four checkpoint ticks, next-step agreement, source non-mutation
and atomic refusal of inconsistent clocks. The source pin above includes this
correction; the earlier failing captures remain separate evidence. The complete
cross-repository campaign must pass before claiming the corrected slice qualified.
