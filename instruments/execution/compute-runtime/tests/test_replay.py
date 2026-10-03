"""§21 test 14: projection from a restored version equals projection from
the original version."""

from core.canonical.version import InMemoryVersionStore
from core.projection.project import project_state, restore_projection
from morpho.compiler import CompilerConfig


def test_restore_projection_matches_original(genesis_version):
    store = InMemoryVersionStore()
    store.put(genesis_version)

    original = project_state(genesis_version)
    restored = restore_projection(store, genesis_version.id, CompilerConfig())

    assert restored == original


def test_restore_projection_matches_after_other_versions_created(sample_schema, genesis_version):
    from core.canonical.delta import CandidateChange, CandidateDelta
    from core.canonical.validation import validate_candidate
    from core.canonical.version import ProvenanceInfo

    store = InMemoryVersionStore()
    store.put(genesis_version)
    original = project_state(genesis_version)

    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=genesis_version.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.mass.value", operation="replace", old_value=10, new_value=42, provenance=provenance
            ),
        ),
    )
    v1 = validate_candidate(sample_schema, genesis_version.state, candidate)
    store.put(v1)

    restored = restore_projection(store, genesis_version.id, CompilerConfig())
    assert restored == original
