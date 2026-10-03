"""§21 tests 7-9, 16: renderer cannot mutate canonical state, geometry
identity survives value changes, deleted entities disappear downstream,
and the Three.js backend cannot become a source of truth."""

import ast as pyast
import inspect
import re
from pathlib import Path

from backends.threejs import compiler as threejs_compiler
from backends.threejs.compiler import ThreeJSRenderConfig, compile_threejs
from core.canonical.delta import CandidateChange, CandidateDelta
from core.canonical.schema import FieldSchema, StateSchema
from core.canonical.validation import validate_candidate
from core.canonical.version import ProvenanceInfo, create_genesis_version
from core.projection.project import project_state
from morpho.compiler import CompilerConfig, compile_morpho

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDERER_HTML = REPO_ROOT / "renderer" / "index.html"

FORBIDDEN_RENDERER_REFERENCES = (
    "validate_candidate",
    "CanonicalState",
    "VersionStore",
    "core.canonical",
    "core/canonical",
)


def _strip_comments(html_source: str) -> str:
    """Strip HTML comments (<!-- ... -->), JS block comments (/* ... */),
    and JS line comments (// ...) so the check below looks at actual code
    and markup, not at explanatory prose that is allowed to name the
    boundary it documents (this file's own comments do exactly that)."""
    text = re.sub(r"<!--.*?-->", "", html_source, flags=re.DOTALL)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def test_renderer_html_never_references_canonical_mutation_endpoints():
    """Static check (§7 in §21's own description: 'renderer/ manual'):
    renderer/index.html has no import, fetch target, or identifier that
    could write back into CanonicalState, Version, or ProjectedState."""
    code_only = _strip_comments(RENDERER_HTML.read_text())
    for forbidden in FORBIDDEN_RENDERER_REFERENCES:
        assert forbidden not in code_only, f"renderer/index.html code references {forbidden!r}"


def test_threejs_scene_descriptor_is_plain_declarative_data():
    schema = StateSchema(
        schema_version="1.0.0", fields={"mass": FieldSchema(id="mass", type="scalar", default=10)}
    )
    v0 = create_genesis_version(schema, "2026-08-22T00:00:00Z")
    ir_doc = compile_morpho(project_state(v0), CompilerConfig())
    descriptor = compile_threejs(ir_doc, ThreeJSRenderConfig())

    import json

    json.dumps(
        {
            "geometries": descriptor.geometries,
            "materials": descriptor.materials,
            "meshes": descriptor.meshes,
            "hierarchy": descriptor.hierarchy,
        }
    )  # must be plain JSON-serializable data, never a THREE.* object


def test_geometry_identity_survives_value_changes(sample_schema, genesis_version):
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

    config = ThreeJSRenderConfig()
    scene_before = compile_threejs(compile_morpho(project_state(genesis_version), CompilerConfig()), config)
    scene_after = compile_threejs(compile_morpho(project_state(v1), CompilerConfig()), config)

    geoms_before = {g["id"]: g for g in scene_before.geometries}
    geoms_after = {g["id"]: g for g in scene_after.geometries}
    meshes_before = {m["id"]: m for m in scene_before.meshes}
    meshes_after = {m["id"]: m for m in scene_after.meshes}

    assert "mass" in geoms_before and "mass" in geoms_after
    assert "mass" in meshes_before and "mass" in meshes_after
    assert meshes_after["mass"]["geometry"] == meshes_before["mass"]["geometry"] == "mass"


def test_deleted_entity_disappears_from_scene_descriptor():
    schema = StateSchema(
        schema_version="1.0.0",
        fields={
            "mass": FieldSchema(id="mass", type="scalar", default=10),
            "note": FieldSchema(id="note", type="string", default="temp", required=False),
        },
    )
    v0 = create_genesis_version(schema, "2026-08-22T00:00:00Z")
    scene_before = compile_threejs(compile_morpho(project_state(v0), CompilerConfig()), ThreeJSRenderConfig())
    assert any(m["id"] == "note" for m in scene_before.meshes)

    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=v0.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.note",
                operation="remove",
                old_value={"id": "note", "type": "string", "value": "temp", "unit": None},
                new_value=None,
                provenance=provenance,
            ),
        ),
    )
    v1 = validate_candidate(schema, v0.state, candidate)
    assert not isinstance(v1, list), v1

    scene_after = compile_threejs(compile_morpho(project_state(v1), CompilerConfig()), ThreeJSRenderConfig())
    assert not any(m["id"] == "note" for m in scene_after.meshes)
    assert not any(g["id"] == "note" for g in scene_after.geometries)
    assert any(m["id"] == "mass" for m in scene_after.meshes)


def test_threejs_backend_cannot_become_source_of_truth():
    # representation_never_enters_canonical_state (I8): a backend holds
    # no import of the canonical mutation surface.
    source = inspect.getsource(threejs_compiler)
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
            f"backends/threejs/compiler.py must not import {module_name}"
        )
    assert "VersionStore" not in source
    assert "validate_candidate" not in source


# -- Phase 12 §5: deterministic value-to-geometry encoding -----------------


def test_same_identity_different_value_yields_same_id_but_different_geometry(sample_schema, genesis_version):
    """same canonical identity + different numeric value -> same entity
    identity -> different deterministic geometry (Phase 12 §5, verbatim
    requirement)."""
    provenance = ProvenanceInfo(author="test", transaction_id="tx1", source="manual_edit")
    candidate = CandidateDelta(
        version_from=genesis_version.id,
        transaction_id="tx1",
        timestamp="2026-08-22T00:01:00Z",
        changes=(
            CandidateChange(
                path="fields.mass.value", operation="replace", old_value=10, new_value=9999, provenance=provenance
            ),
        ),
    )
    v1 = validate_candidate(sample_schema, genesis_version.state, candidate)
    assert not isinstance(v1, list), v1

    config = ThreeJSRenderConfig()
    scene_before = compile_threejs(compile_morpho(project_state(genesis_version), CompilerConfig()), config)
    scene_after = compile_threejs(compile_morpho(project_state(v1), CompilerConfig()), config)

    geom_before = next(g for g in scene_before.geometries if g["id"] == "mass")
    geom_after = next(g for g in scene_after.geometries if g["id"] == "mass")

    assert geom_before["id"] == geom_after["id"] == "mass"  # same entity identity
    assert geom_before["params"]["size"] != geom_after["params"]["size"]  # different deterministic geometry


def test_same_canonical_state_yields_byte_equivalent_scene_descriptor(genesis_version):
    # projection_is_deterministic (I6/I7), at the backend end: byte
    # equivalence, not merely equivalence.
    """same canonical state -> byte-equivalent scene descriptor (Phase 12
    §5, verbatim requirement) -- recompiling from the identical Version
    twice, including the new value-dependent geometry sizing, must be
    exactly equal, not merely "close.\""""
    config = ThreeJSRenderConfig()
    ir_doc = compile_morpho(project_state(genesis_version), CompilerConfig())
    scene1 = compile_threejs(ir_doc, config)
    scene2 = compile_threejs(ir_doc, config)
    assert scene1 == scene2

    import json

    assert json.dumps(
        {"geometries": scene1.geometries, "meshes": scene1.meshes}, sort_keys=True
    ) == json.dumps({"geometries": scene2.geometries, "meshes": scene2.meshes}, sort_keys=True)
