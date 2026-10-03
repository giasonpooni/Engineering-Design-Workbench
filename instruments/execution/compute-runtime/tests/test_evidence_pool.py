"""EvidencePool: idempotent puts, non-deletion, conflict coexistence,
serialization/round-trip."""

from evidence.identity import canonical_json_bytes
from evidence.pool import EvidencePool
from evidence.types import make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source


def _seeded_pool():
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="body", retrieval_method="fixture", retrieved_at="t")
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="p1", raw_content="body")
    pool.put_record(record)
    return pool, source, document, record


def test_duplicate_put_is_idempotent():
    pool, source, document, record = _seeded_pool()
    size_before = len(pool)
    pool.put_source(source)
    pool.put_document(document)
    pool.put_record(record)
    assert len(pool) == size_before


def test_pool_never_loses_conflicting_observations():
    """Two different sources reporting different values for the same
    thing must both survive in the pool, unmodified -- §E's conflict
    model, exercised at the pool level."""
    pool, source, document, record = _seeded_pool()
    o1 = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1", content={"value": 1200}, confidence=1.0, extracted_at="t"
    )
    o2 = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1", content={"value": 1300}, confidence=1.0, extracted_at="t"
    )
    pool.put_observation(o1)
    pool.put_observation(o2)
    assert o1.id != o2.id
    stored = pool.all_observations()
    assert len(stored) == 2
    assert {o.id for o in stored} == {o1.id, o2.id}
    assert {dict(o.content)["value"] for o in stored} == {1200, 1300}


def test_observations_about_and_relationships_touching():
    pool, source, document, record = _seeded_pool()
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    pool.put_referent(fep)
    pool.put_referent(extrusion)
    obs = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1", content={"value": 1}, confidence=1.0, extracted_at="t"
    )
    pool.put_observation(obs)
    rel = make_claimed_relationship(
        from_referent_id=fep.id, to_referent_id=extrusion.id, type="used_in", observation_id=obs.id, confidence=1.0
    )
    pool.put_claimed_relationship(rel)

    assert pool.observations_about(fep.id) == (obs,)
    assert pool.relationships_touching(fep.id) == (rel,)
    assert pool.relationships_touching(extrusion.id) == (rel,)
    assert pool.observations_about("nonexistent") == ()


def test_pool_has_no_delete_method():
    """Non-deletion is structural, not just a convention: EvidencePool
    exposes no delete/remove method for any object type (§B: Document/
    Record/Observation/Referent/ClaimedRelationship are all "No" under
    "Deletable?")."""
    pool = EvidencePool()
    for name in dir(pool):
        assert "delete" not in name.lower() and "remove" not in name.lower(), (
            f"EvidencePool exposes {name!r} -- pool objects must never be deletable"
        )


def test_fingerprint_identical_for_identical_state():
    """Two independently-built pools holding the identical set of
    objects fingerprint identically -- `fingerprint()` is a pure
    function of pool contents, not of which process or order built
    them."""
    pool_a, source_a, document_a, record_a = _seeded_pool()
    pool_b, source_b, document_b, record_b = _seeded_pool()
    assert source_a.id == source_b.id  # content-addressed: same inputs, same ids
    assert pool_a.fingerprint() == pool_b.fingerprint()


def test_fingerprint_changes_when_evidence_is_added():
    pool, source, document, record = _seeded_pool()
    before = pool.fingerprint()
    pool.put_referent(make_referent(natural_key="FEP", kind="material"))
    after = pool.fingerprint()
    assert before != after


def test_fingerprint_unchanged_by_redundant_put_of_identical_object():
    """Re-putting an object that is already present (same content, same
    content-addressed id) must NOT change the fingerprint -- this is
    the "duplicate evidence" case, and by construction it is a true
    no-op, not merely a fingerprint coincidence."""
    pool, source, document, record = _seeded_pool()
    before = pool.fingerprint()
    pool.put_source(source)
    pool.put_document(document)
    pool.put_record(record)
    assert pool.fingerprint() == before


