# Representation realization adapters V1

This increment separates a **representation contract** from an **actual retained
artifact that realizes that contract**.

The distinction is operationally important:

```text
representation declaration
      !=
retained artifact realization
      !=
projection/morphism execution
      !=
intervention sufficiency
      !=
execution authority
```

A representation may say that a state is a covariance-bearing vector or a
uniform sampled scalar signal. That declaration alone cannot prove that an
arbitrary JSON object is such a state or signal.

V1 therefore registers trusted family-specific validators against exact
representation identities.

## Registry

`ciw.realization-adapter-registry.v1` is content-bound to one exact
`ciw.morphism-registry.v1`.

Each `ciw.realization-adapter.v1` declares:

- adapter identity;
- exact representation identity and digest;
- one trusted built-in validator family;
- exact quantity order;
- exact units;
- exact frame;
- whether retained uncertainty is required.

The explicit binding is deliberate. NET does not parse free-text
`unit_semantics`, `frame_semantics` or `quantity_semantics` and silently
turn those strings into scientific proof.

Changing the representation registry invalidates the adapter registry.

## V1 trusted realization families

### 1. `run-channel.v1`

Source representation schema:

```text
ciw.run-channel.v1
```

The validator reuses the existing retained-run and evidence-identity checks.
A realization additionally requires an explicit:

```json
{
  "channel": "q",
  "interval_s": [0.0, 12.0]
}
```

The selected channel must be declared by the adapter, its unit must match, the
run coordinate frame must match, the half-open interval must remain within the
retained run duration, and it must select at least one actual retained sample.

The realization records sample count and the first/last selected sample times
but does not duplicate the source array.

No per-channel uncertainty is invented in V1.

### 2. `state-record.v1`

Source representation schema:

```text
ciw.state.v1
```

The validator delegates to the existing strict state validator. It then binds:

- exact variable order;
- exact units;
- exact frame;
- required covariance presence when declared by the adapter.

A covariance-bearing state therefore has to pass the already-existing full
covariance checks. The realization retains the covariance content identity and
the state's original provenance references.

### 3. `covariance-artifact.v1`

Source representation schema:

```text
covariance-artifact.v1
```

The validator delegates directly to
`validate_covariance_artifact(... expected_quantity_ids, expected_units,
expected_frame)`.

That retains the existing requirements for:

- exact content identity;
- ordered axes;
- units and frame;
- finite entries;
- nonnegative variances;
- exact zero rows/columns for zero variance;
- symmetry in normalized correlation coordinates;
- positive semidefiniteness;
- basis/provenance structure.

NET does not repair a covariance to make it pass.

## Realization record

A successful validation produces `ciw.representation-realization.v1`.

It retains:

```text
adapter registry
adapter
representation
artifact content identity
selector
normalized realized view
source evidence/provenance identities
```

Its claims are deliberately bounded:

```text
artifact_realizes_representation_under_adapter = true
family_validator_executed = true
empirical_truth_established = false
provider_execution = false
canonical_state_mutated = false
state_admission = false
execution_authority = false
```

Validation recomputes the entire realization from the original retained
artifact. Re-sealing a modified derived view is insufficient.

## Recovery binding

`ciw.recovery-realization-binding.v1` connects one validated realization to
one existing EXPAND gate.

It requires:

- the gate still validates against the exact morphism registry;
- the gate decision remains `EXPAND`;
- the realization is the exact richer representation named by that gate;
- the exact representation digest matches;
- the gate's recovery evidence identity occurs in the realization's validated
  evidence/provenance set.

This is an intentionally **earlier** boundary than PR #98's projection
verification:

```text
EXPAND gate
   ↓
recovery realization binding
   ↓ proves retained artifact realizes richer representation
projection execution/witness
   ↓ separate existing PR #98 check
intervention reconsideration
```

Accordingly a recovery binding explicitly records:

```text
projection_execution_verified = false
intervention_reconsidered = false
```

The adapter layer cannot bypass evidence-bound expansion or directly make a
Needle LOCAL.

## CLI

```sh
net realization create-registry \
  morphism-registry.json adapter-spec.json \
  --output realization-registry.json

net realization realize \
  realization-registry.json morphism-registry.json source.json realization-spec.json \
  --output realization.json

net realization bind-recovery \
  realization-registry.json morphism-registry.json expand-gate.json \
  realization.json source.json recovery-binding-id \
  --output recovery-binding.json
```

Outputs use the existing create-only publication boundary.

## Why this is an extension, not another architecture

V1 reuses:

- the existing representation/morphism registry;
- existing run/evidence validation;
- existing state contract;
- existing covariance artifact contract;
- existing EXPAND gate;
- existing content identities and create-only records.

It introduces no scheduler, numerical provider, alternate state owner or
parallel provenance system.

The registry is intended to let additional scientific families plug into this
same boundary without changing the meaning of existing ones.

Likely follow-on families include:

- calibrated observations and observation streams;
- spatial/geographic retained contexts;
- finite meshes and mesh results;
- dense/sparse matrices with explicit bases;
- graphs with typed node/edge semantics;
- molecular configurations and trajectories;
- continuum fields and discretizations.

Each should receive a domain-specific validator and explicit binding. A generic
"JSON is structurally valid" adapter would violate the purpose of this layer.

## Qualification target

The dedicated V1 qualification covers all three realization families,
representation-schema/validator mismatch, altered registry identity, channel
and interval bounds, stale source evidence, state covariance requirements,
covariance tampering, re-sealed derived realization tampering, EXPAND recovery
evidence mismatch, recovery-binding tampering and the complete CLI flow.

It also reruns the 197-test PR #98 scientific/regression surface.

No claim of physical calibration, empirical authenticity, automatic inverse
reconstruction or universal representation theory follows from these tests.
