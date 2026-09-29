# Recurring reconstruction production for 1792

This is an implemented workload on the existing NET production controller, not
another scheduler, game engine, evidence store or agent framework. It attaches a
real game-owned file and checker rather than the synthetic courier fixture.
The first production family is **bounded reconstruction-layout variants**.

```text
operator-approved source snapshot + feature/field contract
    -> external agent's data proposal
    -> NET capability / experiment / original Session execution
    -> independently bound, game-owned reconstruction checker
    -> accept / retain rejection / select declared repair / block dependents
    -> export the exact accepted candidate for integration review
```

The controller and its base PR #65 remain development work. Consult the PR and
actual workflow results for qualification of an exact revision; this document
alone is not a passing test or a release announcement.

## What is attached

The profile reads `game/data/gujranwala_reconstruction.v1.json` from an explicit
1792 checkout. The game continues to own the schema, actual scene construction,
state, clock, saves, sources and creative direction. NET imports **no game source
into its distribution**. It binds the separately provisioned checker at
`tools/check_reconstruction.py` by an audited SHA256, before executing that code.

Reference game revision: `5b19fda41a50516bc595c32a5455c07016b90212`.
Checker digest: `sha256:180a3c867a0dbfd3c72a9fc0adf0711e487bae1a59cd923cb99ce2681e507568`.
A different checker requires review and a new profile revision, not an agent
changing a gate until its work passes. The current pure game checker checks
source references, exclusions, geometry and protected-route clearance. It does
not establish historical truth, visual quality or complete gameplay correctness.

Only operator-listed feature fields are editable: `position`, `size`, and `bays`
for arcades. Sources, claims, exclusions, chronology, world bounds, routes,
collision flags, feature identities, scene code, saves and licences are not
agent-editable through this profile. New features and historical assertions need
a separate reviewed contract; do not disguise them as parameter edits.

## Prepare a recurring job

Install this feature branch using the existing project installation procedure.
The existing `ciw` CLI and other `net production` profiles remain unchanged.

```sh
net production reconstruction prepare \
  --game-root /path/to/1792 \
  --task-id gujranwala-market-001 \
  --allow market_awning.size \
  --allow grain_stack.position \
  --output-dir results/market-order-001
```

The new directory contains `packet.json`, `AGENT_TASK.md`, and
`proposal.template.json`. The template is a no-op **shape example**, not a claim
that creative work has been completed. The packet retains exact baseline bytes,
source and contract digests, the allowlist, edit budget and authority limits.
Preparing work starts neither a model nor the game.

Give the packet to an existing agent, or bind a host-managed Python worker with
`request_proposal(packet, worker)`. That callback receives detached data and must
return the strict proposal envelope. Its execution permissions, authentication,
cost and timeout enforcement belong to its host. A Python callback is not an OS
sandbox. The default file handoff does not invoke any provider API or use stored
credentials; qualification inputs are explicitly declared, not claimed LLM work.

An agent can return the full proposal format, or write an edits file:

```json
{
  "edits": [
    {"feature_id": "market_awning", "field": "size", "value": [4.5, 2.8, 3]}
  ]
}
```

Bind this response to the original packet without granting it check authority:

```sh
net production reconstruction reply \
  --packet results/market-order-001/packet.json \
  --edits market-edits.json --worker-label environment-worker-01 \
  --output market-proposal.json
```

The worker label is attribution, **not authenticated producer identity**. Content
digests detect mismatches; they are not signatures. Keep the approved packet
outside the worker's write authority. An operator explicitly selecting a modified
packet authorizes a different job; a hash alone does not prove operator consent.

## Run, inspect, export

```sh
net production reconstruction run \
  --packet results/market-order-001/packet.json \
  --proposal market-proposal.json \
  --game-root /path/to/1792 \
  --max-operations 8 --output-dir results/market-run-001

net production reconstruction inspect results/market-run-001 \
  --game-root /path/to/1792

net production reconstruction export results/market-run-001 \
  --game-root /path/to/1792 --job candidate \
  --output-dir results/market-accepted-001
```

The source checkout is read-only to this workflow. A changed baseline refuses
execution before creating the campaign directory. A stale proposal, forbidden
edit, changed checker or over-budget batch also refuses rather than dispatching
part of the work. Existing destinations are never overwritten.