def test_fingerprint_is_insensitive_to_insertion_order():
    """Insertion order carries no semantics for this pool (its own
    module docstring: "no single current state" -- conflicting,
    coexisting objects are the point). Two pools built by inserting the
    identical objects in reverse order must fingerprint identically."""
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    rheo = make_referent(natural_key="rheo-sim", kind="software")

    pool_forward = EvidencePool()
    for r in (fep, extrusion, rheo):
        pool_forward.put_referent(r)

    pool_reverse = EvidencePool()
    for r in (rheo, extrusion, fep):
        pool_reverse.put_referent(r)

    assert pool_forward.fingerprint() == pool_reverse.fingerprint()


def test_fingerprint_does_not_depend_on_python_hash_randomization():
    """Cross-process check: PYTHONHASHSEED only takes effect at
    interpreter startup, so this cannot be exercised in-process --
    mirrors `tests/test_versioning.py`'s and `tests/test_trust_graph.py`'s
    own PYTHONHASHSEED subprocess checks."""
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.pool import EvidencePool\n"
        "from evidence.types import make_document, make_record, make_referent, make_source\n"
        "pool = EvidencePool()\n"
        "s = make_source(kind='paper', name='X')\n"
        "pool.put_source(s)\n"
        "d = make_document(source_id=s.id, raw_content='body', retrieval_method='fixture', retrieved_at='t')\n"
        "pool.put_document(d)\n"
        "r = make_record(document_id=d.id, locator='p1', raw_content='body')\n"
        "pool.put_record(r)\n"
        "for key in ('FEP', 'extrusion', 'rheo-sim'):\n"
        "    pool.put_referent(make_referent(natural_key=key, kind='material'))\n"
        "print(pool.fingerprint())\n"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout)
    assert len(outputs) == 1, f"fingerprint differed across PYTHONHASHSEED values: {outputs}"


def test_fingerprint_history_empty_for_new_pool():
    pool = EvidencePool()
    assert pool.fingerprint_history() == ()


def test_fingerprint_history_first_observed_fingerprint():
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    assert pool.fingerprint_history() == (pool.fingerprint(),)


def test_fingerprint_history_unaffected_by_repeated_duplicate_put():
    pool, source, document, record = _seeded_pool()
    history_before = pool.fingerprint_history()
    pool.put_source(source)
    pool.put_source(source)
    pool.put_document(document)
    assert pool.fingerprint_history() == history_before


def test_fingerprint_history_duplicate_evidence_from_independent_reconstruction_is_still_a_no_op():
    """A second, independently-constructed object with identical content
    (same content-addressed id, built via a fresh make_* call rather than
    reusing the original object reference) must behave exactly like
    re-putting the same object -- no new history entry."""
    pool, source, document, record = _seeded_pool()
    history_before = pool.fingerprint_history()
    same_source_again = make_source(kind="paper", name="X")
    assert same_source_again.id == source.id
    pool.put_source(same_source_again)
    assert pool.fingerprint_history() == history_before


def test_fingerprint_history_grows_by_one_entry_on_genuine_change():
    pool, source, document, record = _seeded_pool()
    length_before = len(pool.fingerprint_history())
    pool.put_referent(make_referent(natural_key="FEP", kind="material"))
    history_after = pool.fingerprint_history()
    assert len(history_after) == length_before + 1
    assert history_after[-1] == pool.fingerprint()


def test_fingerprint_history_preserves_chronological_order():
    """The one place in EvidencePool where insertion order IS semantically
    meaningful -- a deliberate exception to fingerprint()'s own
    order-independence (`docs/RETRIEVAL_ARCHITECTURE.md` §6)."""
    pool = EvidencePool()
    pool.put_referent(make_referent(natural_key="FEP", kind="material"))
    fp1 = pool.fingerprint()
    pool.put_referent(make_referent(natural_key="extrusion", kind="process"))
    fp2 = pool.fingerprint()
    pool.put_referent(make_referent(natural_key="rheo-sim", kind="software"))
    fp3 = pool.fingerprint()

    assert pool.fingerprint_history() == (fp1, fp2, fp3)


def test_fingerprint_history_returns_immutable_snapshot():
    """A tuple already captured from fingerprint_history() must not
    retroactively grow when more evidence is added afterward -- proves a
    defensive copy was taken, not a live view over internal state."""
    pool, source, document, record = _seeded_pool()
    captured = pool.fingerprint_history()
    pool.put_referent(make_referent(natural_key="FEP", kind="material"))
    grown = pool.fingerprint_history()
    assert captured != grown
    assert len(grown) == len(captured) + 1
    assert grown[: len(captured)] == captured  # the captured prefix is untouched


