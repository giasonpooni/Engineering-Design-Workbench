# Operate a simulation through NET's existing agent interface

This integration joins the stateful Session/provider work from PR #59 to the
existing local MCP interface from PR #60. It adds four tools, not another agent
server, numerical solver, execution ledger or authoritative world-state store.
The original eleven tools remain available under their original operator grants.

## Start with the reference provider

```sh
python -m pip install -e '.[dev]'
net agent demo-config --stateful --output-dir agent-simulation
net agent serve --profile agent-simulation/profile.json \
  --simulation-profile agent-simulation/simulation-profile.json
```

`serve` speaks MCP over stdin/stdout; it is not an interactive text prompt. Register
that command as a local stdio server in the coding host. Use an absolute Python
path and absolute profile paths in host configuration:

```json
{
  "mcpServers": {
    "net": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "ciw.agent_mcp", "serve",
        "--profile", "/absolute/path/agent-simulation/profile.json",
        "--simulation-profile", "/absolute/path/agent-simulation/simulation-profile.json"]
    }
  }
}
```

The host's configuration-file format may differ. No external model account,
application registration or paid API is configured by these commands. Launching
without `--simulation-profile` preserves the original eleven-tool interface.
Launching with it offers fifteen tools. Output directories remain create-only;
use a new operator profile/output directory for each new server process.

The installed transport retains its existing MCP versions and sequential framing.
Tool discovery is not an execution grant. This integration does not add HTTP,
background tasks, autonomous polling or arbitrary shell access.

## The four additional tools

| Tool | Purpose |
| --- | --- |
| `net_sim_create(model, attempt)` | Attach a fresh provider from an operator-bound model preset. Returns an opaque instance handle; does not invent a simulation execution for attachment. |
| `net_sim_inspect(instance)` | Return last captured metadata and the owner/control/state revision fence. No provider call or snapshot bytes. |
| `net_sim_command(instance, attempt, expected, action, preset)` | Dispatch one approved lifecycle action or preset to the existing SimulationControl. |
| `net_sim_branch(checkpoint, attempt)` | Restore a host-captured opaque checkpoint into a fresh owner from the same factory. |

Call `net_capabilities` first. Its extra `stateful` section lists frozen policies,
model names, active handles, budgets and captured instance metadata. The operator
chooses permissible actions and exact step, observer and intervention presets.
Agent calls cannot change tolerances, pick a filesystem path, inject executable
code, change an observer definition or submit arbitrary intervention parameters.

For a command, copy the `expected` object from the most recently inspected view.
It includes the owner, controller revision and provider state revision. Inspect
again after each successful command; observations and checkpoints also advance
the controller revision. Step/observe/intervene require a preset name. Other
lifecycle actions require `preset: null`. Unsupported or stale commands refuse;
expected revisions are not silently replaced with the current values.

An example task for a coding agent:

> Discover the granted stateful tools. Create motion, observe the initially
> unavailable delayed position, start, advance one tick, pause and checkpoint.
> Branch that checkpoint, apply the granted push to the child, and advance both
> instances to tick three. Observe position in both, compare candidate against
> baseline using strict, and stop both. Keep returned execution references.
> Do not change policies or treat an expected differing branch as a failed run.

The original `net_replay` remains analysis-graph replay, not native checkpoint
replay. Existing native campaign/capture APIs are unchanged and are not
newly exposed as agent tools in this increment.

The new observation results expose ordinary retained observation-stream artifact
handles. The **existing** `net_observe`, `net_compare` and `net_qualify` tools consume
them. Per-quantity streams preserve original sample/model/entity/frame/unit and
uncertainty fields, with the actual enclosing observation execution attached by
the existing projector. Empty evidence stays INDETERMINATE. Checkpoint handles do
not make native bytes available through `net_inspect`.

## Retention, retries and failures

Every attempted stateful action that reaches dispatch gets a frozen intent before
any factory/provider call. The original Session retains numerical execution and
result records; per-attempt workspace copies and response receipts link back to
those original occurrences. The journal is a request/publication aid, not another
numerical result authority.

Repeat the **same attempt and complete request**, including its original revision
fence, after an ambiguous transport failure. The process returns the original
response without invoking a provider again. A changed request cannot reuse the
same attempt. Fresh branches use new handles/owners/executions; replay is not
implied by retrying. Request IDs belong to MCP and must be new for each transport
call, while the stateful attempt stays the same for a retry.

