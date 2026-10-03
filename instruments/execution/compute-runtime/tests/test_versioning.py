"""Phase 2: Version + VersionStore + deterministic content-addressed
VersionId (§4). §21 tests 11-13: every accepted update creates a new
version, versions have parent relationships, and previous versions
remain recoverable.
"""

import subprocess
import sys
from pathlib import Path

from core.canonical.delta import CandidateChange, CandidateDelta
from core.canonical.state import CanonicalState, Field
from core.canonical.validation import validate_candidate
from core.canonical.version import InMemoryVersionStore, ProvenanceInfo, compute_version_id

REPO_ROOT = Path(__file__).resolve().parent.parent


def _accept_mass_change(schema, base_version, new_value, tx_id):
    provenance = ProvenanceInfo(author="test", transaction_id=tx_id, source="manual_edit")
    candidate = CandidateDelta(
        version_from=base_version.id,
        transaction_id=tx_id,
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.mass.value",
                operation="replace",
                old_value=base_version.state.fields["mass"].value,
                new_value=new_value,
                provenance=provenance,
            ),
        ),
    )
    result = validate_candidate(schema, base_version.state, candidate)
    assert not isinstance(result, list), result
    return result


# -- Version ID is content-addressed over (schema_version, fields, edges)
#    ONLY -- id/parent/provenance/timestamp are excluded (§4) -------------


def test_version_id_excludes_parent_provenance_and_timestamp():
    state = CanonicalState(schema_version="1.0.0", fields={"mass": Field(id="mass", type="scalar", value=10)})
    id_a = compute_version_id(state)
    id_b = compute_version_id(state)
    assert id_a == id_b  # same content -> same id regardless of when computed

    # Two independently-built states with identical (schema_version,
    # fields, edges) must hash identically even if everything else about
    # how they'd be wrapped into a Version (parent/provenance/timestamp)
    # differs -- those fields are simply not part of the hash input.
    other_state = CanonicalState(schema_version="1.0.0", fields={"mass": Field(id="mass", type="scalar", value=10)})
    assert compute_version_id(other_state) == id_a


def test_version_id_changes_when_content_changes():
    state_a = CanonicalState(schema_version="1.0.0", fields={"mass": Field(id="mass", type="scalar", value=10)})
    state_b = CanonicalState(schema_version="1.0.0", fields={"mass": Field(id="mass", type="scalar", value=11)})
    assert compute_version_id(state_a) != compute_version_id(state_b)


def test_version_id_is_stable_across_process_and_hash_seed_boundaries():
    """§20 names 'non-deterministic dict/set ordering leaking into
    hashes' as a specific failure mode, prevented (per that section) by
    always sorting keys during canonical serialization. That claim was
    previously verified only ad hoc (manual multi-PYTHONHASHSEED runs
    during a review session), never as a committed regression test --
    meaning a future change reintroducing raw dict/set iteration into
    the hash path would not be caught automatically. This test closes
    that gap directly: it computes the same Version.id in two fresh
    subprocesses with different hash seeds and asserts equality.
    Intentionally spawns real subprocesses rather than mocking
    PYTHONHASHSEED in-process, because Python only applies
    PYTHONHASHSEED at interpreter startup -- an in-process test cannot
    exercise it at all.
    """
    script = (
        "from core.canonical.state import CanonicalState, Field\n"
        "from core.canonical.version import compute_version_id\n"
        "state = CanonicalState(schema_version='1.0.0', fields={\n"
        "    'mass': Field(id='mass', type='scalar', value=10, unit='kg'),\n"
        "    'temperature': Field(id='temperature', type='scalar', value=293.15, unit='K'),\n"
        "    'pressure': Field(id='pressure', type='scalar', value=101325, unit='Pa'),\n"
        "})\n"
        "print(compute_version_id(state))\n"
    )

    ids = set()
    for seed in ("0", "1", "12345"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        ids.add(result.stdout.strip())

    assert len(ids) == 1, f"Version.id differed across PYTHONHASHSEED values: {ids}"


# -- §21 tests 11-13 ----------------------------------------------------


def test_every_accepted_update_creates_a_new_version(sample_schema, genesis_version):
    store = InMemoryVersionStore()
    store.put(genesis_version)
    assert len(store) == 1

    v1 = _accept_mass_change(sample_schema, genesis_version, 42, "tx1")
    store.put(v1)
    assert len(store) == 2
    assert v1.id != genesis_version.id


def test_versions_have_parent_relationships(sample_schema, genesis_version):
    v1 = _accept_mass_change(sample_schema, genesis_version, 42, "tx1")
    assert v1.parent == genesis_version.id

    v2 = _accept_mass_change(sample_schema, v1, 7, "tx2")
    assert v2.parent == v1.id
    assert v2.parent != genesis_version.id


def test_previous_versions_remain_recoverable(sample_schema, genesis_version):
    # Version/CanonicalState are immutable, so holding the original
    # `genesis_version` reference and comparing against it later is a
    # valid recoverability check -- nothing in this codebase has a way
    # to mutate it in place.
    store = InMemoryVersionStore()
    store.put(genesis_version)

    v1 = _accept_mass_change(sample_schema, genesis_version, 42, "tx1")
    store.put(v1)
    v2 = _accept_mass_change(sample_schema, v1, 7, "tx2")
    store.put(v2)

    recovered = store.get(genesis_version.id)
    assert recovered == genesis_version

    chain = store.parent_chain(v2.id)
    assert [v.id for v in chain] == [v2.id, v1.id, genesis_version.id]