def test_fingerprint_history_accessor_has_no_side_effects():
    pool, source, document, record = _seeded_pool()
    before = pool.fingerprint_history()
    for _ in range(5):
        pool.fingerprint_history()
        pool.fingerprint()
    assert pool.fingerprint_history() == before


def test_fingerprint_history_deterministic_across_hash_seeds():
    """Same discipline as
    `test_fingerprint_does_not_depend_on_python_hash_randomization`
    above, applied to `fingerprint_history()`'s sequence and content --
    including a redundant put, to confirm the no-op case is itself
    hash-seed independent, not just the growth case."""
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.pool import EvidencePool\n"
        "from evidence.types import make_document, make_record, make_referent, make_source\n"
        "pool = EvidencePool()\n"
        "s = make_source(kind='paper', name='X')\n"
        "pool.put_source(s)\n"
        "pool.put_source(s)\n"
        "d = make_document(source_id=s.id, raw_content='body', retrieval_method='fixture', retrieved_at='t')\n"
        "pool.put_document(d)\n"
        "r = make_record(document_id=d.id, locator='p1', raw_content='body')\n"
        "pool.put_record(r)\n"
        "for key in ('FEP', 'extrusion', 'rheo-sim'):\n"
        "    pool.put_referent(make_referent(natural_key=key, kind='material'))\n"
        "print(pool.fingerprint_history())\n"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout)
    assert len(outputs) == 1, f"fingerprint_history differed across PYTHONHASHSEED values: {outputs}"


def test_fingerprint_history_entries_are_all_distinct_current_monotonicity_invariant():
    """Public-API invariant, not a manufactured abstraction: because
    EvidencePool has no removal operation (`test_pool_has_no_delete_method`)
    and every id is content-addressed, the set of ids it holds can only
    grow, never revert -- so `fingerprint()` cannot return to an earlier
    value within one pool's lifetime today, and `fingerprint_history()`
    cannot contain a repeated (non-consecutive) entry through the public
    API. This proves that over a representative sequence of distinct
    writes -- it does not assert it as a permanent guarantee. The
    compare-and-append rule in `_observe_fingerprint` remains the general
    rule regardless (append iff changed from the last entry), so it would
    still be correct if some future, currently-nonexistent operation ever
    permitted revisiting a prior state -- see
    `docs/RETRIEVAL_ARCHITECTURE.md` §7's `F1 -> F2 -> F1` discussion."""
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="body", retrieval_method="m", retrieved_at="t")
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="p1", raw_content="body")
    pool.put_record(record)
    for key in ("FEP", "extrusion", "rheo-sim", "viscosity"):
        pool.put_referent(make_referent(natural_key=key, kind="material"))

    history = pool.fingerprint_history()
    assert len(history) == len(set(history)), (
        "fingerprint_history contains a repeated entry -- monotonicity invariant violated"
    )


def test_fingerprint_history_introduces_no_reconstruction_mechanism():
    """Structural/negative test, same style as `test_pool_has_no_delete_method`:
    Phase 16 must not introduce any method that maps a historical
    fingerprint back to the object ids/contents that produced it."""
    pool = EvidencePool()
    forbidden_substrings = ("reconstruct", "restore", "snapshot", "contents_at", "evidence_at")
    for name in dir(pool):
        lowered = name.lower()
        assert not any(s in lowered for s in forbidden_substrings), (
            f"EvidencePool exposes {name!r} -- historical evidence reconstruction must remain unimplemented"
        )


def test_round_trip_content_hash_stable_for_serialized_observation():
    """An Observation's identity-defining payload survives a JSON
    round-trip unchanged -- the same discipline
    `core/canonical/version.py::canonical_json_bytes` already proves for
    CanonicalState, exercised here for Observation content."""
    import json

    obs = make_observation(
        record_ids=("r1", "r2"),
        extraction_method="regex:kv_v1",
        content={"value": 1250, "unit": "Pa.s"},
        confidence=1.0,
        extracted_at="t",
    )
    payload = {"record_ids": list(obs.record_ids), "extraction_method": obs.extraction_method, "content": dict(sorted(obs.content.items()))}
    round_tripped = json.loads(canonical_json_bytes(payload))
    assert round_tripped["content"] == dict(obs.content)
    assert round_tripped["record_ids"] == list(obs.record_ids)
