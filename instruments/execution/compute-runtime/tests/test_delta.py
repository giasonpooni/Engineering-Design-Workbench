"""Phase 3: StateDelta + structural diff + candidate delta validation
(§5). §21 test 10: nested state changes produce path-level (leaf)
deltas.
"""

import dataclasses

from core.canonical.delta import CandidateChange, CandidateDelta, StateDelta, apply_changes, diff
from core.canonical.version import ProvenanceInfo


def test_single_leaf_value_change_produces_one_path_level_change(genesis_version):
    old_state = genesis_version.state
    new_fields = dict(old_state.fields)
    new_fields["mass"] = dataclasses.replace(new_fields["mass"], value=99)
    new_state = dataclasses.replace(old_state, fields=new_fields)

    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    changes = diff(old_state, new_state, provenance)

    assert len(changes) == 1
    assert changes[0].path == "fields.mass.value"
    assert changes[0].operation == "replace"
    assert changes[0].old_value == 10
    assert changes[0].new_value == 99


def test_diff_is_deterministically_ordered(genesis_version):
    old_state = genesis_version.state
    new_fields = dict(old_state.fields)
    new_fields["velocity"] = dataclasses.replace(new_fields["velocity"], value=5)
    new_fields["mass"] = dataclasses.replace(new_fields["mass"], value=99)
    new_state = dataclasses.replace(old_state, fields=new_fields)

    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    changes1 = diff(old_state, new_state, provenance)
    changes2 = diff(old_state, new_state, provenance)

    assert changes1 == changes2
    assert [c.path for c in changes1] == sorted(c.path for c in changes1)


def test_apply_changes_round_trips_diff(genesis_version):
    old_state = genesis_version.state
    new_fields = dict(old_state.fields)
    new_fields["mass"] = dataclasses.replace(new_fields["mass"], value=99)
    new_state = dataclasses.replace(old_state, fields=new_fields)

    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    changes = diff(old_state, new_state, provenance)

    candidate_changes = tuple(
        CandidateChange(
            path=c.path, operation=c.operation, old_value=c.old_value, new_value=c.new_value, provenance=c.provenance
        )
        for c in changes
    )
    rebuilt = apply_changes(old_state, candidate_changes)
    assert rebuilt == new_state


def test_only_add_remove_replace_are_supported_operations(genesis_version):
    # move/rename are reserved in the Operation type (forward-compatible)
    # but diff() must never emit them in v1 (§5, §23).
    old_state = genesis_version.state
    new_fields = dict(old_state.fields)
    new_fields["mass"] = dataclasses.replace(new_fields["mass"], value=99)
    new_state = dataclasses.replace(old_state, fields=new_fields)
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    changes = diff(old_state, new_state, provenance)
    assert all(c.operation in ("add", "remove", "replace") for c in changes)


def test_state_delta_is_a_distinct_shape_from_candidate_delta():
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    change = CandidateChange(
        path="fields.mass.value", operation="replace", old_value=10, new_value=42, provenance=provenance
    )
    delta = StateDelta(
        version_from="v0", version_to="v1", transaction_id="tx1", timestamp="2026-08-22T00:01:00Z", changes=(change,)
    )
    candidate = CandidateDelta(
        version_from="v0", transaction_id="tx1", timestamp="2026-08-22T00:01:00Z", changes=(change,)
    )
    assert delta.version_to == "v1"
    assert not hasattr(candidate, "version_to")  # a candidate has no minted version yet
