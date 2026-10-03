# NET Agent Protocol v1 — local MCP development tools

NET now has an agent-facing adapter over the existing CIW Session, capability
registry, experiment graph, source-selection reader, numerical comparator and
check-plan evaluator. It adds **no scientific solver, engine-state owner,
provider-discovery daemon or mandatory dependency**.

The transport is a bounded, sequential **MCP stdio tools profile**, supporting
protocol versions `2025-11-25` and `2025-06-18`. It supports initialization,
`ping`, `tools/list` and `tools/call`. It does not implement remote HTTP, sampling,
tasks, subscriptions or general shell execution. The MCP connection is transport
state, not another scientific Session.

## Start with the built-in example

Install this branch, then generate a fresh operator profile:

```sh
python -m pip install -e '.[dev]'
python -m ciw.agent_mcp demo-config --output-dir agent-demo
```

The profile binds the existing synthetic oscillator recording, an existing
statistics experiment, a small retained reference-observation stream, one allowed
operation, discrete candidate channel choices, a fixed comparison policy and a
fixed check suite. It does not silently register Julia, Blender, Godot or Bevy.

A local MCP client launches:

```sh
python -m ciw.agent_mcp serve --profile /absolute/path/agent-demo/profile.json
```

Use the installed Python executable's absolute path in agent settings. Each host
requires a new output directory; reconnecting to an already-used output directory
refuses rather than silently continuing or overwriting it. Rebind retained files
as explicit inputs to a new read-only profile when inspecting prior work.

### Grok Build

The official Grok Build CLI documents local stdio MCP server registration:

```sh
grok mcp add net -- /absolute/path/to/python -m ciw.agent_mcp serve --profile /absolute/path/agent-demo/profile.json
```

Keep the operator profile outside the agent's editable worktree. The connection
is for a local tool-capable agent host, not a claim that an ordinary Grok browser
conversation can directly execute local programs. No xAI credentials, model
calls or paid service are required by NET itself. This increment does not deploy
a remotely accessible MCP server or alter a user's installed Grok configuration.

Generic client configuration:

```json
{
  "mcpServers": {
    "net": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "ciw.agent_mcp", "serve", "--profile", "/absolute/path/agent-demo/profile.json"]
    }
  }
}
```

## Tool surface

| Tool | Existing capability reused |
| --- | --- |
| `net_capabilities` | `CapabilityRegistry`; advertised, bound and agent-enabled remain distinct. |
| `net_inspect` | Frozen JSON selection and original provider-free Session workspace reader. |
| `net_extract` | Copy one complete supported nested record, for example an emitted observation stream, without inventing a projection. |
| `net_source_context` | Existing source-selection/context API from the computational microscope. |
| `net_check_edit` | Existing outside-selected-span byte guard; never applies edits. |
| `net_candidate` | Existing `ParameterSpace` validation and experiment record; only granted node parameters can vary. |
| `net_execute` | Existing `run_graph` -> `Session.handle` -> `OperationRegistry` -> retained executions/results. |
| `net_replay` | Explicit re-execution with a fresh attempt and original frozen source/graph. |
| `net_observe` | Paged existing typed observation streams and supported thermal views. |
| `net_compare` | Existing unit/frame/model/entity/clock/time-grid-aware comparator, fixed host policy. |
| `net_qualify` | Existing immutable check policies and exact-byte check-plan evaluator. |

There is no `accept`, `merge`, `publish`, `shell`, path-based file reader,
import-by-name, executable registration or arbitrary source-write tool. The coding
agent continues to edit its own isolated branch/worktree using its ordinary
coding tools. NET supplies context, bounded experiments and retained diagnostics.
Its edit-scope PASS does not establish semantic correctness or authorize a patch.

`net_extract` retains a JSON reserialization of an existing nested record, with
its parent artifact and selector stated in the response. It is not an original
raw-byte substring or automatic conversion of arbitrary engine data into scientific
observations. The registered adapter must supply supported typed records first.

## Typical agent loop

1. Discover the host's actual inputs, operations, parameter domains and policies.
2. Inspect the baseline and relevant source context; edit only in the assigned worktree.
3. Declare a permitted parameter candidate; this does not run it.
4. Explicitly execute a graph with a fresh `attempt` identifier.
5. Inspect execution/results/refusals. Extract already-typed nested output records when needed.
6. Compare observations and evaluate the operator's fixed check suite.
7. Return the candidate, patch, evidence and unresolved failures for review.