Inspection reopens the original Session, validates proposal-to-result bindings
and recomputes the original acceptance checks. It starts no agent, shell or game.
It still requires an explicitly provisioned checkout containing the trusted
checker; it does not recover executable code from saved data. Its baseline comes
from retained evidence, not a silently substituted current game manifest.

Export follows the selected job's last accepted **attempt receipt**, not the last
Session result. Its manifest references the original execution and result IDs,
source and candidate digests. Export is an additional artifact view, not another
execution or evidence ledger. It does not edit or merge the game checkout.

## Batches and bounded repair

Repeat `--proposal` up to three times to declare an initial candidate and its
ordered alternatives. All alternatives are checked for valid permissions before
execution. Only a definite failed acceptance gate selects the next alternative.
This reuses PR #65's parameter-repair semantics; it is not autonomous source-code
rewriting or an LLM inventing new criteria after failure.

For recurring lots, `--batch batch.json` accepts this shape; each `proposals`
entry is a complete data proposal, not a file path, executable or import:

```text
{
  "schema": "ciw.reconstruction-batch.v1",
  "jobs": [
    {"job_id": "market-variant", "proposals": [PROPOSAL_OBJECT], "depends_on": []},
    {"job_id": "next-variant", "proposals": [PROPOSAL_OBJECT], "depends_on": ["market-variant"]}
  ]
}
```

This is schematic notation, not directly executable JSON. The existing NET DAG
supplies ordering and dependency blocking. Independent jobs can still succeed
when another is rejected. **Each candidate derives from the same pinned
baseline**: a dependency orders acceptance, it does not automatically compose the
upstream candidate's edits into the downstream one. Combining variants needs a
new explicit packet against an operator-approved combined baseline.

Limits are 64 jobs, three attempts per job, 16 editable features and 16 edits per
proposal, with the inherited maximum of 256 operation nodes. The CLI defaults to
32 reserved operations and limits input files to 64 KiB. This is sequential local
execution, not a distributed queue, lease service or crash-resume system. The
operation budget is not a model-token or currency budget.

## Build and audit together

`tests/test_production_reconstruction.py` tests strict data boundaries, immutable
fields, source/validator drift, rejection and repair, dependency blocking, offline
inspection, exact primary-candidate export and CLI dispatch. Unit fixtures are
labelled test doubles. They do not stand in for the real game attachment.

`scripts/check_reconstruction_production.py --game-root /path/to/1792
--output-dir NEW_DIRECTORY` exercises the real source and checker: an obstructing
well proposal is rejected; a declared correction with a changed market awning is
accepted; descendants unblock; an exhausted job blocks only its dependents.
All failed and accepted original Session occurrences remain retained.

With `--godot /absolute/executable --godot-sha256 sha256:DIGEST`, qualification
copies the game to a fresh temporary staging directory, proves that only the
exported manifest differs, and runs the game's original `tools/run_checks.py`.
`--render` additionally requires a provisioned `xvfb-run` and exercises the game's
existing four-capture reconstruction render test. The operator checkout remains
unchanged. This staging runner executes explicitly provisioned trusted game code;
it is a qualification script, not a sandbox for arbitrary downloaded projects.

The extended `net-production.yml` keeps the original Linux/Windows, installed
wheel and courier checks. It adds a pinned 1792 checkout and the game's existing
Godot 4.5.1 distribution digest; it does not replace the courier's 4.5.2 pin.
Artifacts retain exact candidates, source-file digests, failed attempts, checks,
logs and, when rendering passes, screenshots. Passing headless/render tests is
not human playtesting or art-direction approval.

## Authority, rights and next attachments

Evidence, operation, execution, result, ordinary acceptance and export identities
remain distinct. `verification_id` stays null. State admission, game integration
and publication remain `not_performed`. No release, merge, permission expansion,
licence change, paid provider call or live-game AI dependency is introduced.
NET's existing licence applies to its original tooling; external 1792 source and
candidate game materials retain their existing Cartesian Graphics rights.

This is one working production family, not a claim to have industrialized every
asset class. Other families—Blender kit generation, asset import/LOD checks,
mission test batches, animation retargeting and bounded code-agent proposals—must
attach through the same CapabilityRegistry, experiment, Session and independent
Gate interfaces. They should not create competing controllers or silently inherit
permissions from this data-only profile. Human visual/narrative review and release
approval stay explicit as production throughput grows.
