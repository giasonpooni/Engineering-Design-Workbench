# Intervention campaigns: one checkpoint, independent alternatives

Run a declared set of interventions through the existing `SimulationControl`,
compare their returned observations, and inspect the results without restarting
any provider. This is an extension of [stateful simulation](STATEFUL_SIMULATION.md),
not another scheduler, solver, Session or world-state store.

## Run the complete example

```sh
python -m pip install -e '.[dev]'
net simulation campaign-demo --output-dir results/campaign-001
net simulation campaign-check results/campaign-001/campaign.json
```

The synthetic Python reference provider actually executes four independent
branches restored from the same paused tick-two checkpoint. Baseline has no new
intervention; three alternatives queue velocity changes of -2, +2 and +4 at tick
three. Each advances four one-second steps, observes position, pauses and stops.
The provider owns the motion and randomness. NET does not implement either.

The report records **39 new command executions**, plus five source preparation
executions in the existing workspace: **44 execution/result pairs** in total.
All children stop, and the parent remains unchanged. Each child has a fresh
instance and owner; each command has its original CIW execution/result identity.

The three maximum differences from baseline are **8, 8 and 16 m** over the
returned seven-sample observation batches. All three zero-tolerance equivalence
checks report `FAIL`, as intended. This does not mean the alternatives are worse
or that execution failed. A completed campaign can contain `PASS`, `FAIL` and
`INDETERMINATE` comparisons; there is no aggregate scientific-success verdict.

This is simulated integer motion with a toy PRNG, not measured physical accuracy.
The demo does not run Godot, Bevy, SCR, Julia or C++.

## Open the offline inspector

Compute the exact report-file digest, then select it explicitly when exporting:

```sh
python -c "import hashlib,pathlib; print('sha256:'+hashlib.sha256(pathlib.Path('results/campaign-001/campaign.json').read_bytes()).hexdigest())"
net simulation campaign-view results/campaign-001/campaign.json --expected-sha256 sha256:REPLACE_WITH_PRINTED_HEX --output results/campaign-001/inspector.html
```

Open `inspector.html` in a browser. The single file contains the comparison table,
per-variant plots, keyboard-accessible exact-value tables, acquisition and
availability times, and original observation execution/result references. Every
plot has independent labelled axes; points are samples, not interpolated paths.
Missing values are not turned into zeros. Vector values stay in the table rather
than being silently flattened. Declared covariance stays in the source report;
this view does not calculate confidence bands or assume independence.

The page embeds **no snapshots, world configuration, intervention payloads,
unselected channels, scripts, remote fonts or external dependencies**. Provider
and controller objects are not instantiated by inspection. Labels are escaped
and the page has a restrictive Content Security Policy. This is an observation
projection for a trusted operator, not an authentication/access-control system.
The full `campaign.json` and workspace do contain privileged checkpoint state.

The command hashes and parses the same single bounded file read. A supplied
checksum binds bytes, not publisher identity. The HTML's displayed report digest
is a content reference, not a signature. Recheck the source JSON and regenerate
the view rather than treating a modified HTML page as evidence.

## Run another declared plan

The generated `plan.json` explicitly binds the selected checkpoint result digest.
Run that plan again on a fresh set of reference owners:

```sh
net simulation campaign-reference results/campaign-001/workspace.json --plan results/campaign-001/plan.json --output-dir results/campaign-002
```

This executes new commands; it is not just reopening the previous report. The
new workspace preserves the previous records and appends fresh occurrences.
Exact original provider runtime/model/configuration bindings must match. The
command selects only the built-in reference provider; files cannot request an
import path, executable or different engine.

To change alternatives, use the Python plan constructor rather than editing a
sealed record in place:

```python
from pathlib import Path
from ciw.control_contracts import save_new
from ciw.simulation_campaign import plan, read_campaign

original = read_campaign(Path("results/campaign-001/campaign.json"))
selected = original["plan"]
new_plan = plan(
    original["checkpoint"],
    campaign_id="smaller-impulse",
    variants=[
        {"variant_id": "baseline", "interventions": []},
        {"variant_id": "plus-one", "interventions": [{
            "actor_id": "experimenter",
            "operation": "motion.queue-impulse.v1",
            "target": "body-1",
            "parameters": {"at_tick": 3, "delta_v": 1},
        }]},
    ],
    steps=4, dt=1, observer=selected["observer"],
    quantity="position", atol=0, rtol=0,
)
save_new(Path("results/plus-one-plan.json"), new_plan)
```

