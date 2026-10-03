"""Locks on the response envelope.

THE INVARIANT, AS THE ARCHITECTURE STATES IT: every API response either
includes a canonical reference and proof root, or explicitly says it is
an operational observation with its limitations.

It is a TYPE and not a convention because a convention is satisfied by
whoever remembers it, and the response that forgets is indistinguishable
from the response that had nothing to say. That shape has appeared four
times in this project already -- an unreached gate reading as a clean
rate, a dropped field looking like one that never existed, a silence
read as cleanliness, a register stale about itself -- and the fix each
time was to make the absent case a STATED case rather than a missing
one.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


from api import envelope as env

DIGEST = "sha256:" + "a" * 64


# ------------------------------------------- there is no third arm --


def test_a_response_is_grounded_or_says_it_is_not():
    grounded = env.grounded("tenant_read", {"x": 1}, "sha256:ref", "root:1", DIGEST)
    observed = env.observed("governance", {"lag": 4}, "replica lag",
                            ("sampled once",), "no canonical record of lag", DIGEST)
    assert grounded.is_grounded is True
    assert observed.is_grounded is False


def test_there_is_no_third_construction():
    """Anything that is neither arm cannot be built at all."""
    with pytest.raises(env.EnvelopeError):
        env.Envelope(plane="tenant_read", payload={}, grounding="nothing",
                     engine_digest=DIGEST)
    with pytest.raises(env.EnvelopeError):
        env.Envelope(plane="tenant_read", payload={}, grounding=None,
                     engine_digest=DIGEST)


def test_both_arms_are_reachable_so_the_distinction_is_not_decorative():
    """An envelope type that only ever produced one arm would be a
    wrapper, and every response would be grounded by fiat."""
    arms = {
        type(env.grounded("verification", {}, "r", "p", DIGEST).grounding),
        type(env.observed("governance", {}, "o", ("l",), "b", DIGEST).grounding),
    }
    assert arms == {env.CanonicalReference, env.OperationalObservation}


# ------------------------------------------ each arm refuses its own --


def test_a_reference_without_a_proof_root_is_refused():
    """A reference whose position cannot be checked is a citation, not a
    warrant -- and an unresolvable citation is the shape a fabricated
    one takes."""
    with pytest.raises(env.EnvelopeError):
        env.CanonicalReference(reference="sha256:ref", proof_root="")
    with pytest.raises(env.EnvelopeError):
        env.CanonicalReference(reference="", proof_root="root:1")


def test_an_observation_with_no_limitations_is_refused():
    """It would be a canonical claim wearing a disclaimer. This arm
    exists so ungrounded answers are STATED, not so they are permitted
    quietly."""
    with pytest.raises(env.EnvelopeError):
        env.OperationalObservation(observed="lag", limitations=(),
                                   not_canonical_because="no record")


def test_an_observation_must_say_why_it_is_not_canonical():
    """Otherwise a reader cannot tell a deliberate observation from a
    lost proof."""
    with pytest.raises(env.EnvelopeError):
        env.OperationalObservation(observed="lag", limitations=("sampled",),
                                   not_canonical_because="")


# ---------------------------------------- never public canonical CRUD --


def test_a_read_only_plane_cannot_report_a_mutation():
    for plane in ("tenant_read", "verification", "governance"):
        with pytest.raises(env.EnvelopeError):
            env.grounded(plane, {}, "r", "p", DIGEST, reports_mutation=True)


def test_the_operator_plane_is_the_only_one_that_may():
    assert env.MUTATING_PLANES == ("internal_operator",)
    allowed = env.grounded("internal_operator", {}, "r", "p", DIGEST,
                           reports_mutation=True)
    assert allowed.reports_mutation is True


def test_every_declared_plane_is_in_the_table_and_no_others():
    """A plane not in the table is refused, so a fifth plane cannot be
    introduced by spelling one."""
    assert set(env.PLANES) == {"tenant_read", "verification", "governance",
                               "internal_operator"}
    with pytest.raises(env.EnvelopeError):
        env.grounded("public_admin", {}, "r", "p", DIGEST)


# ------------------------------------------------- the engine digest --


def test_a_response_without_an_engine_digest_is_refused():
    """A version label is a compatibility statement and many builds
    share one. Without the digest a stored answer cannot be checked
    later against the build that produced it."""
    with pytest.raises(env.EnvelopeError):
        env.grounded("tenant_read", {}, "r", "p", "")


def test_the_digest_the_core_reports_is_acceptable_as_one():
    """It must be the real thing, not a shape that merely looks like
    one -- otherwise the field is decorative.

    Driven over BOTH published surfaces. This repository holds two
    disjoint tracks and the envelope is deliberately agnostic between
    them: it carries whichever digest the caller stamps. The choice of
    WHICH belongs to the plane, and a plane serving evidence-platform
    data that stamped the twin-compiler digest would be publishing a
    fingerprint of code it does not run -- the defect `core_identity`
    exists to refuse, arriving here by a different door."""
    from architecture.core_identity import SURFACES, core_digest

    root = pathlib.Path(__file__).resolve().parent.parent
    seen = set()
    for name, surface in SURFACES.items():
        digest = core_digest(root, surface)
        seen.add(digest)
        assert env.grounded("verification", {}, "r", "p", digest).engine_digest == digest
    assert len(seen) == len(SURFACES), (
        "two tracks reporting one digest would make the stamp unable to "
        "say which engine answered")


# ------------------------------------------- what it does NOT claim --


def test_the_envelope_makes_no_tenancy_claim():
    """Three of the four planes are defined as tenant-bound and no
    tenant concept exists in this tree. An envelope carrying a tenant
    field nothing enforces would read as isolated while isolating
    nothing, which is worse than one that never claimed to."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(env.Envelope)}
    assert not any("tenant" in name for name in fields)
    assert not any("auth" in name for name in fields)
    assert "does not authenticate, authorise, or bind a tenant" in env.__doc__ \
        or "does not authenticate" in (env.__doc__ or "")


def test_the_payload_is_not_mutable_through_the_envelope():
    response = env.grounded("tenant_read", {"x": 1}, "r", "p", DIGEST)
    with pytest.raises(TypeError):
        response.payload["x"] = 2
