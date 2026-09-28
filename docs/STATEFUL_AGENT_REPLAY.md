# Agent-requested stateful replay

Complete the existing **checkpoint → branch → observe → compare → reproduce**
loop without a second replay engine or agent server. `net_sim_replay` dispatches
through the unchanged `simulation_replay.replay` implementation and CIW Session.
It is an optional sixteenth MCP tool, not a replacement for `net_replay`.

## Enable explicitly

```sh
python -m pip install -e '.[dev]'
net agent demo-config --stateful --stateful-replay --output-dir agent-replay
net agent serve --profile agent-replay/profile.json --simulation-profile agent-replay/simulation-profile.json
```

Register the serve command with the coding host using absolute paths. It speaks
MCP stdio, not a text prompt, and requires a fresh operator output directory.
The generated provider is synthetic ReferenceMotion. The existing `godot-point`
startup route also works with this grant when the operator provisions its original
executable and SHA256 binding. No account, network listener or model API is added.

The optional simulation-profile field is:

```json
"replay": {"max_commands": 32, "max_executions": 128}
```

Omit `replay` to retain the original fifteen-tool stateful profile. Without a
simulation profile the original eleven tools remain. Limits are operator-fixed:
1–32 accepted source commands per request and 2–128 reserved replay executions
per server process. **A restoration counts as an execution**, so five source
commands reserve six executions. The original attempt and instance caps also apply.
Cleanup retains its existing separate budget/retention semantics.

## Select the experiment, not executable instructions

Capture a checkpoint while the source is paused. Continue that source using the
existing approved presets, return it to paused or stopped status, then inspect it.
Pass its opaque checkpoint/instance handles and the exact inspected fence:

```json
{
  "checkpoint": "c-REPLACE_WITH_RETURNED_HANDLE",
  "instance": "s-REPLACE_WITH_RETURNED_HANDLE",
  "expected": {
    "owner_id": "REPLACE_WITH_INSPECTED_OWNER",
    "revision": 10,
    "state_revision": 4
  },
  "attempt": "reproduce-baseline-1"
}
```

The example numbers are placeholders, not reusable state. Do not refresh the
fence silently. NET selects every **accepted contiguous command** after that
checkpoint through the inspected source boundary, ordered by control revision.
A checkpoint from another instance, incomplete source history, an empty suffix,
a running/uncertain source, an ungranted action/preset or insufficient capacity
refuses before any provider factory runs. Original stale/refused attempts stay in
history but are not replayed as accepted world transitions.

The agent cannot submit a command list, raw checkpoint, native path, tolerance,
provider import or altered policy. Every selected step, observation and intervention
must still match the fixed operator grants. The existing replay implementation
restores into a fresh provider owner and checks captured state/observations for the
whole selected suffix. The original source is neither restored nor stepped.

## Read the result correctly

`status: completed` means the requested replay and response retention completed.
`outcome.status` can be **PASS or FAIL**. A valid divergent replay is completed
execution with a failed equality check, not an MCP transport error. The outcome
retains the existing first-divergence index and bounded claim scope. Equality for
this executed suffix is not universal determinism, physical validation or signer
attestation, and the verification identity remains null.

The response includes the fresh instance/fence, original source execution IDs,
new restore/suffix execution IDs, result IDs and a content reference to the full
operator-side replay report. There is no fabricated aggregate execution identity.
Only the **last replayed observation batch**, when present, is projected into the
existing agent artifact store. Its stream handles feed `net_observe`, `net_compare`
and `net_qualify`; they retain the replay observation execution, not an analysis ID.
Earlier observation batches and checkpoint bytes stay in original operator records.
A replay of two empty observation batches can agree while their numerical comparison
remains **INDETERMINATE** because no measurement evidence exists.

Original `net_replay` still reruns an analysis graph. `net_sim_replay` restores and
reexecutes a retained simulation suffix. Campaign/capture APIs stay available through
their existing Python/CLI routes; this increment does not grant them through MCP.

## Retry, refusal and failure

An identical full request with the **same attempt** returns its original receipt,
even after the source advances/stops or this host closes. It performs no new
factory call, execution or budget reservation. A new attempt explicitly requests
new work; reusing an attempt with different data refuses.

Preflight refusals consume a reached agent attempt, retain request/response/workspace
files and disclose `dispatch_performed: false`. They are not fabricated simulation
execution records, and they do not quarantine a healthy parent. Once a source
selection is admitted, NET reserves the restore plus complete suffix before
factory invocation. Factory/provider/storage failures do not refund that reservation.

A partial replay retains its completed prefix and original refusal records in
Session. Attached children remain tracked for cleanup. Unexpected execution or
publication failure blocks new stateful actions; no rollback or restart recovery
is inferred. The full report may exist when later workspace/response publication
fails: it is not a completed agent attempt without a completed response. Retry
returns the original failure rather than repeating a possibly executed mutation.

## Inspect original evidence

Each accepted attempt records `request.json` and `replay-selection.json` before
native launch. A complete replay additionally retains `replay.json` with the
original full report, alongside the existing attempt workspace/response. For example:

```sh
net simulation check-replay agent-replay/agent-output/stateful/attempt-reproduce-baseline-1/replay.json
net simulation timeline build --workspace agent-replay/agent-output/stateful/workspace.json --report agent-replay/agent-output/stateful/attempt-reproduce-baseline-1/replay.json --output-dir results/replay-timeline
```

The final `stateful/workspace.json` is written at host shutdown. While the server
is active, select the corresponding attempt's `workspace.json` instead. Inspection
and timeline construction are provider-free. Full reports are privileged operator
evidence; they are not inserted into the agent artifact store.

## Qualification

The dedicated replay tests cover actual reference continuation, RNG/queued state,
source isolation, deliberate divergence, failed restore/step, retry after source
changes, permissions, bounds, source selection before factory and storage failures.
The original bridge, agent, source-selection, control and campaign tests remain.
The existing bridge workflow is extended to repeat installed tests and run the
unchanged SDK clients plus `scripts/check_simulation_agent_replay.py`. The latter
exercises both ReferenceMotion and, on Linux, the same provisioned Godot point provider.
`--wire` is a separately labelled local stdlib diagnostic, not official SDK evidence.
Observed results and exact source revisions belong in the PR, not assumptions from
this workflow description. No LLM effectiveness or arbitrary game-world claim is made.
