# Game-development workbench: first executable trace slice

This increment extends the existing `ciw` Session and NET control primitives.
It is **not** a new game engine, state store, ontology or a second observation
bus. The first native adapter exercises a small **synthetic Godot courier**
scenario; it does not attach to 1792, Hero of the Two Worlds or Geronimo yet.

## What now exists

- A bounded project/scenario declaration, logical clock, stable entity IDs,
  selected scalar channels, explicit perspective and authored check plan.
- Event capture with capture-local IDs, actor/targets and causal references.
- Raw trace text/digest retained inside ordinary CIW operation results.
- Projection to unchanged `ciw.observation.v1` / `ciw.observation-stream.v1`,
  using the existing `ObservationBus`, units, frames and capture execution ID.
- Authored-rule checks for a bounded scalar, final scalar, pre-event value and
  selected event sequence. Numerical checks reuse `control_checks.verify`.
- Baseline/candidate comparison using `control_checks.compare`, plus explicit
  event-structure comparison and the first divergent logical tick.
- Fresh same-runtime reproduction and new candidate executions; original
  workspaces and prior failures remain retained.
- Provider-free reopening/inspection and selected observation export.
- A bounded, optional Godot recorder and an engine-owned courier reference.

The capture, audit and comparison have **separate operation/execution/result
identities**: `game.trace-capture.v1`, `game.trace-audit.v1`,
`game.trace-compare.v1`. They use the original Session and payload registry.
An authored-rule PASS is not a verification occurrence or historical truth.

## Study of the existing code

The implementation builds above PR #51's actual head
`4b955e4c85a3fc6798da57ec01fe23fe890fd4ae`, which composes the earlier controls and
unchanged PR #45 projectile files. Its PR prose still referenced an earlier
head during inspection; the actual Git ref was used rather than that prose.

| Existing code | Reused here |
| --- | --- |
| `control_contracts.py` | Bounded inert JSON, exact source hashes, create-only output, observation records |
| `control_plane.py` | Existing bounded `ObservationBus` |
| `control_checks.py` | Typed numerical comparison and bounded assertions, including missingness semantics |
| `operations/registry.py`, `operations/schemas.py` | Explicit trusted operations and saved-payload validation |
| `session.py` | Original session, accepted attempt/refusal/result retention, save/reopen |
| `interactive_simulation.py` | Existing bounded process runner and binary hashing |

PR #49's installed-adapter work informed the explicit `--adapter-root` boundary.
PR #54's source inspector and #55/#56's spatial consumers remain separate
increments. No private providers, specialist algorithms or sibling game code
were copied. Existing source files, pins, scientific methods and licences are
unchanged by this additive slice.

## Run it

Use the feature branch containing this document, not an older `main` checkout.
Python 3.11+ is supported by the parent package. Install the existing dependency
set; there is no new mandatory library:

```sh
python -m pip install -e '.[dev]'
python -m ciw.game_workflow catalog
python -m ciw.game_workflow example --output results/courier-scenario.json
```

For the native example, use an explicitly selected Godot executable and the
adapter directory. The engine qualification target is Godot 4.5.2 Standard;
this is a pinned profile, not a recommendation to upgrade an existing game.
Replace `sha256:HEX` with the SHA-256 of your exact executable, independently
selected before the run. The native CI also checks the downloaded release ZIP
against the pre-existing projectile gate's fixed digest.

```sh
python -m ciw.game_workflow run \
  --scenario results/courier-scenario.json \
  --godot /absolute/path/to/godot \
  --godot-sha256 sha256:HEX \
  --adapter-root /absolute/path/to/NET/tools/game-development/godot \
  --output-dir results/courier-baseline

python -m ciw.game_workflow inspect results/courier-baseline/workspace.json
```

`inspect` lists the exact capture execution ID. Use it explicitly; do not
substitute an audit execution, result digest or scenario ID:

```sh
python -m ciw.game_workflow reproduce results/courier-baseline/workspace.json \
  --execution-id CAPTURE_EXECUTION_ID \
  --godot /absolute/path/to/godot --godot-sha256 sha256:HEX \
  --adapter-root /absolute/path/to/NET/tools/game-development/godot \
  --output-dir results/courier-reproduced

python -m ciw.game_workflow observations results/courier-baseline/workspace.json \
  --execution-id CAPTURE_EXECUTION_ID --output results/courier-observations.json
```

The exported observations also work with the existing `net inspect` and
`net compare` commands. `python -m ciw.game_workflow` is this slice's actual
entry point; it does not replace the existing `ciw` or `net` facade.
Installed wheels use the same explicit adapter-root argument, without assuming
that the checkout lives beside `site-packages`.

## What the courier demonstrates

The fixture samples logical ticks 0..8 at 0.25 seconds per logical tick. At tick
1 an order is issued; at tick 3 it is received and acknowledged; at tick 6 the
mission completes and its report returns. Knowledge, mission stage, one manifest
and one reward are separate state fields. These are authored test rules and
synthetic people, not a historical reconstruction or a real-time performance
claim. The engine owns the actor nodes, state and logical tick loop.

