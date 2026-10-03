"""Phase 8: SVG/diagram backend (§15). No test coverage existed for this
backend before this pass -- this file is new, not a relocation.
"""

import ast as pyast
import copy
import inspect
import xml.etree.ElementTree as ET

import pytest

from backends.diagram import compiler as diagram_compiler
from backends.diagram.compiler import DiagramLayoutConfig, compile_svg
from backends.threejs.compiler import ThreeJSRenderConfig, compile_threejs
from core.canonical.delta import CandidateChange, CandidateDelta
from core.canonical.validation import validate_candidate
from core.canonical.version import ProvenanceInfo
from core.projection.project import project_state
from morpho.compiler import CompilerConfig, compile_morpho
from morpho.ir import Entity, MorphoDocument, MorphoRelation
from morpho.provenance import canonical_provenance, derived_provenance


def _entity(entity_id, value=10):
    return Entity(
        id=entity_id,
        attributes={"type": "scalar", "value": value, "unit": None},
        provenance=canonical_provenance(origin_version="v0", compiler_version="1.0.0"),
    )


def test_compile_svg_produces_well_formed_xml(genesis_version):
    ir_doc = compile_morpho(project_state(genesis_version), CompilerConfig())
    svg = compile_svg(ir_doc, DiagramLayoutConfig())
    root = ET.fromstring(svg)  # raises if malformed
    assert root.tag.endswith("svg")


def test_compile_svg_is_deterministic(genesis_version):
    ir_doc = compile_morpho(project_state(genesis_version), CompilerConfig())
    config = DiagramLayoutConfig()
    svg1 = compile_svg(ir_doc, config)
    svg2 = compile_svg(ir_doc, config)
    assert svg1 == svg2


def test_compile_svg_renders_every_entity(genesis_version):
    ir_doc = compile_morpho(project_state(genesis_version), CompilerConfig())
    svg = compile_svg(ir_doc, DiagramLayoutConfig())
    for field_id in genesis_version.state.fields:
        assert f'data-entity-id="{field_id}"' in svg


def test_compile_svg_distinguishes_inferred_from_explicit_relations():
    doc = MorphoDocument(
        entities=(_entity("A"), _entity("B")),
        relations=(
            MorphoRelation(
                id="explicit_rel", from_id="A", to_id="B", type="depends_on",
                is_canonical=True, inference_status="explicit",
                provenance=canonical_provenance(origin_version="v0", compiler_version="1.0.0"),
            ),
            MorphoRelation(
                id="inferred_rel", from_id="A", to_id="B", type="near",
                is_canonical=False, inference_status="inferred",
                provenance=derived_provenance(
                    source="graph_backend:adjacency_heuristic_v1", origin_version="v0", compiler_version="1.0.0"
                ),
                confidence=0.7,
            ),
        ),
    )
    svg = compile_svg(doc, DiagramLayoutConfig())
    assert 'data-relation-id="explicit_rel"' in svg
    assert 'data-relation-id="inferred_rel"' in svg
    # Visually distinguishable: inferred relations are dashed, explicit are not.
    lines = [line for line in svg.splitlines() if "<line" in line]
    explicit_line = next(l for l in lines if 'data-relation-id="explicit_rel"' in l)
    inferred_line = next(l for l in lines if 'data-relation-id="inferred_rel"' in l)
    assert "stroke-dasharray" not in explicit_line
    assert "stroke-dasharray" in inferred_line


def test_compile_svg_rejects_nondeterministic_layout_algorithm():
    doc = MorphoDocument(entities=(_entity("A"),))
    with pytest.raises(ValueError):
        compile_svg(doc, DiagramLayoutConfig(layout_algorithm="force_directed_random_v1"))


def test_compile_svg_handles_empty_document():
    svg = compile_svg(MorphoDocument(), DiagramLayoutConfig())
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")


def test_compile_svg_escapes_entity_content():
    doc = MorphoDocument(entities=(_entity('A"<script>'),))
    svg = compile_svg(doc, DiagramLayoutConfig())
    ET.fromstring(svg)  # must still be well-formed XML despite hostile content
    assert "<script>" not in svg


def test_compile_svg_strips_xml_illegal_control_characters():
    # Escaping &/</>/" is not sufficient on its own: a raw control
    # character (e.g. U+000B, U+0000) is illegal in XML regardless of
    # escaping and makes xml.etree reject the document outright. Found
    # via direct testing of compile_svg's "complete SVG document string"
    # contract against arbitrary entity ids -- not merely for tidiness.
    doc = MorphoDocument(entities=(_entity("A\x0bB\x00C"),))
    svg = compile_svg(doc, DiagramLayoutConfig())
    ET.fromstring(svg)
    assert "\x0b" not in svg
    assert "\x00" not in svg


