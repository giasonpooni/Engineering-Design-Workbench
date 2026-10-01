# System Board Visual Editor V1

This is the first graphical projection of the typed, parameterized
[System Board](SYSTEM_BOARD.md).

It is intentionally a **local candidate editor**, not a browser runtime and not
a second source of scientific state.

## Purpose

The visual editor gives the System Board a direct-manipulation surface similar
in interaction style to hierarchical node systems while preserving the same
Board contracts used by CLI, agents and parameter programs.

The initial loop is:

~~~text
sealed Board
   ↓
local no-network HTML projection
   ↓
navigate group abstraction
   ↓
select typed node
   ↓
inspect sockets / scale / authority / invariants
   ↓
stage one exposed parameter replacement
   ↓
highlight declared dependency closure
   ↓
download bounded edit spec
   ↓
Python revalidates exact Board identity + parameter domain
   ↓
new immutable candidate Board
~~~

The base Board is never mutated.

## Hierarchical abstraction

Board groups are architectural objects, not drawing folders.

The visualizer starts at the highest useful group level and lets the operator
enter nested groups. Collapsing a group hides internal complexity while leaving
its Board identity and members unchanged.

The graph projection aggregates relations that cross currently visible group
boundaries. Entering a group exposes its direct child groups and direct member
nodes.

This is the first concrete implementation of the abstraction-ladder UI idea:
the same Board can be inspected at more than one architectural depth without
maintaining separate state stores.

## Relational views

The editor can switch between:

- execution relations: DATAFLOW + DEPENDENCY;
- all declared relations;
- individual DATAFLOW, DEPENDENCY, SEMANTIC, SPATIAL, TEMPORAL,
  AUTHORITY, or SCALE projections.

Only the execution relations participate in the candidate dependency closure.

As elsewhere in NET:

~~~text
declared dependency != observed numerical change != physical causality
~~~

## Node inspection

Selecting a node exposes the Board-retained:

- node kind and identity;
- semantic capability when present;
- scale label;
- resource and authority requirements;
- typed input/output sockets;
- unit, frame, uncertainty and provenance requirements;
- current parameters and domains;
- invariants;
- validity conditions.

No hidden provider state is reconstructed by the page.

## Visual parameter editing

Only Board parameters carrying exposed=true can be staged.

The page performs a convenience domain check, but that check is not
authoritative. It exports:

~~~json
{
  "schema": "ciw.board-visual-edit-spec.v1",
  "edit_id": "...",
  "board_ref": "sha256:...",
  "target": {
    "node_id": "...",
    "parameter": "..."
  },
  "replacement": "...",
  "notes": "..."
}
~~~

Apply it with:

~~~sh
net board apply-edit board.json edit.json --output candidate-board.json
~~~

Python then:

1. validates the exact sealed base Board;
2. requires the exact board_ref;
3. requires an existing exposed parameter;
4. preserves the declared parameter type;
5. reconstructs the candidate through board_from_spec, reusing the Board's
   authoritative domain validation;
6. emits a new sealed candidate Board.

The visual page cannot weaken these rules.

## Local rendering

Create the editor:

~~~sh
net board render board.json --output board.html
~~~

The result is self-contained.

Its Content Security Policy disables network connections and permits only the
packaged, hash-bound CSS and JavaScript embedded at export. Board data is
embedded as inert base64-encoded JSON and inserted into the DOM through text
operations rather than HTML interpolation.

Opening the page:

- does not start the NET server;
- does not bind or execute providers;
- does not compile the Board;
- does not mutate canonical state;
- does not verify a scientific claim;
- does not authorize physical action.

## Visual Needle semantics

When an edit is staged, the page highlights descendants reachable through the
Board's declared DATAFLOW and DEPENDENCY edges.

This is a preview of the recomputation frontier. It is not a causal claim and it
does not perform the [Needle](NEEDLE.md) execution itself.

A later connected editor can lower an accepted visual edit through the existing
Needle operation. V1 keeps the browser isolated and makes the edit spec cross an
explicit Python validation boundary first.

## Why the UI is not a second architecture

The intended invariant is:

~~~text
mouse / touch
Julia
CLI
agent
optimizer
      ↓
same Board identity + same typed parameter/morphism contracts
      ↓
candidate state
      ↓
existing NET execution / verification machinery
~~~

The graphical representation is therefore another notation over the Board, not
an independent workflow engine.

## Deliberate V1 limits

V1 does **not** implement:

- provider execution from the browser;
- live WebSocket mutation;
- drag-to-connect morphism creation;
- multi-edit transactions;
- structural topology edits;
- operation/model/backend replacement;
- candidate acceptance;
- scale-aware cross-model navigation;
- context-twin inspection;
- persisted node layout;
- physical control.

Those are follow-on increments only after this bounded projection/edit path is
qualified.
