# NET production work orders

A bounded production controller over the existing `CapabilityRegistry`,
`OperationRegistry`, `Session`, experiment DAG and graph runner. This is an
additive work-order layer, not another game engine, evidence database, numerical
backend, or agent framework. Existing provider and game-state ownership remains
unchanged.

## Run the first working loop

From this feature branch:

```sh
python -m pip install -e '.[dev]'
net production demo --output-dir results/production-001
net production inspect results/production-001 --profile builtin
```

`python -m ciw.production_workflow` is the equivalent module entry point.
Use a new destination for every execution. The demo performs real built-in
statistics operations on the existing synthetic oscillator recording:

```text
128-sample candidate -> failed 64-sample contract
                    -> declared one-second correction -> accepted
                    -> dependent analysis -> accepted
```

There are three original CIW execution/result pairs, not three developers or
three native engine launches. The rejected attempt stays retained. This is an
executable production-control example, not a claim of scientific discovery.

To separate declaration from execution:

```sh
net production example --profile builtin --output-dir results/order-001
net production run results/order-001/plan.json \
  --source results/order-001/source.json --profile builtin \
  --max-operations 8 --output-dir results/execution-001
```

`example` does not execute. `inspect` validates original records and recomputes
acceptance from retained outputs without dispatching operations. Exit status is
0 for a completed campaign, 2 for a valid incomplete campaign, and 1 for a
malformed/refused command.

## What an agent can hand to this controller

A `ciw.production-plan.v1` declares a project, exact source-evidence identity,
and jobs. Each job supplies an existing NET experiment, a logical worker lane,
required capabilities, dependencies, immutable acceptance checks, and optionally
up to two predeclared parameter-repair variants. Every graph sink must be checked.
Use `ciw.production.plan(...)` to construct and seal a Python-authored plan.

The host, not the JSON, supplies `Worker` allowlists over the original capability
registry and explicitly bound `Gate` check implementations. Declared capabilities
never become executable registrations by themselves. The two installed CLI
profiles are deliberately closed; custom providers are explicitly supplied to
`run_production(...)` through the Python API.

`Gate` callbacks receive detached retained results. They are trusted host code,
not a sandbox and not code selected/imported by a plan. Keep generative workers
separate from the operator-controlled acceptance implementation and policy.
Hashes provide content integrity, not producer authentication or historical truth.
The worker lane is not a vendor account, process pool, or autonomous coding agent.

## Scheduling, repair and acceptance

The original experiment validator supplies stable dependency order. Each job
executes its ordinary experiment through the original `run_graph` and Session.
Independent jobs can continue after another job fails; a dependent job cannot
start until every prerequisite is accepted. Internal graph port and runtime
checks remain unchanged.

| Result | Production behavior |
| --- | --- |
| Complete graph and all checks PASS | Accept this candidate; allow dependent work |
| Definite FAIL | Try only the next declared parameter variant; retain every attempt |
| INDETERMINATE without a definite FAIL | Hold; do not spend retries on absent evidence |
| Runtime refusal, graph error or rejected output contract | Retain original outcome; no automatic retry |
| Failed/held/refused prerequisite | Block downstream job without dispatch |
| Gate failure, interruption or storage error | Stop; preserve available original Session history; no successful campaign marker |

Acceptance policy, model, operation routes and graph edges cannot change between
repair variants. Parameter changes are retained explicitly. This is bounded
selection among declared corrections, **not an LLM diagnosing and rewriting
source code autonomously**. A new code revision, model, graph or acceptance policy
requires a new explicit plan and provider binding.

Limits: 64 jobs, 3 attempts per job, 16 logical worker lanes, and 256 operation
nodes across all possible attempts. The operator can impose a smaller budget
(default 128). Existing per-experiment 64-node and Session capacity limits remain.
Provider-specific process deadlines still apply; this is not a universal wall-time,
token-spend, or currency-budget enforcement layer.