# -- The SVG backend consumes the SAME upstream Morpho IR as Three.js
#    (§1, §15) -- these tests demonstrate that directly, per this
#    session's Phase 8 checklist: identity, provenance, stable node/edge
#    mapping, no canonical mutation, and cross-backend equivalence. --


def test_svg_and_threejs_backends_agree_on_entity_identity(genesis_version):
    """Same MorphoDocument in -> both backends must reference the exact
    same set of entity ids (§9 identity model applies uniformly
    regardless of which backend consumes the IR)."""
    ir_doc = compile_morpho(project_state(genesis_version), CompilerConfig())

    svg = compile_svg(ir_doc, DiagramLayoutConfig())
    svg_ids = {e.id for e in ir_doc.entities if f'data-entity-id="{e.id}"' in svg}

    scene = compile_threejs(ir_doc, ThreeJSRenderConfig())
    threejs_ids = {m["id"] for m in scene.meshes}

    canonical_ids = set(genesis_version.state.fields.keys())
    assert svg_ids == threejs_ids == canonical_ids


def test_svg_and_threejs_backends_consume_the_same_ir_object_unmutated(genesis_version):
    """Neither backend may mutate the MorphoDocument it's handed --
    compiling one representation must not corrupt or alter what the
    other representation sees, since both read the same upstream IR
    (§1: 'Structural State -> Morpho IR -> Representation')."""
    ir_doc = compile_morpho(project_state(genesis_version), CompilerConfig())
    ir_snapshot = copy.deepcopy(ir_doc)

    compile_svg(ir_doc, DiagramLayoutConfig())
    assert ir_doc == ir_snapshot  # unchanged after SVG compilation

    compile_threejs(ir_doc, ThreeJSRenderConfig())
    assert ir_doc == ir_snapshot  # unchanged after Three.js compilation too


def test_compile_svg_does_not_mutate_canonical_state(genesis_version):
    fields_before = dict(genesis_version.state.fields)
    edges_before = genesis_version.state.edges

    ir_doc = compile_morpho(project_state(genesis_version), CompilerConfig())
    compile_svg(ir_doc, DiagramLayoutConfig())

    assert genesis_version.state.fields == fields_before
    assert genesis_version.state.edges == edges_before


def test_svg_node_mapping_is_stable_across_a_value_change(sample_schema, genesis_version):
    """Stable mapping of nodes (Phase 8 checklist item 4): the same
    canonical field keeps the same data-entity-id in the SVG across two
    versions differing only in that field's value -- mirrors
    test_geometry_identity_survives_value_changes for the Three.js
    backend."""
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=genesis_version.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.mass.value", operation="replace", old_value=10, new_value=99, provenance=provenance
            ),
        ),
    )
    v1 = validate_candidate(sample_schema, genesis_version.state, candidate)
    assert not isinstance(v1, list), v1

    config = DiagramLayoutConfig()
    svg_before = compile_svg(compile_morpho(project_state(genesis_version), CompilerConfig()), config)
    svg_after = compile_svg(compile_morpho(project_state(v1), CompilerConfig()), config)

    assert 'data-entity-id="mass"' in svg_before
    assert 'data-entity-id="mass"' in svg_after  # same node identity, different value


def test_svg_edge_mapping_is_stable_across_a_value_change():
    """Stable mapping of edges (Phase 8 checklist item 5): a relation's
    id/endpoints are unaffected by an unrelated entity's value changing
    -- the edge mapping is a pure function of the IR's relations, not of
    any particular entity's current value."""
    provenance = canonical_provenance(origin_version="v0", compiler_version="1.0.0")
    relation = MorphoRelation(
        id="rel1", from_id="A", to_id="B", type="depends_on",
        is_canonical=True, inference_status="explicit", provenance=provenance,
    )
    doc_before = MorphoDocument(entities=(_entity("A", value=1), _entity("B", value=2)), relations=(relation,))
    doc_after = MorphoDocument(entities=(_entity("A", value=999), _entity("B", value=2)), relations=(relation,))

    config = DiagramLayoutConfig()
    svg_before = compile_svg(doc_before, config)
    svg_after = compile_svg(doc_after, config)

    assert 'data-relation-id="rel1"' in svg_before
    assert 'data-relation-id="rel1"' in svg_after


def test_diagram_backend_cannot_become_source_of_truth():
    """Same CRITICAL RULE as the Three.js backend: no backend may mutate
    canonical state, and none may import the machinery that mints a
    Version."""
    source = inspect.getsource(diagram_compiler)
    tree = pyast.parse(source)
    imported_modules = []
    for node in pyast.walk(tree):
        if isinstance(node, pyast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, pyast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    disallowed_prefixes = ("core.canonical.validation", "core.canonical.version")
    for module_name in imported_modules:
        assert not module_name.startswith(disallowed_prefixes), (
            f"backends/diagram/compiler.py must not import {module_name}"
        )
    assert "validate_candidate" not in source
