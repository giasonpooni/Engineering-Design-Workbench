"""Phase 17: DerivedValue -- the first representation for "using O1, O2,
and O3, method M, I derive value V." Covers identity determinism,
admission integrity (including the no-cycle proof), pool storage, and
fingerprint/fingerprint_history participation.

Same style as `tests/test_evidence_identity.py`,
`tests/test_evidence_admission.py`, and `tests/test_evidence_pool.py` --
DerivedValue is a seventh peer of the six evidence types those files
already cover, not a new subsystem.
"""

import pytest

from evidence.admission import admit_derived_value
from evidence.pool import EvidencePool
from evidence.types import (
    make_derived_value,
    make_document,
    make_observation,
    make_record,
    make_source,
)


def _pool_with_two_observations():
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="body", retrieval_method="m", retrieved_at="t")
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="p1", raw_content="body")
    pool.put_record(record)
    o1 = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1", content={"value": 1200}, confidence=1.0, extracted_at="t"
    )
    o2 = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1", content={"value": 1300}, confidence=1.0, extracted_at="t"
    )
    pool.put_observation(o1)
    pool.put_observation(o2)
    return pool, o1, o2


# -- A. Identity --------------------------------------------------------


def test_identity_same_inputs_same_id():
    dv1 = make_derived_value(derived_from=["o1", "o2"], method="mean", content={"value": 1250}, confidence=0.9, derived_at="t")
    dv2 = make_derived_value(derived_from=["o1", "o2"], method="mean", content={"value": 1250}, confidence=0.9, derived_at="t")
    assert dv1.id == dv2.id


def test_identity_different_derived_from_different_id():
    base = dict(method="mean", content={"value": 1250}, confidence=0.9, derived_at="t")
    dv1 = make_derived_value(derived_from=["o1", "o2"], **base)
    dv2 = make_derived_value(derived_from=["o1", "o3"], **base)
    assert dv1.id != dv2.id


def test_identity_different_method_different_id():
    base = dict(derived_from=["o1", "o2"], content={"value": 1250}, confidence=0.9, derived_at="t")
    dv1 = make_derived_value(method="mean", **base)
    dv2 = make_derived_value(method="median", **base)
    assert dv1.id != dv2.id


def test_identity_different_content_different_id():
    base = dict(derived_from=["o1", "o2"], method="mean", confidence=0.9, derived_at="t")
    dv1 = make_derived_value(content={"value": 1250}, **base)
    dv2 = make_derived_value(content={"value": 1300}, **base)
    assert dv1.id != dv2.id


def test_identity_excludes_confidence():
    base = dict(derived_from=["o1", "o2"], method="mean", content={"value": 1250}, derived_at="t")
    dv1 = make_derived_value(confidence=0.9, **base)
    dv2 = make_derived_value(confidence=0.1, **base)
    assert dv1.id == dv2.id


def test_identity_excludes_derived_at():
    base = dict(derived_from=["o1", "o2"], method="mean", content={"value": 1250}, confidence=0.9)
    dv1 = make_derived_value(derived_at="2026-01-01T00:00:00Z", **base)
    dv2 = make_derived_value(derived_at="2026-06-01T00:00:00Z", **base)
    assert dv1.id == dv2.id


