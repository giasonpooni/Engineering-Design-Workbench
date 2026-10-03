# Evidence-bound representation expansion V1

This increment closes the planning gap between an `EXPAND` intervention decision
and a fresh `LOCAL` decision over an already retained richer representation.

It does **not** invert a lossy representation, infer a hidden physical state, or
admit new canonical state.

## Chain

```text
coarse representation + EXPAND gate
        |
        v
resolve exact retained richer evidence
        |
        +-- exact source evidence identity
        +-- exact richer representation identity
        +-- exact coarse representation identity
        +-- exact scientific projection morphism
        +-- retained execution/result validation
        |
        v
ciw.representation-expansion.v1
        |
        v
replay the projection from the same retained evidence
        |
        +-- independent execution identity
        +-- same semantic lowering
        +-- same parameters
        +-- same runtime identity
        +-- same scientific data
        |
        v
ciw.representation-expansion-verification.v1
        |
      PASS only
        v
ciw.representation-expansion-promotion.v1
        |
        v
fresh LOCAL intervention gate over richer representation
```

Evidence, retained execution, replay execution, verification and planning remain
separate records.

## Why retained evidence is required

A coarse representation may have a many-to-one preimage. The existence of a
mathematical fibre or compatible-state set does not establish which fine state
actually occurred.

V1 therefore refuses to manufacture a fine state. The richer representation must
already be retained, must validate under its ordinary source contract, and its
scientific evidence identity must equal the `recovery_evidence_ref` named by the
original EXPAND gate.

For the qualified oscillator example:

```text
retained q time series
        |
        | signal.periodogram.transform.v1
        v
retained q periodogram
```

The periodogram cannot locally support the named time-domain selection
intervention. Expansion resolves the original retained recording rather than
attempting spectral inversion.

## Projection binding

The expansion requires an explicit scientific morphism whose:

- domain is the richer representation named by the EXPAND gate;
- codomain is the current coarse representation;
- semantic capability has a currently bound concrete lowering.

The retained execution and result must:

- be sealed and internally consistent;
- point to the exact retained source evidence and run;
- validate against the trusted operation payload schema;
- use the operation selected by the current semantic lowering.

A different source, reversed morphism, stale result, or different concrete
operation refuses.

## Replay verification

Verification is a distinct execution occurrence. It compiles the exact scientific
projection capability using the retained result parameters, runs it again against
the same source evidence, and compares:

1. source evidence identity;
2. concrete operation identity;
3. parameter values;
4. runtime identity;
5. scientific result data.

All five must match for `PASS`.

The verification record embeds the replay execution and result so validation can
recompute the comparison rather than trusting a re-sealed boolean or status.

Replay establishes deterministic agreement for this retained evidence and
runtime. It does not establish general physical validity, empirical calibration,
causality, or a universal morphism law.

## Promotion

Only a `PASS` verification can produce a
`ciw.representation-expansion-promotion.v1`.

Promotion creates a **fresh** ordinary intervention gate whose current
representation is the verified richer representation. That gate must resolve
`LOCAL` under the existing representation contract.

Promotion is planning-only. It does not:

- execute Needle;
- mutate canonical state;
- admit evidence/state;
- authorize hardware;
- infer a unique inverse;
- convert verification into physical truth.

The original coarse EXPAND gate remains retained and unchanged.

## CLI

Given retained files:

```sh
net needle expand \
  source.json current-execution.json current-result.json \
  expand-gate.json morphism-registry.json expansion-spec.json \
  --output expansion.json

net needle verify-expansion \
  source.json current-execution.json current-result.json \
  expand-gate.json morphism-registry.json expansion.json \
  --session-dir replay-session \
  --output expansion-verification.json

net needle promote-expansion \
  source.json current-execution.json current-result.json \
  expand-gate.json morphism-registry.json expansion.json \
  expansion-verification.json promotion-spec.json \
  --output expansion-promotion.json
```

The promotion record contains the newly derived LOCAL gate. Existing files are
create-only and cannot be silently overwritten.

## Failure surfaces deliberately tested

The qualification suite checks refusal for:

- source evidence different from the EXPAND gate;
- non-EXPAND source gates;
- reversed/incorrect projection endpoints;
- retained results using a different concrete operation;
- re-sealed expansion metadata with false evidence refs;
- re-sealed verification records with modified replay data and fake PASS;
- failed/tampered verification promotion;
- output overwrite attempts.

The successful path additionally proves that replay execution/result identities
are distinct from the retained execution/result identities while scientific
data remains identical.

## Architectural consequence

The representation layer now has a bounded transition protocol:

```text
LOCAL  -> plan locally
REFUSE -> stop
EXPAND -> resolve retained richer evidence
          -> verify projection relationship
          -> derive fresh LOCAL gate
```

This makes representation refinement an auditable evidence transition rather
than an implicit act of reconstruction.

`net needle plan-expanded` now closes this planning seam. It reconstructs and
validates the full expansion/promotion chain, then delegates the nested fresh
LOCAL gate to the original `plan_represented_needle` implementation. It does not
create alternate Needle semantics or bypass baseline-target/dependency checks.

The next extension should carry the resulting plan through ordinary Needle
execution while retaining the promotion and verification identities alongside
the run/delta evidence, rather than modifying the existing Needle execution
record format.
