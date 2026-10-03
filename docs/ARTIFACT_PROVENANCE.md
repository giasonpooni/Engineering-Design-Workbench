# Artifact provenance and organization/IP boundaries

Notation Systems and Cartesian Graphics may share computational tools while owning
different outputs. Tool provenance and output ownership therefore need explicit,
portable declarations rather than assumptions derived from repository names.

The core principle is:

```text
open/shared tool != ownership of work produced with the tool
```

## Portable declaration

`notations.artifact-provenance.v1` records:

- artifact identity and SHA-256 content identity;
- declared owner;
- asset class:
  - `OPEN_INFRASTRUCTURE`
  - `PROPRIETARY_IP`
  - `THIRD_PARTY`
  - `INTERNAL`
  - `MIXED`;
- exact repository/revision/path when applicable;
- origin: original, derived, generated, imported, commissioned or upstream;
- declared licence expression + retained licence/notice references;
- contributors;
- dependencies and their declared relationships;
- declared use-policy contexts and basis references.

## Important non-authority

This record is **not legal adjudication**.

Every declaration states:

```text
descriptive provenance = true
ownership verified = false
rights adjudicated = false
licence compatibility verified = false
execution authority = false
```

A declaration cannot transfer rights, waive a licence, make an incompatible
licence compatible, prove authorship, or replace legal review.

## Organization boundary example

A general Notation Systems geometry primitive may declare:

```text
owner:       Notation Systems
asset class: OPEN_INFRASTRUCTURE
licence:     MPL-2.0
```

A game asset produced with it may separately declare:

```text
owner:       Cartesian Graphics
asset class: PROPRIETARY_IP
licence:     LicenseRef-Cartesian-Proprietary
origin:      ORIGINAL / GENERATED / DERIVED as appropriate
dependency:  GENERATED_WITH → Notation Systems tool
```

The provenance record does not infer that the game asset becomes open merely
because it used an open tool.

Conversely, the optional `boundary_review` heuristic flags an
`OPEN_INFRASTRUCTURE` artifact that declares it **incorporates proprietary IP**
for review before distribution. That is a workflow warning, not a legal decision.

## CLI

```sh
net provenance create spec.json --output provenance.json
net provenance inspect provenance.json

net provenance review parent.json dependency-a.json dependency-b.json
```

This gives both organizations a common provenance grammar while preserving
separate ownership, licences and product/IP policies.