def test_derived_from_deduplication():
    dv1 = make_derived_value(derived_from=["o1", "o2"], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    dv2 = make_derived_value(derived_from=["o1", "o2", "o1", "o2"], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    assert dv1.id == dv2.id
    assert dv1.derived_from == ("o1", "o2")


def test_derived_from_ordering_normalization():
    dv1 = make_derived_value(derived_from=["o2", "o1"], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    dv2 = make_derived_value(derived_from=["o1", "o2"], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    assert dv1.id == dv2.id
    assert dv1.derived_from == dv2.derived_from == ("o1", "o2")


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValueError):
        make_derived_value(derived_from=["o1"], method="mean", content={"v": 1}, confidence=1.5, derived_at="t")


# -- B. Admission ---------------------------------------------------------


def test_admit_rejects_empty_derived_from():
    pool = EvidencePool()
    dv = make_derived_value(derived_from=[], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    # __post_init__ normalizes an empty iterable to an empty tuple; admission is where this is checked.
    result = admit_derived_value(pool, dv)
    assert isinstance(result, list)
    assert any(e.code == "NO_DERIVED_FROM" for e in result)


def test_admit_rejects_unknown_observation_id():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=["ghost"], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    result = admit_derived_value(pool, dv)
    assert isinstance(result, list)
    assert any(e.code == "UNKNOWN_INPUT" for e in result)


def test_admit_rejects_unknown_derived_value_id():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=["ghost-derived-value"], method="refine", content={"v": 1}, confidence=1.0, derived_at="t")
    result = admit_derived_value(pool, dv)
    assert isinstance(result, list)
    assert any(e.code == "UNKNOWN_INPUT" for e in result)


def test_admit_rejects_empty_method():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=[o1.id], method="", content={"v": 1}, confidence=1.0, derived_at="t")
    result = admit_derived_value(pool, dv)
    assert isinstance(result, list)
    assert any(e.code == "NO_METHOD" for e in result)


def test_admit_rejects_empty_content():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=[o1.id], method="mean", content={}, confidence=1.0, derived_at="t")
    result = admit_derived_value(pool, dv)
    assert isinstance(result, list)
    assert any(e.code == "EMPTY_CONTENT" for e in result)


def test_admit_accepts_valid_observation_derived_value():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=[o1.id, o2.id], method="mean", content={"value": 1250}, confidence=0.9, derived_at="t")
    result = admit_derived_value(pool, dv)
    assert result is dv


def test_admit_accepts_valid_derived_value_derived_value():
    pool, o1, o2 = _pool_with_two_observations()
    dv1 = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    pool.put_derived_value(dv1)
    dv2 = make_derived_value(derived_from=[dv1.id], method="refine", content={"value": 1210}, confidence=0.95, derived_at="t")
    result = admit_derived_value(pool, dv2)
    assert result is dv2


def test_admit_accepts_mixed_observation_and_derived_value_inputs():
    pool, o1, o2 = _pool_with_two_observations()
    dv1 = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    pool.put_derived_value(dv1)
    dv2 = make_derived_value(derived_from=[dv1.id, o2.id], method="combine", content={"value": 1250}, confidence=0.9, derived_at="t")
    result = admit_derived_value(pool, dv2)
    assert result is dv2


# -- C. Pool --------------------------------------------------------------


def test_pool_put_get():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    pool.put_derived_value(dv)
    assert pool.get_derived_value(dv.id) is dv


def test_pool_has():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    assert not pool.has_derived_value(dv.id)
    pool.put_derived_value(dv)
    assert pool.has_derived_value(dv.id)


def test_pool_all_derived_values():
    pool, o1, o2 = _pool_with_two_observations()
    dv1 = make_derived_value(derived_from=[o1.id], method="a", content={"v": 1}, confidence=1.0, derived_at="t")
    dv2 = make_derived_value(derived_from=[o2.id], method="b", content={"v": 2}, confidence=1.0, derived_at="t")
    pool.put_derived_value(dv1)
    pool.put_derived_value(dv2)
    assert {dv.id for dv in pool.all_derived_values()} == {dv1.id, dv2.id}


def test_pool_duplicate_put_idempotent():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    pool.put_derived_value(dv)
    size_before = len(pool.all_derived_values())
    pool.put_derived_value(dv)
    assert len(pool.all_derived_values()) == size_before


# -- D. Fingerprint ---------------------------------------------------------