A stale/lifecycle refusal is retained without touching a healthy provider. Native
failure is handled by the existing controller's quarantine semantics. A wrapper
exception or uncertain workspace/response publication blocks further new
stateful actions; the consumed attempt is never silently retried. A successful
physical mutation is not assumed to roll back because a disk write failed.

Orderly EOF closes the extension: it attempts original retained stop commands,
then native resource disposal, and saves `stateful/workspace.json` plus a shutdown
report. Cleanup failures remain explicit. Abrupt process termination, machine
crashes, same-user filesystem races and termination of a stuck arbitrary trusted
factory are not solved by this process-local boundary. Native providers keep their
existing timeouts and cleanup behavior. No durable exactly-once guarantee across
server restarts is claimed.

The default bounds are 64 stateful attempts and eight instance attachments; the
operator can choose up to 128 attempts and 16 instances. Instances are not recycled.
Cleanup stops are extra original Session occurrences and are not prevented by the
agent's exhausted attempt budget. MCP connections retain their existing bounds.

## Native Godot startup profile

The optional native route uses the existing Godot point provider without modifying
its worker, equations, binary pin checks or checkpoints. The **operator**, before
launch, selects provider `godot-point` and configuration containing `executable`
and `sha256`. The profile must use its supported 1/64-second step and existing
`projectile.queue-impulse.v1` intervention shape. It is not an arbitrary scene or
savegame loader. The validation script below creates that exact bounded profile.

```sh
python scripts/check_simulation_agent.py \
  --godot /absolute/path/to/godot \
  --godot-sha256 sha256:EXECUTABLE_HASH \
  --output-dir results/agent-native-check
```

That script requires the **test-only** official `mcp==1.26.0` SDK. It is not a new
runtime dependency. Without native arguments, it exercises ReferenceMotion.
`--wire` explicitly selects a stdlib diagnostic client when the SDK is unavailable;
its report does not claim official-client qualification.

The resulting original workspace can be opened by the unchanged timeline:

```sh
net simulation timeline build \
  --workspace results/agent-native-check/profiles/agent-output/stateful/workspace.json \
  --output-dir results/agent-native-timeline
```

## Source integration and qualification

`STATEFUL_AGENT_REUSE.json` records exact source hashes from PR #60's pinned
009144f6 commit, including the computational-source prerequisites inherited from
PR #54. Existing source readers, AgentHost, tool validators and their tests are
reused, not rewritten. Only the existing MCP adapter receives optional catalog and
startup hooks; default behavior is covered by its original tests. The `net` facade
keeps all existing commands and adds the previously separate object and agent
routes. No default branch or parent feature branch needs to be modified.

New tests cover real reference stepping and comparison, retries, stale revisions,
opaque checkpoints, failures after mutation, uncertain storage, bounds, frozen
policies, concurrency, metadata-only reads, lifecycle cleanup and protocol use.
CI also runs original agent/source/control tests, installed-package repeats and
an independent official SDK client against a real server subprocess. The Linux
native stage uses the unchanged checksum-pinned Godot 4.5.2 executable. Observed
results belong to their exact source commit; a workflow definition is not a pass.

All ordinary results remain `not_verified`, with no verification occurrence,
physical validation, baseline acceptance, state admission, merge or publish tool.

Protocol references (not claims of external host installation):
- https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools

## Optional stateful reproduction

The separate [stateful replay grant](STATEFUL_AGENT_REPLAY.md) adds
`net_sim_replay` to reproduce a retained accepted command suffix on a fresh
owner. Enable it with `demo-config --stateful --stateful-replay` or an explicit
operator `replay` policy. Existing eleven/fifteen-tool profiles remain unchanged.


## Optional intervention campaigns

[Agent campaign grants](STATEFUL_AGENT_CAMPAIGNS.md) add `net_sim_campaign`
for named operator templates on the existing campaign runner. Enable with
`--stateful --stateful-campaign`; add `--stateful-replay` to expose both optional
tools. Default profiles keep their prior catalogs and no campaign permission.

## Optional image observations

The [capture grant](STATEFUL_AGENT_CAPTURE.md) adds `net_sim_capture` for selected
retained XYZ observations and bounded inline PNG delivery. It reuses the original
image operation and Session; all prior profiles remain unchanged without the grant.