V1 executes sequentially under one controller. There is no distributed queue,
lease service, speculative parallel Session mutation, unattended daemon, automatic
Git merge, or resume-after-crash claim. Re-running is explicit fresh execution into
a new destination, not exactly-once recovery.

## Retained files and authority

```text
production-001/
  plan.json
  bindings.json
  attempt-0001-graph.json    # unchanged existing graph-run contract
  attempt-0001-checks.json   # ordinary evidence-backed acceptance
  attempt-0001.json          # content-bound work-order receipt
  ...
  session/                  # original recording/execution/result records
    workspace.json
  production.json           # final campaign summary and exact references
```

The Session remains the authority for execution and result records. Receipts
reference its occurrences; they do not create competing scientific execution
identities. `production_id` names an orchestration occurrence only.

Inspection verifies file references, graph plans, worker/operation bindings,
unique original execution/result occurrences, source identity, acceptance policies,
budgets, repair order, blocking, and full history accounting. It reopens a frozen
workspace in scratch storage and recomputes every check using the explicitly
selected installed gate profile. A changed check implementation refuses inspection
rather than silently changing the meaning of old reports.

All ordinary acceptance records retain `verification_id: null`; state admission
and publication are `not_performed`. Accepted means the declared checks passed,
not a release approval, cryptographic proof, physical validation, authentic source,
historical fact, or good gameplay.

After interruption, retained per-operation files and `session/workspace.json`
remain available to the existing readers. Without a valid `production.json`, the
campaign is not complete. No continuation is attempted implicitly.

## Native Godot attachment

The existing optional courier adapter is the first native workload, not a new
runtime. Godot owns its state, logical clock and event generation. The original
`game_trace.audit` checks its authored rules; NET does not reimplement gameplay.

```sh
net production example --profile godot-courier --output-dir results/game-order
net production run results/game-order/plan.json \
  --source results/game-order/source.json --profile godot-courier \
  --godot /absolute/path/to/godot \
  --godot-sha256 sha256:REPLACE_WITH_EXACT_EXECUTABLE_DIGEST \
  --adapter-root /absolute/path/to/NET/tools/game-development/godot \
  --max-operations 8 --output-dir results/game-production
net production inspect results/game-production --profile godot-courier
```

The executable digest is for the extracted binary, not its distribution ZIP.
No saved plan selects an executable, module, shell command, credentials or network
endpoint. Capture/schema and runtime guards reuse the original game adapter.

The focused native qualification runs baseline, early-knowledge correction,
duplicate-reward correction, missing evidence, exhausted repair, and a real failing
Godot process. It also uses the original comparator to compare corrected captures
with baseline, and forbids subprocess creation during retained inspection:

```sh
python scripts/check_production.py --godot /absolute/path/to/godot \
  --adapter-root tools/game-development/godot \
  --output-dir results/production-native
```

`.github/workflows/net-production.yml` runs source and installed-wheel contracts
on Linux/Windows, then the explicitly pinned native Godot campaign on Linux.
The script's generated qualification record and actual workflow outcome, not the
existence of this guide, establish whether a particular revision passed.

## 1792 boundary and next integration

This is a reusable production controller for 1792 and later titles. The native
fixture is explicitly synthetic: **1792, Gujranwala, Hero of the Two Worlds and
Geronimo are not attached by this increment.** No terrain/building generator,
Blender factory, renderer, native LLM worker, console build or finished game is
claimed. The existing PR #57 game trace and PR #51 controller work remain the base;
the independent agent/MCP and GIS branches are not silently merged or replaced.

The next attachment is one game-owned 1792 scenario or asset operation with
actual output and acceptance evidence, followed by an explicitly provisioned
coding-agent worker that returns bounded candidate changes. Keep the childhood
campaign priority and all game-owned saves, narrative, sacred-site and world-state
rules in the title repository. Do not start a second generic historical engine
inside NET.
