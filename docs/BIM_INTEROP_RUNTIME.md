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
