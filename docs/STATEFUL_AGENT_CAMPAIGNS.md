# Agent-run intervention campaigns

Run a fixed, operator-declared set of alternatives from one retained checkpoint
through the **existing campaign runner**. The agent selects a template, not a new
simulation program. Each variant receives a fresh provider owner, runs through the
original CIW Session, returns typed observations, and stops. NET does not rank the
alternatives or replace their scientific comparison policy.

## Enable the optional tool

```sh
python -m pip install -e '.[dev]'
net agent demo-config --stateful --stateful-campaign --output-dir agent-campaign
net agent serve --profile agent-campaign/profile.json --simulation-profile agent-campaign/simulation-profile.json
```

The generated profile uses the existing synthetic ReferenceMotion provider.
Add `--stateful-replay` when generating the profile to enable both extensions.
The original analysis profile still has eleven tools, ordinary stateful has
fifteen, either optional extension alone has sixteen, and both have seventeen.
An absent campaign grant gives no campaign capability.

Serve is local MCP stdio. Configure the coding host with absolute Python/profile
paths and a fresh output directory per server process. No external model account,
remote service, paid API, renderer or hardware device is configured or invoked.

## Declare the template as an operator

The optional `campaigns` field in the simulation profile contains:

```json
{
  "max_executions": 44,
  "templates": {
    "impulses": {
      "model": "motion",
      "steps": 2,
      "step": "tick",
      "observer": "position",
      "quantity": "position",
      "comparison": "strict",
      "variants": [
        {"variant_id": "baseline", "interventions": []},
        {"variant_id": "replica", "interventions": []},
        {"variant_id": "push", "interventions": ["push"]}
      ]
    }
  }
}
```

Model, step, observer and intervention names must refer to the existing operator
bindings. The comparison name refers to an immutable base AgentHost comparison
policy. The observer must select exactly the compared quantity. Templates resolve
and freeze those values at startup, before the stateful output directory or any
native provider is allocated. Later edits to the profile do not change a running
host. Quantity names keep the existing observation contract's grammar.

The first variant is always an unchanged baseline. Repeated intervention presets
are explicit repeated interventions, not deduplicated requests. No Cartesian
product, optimizer, parallel scheduler or automatic parameter search is introduced.
The same trusted `godot-point` startup route works with its existing 1/64-second
step, position_x channel, native intervention preset and executable SHA256 pin.
The campaign wrapper does not add a different Godot worker or scene loader.

## Call `net_sim_campaign`

Create a source, start it, step to the desired boundary, pause and checkpoint using
the existing tools. Inspect the source and pass its exact owner/control/state fence:

```json
{
  "checkpoint": "c-RETURNED_CHECKPOINT_HANDLE",
  "instance": "s-RETURNED_SOURCE_HANDLE",
  "expected": {
    "owner_id": "INSPECTED_OWNER",
    "revision": 5,
    "state_revision": 2
  },
  "campaign": "impulses",
  "attempt": "compare-impulses-1"
}
```

Handles and numbers are placeholders: copy actual returned values. The source must
currently be paused or stopped with a uniquely retained boundary. The selected
checkpoint must have been captured while paused, belong to that source instance,
and remain identical to its original Session result. A campaign runs from that
checkpoint, which may be older than the inspected current boundary; it does not
silently replace the checkpoint with the latest source state.

The agent supplies no variant list, step count, model parameters, tolerance, path,
command list, observer policy or executable instructions. Source/owner capacity,
fixed presets and the full execution reservation are checked before a provider
factory is called. Inspection uses captured metadata, not a call into the source
provider. The parent is neither stepped nor restored.

## Execution, results and numerical meaning

For every variant, the unchanged runner performs:

```text
restore → declared interventions → resume → N steps → observe → pause → stop
```

The template above costs **22 executions**: seven each for baseline/replica, eight
for the intervention variant. Restoration and stop count; source preparation is
not charged again. A second explicit attempt costs another 22, while an identical
retry costs zero. Separate replay and campaign reservation budgets are reported
under `net_capabilities`; neither is mislabelled as an all-tools global budget.
Original host attempt/instance limits still apply. Stopped handles are not recycled.

A completed response returns the original campaign summary, comparison outcomes,
report and plan references, fresh instance handles, exact command/result IDs, and
per-variant observation-stream handles. `net_observe`, `net_compare` and
`net_qualify` consume those streams through their original implementations.
The baseline is the comparator's right-hand reference; existing units, frames,
clocks, sampling and missing-data checks remain in force.

`status: completed` does not imply all comparisons PASS. The example gives a
matching replica and an intentionally different alternative. A FAIL means the
fixed equivalence condition was not met, not that the variant is worse. Empty
observation batches remain INDETERMINATE. No ranking, physical validation,
verification occurrence, baseline acceptance or state admission is created.

Full checkpoint bytes, resolved plans and full campaign reports remain privileged
operator evidence. They are not inserted into agent-inspectable artifact storage.
Returned observation streams retain their actual variant observation occurrence.

## Retry, partial failures and bounds

The original attempt gate retains request intent before work. `campaign-selection.json`
and the original `plan.json` are written before any fresh owner is created. Retry
lookup precedes source-fence and budget checks: the same complete request/attempt
returns its original receipt, even after source stop or orderly host closure.
Changing a request cannot reuse that attempt. A new attempt explicitly asks for
another campaign with new occurrences.

Preflight refusals consume a reached agent attempt but no simulation execution or
campaign reservation. They do not quarantine a healthy parent. After admission,
the complete cost is reserved once; factory, provider or publication failures do
not refund it. A partial campaign preserves original completed commands and
refusals, tracks attached owners for cleanup, and emits no completed campaign.
A full report can exist when later observation/workspace/response publication
fails; that is not a successful agent attempt. No mutation is implicitly retried
or claimed rolled back. Uncertain failures block new stateful actions.

Orderly EOF retains the original stop/discard/close behaviour. Unexpected process
termination is not transactional recovery. Limits are 1–8 templates, 2–8 explicit
variants per template, 1–32 common steps, up to sixteen intervention presets per
variant, and 1–512 reserved campaign executions per process. Existing instance,
attempt, snapshot, artifact and response limits remain. Cleanup keeps its original
separate semantics. This is not an operating-system sandbox or a distributed lease.

## Recheck the original evidence

After orderly shutdown:

```sh
net simulation campaign-check agent-campaign/agent-output/stateful/attempt-compare-impulses-1/campaign.json
net simulation timeline build --workspace agent-campaign/agent-output/stateful/workspace.json --report agent-campaign/agent-output/stateful/attempt-compare-impulses-1/campaign.json --output-dir results/campaign-timeline
```

During execution, use the attempt's retained workspace instead of the final
shutdown workspace. The original campaign/timeline readers validate evidence
without a provider. Hashes bind bytes, not publisher authenticity.

`tests/test_simulation_agent_campaign.py` covers reference execution, frozen grants,
source/occurrence isolation, missing observations, limits, retry, partial failure,
publication and default-profile compatibility. The existing bridge workflow adds
these cases without dropping previous tests or SDK scenarios. Its independent
client `scripts/check_simulation_agent_campaign.py` runs the reference route and,
on Linux, the same pinned native provider. `--wire` is separately labelled local
diagnostic evidence, not official SDK or native qualification. Passing a scripted
client test does not establish language-model effectiveness or game compatibility.
