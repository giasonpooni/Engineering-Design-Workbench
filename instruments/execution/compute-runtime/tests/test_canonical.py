"""Phase 1: schema + immutable CanonicalState + validation.

Covers §21 tests 5-6 (no inferred edges enter canonical state; inferred
relations parsed from Morpho source stay marked inferred) plus direct
coverage of the CRITICAL RULES: CanonicalState is immutable, field
identity is never silently corrected, and validate_candidate is the one
legal route into a new Version/CanonicalState/EdgeRecord.
"""

import ast as pyast
import dataclasses
import inspect
from types import MappingProxyType

import pytest

from core.canonical import validation
from core.canonical.delta import CandidateChange, CandidateDelta
from core.canonical.schema import EdgeSchema, FieldConstraints, FieldSchema, StateSchema
from core.canonical.state import CanonicalState, Field
from core.canonical.validation import ValidationError, validate_candidate
from core.canonical.version import ProvenanceInfo, create_genesis_version
from morpho.ir import from_ast
from morpho.parser import parse_document

INFERRED_RELATION_SOURCE = """
morpho "1.0.0";

inferred relation A_near_B {
    from: "A";
    to: "B";
    type: "spatial_adjacency";
    confidence: 0.82;
    provenance {
        source: "graph_backend:adjacency_heuristic_v1";
        origin_version: "5f2a...c91";
    }
}
"""

DERIVED_RELATION_SOURCE = """
morpho "1.0.0";

derived relation A_linked_B {
    from: "A";
    to: "B";
    type: "manual_link";
    provenance {
        source: "diagram_tool:manual_edit";
        origin_version: "5f2a...c91";
    }
}
"""


# -- CanonicalState immutability and identity (CRITICAL RULES) --------------


def test_field_id_mismatch_is_never_silently_corrected():
    with pytest.raises(ValueError):
        CanonicalState(schema_version="1.0.0", fields={"mass": Field(id="not-mass", type="scalar", value=1)})


def test_canonical_state_fields_mapping_is_immutable():
    state = CanonicalState(schema_version="1.0.0", fields={"mass": Field(id="mass", type="scalar", value=10)})
    assert isinstance(state.fields, MappingProxyType)
    with pytest.raises(TypeError):
        state.fields["mass"] = Field(id="mass", type="scalar", value=999)


def test_canonical_state_is_a_frozen_dataclass():
    state = CanonicalState(schema_version="1.0.0", fields={"mass": Field(id="mass", type="scalar", value=10)})
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.schema_version = "2.0.0"


def test_field_itself_is_frozen():
    f = Field(id="mass", type="scalar", value=10)
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.value = 999


# -- validate_candidate schema-stage checks ----------------------------------


def _schema():
    return StateSchema(
        schema_version="1.0.0",
        fields={"mass": FieldSchema(id="mass", type="scalar", default=10, constraints=FieldConstraints(min=0))},
    )


def test_unknown_field_is_rejected():
    schema = _schema()
    v0 = create_genesis_version(schema, "2026-08-22T00:00:00Z")
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=v0.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.not_declared.value", operation="replace", old_value=None, new_value=1, provenance=provenance
            ),
        ),
    )
    result = validate_candidate(schema, v0.state, candidate)
    assert isinstance(result, list)
    assert any(e.code == "UNKNOWN_FIELD" for e in result)


def test_type_mismatch_is_rejected():
    schema = _schema()
    v0 = create_genesis_version(schema, "2026-08-22T00:00:00Z")
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=v0.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.mass.value", operation="replace", old_value=10, new_value="not-a-number", provenance=provenance
            ),
        ),
    )
    result = validate_candidate(schema, v0.state, candidate)
    assert isinstance(result, list)
    assert any(e.code == "TYPE_MISMATCH" for e in result)


def test_required_field_removal_is_rejected():
    schema = _schema()
    v0 = create_genesis_version(schema, "2026-08-22T00:00:00Z")
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=v0.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.mass",
                operation="remove",
                old_value={"id": "mass", "type": "scalar", "value": 10, "unit": None},
                new_value=None,
                provenance=provenance,
            ),
        ),
    )
    result = validate_candidate(schema, v0.state, candidate)
    assert isinstance(result, list)
    assert any(e.code == "REQUIRED_FIELD_REMOVED" for e in result)


def test_constraint_violation_is_rejected_and_base_state_untouched():
    schema = _schema()
    v0 = create_genesis_version(schema, "2026-08-22T00:00:00Z")
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=v0.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.mass.value", operation="replace", old_value=10, new_value=-5, provenance=provenance
            ),
        ),
    )
    result = validate_candidate(schema, v0.state, candidate)
    assert isinstance(result, list)
    assert any(e.code == "OUT_OF_RANGE" for e in result)
    assert v0.state.fields["mass"].value == 10  # rejection is atomic; base is untouched


