# Evidence-bound representation expansion V1

This increment closes the next narrow gap in representation-aware Needle:

```text
coarse representation
    ↓ intervention unsupported
EXPAND planning decision
    ↓ previously: richer representation ID + evidence hash only
actual retained source + exact transform occurrence + witness
    ↓ validate without rerunning the provider
fresh LOCAL gate over the richer representation
    ↓
ordinary Needle plan
```

It is stacked on finite representation preservation and does not replace the
existing representation registry, intervention gate, Session, providers,
System Board or Needle execution path.

## Premise

An `EXPAND` gate is deliberately not execution authority. It states that the
current representation lacks a named intervention and that a declared richer
representation plus retained evidence has been identified. A hash and a
representation name are not enough to establish that the retained source is
actually present or that the current coarse result was derived from it.

V1 adds two records:

- `ciw.representation-expansion.v1` — evidence-bound recovery resolution;
- `ciw.intervention-reconsideration.v1` — a fresh LOCAL planning gate derived
  only after the expansion evidence is completely revalidated.

The original EXPAND gate is retained unchanged.

## Evidence required

A representation expansion is created from:

1. the exact morphism registry;
2. an existing `ciw.intervention-gate.v1` whose decision is `EXPAND`;
3. the actual retained richer `run.v1` source;
4. the declared rich-to-coarse scientific morphism;
5. an existing `ciw.morphism-witness.v1`;
6. the exact retained `ciw.execution.v1` occurrence;
7. the exact retained `ciw.operation-result.v1` occurrence.

The resolver checks all of the following before producing an expansion record:

- the source run passes its existing domain validator;
- the source scientific content recomputes to its retained `evidence_id`;
- the source evidence equals the evidence named by the EXPAND gate;
- the projection morphism is exactly
  `recovery representation -> current representation`;
- the morphism is a declared `PROJECT`, `COARSEN` or `TRANSFORM`;
- the witness is bound to the exact registry, morphism and source evidence;
- the witness contains no retained FAIL check and at least one PASS check;
- the execution/result seals and occurrence identities agree;
- execution and result both name the actual richer source run/evidence;
- the execution operation is an explicitly bound lowering of the morphism's
  semantic capability;
- execution parameters are declared by the scientific morphism;
- the saved result payload passes the existing trusted operation-specific
  payload validator against the actual retained source.

Finally, the witness execution/result content references must equal the exact
supplied execution/result content identities.

A caller cannot make a bad record valid merely by recomputing its hash. The
expansion validator reconstructs the complete record from the retained inputs.

## What is and is not verified

V1 verifies **content integrity and declared projection provenance** for an
already-retained occurrence. It does not rerun the numerical provider during
expansion resolution.

For the qualified periodogram case this means the saved periodogram is checked
against the retained source for:

- source evidence and run identity;
- selected channel and half-open interval;
- operation and result occurrence binding;
- sample count;
- periodic-Hann / constant-detrend / density method fields;
- source sample rate;
- density unit;
- one-sided frequency-grid shape and values;
- nonnegative finite density values;
- stored peak consistency.

The prior finite morphism witness remains a finite execution witness. Any
unresolved physical-validation check remains unresolved.

`projection_reexecuted=false` is retained explicitly. Re-execution, if desired,
should remain a separate verification occurrence rather than being hidden
inside a representation recovery operation.

## Reconsideration

Once the expansion validates, NET creates a separate
`ciw.intervention-reconsideration.v1` record. It derives a new ordinary
`ciw.intervention-gate.v1` against the richer representation.

```text
original gate: periodogram -> EXPAND
                         │
                         ├── evidence-bound expansion validated
                         │
                         └── new gate: retained time series -> LOCAL
```

The new gate has the same intervention ID and Needle coordinate as the original
gate. It does not mutate the original gate.

Planning after expansion additionally requires that the baseline graph-run uses
exactly the same source evidence as the resolved richer representation. Only
then does the code delegate to the existing `plan_represented_needle` function,
which creates the ordinary `ciw.needle-plan.v1`.

This means the new layer adds **preconditions to existing planning** rather than
adding a second intervention engine.

## CLI

The explicit retained-artifact flow is:

```sh
net needle expand \
  registry.json expand-gate.json source-run.json morphism-witness.json \
  projection-execution.json projection-result.json expansion-spec.json \
  --output expansion.json

net needle reconsider \
  registry.json expand-gate.json source-run.json morphism-witness.json \
  projection-execution.json projection-result.json expansion.json \
  reconsideration-spec.json --output reconsideration.json

net needle plan-expanded \
  baseline-graph-run.json needle-spec.json registry.json expand-gate.json \
  source-run.json morphism-witness.json projection-execution.json \
  projection-result.json expansion.json reconsideration.json \
  --output needle-plan.json
```

The verbosity is intentional in V1: each evidence/verification identity remains
explicit. The CLI does not silently search a directory or infer which source,
execution or result the caller intended.

All outputs remain create-only through the existing `save_new` boundary.

## Qualified adversarial cases

The test suite includes:

- a valid retained oscillator time-series -> periodogram path;
- source-data tampering with a stale evidence identity;
- a changed source with a newly self-consistent evidence identity but a mismatch
  against the prior EXPAND gate;
- a reverse scientific morphism direction;
- a witness containing an explicit failed check;
- an exact result occurrence changed without invalidating its numerical payload;
- a result whose caller-generated witness points at corrupted payload data;
- re-sealed fabricated expansion/reconsideration records;
- a Needle baseline using different evidence from the recovered source;
- complete CLI expansion -> reconsideration -> ordinary Needle planning;
- create-only refusal on an existing expansion output.

The corrupted-payload case is important: a caller can create a fresh witness
pointing to a modified result hash, but that does not bypass the trusted saved
payload validator.

## Boundaries

This increment does **not**:

- fetch or reconstruct missing data;
- infer a unique fine state from a coarse state;
- materialize a representation from a lossy inverse;
- rerun the projection provider during expansion resolution;
- establish empirical calibration or physical validity;
- infer causal effects;
- mutate or admit canonical state;
- execute the candidate Needle;
- authorize hardware or physical action;
- prove a universal commutative or categorical law.

The stronger architecture now has a concrete separation:

```text
representation contract
    !=
retained representation realization
    !=
projection execution/witness
    !=
intervention sufficiency
    !=
execution authority
```

## Next dependency

The next substantive extension is **representation realization adapters** for
additional scientific object families. V1 resolves the existing retained
`run.v1`/operation-result path. A general system should register typed,
trusted realization validators for state estimates, spatial fields, meshes,
matrices, graphs, molecular configurations and other representation families
rather than encoding their semantics as strings or pretending one universal
inverse exists.
