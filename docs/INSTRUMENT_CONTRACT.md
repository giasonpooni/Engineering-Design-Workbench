# Portable instrument contract

Notation Systems instruments should expose one portable machine-readable surface
in addition to their domain API:

```text
Problem → Inputs → Model → Computation → Output → Verification → Limits
```

The repository owns its mathematics and implementation. NET owns investigation,
composition and dispatch. A portable manifest does not move the implementation
into NET.

## notations.instrument.v1

The portable manifest carries:

- instrument identity and lifecycle maturity;
- numerical/domain operation identity;
- stable semantic capability identity;
- typed input/output ports;
- declared effects;
- provider/runtime family and execution profile;
- model, human-facing input/output descriptions and explicit limits;
- verification and representation locations.

Lifecycle vocabulary is descriptive rather than a quality ranking:

- **EXPERIMENT** — hypothesis/work under investigation;
- **REFERENCE** — minimal implementation of the mathematics;
- **INSTRUMENT** — tested API, examples and verification surface;
- **RELEASE** — versioned/package-published external release.

A manifest is data. It **cannot bind executable code**.

## notations.verification.v1

A verification report binds the instrument identity and operation identity to a
specific source revision and records claims/exclusions. Individual instruments
may add numerical/reference/build evidence.

NET requires the core identities to agree and, when a JUnit summary is supplied,
requires at least one test and zero failures, errors and skips before accepting
the report as a checked portable verification document.

This means:

```text
verified manifest
       ↓
advertised provider
       ↓
UNBOUND
```

not:

```text
verified manifest → executable provider
```

Trusted installed adapter code must still be explicitly bound through the
original CapabilityRegistry before the semantic resolver can select it.

## Semantic-plane attachment

The portable contract maps into the semantic-capability plane:

- typed ports → semantic objects;
- semantic capability → morphism;
- provider metadata → functor-like engine lowering;
- verification digest/source revision → retained provider identity.

Engine/runtime metadata does not confer authority. A saved file cannot select a
binary path, dynamically import code, mount a container, merge source, admit
state or actuate equipment.

Example:

```sh
net instrument inspect instrument.json --verification verification.json
```

returns the unbound concrete/semantic catalogs and the ingest descriptor. It
starts no provider.

ClockSync is the first repository intended to exercise the contract. The schema
is deliberately small; extend it only after a second/third instrument exposes a
real missing invariant rather than adding domain-specific fields to NET.