def test_valid_candidate_is_accepted():
    schema = _schema()
    v0 = create_genesis_version(schema, "2026-08-22T00:00:00Z")
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=v0.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.mass.value", operation="replace", old_value=10, new_value=42, provenance=provenance
            ),
        ),
    )
    result = validate_candidate(schema, v0.state, candidate)
    assert not isinstance(result, list), result
    assert result.state.fields["mass"].value == 42


# -- validation.py has no path to Morpho/backends (§6, §11, §20) ------------


def test_validation_module_has_no_dependency_on_morpho():
    """core.canonical.validation is the ONLY function that may mint a
    Version/EdgeRecord (§6). It must not import anything from morpho/ or
    backends/ -- there is structurally no path from a Morpho construct
    (canonical or inferred) into canonical state (§11, §20)."""
    source = inspect.getsource(validation)
    tree = pyast.parse(source)
    imported_modules = []
    for node in pyast.walk(tree):
        if isinstance(node, pyast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, pyast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    for module_name in imported_modules:
        assert not module_name.startswith("morpho"), f"validation.py must not import {module_name}"
        assert not module_name.startswith("backends"), f"validation.py must not import {module_name}"


# -- §21 tests 5-6: inferred/derived relations never become canonical -------


def test_inferred_relation_parses_as_inferred_and_noncanonical():
    document = parse_document(INFERRED_RELATION_SOURCE)
    ir = from_ast(document, compiler_version="1.0.0")
    assert len(ir.relations) == 1
    relation = ir.relations[0]
    assert relation.inference_status == "inferred"
    assert relation.is_canonical is False


def test_derived_relation_parses_as_explicit_but_noncanonical():
    document = parse_document(DERIVED_RELATION_SOURCE)
    ir = from_ast(document, compiler_version="1.0.0")
    assert len(ir.relations) == 1
    relation = ir.relations[0]
    assert relation.inference_status == "explicit"
    assert relation.is_canonical is False


def _edge_schema_with_type(edge_type: str) -> StateSchema:
    return StateSchema(
        schema_version="1.0.0",
        fields={
            "A": FieldSchema(id="A", type="scalar", default=1),
            "B": FieldSchema(id="B", type="scalar", default=2),
        },
        edges=(EdgeSchema(type=edge_type),),
    )


def test_explicit_edge_add_and_remove_round_trip_through_validation():
    schema = _edge_schema_with_type("depends_on")
    v0 = create_genesis_version(schema, "2026-08-22T00:00:00Z")
    assert v0.state.edges == ()

    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    add_candidate = CandidateDelta(
        version_from=v0.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="edges[0]",
                operation="add",
                old_value=None,
                new_value={"id": "e1", "from": "A", "to": "B", "type": "depends_on", "attributes": {}},
                provenance=provenance,
            ),
        ),
    )
    v1 = validate_candidate(schema, v0.state, add_candidate)
    assert not isinstance(v1, list), v1
    assert len(v1.state.edges) == 1
    assert v1.state.edges[0].id == "e1"
    assert v1.state.edges[0].from_ == "A"
    assert v1.state.edges[0].to == "B"

    remove_candidate = CandidateDelta(
        version_from=v1.id,
        transaction_id="tx2",
        timestamp="2026-08-22T00:02:00Z",
        changes=(
            CandidateChange(
                path="edges[0]",
                operation="remove",
                old_value={"id": "e1", "from": "A", "to": "B", "type": "depends_on", "attributes": {}},
                new_value=None,
                provenance=provenance,
            ),
        ),
    )
    v2 = validate_candidate(schema, v1.state, remove_candidate)
    assert not isinstance(v2, list), v2
    assert v2.state.edges == ()


def test_edge_add_rejected_when_schema_declares_no_edge_types():
    # edges_are_explicit_only (I4): an edge type the schema does not
    # declare is refused -- relationships are stated, never inferred.
    schema = StateSchema(
        schema_version="1.0.0",
        fields={"A": FieldSchema(id="A", type="scalar", default=1), "B": FieldSchema(id="B", type="scalar", default=2)},
        edges=(),  # empty => no edges may ever be asserted (§6)
    )
    v0 = create_genesis_version(schema, "2026-08-22T00:00:00Z")
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=v0.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="edges[0]",
                operation="add",
                old_value=None,
                new_value={"id": "e1", "from": "A", "to": "B", "type": "depends_on", "attributes": {}},
                provenance=provenance,
            ),
        ),
    )
    result = validate_candidate(schema, v0.state, candidate)
    assert isinstance(result, list)
    assert all(isinstance(e, ValidationError) for e in result)
    assert v0.state.edges == ()
