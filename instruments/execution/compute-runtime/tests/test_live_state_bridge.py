"""Phase 11: live state / feedback loop -- CanonicalState_t -> state delta
-> updated representation, across the 9 scenarios named in this
session's Phase 11 instructions. Uses a dedicated small schema (rather
than touching the shared conftest.py fixtures other tests key off) so
the field-add/remove and vector3 scenarios below don't ripple into
unrelated tests.
"""

from core.canonical.delta import CandidateChange, CandidateDelta, diff
from core.canonical.schema import FieldConstraints, FieldSchema, StateSchema
from core.canonical.validation import validate_candidate
from core.canonical.version import InMemoryVersionStore, ProvenanceInfo, create_genesis_version
from core.projection.project import project_state
from morpho.compiler import CompilerConfig, compile_morpho

BRIDGE_SCHEMA = StateSchema(
    schema_version="1.0.0",
    fields={
        "temperature": FieldSchema(id="temperature", type="scalar", default=20.0, constraints=FieldConstraints(min=-273.15)),
        "note": FieldSchema(id="note", type="string", default="baseline", required=False),
        "position": FieldSchema(id="position", type="vector3", default=(0.0, 0.0, 0.0)),
    },
)


def _prov(tx_id="tx"):
    return ProvenanceInfo(author="test", transaction_id=tx_id, source="manual_edit")


def _accept(base_version, changes, tx_id="tx"):
    candidate = CandidateDelta(
        version_from=base_version.id, transaction_id=tx_id, timestamp="2026-08-22T00:01:00Z", changes=changes
    )
    result = validate_candidate(BRIDGE_SCHEMA, base_version.state, candidate)
    assert not isinstance(result, list), result
    return result


# -- 1. initial state ---------------------------------------------------


def test_initial_state():
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    assert v0.parent is None
    assert v0.state.fields["temperature"].value == 20.0
    assert v0.state.fields["note"].value == "baseline"
    assert v0.state.fields["position"].value == (0.0, 0.0, 0.0)


# -- 2. unchanged state ---------------------------------------------------


def test_unchanged_state_produces_no_diff_and_a_no_op_version():
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    changes = diff(v0.state, v0.state, _prov())
    assert changes == ()

    # An empty candidate is a no-op: content-addressing means it "mints"
    # a version with the SAME id as the base, not a new one -- there is
    # no way to produce two different Version ids for identical content
    # (§4).
    empty_candidate = CandidateDelta(version_from=v0.id, transaction_id="tx-noop", timestamp="2026-08-22T00:01:00Z", changes=())
    result = validate_candidate(BRIDGE_SCHEMA, v0.state, empty_candidate)
    assert not isinstance(result, list), result
    assert result.id == v0.id


# -- 3. changed scalar ---------------------------------------------------


def test_changed_scalar():
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    v1 = _accept(
        v0,
        (CandidateChange(path="fields.temperature.value", operation="replace", old_value=20.0, new_value=25.5, provenance=_prov()),),
    )
    assert v1.state.fields["temperature"].value == 25.5
    assert v1.id != v0.id
    assert v1.parent == v0.id
    assert v0.state.fields["temperature"].value == 20.0  # prior version untouched


# -- 4. added field / 5. removed field -----------------------------------


def test_removed_field_then_added_back():
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    assert "note" in v0.state.fields

    # 5. removed field -- "note" is required=False, so this is legal.
    v1 = _accept(
        v0,
        (CandidateChange(
            path="fields.note", operation="remove",
            old_value={"id": "note", "type": "string", "value": "baseline", "unit": None},
            new_value=None, provenance=_prov("tx-remove"),
        ),),
        tx_id="tx-remove",
    )
    assert "note" not in v1.state.fields
    assert "note" in v0.state.fields  # prior version untouched by the removal

    # 4. added field -- re-adding it is legal too (schema still declares it).
    v2 = _accept(
        v1,
        (CandidateChange(
            path="fields.note", operation="add", old_value=None,
            new_value={"id": "note", "type": "string", "value": "restored", "unit": None},
            provenance=_prov("tx-add"),
        ),),
        tx_id="tx-add",
    )
    assert v2.state.fields["note"].value == "restored"
    assert "note" not in v1.state.fields  # v1 still untouched by the later add

    # diff() independently derives the same add/remove operations.
    remove_changes = diff(v0.state, v1.state, _prov())
    assert len(remove_changes) == 1 and remove_changes[0].operation == "remove" and remove_changes[0].path == "fields.note"

    add_changes = diff(v1.state, v2.state, _prov())
    assert len(add_changes) == 1 and add_changes[0].operation == "add" and add_changes[0].path == "fields.note"


def test_required_field_cannot_be_removed():
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    candidate = CandidateDelta(
        version_from=v0.id, transaction_id="tx-bad-remove", timestamp="2026-08-22T00:01:00Z",
        changes=(CandidateChange(
            path="fields.temperature", operation="remove",
            old_value={"id": "temperature", "type": "scalar", "value": 20.0, "unit": None},
            new_value=None, provenance=_prov(),
        ),),
    )
    result = validate_candidate(BRIDGE_SCHEMA, v0.state, candidate)
    assert isinstance(result, list)
    assert any(e.code == "REQUIRED_FIELD_REMOVED" for e in result)


# -- 6. multiple simultaneous changes -------------------------------------


