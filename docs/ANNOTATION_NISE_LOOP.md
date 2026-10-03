# Annotation → NISE → NET investigation loop

This closes a central representational loop:

```text
human observation / interpretation
        ↓
ciw.annotation.v1
        ↓
explicit annotation→NISE seed plan
        ↓
nise.query.v1
        ↓
NISE candidate inference schematic
        ↓
operator NET binding plan
        ↓
ciw.experiment.v1
```

No stage silently promotes interpretation into evidence, truth, state admission or
execution authority.

## Why the focus mapping is explicit

An annotation target may be a NET observation/result/artifact identity while a
NISE catalog uses a different node identity. V1 therefore does **not** infer a
NISE focus from the annotation target.

The operator provides `focus_node_ids` explicitly in
`ciw.annotation-nise-seed.v1`.

That seed plan may also add semantic capabilities, but it cannot name providers,
engines, binaries or containers.

## What the annotation contributes

The bridge carries forward:

- annotation content as the NISE question;
- requested semantic operations;
- annotation identity;
- author;
- target and target version;
- evidence refs;
- model refs;
- interpretive kind/status.

A withdrawn annotation cannot seed a new investigation in V1.

## CLI

```sh
net annotation nise-query annotation.json seed.json \
  --query-output query.json \
  --receipt-output annotation-nise-receipt.json

nise compile catalog.json query.json --output schematic.json

net nise compile-handoff schematic.json binding.json --output handoff.json
```

The first command performs no semantic retrieval. NISE performs bounded relevance
construction. The final NET command compiles selected operation meanings into an
ordinary NET experiment contract. Provider execution remains a separate action.

This gives human interpretation a computational attachment point without making
it evidence.
