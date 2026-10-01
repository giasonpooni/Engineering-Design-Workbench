# Executable Interoperability Ingress V1

This increment treats industrial standards and proprietary schemas as inputs to
the existing NET identity, representation, preservation and transition system.

It does **not** attempt to replace STEP, OPC UA, MTConnect, vendor schemas,
PLM/MES/ERP/SCADA systems, or their own conformance machinery.

The executable seam is:

~~~text
external payload / standard profile
        ↓
interoperability profile
        ↓
retained payload occurrence
        ↓
profile + mapping verification
        ↓
qualified ingress
        ↓
entity-binding reference + representation/morphism/preservation identity
        ↓
existing industrial transition envelope
~~~

The core distinction is:

~~~text
transport/schema conformance
    != semantic preservation
    != physical validity
    != canonical-state admission
~~~

## 1. Interoperability profile

`ciw.interoperability-profile.v1` binds an external representation profile to
one exact existing scientific morphism and one exact preservation contract.

It records:

- source family: STANDARD or PROPRIETARY;
- optional internal standard identity for STANDARD sources;
- exact external profile identity;
- source-system identity;
- external schema label;
- exact morphism-registry identity;
- exact source and target representation identities;
- exact scientific morphism identity;
- exact preservation-contract identity;
- mapping identity and assumptions;
- uncertainty semantics;
- declared information-loss properties;
- verification requirements.

The profile itself establishes neither external-standard conformance nor
semantic preservation. Those are later verification obligations.

### Loss cannot be hidden

The profile's declared loss properties must equal the FORGET effects in the
bound preservation contract.

This prevents an adapter declaration from presenting a lossy map as lossless
merely because the external schema was successfully parsed.

## 2. Standard and proprietary sources share one ingress grammar

A STANDARD profile requires a non-null internal `standard_id`.

A PROPRIETARY profile requires `standard_id = null`.

Beyond that distinction, both participate in the same identity and semantic
contracts. The system does not grant a proprietary representation less rigor,
or a standardized representation more truth authority, merely because of its
origin.

This is intentional:

~~~text
STEP-like source ────────┐
OPC-UA-like source ──────┤
proprietary source ──────┼──> same NET preservation/identity discipline
other declared source ───┘
~~~

The current tests use standards-shaped synthetic labels only. There is no STEP,
OPC UA or MTConnect parser and no claim of certification against those standards.

## 3. Retained external ingress

`ciw.external-ingress.v1` records one concrete external payload occurrence.

It retains:

- exact payload content reference;
- media type;
- source identity fragment;
- explicit mapping parameters;
- mapping-evidence references;
- exact interoperability-profile identity.

Retaining the payload does not execute the mapping.

Therefore the record explicitly retains:

~~~text
mapping_executed = false
profile_conformance_established = false
semantic_preservation_established = false
identity_admission_performed = false
canonical_state_mutated = false
~~~

## 4. Verification

`ciw.external-ingress-verification.v1` requires exactly one check for every V1
interoperability obligation:

- PROFILE_CONFORMANCE;
- SOURCE_IDENTITY;
- REPRESENTATION_MAPPING;
- MAPPING_ASSUMPTIONS;
- UNCERTAINTY_HANDLING;
- PRESERVATION_PRECONDITIONS.

Statuses are VERIFIED, REFUTED and UNRESOLVED.

Method classes are:

- CONFORMANCE_TOOL;
- DECLARED_PROFILE;
- MAPPING_TEST;
- EVIDENCE_CROSSCHECK;
- HUMAN_ATTESTATION;
- NOT_PERFORMED.

Resolved checks require evidence and cannot use NOT_PERFORMED.

The receipt retains the method class because a profile declaration, an external
conformance tool, a mapping test and a human attestation are not interchangeable
kinds of evidence.

## 5. Qualification

`ciw.external-ingress-qualification.v1` recomputes the exact profile, payload
occurrence and verification bindings.

It returns:

~~~text
VERIFIED verification    -> QUALIFIED
REFUTED verification     -> REFUSED
otherwise                -> UNRESOLVED
~~~

QUALIFIED means only that the external occurrence is qualified to participate
in NET's identity and semantic workflow.

It still retains:

~~~text
mapping_executed = false
canonical_entity_created = false
state_admission_performed = false
physical_validity_established = false
canonical_state_mutated = false
~~~

## 6. Bridge into the existing identity layer

A recomputed QUALIFIED ingress can be projected into the exact reference shape
already consumed by `ciw.entity-binding.v1`.

The resulting reference uses the qualification record itself as its evidence
content reference.

Therefore the chain is explicit:

~~~text
external payload
    ↓
qualified ingress
    ↓
entity reference
    ↓
candidate entity binding
    ↓
identity verification
    ↓
industrial transition envelope
~~~

An UNRESOLVED or REFUSED ingress cannot be projected into an entity-binding
reference.

## 7. CLI

Create an interoperability profile:

~~~sh
net interop create-profile \
  morphism-registry.json \
  preservation-contract.json \
  profile-spec.json \
  --output profile.json
~~~

Retain an external payload occurrence:

~~~sh
net interop retain profile.json ingress-spec.json --output ingress.json
~~~

Retain profile/mapping verification:

~~~sh
net interop verify \
  profile.json ingress.json verification-spec.json \
  --output ingress-verification.json
~~~

Qualify the occurrence:

~~~sh
net interop qualify \
  morphism-registry.json preservation-contract.json \
  profile.json ingress.json ingress-verification.json \
  --output qualification.json
~~~

Project a qualified occurrence into the existing identity-binding reference
shape:

~~~sh
net interop identity-reference \
  morphism-registry.json preservation-contract.json \
  profile.json ingress.json ingress-verification.json qualification.json \
  --output identity-reference.json
~~~

## 8. Architectural meaning

The external standard becomes one evidence-bearing input to the execution loop,
not a source of automatic truth.

A successful external conformance check can establish that a payload satisfies
a declared external profile. It does not by itself establish that:

- the external identifier names the intended physical asset;
- the mapping into the NET representation preserves the required meaning;
- uncertainty was propagated correctly;
- a lossy transform is acceptable for the task;
- the physical source is calibrated;
- the candidate state should be admitted.

Those remain separate typed obligations.

## Non-claims

V1 does not:

- parse STEP, OPC UA, MTConnect or a proprietary industrial format;
- certify conformance against an external standard;
- execute a mapping transform;
- infer entity identity from strings;
- infer semantic preservation from schema validity;
- establish physical calibration or truth;
- admit canonical state;
- authorize physical action;
- replace external standards or certification systems.

The next substantive experiment is to attach a real retained external artifact
from an existing CIW workload to this ingress contract, execute its already
qualified mapping through an existing provider, and compare the runtime result
against the declared preservation contract.
