# IFC/CSE Executable Interoperability Bridge V1

This is the first concrete execution bridge over the generic interoperability
ingress layer.

It reuses the existing bounded `ciw.bim-quantity.v1` workload and pinned CSE
runtime. It does not introduce another IFC parser, estimator or state store.

~~~text
exact IFC bytes
    ↓
external-ingress qualification
    ↓
exact payload identity check
    ↓
existing CSE BIM quantity workflow
    ↓
native prior/posterior + covariance + invariants + ledger replay
    ↓
ciw.interop-mapping-witness.v1
    ↓
future typed preservation verifier
~~~

## Runtime witness

`ciw.interop-mapping-witness.v1` binds the exact ingress qualification and IFC
payload to the existing CSE session/result/execution identities.

It retains the native mapping outcome as `MAPPED`, `HELD` or `REFUSED`, along
with target identity, prior/posterior world commitments, invariant report and
ledger-replay result.

A MAPPED witness establishes that the already-qualified external bytes were
actually executed through the pinned bounded mapping and accepted by that
runtime. It does **not** establish the full preservation contract or physical
truth.

Therefore every witness explicitly retains:

~~~text
mapping_executed = true
preservation_verification_performed = false
physical_validity_established = false
canonical_entity_created = false
state_admission_performed = false
canonical_state_mutated = false
~~~

## Exact byte identity

The bridge requires:

~~~text
qualified ingress payload_ref
    ==
SHA256(exact IFC bytes embedded in the BIM source)
    ==
native CSE retained ifc_sha256
~~~

A valid qualification for different bytes cannot be rebound to a CSE run.

## Existing CSE authority is preserved

The runtime still owns its existing checks:

- bounded IFC parsing/lowering;
- target binding;
- declared unit handling;
- frame applicability;
- explicit cross-covariance policy;
- Gaussian conditioning;
- full prior/posterior covariance;
- native invariants;
- hash-chained execution ledger;
- ledger replay.

The interoperability bridge wraps those retained results; it does not duplicate
or weaken them.

## CLI

~~~sh
net interop-bim execute \
  registry.json preservation-contract.json profile.json ingress.json \
  ingress-verification.json qualification.json bim-source.json execution-spec.json \
  --cse-repository /path/to/pinned/CSE \
  --output mapping-witness.json
~~~

V1 deliberately stops before converting the mapping witness into a typed
`ciw.preservation-verification.v1` receipt. That adapter is the next bounded
increment: map specific native CSE evidence to specific declared preservation
obligations without promoting a runtime PASS into a universal proof.


## Preservation verifier and state projection tools

The runtime bridge now has a second layer that converts retained CSE evidence
into the generic preservation/transition machinery without treating runtime
success as universal proof.

### Project native CSE worlds into NET states

A projected state requires a VERIFIED cross-system identity binding. The
projector then assigns the binding's canonical entity identity to the exact
native prior/posterior worlds and retains the complete CSE covariance without
repair.

```sh
net interop-bim project-states \
  registry.json preservation-contract.json profile.json ingress.json \
  ingress-verification.json qualification.json mapping-witness.json \
  native-bim-bundle.json identity-binding.json identity-verification.json \
  --source-output source-state.json \
  --candidate-output candidate-state.json
```

The two state records preserve:

- canonical entity identity from the VERIFIED binding;
- exact native quantity order and units;
- exact prior/posterior means;
- complete native covariance matrices;
- native CSE world/belief commitments;
- mapping-witness and bundle provenance;
- the native execution identity on the candidate.

The projection clock is a two-step transition index, not physical time.

### Verify only supported preservation properties

`net interop-bim verify-preservation` uses a deliberately small CSE verifier.
It currently knows how to evaluate:

- `identity.ifc-target.v1`;
- `frame.declared-compatible.v1`;
- `uncertainty.independent-measurement.v1`;
- `unit.length-metres.v1`;
- `uncertainty.full-covariance.v1`;
- `geometry.solid-authority.v1`.

Any other property remains `UNRESOLVED`.

```sh
net interop-bim verify-preservation \
  registry.json preservation-contract.json profile.json ingress.json \
  ingress-verification.json qualification.json mapping-witness.json \
  native-bim-bundle.json \
  --verification-id interop.ifc-cse-preservation.v1 \
  --source-state source-state.json \
  --candidate-state candidate-state.json \
  --binding identity-binding.json \
  --identity-verification identity-verification.json \
  --output preservation-verification.json
```

This produces the ordinary `ciw.preservation-verification.v1` record. The
method class remains explicit: exact identity/frame/unit declarations use
`EXACT_ALGEBRA`; covariance retention uses `NUMERICAL_BOUND` because the
existing workbench validator applies its declared PSD/symmetry tolerances.

A held mapping cannot be upgraded into a fully verified transition. Unsupported
properties cannot be silently promoted.

### Prepare the authority handoff

The generic transition CLI can now combine an existing preservation receipt,
loss policy and transition proposal in one bounded command:

```sh
net transition prepare \
  source-state.json candidate-state.json \
  identity-binding.json identity-verification.json \
  registry.json preservation-contract.json preservation-verification.json \
  gate-policy.json transition-spec.json \
  --gate-output preservation-gate.json \
  --output transition-envelope.json
```

The command writes both the preservation eligibility gate and the industrial
transition envelope.

A successful chain ends at:

```text
READY_FOR_AUTHORITY_REVIEW
```

not at canonical-state admission.

## Current end-to-end experiment

The resulting executable path is now:

```text
exact IFC bytes
  -> ingress qualification
  -> pinned CSE execution
  -> mapping witness
  -> VERIFIED external identity
  -> typed NET prior/candidate states
  -> scoped CSE preservation verifier
  -> preservation eligibility gate
  -> industrial transition envelope
  -> READY_FOR_AUTHORITY_REVIEW
```

Every stage retains its own identity and authority boundary. Rejection or
unresolved verification leaves the retained source state unchanged.