Add `candidate` with the same arguments as `reproduce`, and choose one explicit
`--diagnostic-fault`:

| Diagnostic | Expected check outcome |
| --- | --- |
| `early-knowledge` | Rule failure and first baseline divergence at tick 1 |
| `duplicate-reward` | Rule failure and first baseline divergence at tick 7 |
| `drop-sample` | INDETERMINATE; the absent sample is not invented or zero-filled |
| `none` | Corrected candidate agrees with the selected baseline |

Faults are test instrumentation, not features of any game. A faulty but
structurally valid trace remains a successful capture followed by a failed
check. Malformed data or a failed process instead produces an execution refusal
without a successful capture result. CLI exits: 0 pass, 1 refusal, 2 failed
check/comparison, 3 indeterminate. Older failed results are not erased by a
later correction. Reproducing a faulty run preserves that run's fault.

## Ownership and trust boundaries

NET does not own player input, rendering, physics, gameplay decisions, inventory
or save state. The recorder only copies selected observations into bounded
buffers; it has no pause/restore/control interface and makes no runtime network
calls. There is no live attachment, arbitrary executable loader or hidden
provider launch when opening saved data. Existing process bounds are not an OS
sandbox or a guarantee about descendants on every platform.

`perspective` names the declared observer scope; it is not a probability or a
source-authentication claim. Game-world facts and actor knowledge have distinct
channels. The recorder does not give NPCs access to NET's complete trace.
Event causality is producer-declared and structurally checked; it is not an
independent discovery of causal truth. A causal reference must resolve to an
earlier retained event. A dropped causal parent cannot silently become a valid
reference to a missing event.

Trace limits: 1..16 scalar channels, 1..255 logical ticks, at most 1,024 selected
samples and 1,024 events. The inherited control record bounds also limit each
retained raw JSON text string to 65,536 characters; the native reader uses a
stricter 65,536-byte cap. Capture completeness is a producer declaration checked
against required sample slots and loss counters, not proof that the producer
recorded everything that happened. Null remains missing. It never passes a
complete-capture claim. These bounds are for small regression cases, not a
production telemetry backend.

Reproduction compares the original selected executable hash, captured adapter
bytes and platform identity. It is a **new attempt**, not playback or checkpoint
continuation. Build hashes do not attest all shared libraries, source provenance
or cross-platform determinism. Reopening checks retained data and derived
consistency without running a game; hashes establish consistency, not signer
authentication. Rule/tolerance policies remain explicit and are not balance or
artistic judgements.

## Shared development coverage

| Development category | First available surface | Next game-owned adapter work |
| --- | --- | --- |
| Character, traversal, combat, mounts, maritime | Selected scalar channels and event traces | Actual transforms, input traces, contacts and domain metrics |
| NPC AI and knowledge | Actor-scoped knowledge and causal event labels | Decision alternatives, observations and independently owned AI state |
| Relationships, factions, politics | Typed scalar/event slots only | Game-specific rules and richer declared state; no generic social equation imposed |
| Inventory, logistics and economy | Count/range/final checks; duplicate-reward diagnostic | Item ownership and resource-flow invariants |
| Missions, chronology and command | Event sequence, logical clock, pre-event knowledge checks | Actual game objectives, delayed orders and timeline policies |
| Narrative, dialogue, cinematics, audio and UI | Can emit declared events; no editor/runtime implementation | Context-specific content, presentation and playtesting |
| World generation, streaming, maps, assets | Existing separate authoring/spatial increments stay intact | Connect actual asset/build identities and regional scenarios |
| Persistence and reproduction | Retained investigation; fresh whole-scenario execution | Game-owned checkpoints and explicit restoration capability |
| Performance and regression | Bounded capture and retained checks | Measured frame/AI/memory budgets; no FPS claim from this fixture |
| Historical evidence and rights | Source class remains explicit | Game-owned claims, locators, chronology and asset permissions |

This is a common **development interface**, not an implementation of all these
game systems. Attach one real mission from one game next; only extract a shared
runtime module once a second game demonstrates that it actually shares the
same semantics. Python owns this workbench, Godot owns this fixture, existing
Rust/Bevy and C++/Julia providers remain optional independent implementations.

## Validation

```sh
python -m pytest -q tests/test_game_trace.py tests/test_game_session.py \
  tests/test_control_plane.py tests/test_interactive_contract.py tests/test_interactive_session.py
```

The Python fixtures are explicitly labelled doubles. The separate native gate
builds/installs the wheel, runs Godot on Linux, reproduces a capture, injects and
corrects both behavioural faults, refuses a failed native process and reopens
with subprocess creation forbidden. It retains prior failures and exact runtime
identities. Windows contract qualification is separate from Linux native engine
qualification. CI artifacts retain the JUnit reports, wheel, native records and
exact source archive. A workflow definition alone is not evidence of a pass;
consult the exact run and PR report.
