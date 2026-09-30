# Visual System Board V1

A first executable visual notation over the existing System Board, not a second
scientific state store, a new scheduler, or a replacement runtime.

## Brief → implementation

The supplied interface brief asks for a multi-resolution executable system board:
visual nodes address real typed objects; collapse hides structure without deleting
it; mouse, textual notation and programs share the graph; every visual action is
inspectable. V1 implements a bounded part of that brief.

| Brief capability | V1 implementation / boundary |
| --- | --- |
| Nested system/subsystem navigation | Existing Board groups; collapse/expand, node selection, pan/zoom and layout drag |
| Collapse preserves underlying identity | Exact Board digest, node IDs and edge IDs preserved; hidden edges remain accounted for |
| Different projections of the same system | All, dependency, scientific and authority relationship filters |
| Units, frames, uncertainty, scale, validity, provenance | Inspect actual retained node/socket declarations; missing values remain missing |
| Same visual/programmatic operation | One JSON parameter request consumed by the browser API or `net board edit`; both call the same Python function |
| Exposed parameter editing | Existing Parameter Program creates one immutable candidate; existing Board/semantic compiler validates it |
| Needle overlay | Full underlying dependency closure, then ordinary Session/Needle execution and retained changed/unchanged/reused observations |
| Inspectable notation | Node contracts, view specifications, edit requests and execution receipts displayed/exportable |
| Context Twin | Not bound; inspector exposes declared node metadata only, not stable/inherited/working context inference |
| Groups become actual containers | Not implemented. Visual grouping must not fabricate a container contract |
| Drag wires / insert adapters | Edges are read-only in this increment. Existing Board typing remains authoritative |
| Julia composition round trip | Not implemented. Julia can later emit the same request contract without a parallel graph |
| Optimizers, sensitivities, 3D/molecular/factory navigation | Not implemented or claimed by the oscillator specimen |

**Visual expansion is not scientific evidence expansion.** Expanding a collapsed
Board group is a display operation. It does not perform PR #101's EXPAND recovery,
verify a projection, or authorize intervention through a lossy representation.
The existing representation/realization branches are not modified or replaced.

## Commands

Create the synthetic oscillator Board and standalone HTML:

```sh
net board demo --output-dir board-demo
```

Open `board-demo/board.html` in a browser. It has no network connection or provider
execution. It can inspect the graph and export an uncompiled edit request.

For a locally running instrument:

```sh
net board serve board-demo/board.json --source board-demo/source.json --output-dir board-session --allow-run
```

Open the loopback URL printed by the command. Its fragment contains a fresh local
capability token; keep it private. Click **Run baseline**, select **Signal
statistics**, change `channel` from `q` to `v`, click **Compile candidate**, then
**Run candidate Needle**. A candidate is not automatically accepted.

Without `--allow-run`, the local server offers inspection/proposals only. V1 live
execution additionally requires the existing analytic oscillator source/model,
at most 16 operations and 4096 samples, and only the already-existing statistics
and periodogram operations. There is no general provider-loading or shell endpoint.
Other valid Boards may be inspected; compilation/execution can still refuse.

Render an existing Board without starting a server:

```sh
net board view board.json --output board.html
```

Compile the exact request exported by the browser using the CLI:

```sh
net board edit board.json board-edit.json --output preview.json
```

The preview contains the existing Parameter Program, immutable candidate Board,
ordinary Board compilation, dependency closure and unchanged operation IDs.
No provider executes during this command.

## Records and identities

`ciw.board-view.v1` retains a specification containing the exact Board revision,
selected node ID, collapsed group IDs, relationship mode, layout positions and
viewport. No scientific graph node is replaced or deleted.

`ciw.board-scene.v1` is an in-memory derived projection. Each displayed item
retains its exact member node IDs. Each original edge is either displayed,
hidden within a collapsed group, or filtered by view mode. There is no invented
execution edge between collapsed groups.

`ciw.board-parameter-edit.v1` is a request, not an authorization or result:

