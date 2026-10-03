# Annotation — first-class human interpretive state

NET now treats an annotation as a computationally addressable record rather than
a comment string.

```text
observation
    ↓
human annotation
    ↓
requested semantic operation
    ↓
result
    ↓
new annotation / correction
```

The underlying dependency structure may be a graph, while annotations can be
projected chronologically for the human investigation history.

## Boundary

`ciw.annotation.v1` is specifically **human interpretive state**.

It is not:

- evidence;
- canonical state;
- verification;
- an execution occurrence;
- an agent proposal;
- execution/release/actuation authority.

The record therefore carries explicit false authority claims for those categories.

Machine-generated hypotheses/proposals should receive their own record class; V1
refuses `author.kind != human` rather than blurring human interpretation and
machine output.

## Shape

An annotation retains:

- human author;
- timezone-aware authored time;
- typed target and target version;
- kind:
  `OBSERVATION | HYPOTHESIS | INTERPRETATION | CONSTRAINT | QUESTION | DECISION | INSTRUCTION`;
- text plus optional bounded structured content;
- evidence references;
- model references;
- referenced semantic operations;
- requested semantic operations;
- optional self-assessed confidence;
- lifecycle status `OPEN | RESOLVED | WITHDRAWN`;
- optional immutable `supersedes` link.

`confidence` is the author's self-assessment. It is not measurement uncertainty,
a calibrated probability, evidence strength, or verification score.

Evidence references must be canonical SHA-256 content identities. Requested
operations are semantic capability IDs; annotations cannot select Python, Julia,
Rust, C++, an engine, executable or container.

## Corrections are append-like

Existing annotation bytes are never rewritten to "correct" history.

A later annotation can point to an earlier annotation through `supersedes`.
The earlier record remains intact.

```text
14:15 HYPOTHESIS
  possible calibration drift
        ↓ superseded by
14:22 INTERPRETATION / RESOLVED
  drift not supported after calibration check
```

## Chronological projection

`ciw.annotation-stream.v1` is a deterministic read projection ordered by:

```text
authored_at → record_digest
```

It gives the human a linear investigation history without pretending the
underlying evidence/model/operation dependency structure is linear.

## CLI

```sh
net annotation create annotation-spec.json --output annotation.json
net annotation inspect annotation.json

net annotation timeline annotation-2.json annotation-1.json \
  --output investigation-annotations.json
net annotation inspect-timeline investigation-annotations.json
```

No provider executes during these commands.

## Future attachment to NISE

A subsequent NISE contract can treat annotations as their own schematic partition
or consume explicit annotation-derived query seeds. It should **not** collapse
annotations into observations: what a person thinks about an observation remains
distinct from the observation itself.
