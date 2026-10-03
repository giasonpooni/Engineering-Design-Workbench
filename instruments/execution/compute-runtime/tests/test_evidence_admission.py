"""Admission gate tests -- the pool-level analogue of
`core/canonical/test_validation.py`'s coverage of `validate_candidate`:
atomic accept/reject, structural checks, referential integrity."""

from evidence.admission import (
    admit_claimed_relationship,
    admit_document,
    admit_observation,
    admit_record,
    admit_referent,
)
from evidence.pool import EvidencePool
from evidence.types import make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source


def test_admit_document_rejects_unknown_source():
    pool = EvidencePool()
    document = make_document(source_id="ghost", raw_content="x", retrieval_method="m", retrieved_at="t")
    result = admit_document(pool, document)
    assert isinstance(result, list)
    assert result[0].code == "UNKNOWN_SOURCE"


def test_admit_document_accepts_known_source():
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="x", retrieval_method="m", retrieved_at="t")
    result = admit_document(pool, document)
    assert result is document


def test_admit_record_rejects_unknown_document():
    pool = EvidencePool()
    record = make_record(document_id="ghost", locator="p1", raw_content="x")
    result = admit_record(pool, record)
    assert isinstance(result, list)
    assert result[0].code == "UNKNOWN_DOCUMENT"


def test_admit_observation_rejects_unknown_record():
    pool = EvidencePool()
    obs = make_observation(
        record_ids=("ghost",), extraction_method="regex:kv_v1", content={"v": 1}, confidence=1.0, extracted_at="t"
    )
    result = admit_observation(pool, obs)
    assert isinstance(result, list)
    assert any(e.code == "UNKNOWN_RECORD" for e in result)


def test_admit_observation_rejects_empty_content():
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="x", retrieval_method="m", retrieved_at="t")
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="p1", raw_content="x")
    pool.put_record(record)
    obs = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1", content={}, confidence=1.0, extracted_at="t"
    )
    result = admit_observation(pool, obs)
    assert isinstance(result, list)
    assert any(e.code == "EMPTY_CONTENT" for e in result)


def test_admit_referent_rejects_empty_natural_key():
    pool = EvidencePool()
    referent = make_referent(natural_key="", kind="material")
    result = admit_referent(pool, referent)
    assert isinstance(result, list)
    assert any(e.code == "EMPTY_NATURAL_KEY" for e in result)


def test_admit_claimed_relationship_rejects_unknown_referents():
    pool = EvidencePool()
    rel = make_claimed_relationship(
        from_referent_id="ghost1", to_referent_id="ghost2", type="used_in", observation_id="ghost-obs", confidence=1.0
    )
    result = admit_claimed_relationship(pool, rel)
    assert isinstance(result, list)
    codes = {e.code for e in result}
    assert "UNKNOWN_REFERENT" in codes
    assert "UNKNOWN_OBSERVATION" in codes


def test_admit_claimed_relationship_accepts_when_referents_and_observation_exist():
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="x", retrieval_method="m", retrieved_at="t")
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="p1", raw_content="x")
    pool.put_record(record)
    obs = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1", content={"v": 1}, confidence=1.0, extracted_at="t"
    )
    pool.put_observation(obs)
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    pool.put_referent(fep)
    pool.put_referent(extrusion)

    rel = make_claimed_relationship(
        from_referent_id=fep.id, to_referent_id=extrusion.id, type="used_in", observation_id=obs.id, confidence=1.0
    )
    result = admit_claimed_relationship(pool, rel)
    assert result is rel


def test_admission_rejection_never_mutates_pool():
    """Atomicity: a rejected candidate leaves the pool untouched --
    mirrors `validate_candidate`'s own "on failure, base is left
    untouched" guarantee, one layer upstream."""
    pool = EvidencePool()
    size_before = len(pool)
    bad_obs = make_observation(
        record_ids=("ghost",), extraction_method="regex:kv_v1", content={"v": 1}, confidence=1.0, extracted_at="t"
    )
    result = admit_observation(pool, bad_obs)
    assert isinstance(result, list)
    # admission itself never calls pool.put_*; only the caller does, and only on success.
    assert len(pool) == size_before
