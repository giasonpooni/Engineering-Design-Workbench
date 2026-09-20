# The plane architecture, measured — and its key invariant, built

## What the specification names, and what the tree has

| | |
|---|---|
| module-family concepts named | **61** |
| present across the three apparatuses | **21** |
| absent | **40** |

Matched **by name**, which is a stated weakness rather than a hidden one:
a concept implemented under a different word reads as absent. The
measurement is therefore a *lower bound on coverage* and an *upper bound
on the gap* — it over-reports what is missing rather than what exists,
which is the direction that fails safe.

That 21-of-61 is **not a criticism**. A design is allowed to describe
what is not built yet. It is recorded because a document describing a
system reads exactly the same whether the system exists or not, and this
is the only thing that tells them apart.

## One absence is different in kind

`tenant`, `http`, `mcp`, `token`, `signature`.

**Three of the four planes are defined as tenant-bound, and no tenant
concept exists anywhere in the three apparatuses.** A plane distinction
resting on an authority boundary the tree does not have cannot be
enforced.

An API carrying tenant-shaped names with no tenant enforcement **reads as
isolated while isolating nothing** — which is worse than one that never
claimed to, because the claim is what a reader relies on. The rest of the
forty are work not yet done. This one is a claim the architecture cannot
currently keep, and it is separated in the artifact so that "40 missing"
does not flatten the distinction.

## What was built instead: the key invariant, as a type

> every API response should either include a canonical reference and
> proof root, or explicitly say it is an operational observation with its
> limitations

`api/envelope.py`. It is the one part of the architecture buildable
before any of the absent concepts — it needs no tenant, no HTTP host, no
signer.

**It is a type and not a convention** because a convention is satisfied
by whoever remembers it, and the response that forgets is
indistinguishable from the response that had nothing to say. That shape
has appeared four times in this project — an unreached gate reading as a
clean rate, a dropped field looking like one that never existed, a
silence read as cleanliness, a register stale about itself — and the fix
each time was to make the absent case a **stated** case rather than a
missing one.

So there is **no third construction**. Both arms refuse their own
malformations at construction:

- a **reference without a proof root** is refused — a reference whose
  position cannot be checked is a citation, not a warrant, and an
  unresolvable citation is the shape a fabricated one takes
- an **observation with no limitations** is refused — it would be a
  canonical claim wearing a disclaimer, and this arm exists so ungrounded
  answers are *stated*, not so they are permitted quietly
- an observation that does not say **why** it is not canonical is refused
  — otherwise a reader cannot tell a deliberate observation from a lost
  proof

### Never public canonical CRUD, enforced

The plane table declares each plane's mutation posture. Three planes are
read-only **by construction**: a response from them that reports a
mutation cannot be built. Only `internal_operator` may say it changed
anything. A fifth plane cannot be introduced by spelling one — an
undeclared plane is refused.

This is not access control. It is the *shape of the plane*, and it is
checkable here because it is a property of the response rather than of
the caller.

### Every response carries the engine digest

A version label is a compatibility statement, and many builds share one.
Without the digest a stored answer cannot be checked later against the
build that produced it — the same gap `docs/CORE_IDENTITY.md` closes for
the core, applied at the response boundary. A response with no digest is
refused.

**Which digest is the plane's choice, and it matters.** This repository
holds two disjoint tracks with separate published digests (see
`docs/CORE_IDENTITY.md`). The envelope is deliberately agnostic — it
carries whatever the caller stamps — but a plane serving evidence-platform
data that stamped the twin-compiler digest would be publishing a
fingerprint of code it does not run. That is the same defect
`covers_what_is_bound` exists to refuse, arriving at the response
boundary by a different door. The lock drives both surfaces and asserts
they differ: two tracks reporting one digest would leave the stamp unable
to say which engine answered.

## What the envelope deliberately does not do

It does not authenticate, authorise, or bind a tenant. **None of those
concepts exists in this tree**, and an envelope carrying a `tenant_id`
field that nothing enforces would be the most dangerous object here. A
lock asserts no such field exists, and a mutant that adds one is killed.

The plane is declared and its mutation posture is enforced; *who may call
it* is not this module's claim to make.