```json
{
  "schema": "ciw.board-parameter-edit.v1",
  "base_board_ref": "sha256:<exact-board-digest>",
  "node_id": "statistics",
  "parameter": "channel",
  "replacement": "v"
}
```

The placeholder must be replaced by the real Board digest. This object has no
engine, filesystem, arbitrary source code, or authority selector.

`ciw.board-edit-preview.v1` is reconstructed using the original Parameter Program
and Board compiler. Non-exposed/FIXED/out-of-domain values, stale Board revisions,
unknown coordinates and re-sealed fake preview metadata refuse.

`ciw.board-visual-run.v1` is a reference receipt linking the original Board,
candidate Board, preview, source evidence, completed baseline, ordinary Needle
plan, ordinary Needle run and ordinary delta. It does not modify those schemas
or issue a physical verification certificate. The run retains its own execution
occurrences; the receipt is not another execution occurrence or scientific state.

The operator's explicitly opted-in numerical execution is separate from the
planning-only flags in Board/view/edit records. No state admission or physical
actuation is exposed.

## Reproducible specimen

The demo's six nodes include three ordinary analysis operations and three
inspectable descriptive objects. Only the operation nodes compile to execution.
The semantic edges are descriptions, not instructions to rerun.

The baseline executes three operations. Editing `statistics.channel: q -> v`
uses the existing Needle dependency closure:

| Node | Execution observation | Scientific data |
| --- | --- | --- |
| statistics | RERUN | Changed, including m → m/s output units |
| spectrum | RERUN as declared dependent | Unchanged q periodogram |
| energy_statistics | REUSED | Unchanged; no new execution |

The original Board, source evidence and baseline graph-run remain unchanged.
The inspector exposes actual retained result metadata and arrays. Numeric leaf
changes are structural comparisons, not calibrated causal effects; a unit change
must not be interpreted as a same-unit physical delta.

No manufacturing, mesh, chemistry, hardware or empirical calibration result is
claimed by this synthetic oscillator demonstration.

## Local transport and retention

The server binds only IPv4 `127.0.0.1`, checks its exact Host and any supplied
Origin, and requires an unguessable process-local token for every data/action API.
The unauthenticated HTML shell contains no Board/source data or token. There is
no CORS grant, filesystem browser, shell route or arbitrary provider registration.
The interface uses fixed routes, 64 KiB JSON request limits, duplicate-key/nonfinite
refusal and a 256-action session retention budget. This is a local development
instrument, not a hardened multi-user or Internet service.

All records are written under an operator-chosen newly created output directory.
Each action receives a fresh directory. Existing files are not overwritten. The
session stores ordinary Session execution/result evidence, while each action
retains its request and generated artifacts. Restarting/reopening a UI server is
not yet a retained-session resume mechanism.

Browser content is embedded as inert base64 JSON, rendered using textContent and
SVG attributes, with hash-allowlisted packaged CSS/JavaScript. No external fonts,
CDNs or assets are required. A view exported from the offline browser is a
specification, not a Python-validated sealed record.

## Qualification

`tests/test_visual_board.py` adds projection, identity, immutability, shared
compilation, actual ordinary Needle execution, HTTP capability/Origin/Host,
malformed-input, inert-content and overwrite tests. The dedicated workflow also
runs the complete 199-test inherited PR #101 qualification surface.

`validation/visual_board_browser.py` runs actual Chromium controls and checks
Python/browser scene parity, collapsing, selection, drag, zoom, exports, inert
hostile text, narrow layout, live baseline/candidate execution and delta display.
It retains screenshots and a report. The optional `--embedded-only` local mode
qualifies DOM behavior only; it explicitly does not claim file navigation or live
browser execution. Hosted qualification uses the full mode and the installed
wheel, not the source checkout imports.

Read the exact commit's retained reports before claiming a platform or browser
path is qualified. No claim of a faster investigation or productivity multiplier
follows from this interface increment.