def test_empty_derived_values_key_is_present_in_fingerprint_payload():
    """The fingerprint payload's "derived_values" key must exist
    unconditionally, even for a pool that never constructs a
    DerivedValue -- proven directly by reproducing the exact expected
    payload independently and confirming it hashes identically to a
    fresh EvidencePool's fingerprint(). Includes "derived_groundings"
    (Phase 19's eighth key, also unconditional) since this test
    reconstructs the payload's exact shape rather than merely checking
    for "derived_values"'s presence -- it would otherwise assert a stale
    schema."""
    from evidence.identity import content_hash

    pool = EvidencePool()
    expected_empty_payload = {
        "sources": [],
        "documents": [],
        "records": [],
        "observations": [],
        "referents": [],
        "claimed_relationships": [],
        "derived_values": [],
        "derived_groundings": [],
    }
    assert pool.fingerprint() == content_hash(expected_empty_payload)


def test_identical_pools_differing_only_by_derived_value_have_different_fingerprints():
    pool_a, o1_a, o2_a = _pool_with_two_observations()
    pool_b, o1_b, o2_b = _pool_with_two_observations()
    assert pool_a.fingerprint() == pool_b.fingerprint()  # identical before any DerivedValue

    dv = make_derived_value(derived_from=[o1_a.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    pool_a.put_derived_value(dv)
    assert pool_a.fingerprint() != pool_b.fingerprint()


def test_derived_value_admission_changes_fingerprint():
    pool, o1, o2 = _pool_with_two_observations()
    before = pool.fingerprint()
    dv = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    pool.put_derived_value(dv)
    assert pool.fingerprint() != before


def test_duplicate_derived_value_does_not_change_fingerprint():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    pool.put_derived_value(dv)
    before = pool.fingerprint()
    pool.put_derived_value(dv)
    assert pool.fingerprint() == before


def test_fingerprint_history_grows_exactly_once_on_derived_value_admission():
    pool, o1, o2 = _pool_with_two_observations()
    length_before = len(pool.fingerprint_history())
    dv = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    pool.put_derived_value(dv)
    history = pool.fingerprint_history()
    assert len(history) == length_before + 1
    assert history[-1] == pool.fingerprint()


def test_fingerprint_history_unaffected_by_duplicate_derived_value_put():
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    pool.put_derived_value(dv)
    history_before = pool.fingerprint_history()
    pool.put_derived_value(dv)
    assert pool.fingerprint_history() == history_before


def test_fingerprint_history_deterministic_with_derived_values_across_hash_seeds():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.pool import EvidencePool\n"
        "from evidence.types import make_derived_value, make_document, make_observation, make_record, make_source\n"
        "pool = EvidencePool()\n"
        "s = make_source(kind='paper', name='X')\n"
        "pool.put_source(s)\n"
        "d = make_document(source_id=s.id, raw_content='body', retrieval_method='m', retrieved_at='t')\n"
        "pool.put_document(d)\n"
        "r = make_record(document_id=d.id, locator='p1', raw_content='body')\n"
        "pool.put_record(r)\n"
        "o1 = make_observation(record_ids=(r.id,), extraction_method='regex:kv_v1', content={'value': 1200}, confidence=1.0, extracted_at='t')\n"
        "o2 = make_observation(record_ids=(r.id,), extraction_method='regex:kv_v1', content={'value': 1300}, confidence=1.0, extracted_at='t')\n"
        "pool.put_observation(o1)\n"
        "pool.put_observation(o2)\n"
        "dv1 = make_derived_value(derived_from=[o2.id, o1.id], method='mean', content={'value': 1250}, confidence=0.9, derived_at='t')\n"
        "pool.put_derived_value(dv1)\n"
        "pool.put_derived_value(dv1)\n"
        "dv2 = make_derived_value(derived_from=[dv1.id], method='refine', content={'value': 1255}, confidence=0.95, derived_at='t')\n"
        "pool.put_derived_value(dv2)\n"
        "print(dv1.id, dv2.id)\n"
        "print(pool.fingerprint())\n"
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
    assert len(outputs) == 1, f"DerivedValue identity/fingerprint differed across PYTHONHASHSEED values: {outputs}"


# -- E. Determinism (DerivedValue.id specifically) -------------------------


def test_derived_value_identity_deterministic_across_hash_seeds():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    script = (
        "from evidence.types import make_derived_value\n"
        "dv = make_derived_value(derived_from=['o3', 'o1', 'o2', 'o1'], method='mean', "
        "content={'value': 1250, 'unit': 'Pa.s'}, confidence=0.9, derived_at='t')\n"
        "print(dv.id)\n"
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
    assert len(outputs) == 1, f"DerivedValue.id differed across PYTHONHASHSEED values: {outputs}"


# -- G. No-cycle invariant --------------------------------------------------


def test_derivation_chain_admits_successfully_in_order():
    """O1 -> D1 (derived_from=[O1]) -> D2 (derived_from=[D1]): both must
    admit successfully, proving multi-level derivation is representable."""
    pool, o1, o2 = _pool_with_two_observations()

    d1 = make_derived_value(derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t")
    result_d1 = admit_derived_value(pool, d1)
    assert result_d1 is d1
    pool.put_derived_value(d1)

    d2 = make_derived_value(derived_from=[d1.id], method="refine", content={"value": 1205}, confidence=0.95, derived_at="t")
    result_d2 = admit_derived_value(pool, d2)
    assert result_d2 is d2
    pool.put_derived_value(d2)


def test_dangling_reference_to_a_never_admitted_derived_value_is_rejected():
    """This proves admission rejects a *dangling* reference -- an id that
    was never admitted into the pool at all -- not that a true cycle
    (A referencing B, B referencing A) was attempted and blocked. A real
    cycle is impossible for a stronger, separate reason (content-addressed
    identity itself -- see `evidence/types.py::DerivedValue`'s docstring)
    and cannot even be constructed to test against: computing either
    object's id would require the other's id to already be concrete."""
    pool, o1, o2 = _pool_with_two_observations()

    not_yet_admitted = make_derived_value(
        derived_from=[o1.id], method="accept_as_is", content={"value": 1200}, confidence=1.0, derived_at="t"
    )
    # Deliberately never pool.put_derived_value(not_yet_admitted) -- it is
    # only ever constructed, never admitted.

    dependent = make_derived_value(
        derived_from=[not_yet_admitted.id], method="refine", content={"value": 1205}, confidence=0.95, derived_at="t"
    )
    result = admit_derived_value(pool, dependent)
    assert isinstance(result, list)
    assert any(e.code == "UNKNOWN_INPUT" for e in result)


def test_admission_rejection_never_mutates_pool():
    """Atomicity, mirroring `tests/test_evidence_admission.py`'s
    `test_admission_rejection_never_mutates_pool` for the other five
    admission gates: a rejected DerivedValue leaves the pool's
    DerivedValue store untouched. (Uses `all_derived_values()`, not
    `len(pool)` -- `EvidencePool.__len__` deliberately does not count
    DerivedValues; see the Phase 17 post-implementation audit.)"""
    pool, o1, o2 = _pool_with_two_observations()
    size_before = len(pool.all_derived_values())
    bad = make_derived_value(derived_from=["ghost"], method="mean", content={"v": 1}, confidence=1.0, derived_at="t")
    result = admit_derived_value(pool, bad)
    assert isinstance(result, list)
    # admission itself never calls pool.put_*; only the caller does, and only on success.
    assert len(pool.all_derived_values()) == size_before


def test_admission_reports_every_unknown_derived_from_id_not_just_the_first():
    """admit_derived_value's validation loop iterates every id in
    derived_from and appends one AdmissionError per unknown one -- this
    is real, meaningful behavior to pin down (not a case where the
    existing implementation intentionally reports only one error), so it
    is tested directly rather than only inferred from the single-bad-id
    tests above."""
    pool, o1, o2 = _pool_with_two_observations()
    dv = make_derived_value(
        derived_from=["ghost-1", "ghost-2", o1.id], method="mean", content={"v": 1}, confidence=1.0, derived_at="t"
    )
    result = admit_derived_value(pool, dv)
    assert isinstance(result, list)
    unknown_input_errors = [e for e in result if e.code == "UNKNOWN_INPUT"]
    assert len(unknown_input_errors) == 2  # one per unknown id, o1.id (known) contributes none
