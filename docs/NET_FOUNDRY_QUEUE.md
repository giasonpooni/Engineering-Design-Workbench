# Foundry production queue and repeatable packet batches

Use `net foundry pipeline queue` to find the dependency frontier for a milestone.
Use `batch` to prepare up to 16 explicit assignments in one invocation, using the
existing packet format, acceptance text and candidate checker.

This is an additive operator frontend to the current Foundry pipeline. Execution
continues through its existing native recipes and original Session/production
controller. No scheduler, worker pool or alternative game state owner is added.

## Start with the Gujranwala slice

With an installed build containing this change, from the NET checkout:

```sh
net foundry pipeline init --project-id 1792 --source-root ../1792/game --output-dir ../production/1792
net foundry pipeline queue ../production/1792/project.json --source-root ../1792/game --target slice-journey --target art-target --target audio-target
```

Targets select the complete prerequisite closure, in existing dependency order.
They do not waive missing prerequisites. Without targets, the queue covers all
installed tasks. Each row contains the next action, immediate and root blockers,
installed recipe, acceptance requirements and inspected evidence identity.

Supply real retained evidence explicitly, for example `--evidence vision=PATH`.
A new baseline with no supplied evidence will show `vision` as a review frontier;
this means evidence is missing from this assessment, not that prior creative
decisions or implementation never happened. Do not fabricate review receipts to
make the queue green. Human-led work, candidate authoring and runnable recipes
remain different dispositions. A recipe being ready does not attest that its
engine is provisioned or its native inputs are valid; run preflight still applies.

## Prepare a repeated work handoff

The supplied example creates a read-only packet for the installed water recipe:

```sh
net foundry pipeline batch ../production/1792/project.json --source-root ../1792/game --spec examples/foundry-water-batch.json --output-dir ../production/water-batch-001
```

The specification has schema `ciw.foundry-batch-spec.v1` and an `assignments` list.
Every assignment explicitly supplies `task_id`, `assignee`, `writable`, `context`
and `max_changed_bytes`. Paths are exact relative paths, not wildcards. Use a
separate manifest for the actual ready tasks and approved write scope. Assignee
strings are operator declarations, not authenticated agent or human identities.

All requested packets are preflighted before output is created. Unknown,
duplicate, blocked, stale or already satisfied tasks refuse; native qualification
packets remain read-only. Source drift, protected writes and the existing context
and byte limits also refuse. Existing destinations are never overwritten.

Output contains the input specification, recomputed queue, one packet and handoff
guide per task, and `batch.json` written last. Treat an interrupted directory
without `batch.json` as incomplete. The manifest retains exact packet identities
for the existing checker. It reports write/write and write/read conflicts without
claiming a concurrent execution lease. Rebase and requalify at integration.

```sh
net foundry pipeline check ../production/1792/project.json --packet ../production/water-batch-001/water-domain/packet.json --packet-id RETAINED_PACKET_DIGEST --candidate-root ../candidate-game
```

Retain the packet digest independently when issuing work. Scope checking is not
technical, historical, artistic or gameplay acceptance. Batch issuance does not
run the engine, approve a parent task, merge changes or authorize release.

## Inspect returned candidates and package the review

Retain the `record_digest` from `batch.json` independently at issuance. Then inspect
all returned candidates through the same scope checker with one command:

```sh
net foundry pipeline batch-check ../production/1792/project.json --source-root ../1792/game --batch-dir ../production/water-batch-001 --batch-id RETAINED_BATCH_DIGEST --candidate water-domain=../candidate-game --output-dir ../production/water-review-001
```

Repeat `--candidate TASK=DIRECTORY` for each returned task, and provide current
`--evidence TASK=DIRECTORY` bindings. Omitted candidates are retained as missing.
Unknown or duplicate task bindings refuse. The original batch ID anchors the
manifest, packets, specification and issuance queue; a substituted or re-sealed
batch cannot silently replace that identity. Linked packet files refuse.

The command independently recomputes each supplied candidate's scope check and
the current prerequisite frontier. A candidate may pass its old packet scope but
still be held because the source changed, prerequisites are no longer satisfied,
or the task was already completed. Missing, unreadable and out-of-scope candidates
remain visible alongside passing candidates. No returned worker status is trusted.

`REVIEW.md` summarizes the batch; `review.json` retains full scope-check receipts,
current evidence identities, source drift and integration conflicts. The JSON
completion record is written last. Outputs are create-only and must be outside
the source, batch and all candidate roots. Candidate assets are not copied.

Exit codes: **0** means all candidates are ready for quality review, **2** means
the retained report is incomplete, and **1** means the inspection itself refused.
Ready for quality review does not mean accepted or safe to merge. Native tests,
historical/artistic judgment and integration remain separate required steps.
This is an inspection snapshot: keep input directories quiescent, and recheck the
candidate inventory identity before later review or integration.

## Production adoption order

1. Use the slice frontier and packet handoffs during the Gujranwala production loop.
2. Measure repeated setup, inspection, rework and accepted integrated output.
3. Add workers for observed repetition: asset export/import, mission regression,
   preview capture and review packaging. Each needs its own executable binding
   and independent acceptance checks before the queue can call it runnable.
4. Preserve composition, historically significant exceptions, narrative and art
   direction through explicit review. Expand beyond the slice through the
   existing signoff path.

The existing 60-task catalog is unchanged. Repeated occurrences of the same task
use separate batches; this increment does not introduce per-asset unit scheduling.
The existing 1,024-file / 32 MiB packet inventory limit remains. For larger asset
trees use explicit bounded workcells; this is not a full binary asset depot.

Directories and evidence must remain quiescent during issuance. Final rechecks
detect ordinary source/readiness changes, but are not a filesystem transaction or
OS sandbox. A batch is a retained snapshot; reassess evidence before execution.

## Verification

`python -m pytest -q tests/test_foundry_queue.py tests/test_foundry_pipeline.py`

The tests exercise the real pipeline and packet checker, prerequisite closure,
evidence-based frontier advancement, tampered review refusal, source drift,
protected paths, full-batch refusal, retained identities, output containment,
conflicts and CLI behavior. They do not qualify Blender, Godot, production art,
human playtests, or cost/time savings.