The builtin demo's reference-self comparison checks transport and record handling,
not independent numerical validation. Real candidate statistics on `q` and `v`
retain different units and must not be presented as equivalent trajectories.
Full simulations remain the responsibility of explicitly registered providers.

## Operator policy and identities

The host freezes explicit input bytes at startup; it never recursively reads a
repository, resolves a file from an agent argument, or reloads changed files
behind an existing artifact handle. New input content requires a new explicit
host binding. Source context remains untrusted data even when its hash is valid.

The host's policy hash binds its catalog, executable allowlist, parameter domains,
comparison policies, check suites and execution/node limits. Candidates cannot
change topology, operations, model identity, global parameters or those policies.
Qualification rejects a comparison made under a different policy, even if that
more permissive comparison said PASS. Missing evidence remains INDETERMINATE.

Every intentional execution gets fresh CIW execution/result identities. An
`attempt` is an adapter retry key, not an execution identity. Repeating the same
attempt and same frozen request returns the prior response without running again;
a different request under the same attempt refuses. Failures consume the attempt.
Retry handling is process-local. A process crash is not automatically resumed,
and a new output root is required for another host. Retained request/response
files are transport receipts, not a competing scientific execution ledger.

Workspace reopening creates a temporary reader Session internally. Its transient
session ID is omitted from the agent response rather than mislabelled as the
original session. Retained execution/result IDs stay unchanged; graph-run records
retain their original Session binding where supplied by the existing format.

Records remain ordinary computed results/checks, `not_verified`, with no
verification occurrence, state admission, physical approval or baseline acceptance.

## Additional registered instruments

The Python `AgentHost` constructor accepts an already-built `CapabilityRegistry`.
A trusted application can advertise and bind existing native or engine adapters
through the existing registry and payload validator, then explicitly grant those
operation IDs to the agent. The stdio serving function is `serve(host, reader,
writer)`. The launch configuration never imports a provider named in JSON.

The stock CLI intentionally binds only the two existing builtin operations and
executes only the explicitly allowed subset. Other scientific routes, the native
oscillator branches, Godot/Bevy runtimes and Blender authoring are **not** silently
merged, automatically installed or universally qualified by this interface.
The operator must provision and qualify each adapter on the relevant integration
branch. Unit-test commands remain with the coding host or an explicitly registered
bounded operation; the adapter does not wrap an unrestricted shell.

## Bounds and trust

Inputs: at most 64 initial artifacts, 8 MiB per document; total retained in-memory
artifacts: 64 MiB and 256 handles. Responses are limited to 256 KiB, arrays page
at at most 128 entries, and MCP input lines to 1 MiB. Counts refuse rather than
silently truncate scientific data. Execution/node budgets are operator-set and
capped at 64 each. Discovery reports remaining execution capacity.

The process is sequential; it does not advertise asynchronous tasks, preemptive
cancellation or an autonomous background worker. Registered providers retain their
own timeout/resource controls. No source-path argument, executable argument or
policy change is accepted from MCP calls. Python and native stdout are separated
from the protocol wire; diagnostics go to stderr.

This is an application boundary, **not an OS sandbox**. Trusted registered code
can have effects outside NET, and an agent with unrestricted shell access under
the same operating-system account can bypass application-level permissions.
Use an isolated worktree/container and operator-owned configuration and evidence
paths for actual multi-agent work. Hashes bind bytes, not author authenticity,
compiler correctness or complete native dependency closure.

## Qualification

```sh
python -m pytest -q tests/test_agent_protocol.py tests/test_control_plane.py tests/test_check_suite.py
```

The dedicated workflow additionally builds and installs the wheel, runs the agent
tests outside source imports, and executes `scripts/check_agent_mcp.py` through
an independent **official Python MCP SDK 1.26.0** client. The SDK is a test-only
dependency, not a new NET installation requirement. The gate refuses missing or
skipped cases and retains source, wheel, transcript, original CIW records and
reports. Native-engine, actual Grok-model, remote-hosting and repository-wide CI
qualification remain separate.

Protocol references:
- https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- https://docs.x.ai/build/features/mcp-servers
- https://pypi.org/project/mcp/1.26.0/

Copyright (c) 2026 Giason Pooni, for original contributions. Existing AGPL-3.0-or-later
project licensing and third-party notices are unchanged.