def test_multiple_simultaneous_changes_apply_atomically():
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    prov = _prov("tx-multi")
    v1 = _accept(
        v0,
        (
            CandidateChange(path="fields.temperature.value", operation="replace", old_value=20.0, new_value=30.0, provenance=prov),
            CandidateChange(path="fields.note.value", operation="replace", old_value="baseline", new_value="updated", provenance=prov),
            CandidateChange(path="fields.position.value", operation="replace", old_value=(0.0, 0.0, 0.0), new_value=(1.0, 2.0, 3.0), provenance=prov),
        ),
        tx_id="tx-multi",
    )
    assert v1.state.fields["temperature"].value == 30.0
    assert v1.state.fields["note"].value == "updated"
    assert v1.state.fields["position"].value == (1.0, 2.0, 3.0)
    # One transaction -> one new version, not one per change.
    assert v1.parent == v0.id


def test_multiple_changes_are_rejected_as_one_unit_not_partially_applied():
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    prov = _prov("tx-multi-bad")
    candidate = CandidateDelta(
        version_from=v0.id, transaction_id="tx-multi-bad", timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(path="fields.temperature.value", operation="replace", old_value=20.0, new_value=99.0, provenance=prov),
            # -300 violates FieldConstraints(min=-273.15) on a second,
            # unrelated-looking change in the SAME candidate -- the
            # first (individually valid) change must NOT be applied.
            CandidateChange(path="fields.note.value", operation="replace", old_value="baseline", new_value="x", provenance=prov),
            CandidateChange(path="fields.temperature.value", operation="replace", old_value=99.0, new_value=-300.0, provenance=prov),
        ),
    )
    result = validate_candidate(BRIDGE_SCHEMA, v0.state, candidate)
    assert isinstance(result, list)
    assert v0.state.fields["temperature"].value == 20.0  # neither change applied
    assert v0.state.fields["note"].value == "baseline"


# -- 7. nested/list value changes (vector3) --------------------------------


def test_nested_list_value_change_vector3():
    """A vector3 Field's value is a 3-tuple; this codebase's path-
    addressing (§5) treats it as ONE leaf at `fields.<id>.value` -- it
    does NOT decompose into per-component sub-paths like
    `fields.position.value.x`. Stating that precisely here rather than
    assuming a finer granularity the implementation doesn't have."""
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    v1 = _accept(
        v0,
        (CandidateChange(path="fields.position.value", operation="replace", old_value=(0.0, 0.0, 0.0), new_value=(4.0, 5.0, 6.0), provenance=_prov()),),
    )
    assert v1.state.fields["position"].value == (4.0, 5.0, 6.0)
    assert v0.state.fields["position"].value == (0.0, 0.0, 0.0)

    changes = diff(v0.state, v1.state, _prov())
    assert len(changes) == 1
    assert changes[0].path == "fields.position.value"
    assert changes[0].new_value == (4.0, 5.0, 6.0)  # whole tuple, not per-component

    # The vector3 field still compiles into a Morpho CoordinateFrame
    # (§12) on both sides of the change, closing the P8 gap flagged in
    # the prior session's primitive-mapping audit (untested vector3 ->
    # CoordinateFrame path).
    ir_before = compile_morpho(project_state(v0), CompilerConfig())
    ir_after = compile_morpho(project_state(v1), CompilerConfig())
    assert len(ir_before.frames) == 1 and ir_before.frames[0].id == "position"
    assert ir_before.frames[0].transform.position.x == 0.0
    assert ir_after.frames[0].transform.position == ir_after.frames[0].transform.position  # sanity
    assert (ir_after.frames[0].transform.position.x, ir_after.frames[0].transform.position.y, ir_after.frames[0].transform.position.z) == (4.0, 5.0, 6.0)


# -- 8. identity preservation across the whole chain -----------------------


def test_identity_preserved_across_a_multi_step_chain():
    store = InMemoryVersionStore()
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    store.put(v0)
    v1 = _accept(v0, (CandidateChange(path="fields.temperature.value", operation="replace", old_value=20.0, new_value=21.0, provenance=_prov()),), "tx1")
    store.put(v1)
    v2 = _accept(v1, (CandidateChange(path="fields.temperature.value", operation="replace", old_value=21.0, new_value=22.0, provenance=_prov()),), "tx2")
    store.put(v2)

    for version in (v0, v1, v2):
        for field_id in version.state.fields:
            assert field_id == version.state.fields[field_id].id  # I5, every step

    # 9. deterministic replay + no mutation of prior states, together:
    # every version already stored remains exactly recoverable and
    # unchanged after later versions were built on top of it.
    assert store.get(v0.id) == v0
    assert store.get(v1.id) == v1
    assert store.get(v0.id).state.fields["temperature"].value == 20.0
    assert store.get(v1.id).state.fields["temperature"].value == 21.0


# -- 9. deterministic replay ------------------------------------------------


def test_deterministic_replay_of_the_whole_chain():
    from core.projection.project import restore_projection

    store = InMemoryVersionStore()
    v0 = create_genesis_version(BRIDGE_SCHEMA, "2026-08-22T00:00:00Z")
    store.put(v0)
    v1 = _accept(v0, (CandidateChange(path="fields.temperature.value", operation="replace", old_value=20.0, new_value=21.0, provenance=_prov()),), "tx1")
    store.put(v1)

    config = CompilerConfig()
    original_ir_v0 = compile_morpho(project_state(v0), config)
    original_ir_v1 = compile_morpho(project_state(v1), config)

    replayed_ir_v0 = compile_morpho(restore_projection(store, v0.id, config), config)
    replayed_ir_v1 = compile_morpho(restore_projection(store, v1.id, config), config)

    assert replayed_ir_v0 == original_ir_v0
    assert replayed_ir_v1 == original_ir_v1
    assert replayed_ir_v0 != replayed_ir_v1  # genuinely different states, not a stale cache
