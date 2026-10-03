"""Phase 5 (Morpho lexer/parser/AST/IR/compiler) and Phase 6
(deterministic identity and provenance). §21 tests 4, 15.
"""

from core.canonical.delta import CandidateChange, CandidateDelta
from core.canonical.validation import validate_candidate
from core.canonical.version import ProvenanceInfo
from core.projection.project import project_state
from morpho import ast, ir
from morpho.compiler import CompilerConfig, compile_morpho
from morpho.identity import cell_id, geometry_id, node_id, visual_id
from morpho.lexer import KEYWORDS
from morpho.parser import parse_document

FORBIDDEN_TERMS = {
    "three", "webgl", "camera", "material", "mesh", "dom", "canvas",
    "shader", "renderer", "viewport", "texture",
}

FULL_EXAMPLE = """
morpho "1.0.0";

entity mass {
    id: "mass";
    type: "scalar";
    value: 10;
    unit: "kg";
    provenance {
        source: "canonical";
        origin_version: "5f2a...c91";
    }
}

relation A_depends_on_B {
    from: "mass";
    to: "mass";
    type: "depends_on";
    provenance {
        source: "canonical";
        origin_version: "5f2a...c91";
    }
}

frame root_frame {
    position: [0, 0, 0];
    orientation: [0, 0, 0, 1];
    scale: [1, 1, 1];
}

group readings {
    members: ["mass"];
}

constraint mass_nonnegative {
    on: "mass";
    rule: "value >= 0";
}
"""

ALLOWED_AST_DECL_TYPES = (ast.EntityDecl, ast.RelationDecl, ast.FrameDecl, ast.GroupDecl, ast.ConstraintDecl)


# -- §21 test 15: Morpho contains no renderer-specific objects --------------
# Enforced at the grammar level (no keyword, production, or AST/IR node
# type for THREE.js/WebGL/DOM/camera/material concepts exists at all)
# rather than by a runtime check.


def test_keywords_exclude_renderer_concepts():
    for keyword in KEYWORDS:
        assert keyword.lower() not in FORBIDDEN_TERMS, f"keyword {keyword!r} looks renderer-specific"


def test_parsed_document_contains_only_spec_construct_types():
    document = parse_document(FULL_EXAMPLE)
    assert len(document.declarations) == 5
    for decl in document.declarations:
        assert isinstance(decl, ALLOWED_AST_DECL_TYPES)


def test_semantic_ir_contains_only_spec_construct_types():
    document = parse_document(FULL_EXAMPLE)
    morpho_ir = ir.from_ast(document, compiler_version="1.0.0")

    assert len(morpho_ir.entities) == 1 and isinstance(morpho_ir.entities[0], ir.Entity)
    assert len(morpho_ir.relations) == 1 and isinstance(morpho_ir.relations[0], ir.MorphoRelation)
    assert len(morpho_ir.frames) == 1 and isinstance(morpho_ir.frames[0], ir.CoordinateFrame)
    assert len(morpho_ir.groups) == 1 and isinstance(morpho_ir.groups[0], ir.Group)
    assert len(morpho_ir.constraints) == 1 and isinstance(morpho_ir.constraints[0], ir.Constraint)

    # No forbidden term appears anywhere in the parsed content itself.
    rendered = repr(morpho_ir).lower()
    for term in FORBIDDEN_TERMS:
        assert term not in rendered, f"IR unexpectedly mentions renderer concept {term!r}"


# -- compile_morpho: pure, deterministic canonical -> IR compilation --------


def test_compile_morpho_produces_one_entity_per_canonical_field(genesis_version):
    ir_doc = compile_morpho(project_state(genesis_version), CompilerConfig())
    assert {e.id for e in ir_doc.entities} == set(genesis_version.state.fields.keys())


def test_compile_morpho_is_deterministic(genesis_version):
    config = CompilerConfig()
    doc1 = compile_morpho(project_state(genesis_version), config)
    doc2 = compile_morpho(project_state(genesis_version), config)
    assert doc1 == doc2


# -- Phase 6: identity model (§9) --------------------------------------------


def test_identity_chain_equals_field_name(genesis_version):
    for field_id in genesis_version.state.fields:
        assert geometry_id(field_id) == field_id
        assert visual_id(field_id) == field_id
        assert cell_id(field_id) == field_id
        assert node_id(field_id) == field_id


def test_identity_stable_across_value_change(sample_schema, genesis_version):
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
    result = validate_candidate(sample_schema, genesis_version.state, candidate)
    assert not isinstance(result, list), result
    new_version = result

    assert new_version.id != genesis_version.id
    assert geometry_id("mass") == visual_id("mass") == cell_id("mass") == node_id("mass") == "mass"
    assert new_version.state.fields["mass"].value == 99


# -- Phase 6: provenance model (§10) -----------------------------------------


def test_canonical_entities_carry_canonical_provenance(genesis_version):
    ir_doc = compile_morpho(project_state(genesis_version), CompilerConfig())
    for entity in ir_doc.entities:
        assert entity.provenance.source == "canonical"
        assert entity.provenance.confidence is None
        assert entity.provenance.origin_version == genesis_version.id
        assert entity.provenance.compiler_version  # always present (§10)
