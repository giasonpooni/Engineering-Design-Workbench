"""Identity/determinism tests for `evidence/identity.py` and the
`make_*` factories in `evidence/types.py` -- the SCOUT-phase equivalent
of `tests/test_versioning.py`'s Version.id determinism coverage."""

from evidence.identity import canonical_json_bytes, content_hash
from evidence.types import (
    make_claimed_relationship,
    make_document,
    make_observation,
    make_record,
    make_referent,
    make_source,
)


def test_canonical_json_bytes_is_key_order_independent():
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert canonical_json_bytes(a) == canonical_json_bytes(b)


def test_content_hash_is_deterministic_across_calls():
    payload = {"kind": "paper", "name": "Journal of Polymer Science"}
    assert content_hash(payload) == content_hash(dict(payload))


def test_content_hash_differs_for_different_content():
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_source_identity_deterministic_same_name_and_kind_converge():
    s1 = make_source(kind="paper", name="Journal of Polymer Science")
    s2 = make_source(kind="paper", name="Journal of Polymer Science")
    assert s1.id == s2.id
    assert s1 == s2


def test_document_identity_same_content_same_source_converges():
    s = make_source(kind="paper", name="X")
    d1 = make_document(source_id=s.id, raw_content="hello", retrieval_method="fixture", retrieved_at="t1")
    d2 = make_document(source_id=s.id, raw_content="hello", retrieval_method="fixture", retrieved_at="t2")
    # retrieved_at is NOT part of identity -- same content/source/method converges
    # regardless of when it was retrieved.
    assert d1.id == d2.id


def test_document_identity_changes_with_content():
    s = make_source(kind="paper", name="X")
    d1 = make_document(source_id=s.id, raw_content="hello", retrieval_method="fixture", retrieved_at="t1")
    d2 = make_document(source_id=s.id, raw_content="hello v2", retrieval_method="fixture", retrieved_at="t1")
    assert d1.id != d2.id


def test_record_identity_scoped_to_document():
    r1 = make_record(document_id="doc-a", locator="p1", raw_content="x")
    r2 = make_record(document_id="doc-b", locator="p1", raw_content="x")
    assert r1.id != r2.id


def test_observation_identity_deterministic_for_same_extraction():
    """The core determinism requirement (`docs/SCOUT_ARCHITECTURE.md` §3):
    same source records + same extraction configuration -> same
    Observation.id, even if `extracted_at` differs."""
    o1 = make_observation(
        record_ids=("r1",),
        extraction_method="regex:kv_v1",
        content={"property": "melt_viscosity", "value": 1250},
        confidence=1.0,
        extracted_at="2026-01-01T00:00:00Z",
    )
    o2 = make_observation(
        record_ids=("r1",),
        extraction_method="regex:kv_v1",
        content={"value": 1250, "property": "melt_viscosity"},
        confidence=1.0,
        extracted_at="2026-06-01T00:00:00Z",
    )
    assert o1.id == o2.id


def test_observation_identity_changes_with_content():
    base = dict(record_ids=("r1",), extraction_method="regex:kv_v1", confidence=1.0, extracted_at="t")
    o1 = make_observation(content={"value": 1250}, **base)
    o2 = make_observation(content={"value": 1300}, **base)
    assert o1.id != o2.id


def test_observation_identity_changes_with_extraction_method():
    base = dict(record_ids=("r1",), content={"value": 1250}, confidence=1.0, extracted_at="t")
    o1 = make_observation(extraction_method="regex:kv_v1", **base)
    o2 = make_observation(extraction_method="model:mistral-v1", **base)
    assert o1.id != o2.id


def test_observation_confidence_out_of_range_rejected():
    import pytest

    with pytest.raises(ValueError):
        make_observation(
            record_ids=("r1",),
            extraction_method="regex:kv_v1",
            content={"value": 1},
            confidence=1.5,
            extracted_at="t",
        )


def test_referent_identity_same_natural_key_and_kind_converge():
    r1 = make_referent(natural_key="FEP", kind="material")
    r2 = make_referent(natural_key="FEP", kind="material")
    assert r1.id == r2.id


def test_referent_identity_different_natural_key_no_automatic_merge():
    """Entity resolution is explicitly deferred -- "FEP" and "Teflon FEP"
    must NOT converge on one Referent id just because a human knows
    they refer to the same material (`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §S)."""
    r1 = make_referent(natural_key="FEP", kind="material")
    r2 = make_referent(natural_key="Teflon FEP", kind="material")
    assert r1.id != r2.id


def test_claimed_relationship_identity_distinguishes_source_observation():
    """Two different Observations claiming the identical (from, to, type)
    relationship must NOT collapse to one edge -- conflicting/duplicate
    claims from different evidence must coexist (§E)."""
    rel1 = make_claimed_relationship(
        from_referent_id="a", to_referent_id="b", type="used_in", observation_id="obs-1", confidence=1.0
    )
    rel2 = make_claimed_relationship(
        from_referent_id="a", to_referent_id="b", type="used_in", observation_id="obs-2", confidence=1.0
    )
    assert rel1.id != rel2.id