Supply the new plan to `campaign-reference`. All output directories/files are
create-only. Inspection and report checks do not need a live provider.

## Attach another provider through the existing Python boundary

```python
from ciw.simulation_campaign import run_campaign

# control is an existing SimulationControl(session), checkpoint_result is an
# explicitly selected paused checkpoint, and make_fresh_provider is trusted code.
report = run_campaign(control, checkpoint_result, declared_plan, make_fresh_provider)
```

The factory is an explicitly supplied callable, never a provider loader inferred
from data. Each provider implements the existing `SimulationProvider` interface.
No native adapter is added by this campaign increment. Active native-study and
game-trace branches retain their own implementations and qualification gates.

The campaign plan names 2–16 variants; the first must be an unchanged baseline.
Each alternative declares up to 16 interventions, applied while paused before
the common resume/step/observe/pause/stop suffix. A campaign takes 1–32 steps per
variant. The observer selects exactly one comparison quantity. Inputs are frozen
before calling any provider. Opaque snapshots retain the previous 32 KiB bound;
serialized plans/reports/readers are bounded to 8 MiB.

The report is a derived bundle of original results and comparisons, not another
ledger. The existing Session remains the execution history. No parallelism,
automatic parameter-product expansion, optimizer, Monte Carlo statistics,
multirate scheduler, generic parameter-changing restore or ranking is added.

## Checks and failure semantics

`validate_campaign` revalidates every original simulation result, checkpoint
binding, expected action/arguments, contiguous branch history, fresh owner and
occurrence identity, and common control runtime. It then calls the existing
`control_checks.compare` again and requires exact agreement with every retained
comparison and the summary. Resealing a changed outcome is not enough to pass.

The candidate is the comparator's left series; baseline is the right reference:
`abs(candidate - baseline) <= atol + rtol * abs(baseline)`. Units, model/entity,
frame, clock, sampling grid, missingness and shapes remain subject to the original
typed comparator. No time alignment, unit conversion or missing-value repair is
introduced. Comparisons use the provider's returned batch, not an assertion that
it includes the entire simulation history.

A factory, attachment, command, publication or validation failure stops the
campaign immediately. No completed report is emitted. The existing Session
retains all completed commands and recorded refusals; the CLI saves its workspace
also on failure. Generic Python callers must save their Session in `finally`.
Resource cleanup of an already attached failed owner is best-effort; it is not
rollback, successful scientific stop, transactional crash recovery, or proof that
an external process exited. A factory remains responsible for cleaning up objects
that fail before attachment. Parent ownership is never silently transferred.

Numerical checks remain `not_verified`, with no verification occurrence or state
admission. Content checks do not authenticate maliciously fabricated inputs.
Same-binding reproduction is not universal determinism or physical validation.

## Qualification

`tests/test_simulation_campaign.py` contains 40 new tests, including actual
reference execution, original Session reopening, existing-comparator direction,
fresh occurrences, source isolation, missing observations, refusal retention,
invalid plans, resealed corruption, create-only files and script-free projection.
The original 62 stateful cases remain. Their oversized snapshot parameter now has
compact explicit test IDs: the former 32 KiB ID overflowed Windows'
`PYTEST_CURRENT_TEST` environment variable before the assertion executed. Test
inputs, the 32 KiB limit and all assertions are unchanged.

The existing stateful qualification workflow runs 202 source tests (62 original,
40 campaign and 100 original control), repeats the 102 stateful/campaign cases
from an installed wheel outside the checkout, runs both demonstrations and a
fresh plan execution, and checks actual HTML file navigation in Linux Chromium.
The browser harness records 11 checks and three viewport captures. A configured
workflow is not evidence of success; observed runs and artifact audits are
reported in PR #59. Wider repository/native/physical qualification stays separate.
