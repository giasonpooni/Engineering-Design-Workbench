# Industrial Semantic Transitions V1

This increment begins the industrial integration layer above the existing
representation, morphism and preservation machinery.

Its purpose is not to replace PLM, MES, ERP, SCADA, historians, QMS, simulation
or document systems. It supplies a bounded computational seam between their
claims about the same physical entity and a proposed canonical-state transition.

The implemented path is:

~~~text
cross-system references
      ↓
candidate entity binding
      ↓
identity verification
      ↓
retained source state
      ↓
candidate state proposal
      ↓
preservation verification + eligibility gate
      ↓
industrial transition envelope
      ↓
READY_FOR_AUTHORITY_REVIEW / REFUSED / UNRESOLVED
      ↓
separate admission authority
~~~

No state-admission operation is added.

## 1. Cross-system identity binding

`ciw.entity-binding.v1` collects external identifiers that are proposed to refer
to one already named canonical entity.

A reference records a versioned source-system identity, namespace, external
identifier, object kind, and exact evidence content reference.

V1 object kinds include PHYSICAL_ASSET, CAD_OBJECT, BIM_OBJECT, SENSOR_TAG,
ERP_ASSET, MES_ASSET, QMS_RECORD, SIMULATION_VARIABLE, SPECIFICATION, DOCUMENT
and OTHER.

The record is explicitly a **candidate identity map**. It does not create a
canonical entity, admit identity, modify canonical state or execute a provider.

~~~text
CAD PUMP-17 ───────┐
SCADA PT_017 ──────┼──> candidate canonical entity: asset-17
ERP EQ00017 ───────┘
~~~

The point is not that these strings are equal. Their proposed equivalence is
made explicit, content-bound and independently verifiable.

## 2. Identity verification

`ciw.entity-binding-verification.v1` must cover every reference in the exact
binding. Each check retains reference identity, VERIFIED / REFUTED / UNRESOLVED,
verification method, evidence reference when resolved, and notes.

V1 method classes are EXACT_IDENTIFIER, DECLARED_MAPPING, CROSS_SYSTEM_EVIDENCE,
HUMAN_ATTESTATION and NOT_PERFORMED. A resolved check cannot use NOT_PERFORMED.

Aggregation is conservative:

~~~text
any REFUTED     -> REFUTED
all VERIFIED    -> VERIFIED
otherwise       -> UNRESOLVED
~~~

Identity verification is not identity admission.

## 3. Industrial transition envelope

`ciw.industrial-transition-envelope.v1` binds one proposed state transition to:

- exact source-state content identity;
- exact candidate-state content identity;
- exact entity binding;
- exact identity-verification receipt;
- exact preservation contract;
- exact preservation-verification receipt;
- exact preservation admission-eligibility gate;
- proposer identity/kind;
- the external authority class required for final admission.

The envelope requires the preservation verification to refer to the same source
and candidate state records supplied to the transition. This prevents a valid
semantic receipt for one candidate from being attached to another candidate.

It also checks that source and candidate state entity IDs agree with the
canonical entity named by the identity binding.

## 4. Readiness semantics

### READY_FOR_AUTHORITY_REVIEW

Requires matching source/candidate entity identity, VERIFIED cross-system
identity, ELIGIBLE preservation, and exact content bindings.

This does **not** mean admitted. It means identity continuity and semantic
continuity have been established under the supplied records sufficiently to
hand the proposal to the separately named admission authority.

### REFUSED

Examples include a candidate attached to another physical entity, REFUTED
identity verification, or REFUSED preservation.

### UNRESOLVED

Examples include an unresolved source-system identity relationship or unresolved
preservation obligation. The canonical source state remains unchanged.

## 5. Proposal provenance

The envelope records who or what proposed the candidate. V1 proposer kinds are
HUMAN, LLM, OPTIMIZER, SOLVER, SIMULATOR, RULE_SYSTEM and OTHER.

This conveys provenance only. Every proposer passes through the same identity,
preservation and authority boundaries.

## 6. CLI

Create a cross-system identity binding:

~~~sh
net transition bind-identity identity-binding-spec.json --output identity-binding.json
~~~

Verify the identity map:

~~~sh
net transition verify-identity identity-binding.json identity-verification-spec.json --output identity-verification.json
~~~

Create the transition envelope:

~~~sh
net transition envelope \
  source-state.json \
  candidate-state.json \
  identity-binding.json \
  identity-verification.json \
  morphism-registry.json \
  preservation-contract.json \
  preservation-verification.json \
  preservation-gate.json \
  transition-spec.json \
  --output transition-envelope.json
~~~

Inspection is read-only. Transition-envelope inspection requires the exact
dependencies so derived readiness is recomputed rather than trusted from a
valid hash alone.

## 7. Industrial interpretation

The layer does not claim ERP, MES, PLM, SCADA, QMS or simulation systems lack
mature internal controls. It addresses a different question:

> Do their claims refer to the same physical entity, and does the meaning
> required for a proposed state transition survive the transformations between
> them?

The reusable grammar is:

~~~text
IDENTITY
    What object is this?

MEANING
    What is preserved, transformed, bounded, forgotten or required?

AUTHORITY
    Who is allowed to turn the verified proposal into canonical state?
~~~

V1 implements the first two as explicit computational gates and stops at the
handoff to the third.

## 8. Machine-intelligence boundary

A machine may propose:

~~~text
S_t -> S_hat_(t+1)
~~~

The transition envelope does not care whether that proposal came from an LLM,
optimizer, simulator, rule system or human. A candidate becomes
READY_FOR_AUTHORITY_REVIEW only if retained identity and semantic-continuity
records support it.

Thus machine intelligence is a proposal/search mechanism inside the
state-transition system, not the owner of canonical truth.

## Non-claims

V1 does not establish that an arbitrary supplied source state is globally canonical,
connect to a live ERP/PLM/MES/SCADA product, discover entity
equivalence automatically, admit a canonical entity, mutate canonical state,
execute a physical action, infer identity from string similarity, infer semantic
preservation from an API/schema match, grant admission authority to a proposer,
or implement a universal industrial ontology.

The next useful experiment is to bind one genuinely heterogeneous retained
workload, such as CAD/BIM identity + sensor evidence + simulation state, to this
envelope and measure how much manual reconciliation remains.
