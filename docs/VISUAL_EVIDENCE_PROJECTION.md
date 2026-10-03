# Visual Evidence Projection V1

This increment adds a read-only evidence layer to the Visual System Board. It is
stacked on the existing visual representation gate and does not alter
intervention authority.

The selected node can now answer four separate questions:

1. What representation is declared here?
2. What exact retained content realizes that representation?
3. What finite morphism witness exists for this retained execution?
4. What remains unverified or scientifically unresolved?

## Identity separation

    representation declaration
            !=
    representation realization
            !=
    morphism witness
            !=
    operation-result verification
            !=
    physical validity
            !=
    intervention authority

A realization is therefore not a proof or verification certificate.

## Representation realization

The new ciw.representation-realization.v1 record has two bounded forms.

### SOURCE_CHANNEL

A validated retained channel is bound to a representation whose declared schema
is ciw.run-channel.v1.

The record retains the exact representation and source-evidence identities,
channel and half-open interval, a digest of the exact selected retained samples,
unit, coordinate frame, sample count, sample rate, retained source provenance,
and declared uncertainty semantics.

It does not create a second scientific state artifact.

### OPERATION_RESULT

A validated retained operation result is bound to the codomain of an explicit
scientific morphism.

The record checks exact source evidence identity, execution/result integrity and
pairing, the trusted saved-payload schema, semantic-capability lowering, and the
exact morphism codomain representation.

Execution, result, and realized-data content references remain distinct.

The ordinary operation-result verification status remains unchanged. In the
oscillator fixture it remains not_verified.

## Finite morphism witness

For a retained source realization and retained result realization connected by
one declared morphism, the evidence layer creates an ordinary
ciw.morphism-witness.v1.

Four checks are established from retained records:

- domain realization: PASS;
- source provenance retained: PASS;
- execution/result binding: PASS;
- codomain realization: PASS.

Two obligations intentionally remain unresolved:

- general preservation obligations: UNRESOLVED;
- empirical physical validity: UNRESOLVED.

The qualified periodogram fixture therefore reports:

    PASS        4
    FAIL        0
    UNRESOLVED  2

    general morphism law proved: false
    physical validity established: false

Schema conformance is not promoted into a universal preservation claim.

## Board evidence projection

ciw.board-evidence-projection.v1 is derived only after a completed retained
baseline graph-run exists.

It binds the exact Board revision, completed baseline, source evidence, morphism
registry, and Board intervention binding.

Each bound operation node receives:

- current representation;
- current representation realization;
- source realization;
- optional derived-result realization;
- optional morphism witness;
- witness summary;
- result-record verification state;
- representation/morphism uncertainty declarations;
- source and declaration provenance;
- explicit physical_validity = NOT_ESTABLISHED.

The whole projection is recomputed by its validator. Re-sealing changed content
does not make the projection valid.

## Visual behavior

Before a baseline executes, the Board says:

    Evidence projection
    Awaiting retained baseline

After a qualified baseline:

    Evidence projection
    Realizations + finite witnesses retained

Selecting Signal statistics shows a SOURCE_CHANNEL realization. No morphism
witness is invented because the currently bound representation is the retained
source signal itself.

Selecting Periodogram shows an OPERATION_RESULT realization plus its finite
morphism witness. The inspector separately reports:

    record verification: not_verified
    finite witness: FINITE_WITNESS_WITH_UNRESOLVED
    physical validity: NOT_ESTABLISHED
    uncertainty: no uncertainty model declared

The complete retained evidence projection remains inspectable as JSON.

## Candidate execution does not rewrite baseline evidence

The evidence projection is explicitly bound to the completed baseline.

Running a LOCAL Needle or an EXPAND-promoted Needle does not rewrite that record.
Candidate execution already has its own operation/result/delta identities.

A future candidate-evidence projection can be added as a second record; it should
not silently mutate the baseline evidence layer.

## Relationship to LOCAL / EXPAND / REFUSE

Evidence visibility and intervention authority remain orthogonal.

                     evidence projection
                            |
           +----------------+----------------+
           |                                 |
      realization/witness              intervention gate
           |                                 |
    read-only evidence          LOCAL / EXPAND / REFUSE

A morphism witness with unresolved preservation does not grant LOCAL authority.
Likewise a LOCAL intervention does not imply physical verification.

The existing representation contract remains the only input to the intervention
gate.

## Qualified oscillator examples

Signal statistics:

    representation:
      signal.timeseries.uniform-scalar.v1

    realization:
      SOURCE_CHANNEL
      q
      m
      exact retained evidence

    morphism witness:
      none

    record verification:
      not applicable

    physical validity:
      NOT_ESTABLISHED

Periodogram:

    representation:
      signal.periodogram.one-sided-density.v1

    source realization:
      SOURCE_CHANNEL(q)

    result realization:
      OPERATION_RESULT(periodogram)

    morphism:
      signal.periodogram.transform.v1

    finite witness:
      4 PASS
      0 FAIL
      2 UNRESOLVED

    result verification:
      not_verified

    physical validity:
      NOT_ESTABLISHED

## Boundaries

This increment does not admit canonical state, add a new verification identity,
change operation-result verification status, prove every morphism preservation
obligation, infer physical calibration, infer independence from separate
uncertainty declarations, authorize LOCAL intervention, authorize physical
actuation, mutate baseline evidence after candidate execution, or execute a
provider merely to render the evidence panel.

## Next bounded seam

The next evidence-layer extension should attach candidate and comparison evidence
as separate projections: baseline realization, candidate realization,
delta/comparison, verification occurrence, and acceptance/admission decision
should remain individually addressable on the same visual node.
