# Representation + Morphism Registry V1

The scientific substrate distinguishes canonical state from the representations
through which that state becomes computable.

```text
canonical state
    ↓ projection
representation
    ↓ typed morphism
representation
```

The registry does not replace the semantic capability compiler. It supplies the
scientific meaning and preservation contract that the execution layer does not
know by itself.

## Representation contract

`ciw.representation-spec.v1` declares:

- representation identity and role;
- source-state type;
- schema and quantity meaning;
- unit, frame, time and scale semantics;
- uncertainty semantics;
- equivalence contract:
  - EXACT
  - STRUCTURAL
  - TASK_SPECIFIC
  - LOSSY
- named queries preserved;
- named interventions supported;
- a recovery route to richer retained detail;
- provenance.

Query and intervention preservation are separate on purpose. A representation
may answer one query perfectly while lacking the distinctions required to
perform a local intervention correctly.

## Scientific morphism contract

`ciw.scientific-morphism.v1` declares:

- morphism kind:
  Observe / Admit / Project / Transform / Estimate / Simulate / Coarsen /
  Refine / Retrieve / Needle / Verify / Rewrite / Render / Retain;
- domain and codomain representations;
- optional existing semantic capability;
- parameter names and preconditions;
- validity assumptions, operating regime and failure conditions;
- preserved queries, interventions and invariants;
- exact/structural/task-specific/lossy information behavior;
- uncertainty behavior;
- reversibility;
- authority requirements;
- verification requirements;
- provenance.

This describes scientific meaning. It does not select an engine.

## Registry

`ciw.morphism-registry.v1` is bound to the exact current
`ciw.semantic-capability-catalog.v1`.

The architecture is:

```text
scientific morphism meaning
       ↓
semantic capability
       ↓
operator-owned engine lowering
       ↓
ordinary NET experiment
```

The Representation/Morphism Registry therefore cannot bypass the existing
provider-selection or execution-authority boundaries.

## Finite witnesses

`ciw.morphism-witness.v1` records one retained execution plus named checks.

A finite witness can establish only that the named checks passed for that
execution. It explicitly does not prove:

- a universal morphism law;
- a category-theoretic naturality law;
- cross-representation commutativity in general;
- empirical physical validity.

## First real morphism

V1 qualifies:

```text
uniform sampled scalar time series
        ↓ analysis.spectrum.v1
one-sided periodogram density
```

This morphism is intentionally **LOSSY** and **non-reversible**.

It preserves declared spectral queries:

- one-sided periodogram density;
- frequency grid;
- peak frequency.

It declares no time-domain interventions because phase and time-local ordering
are not retained. To perform those operations the system must recover the source
recording.

This gives NET its first executable instance of the rule:

> query sufficiency does not imply intervention sufficiency.

## Relation to the System Board

The System Board already carries typed sockets, scale, uncertainty, provenance,
parameters and validity statements. The Morphism Registry adds the missing
contract for **representation change itself**.

The next integration step is for Transform / Project / Render Board nodes to
reference morphism identities directly. Needle can then refuse to operate through
a projection unless the selected intervention is declared preserved, or request
expansion to the richer representation named by the recovery route.
