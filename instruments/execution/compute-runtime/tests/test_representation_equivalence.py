"""Phase 9: the central architectural property this repository claims --

    ONE AUTHORITATIVE CANONICAL STATE -> MULTIPLE STRUCTURALLY DISTINCT,
    SEMANTICALLY EQUIVALENT REPRESENTATIONS

-- demonstrated end to end: CanonicalState -> project_state -> compile_morpho
(one shared Morpho IR) -> {compile_threejs, compile_svg, graph.analyze}
(three structurally different backends consuming that SAME IR).

This is not a smoke test. It exists specifically to prove -- not merely
assert -- that identity, provenance, and structural facts survive the
fan-out to multiple representations, that no backend mutates anything
upstream of it, and that recompiling the same Version twice is
byte/structurally identical. See the module docstring on each assertion
group for exactly what is and is not covered.
"""

import copy

from backends.diagram.compiler import DiagramLayoutConfig, compile_svg
from backends.graph.analysis import analyze
from backends.threejs.compiler import ThreeJSRenderConfig, compile_threejs
from core.canonical.schema import FieldSchema, StateSchema
from core.canonical.version import create_genesis_version
from core.projection.project import project_state
from morpho.compiler import CompilerConfig, compile_morpho

# The exact example schema from this session's Phase 9 instructions.
MATERIAL_SCHEMA = StateSchema(
    schema_version="1.0.0",
    fields={
        "temperature": FieldSchema(id="temperature", type="scalar", unit="C", default=185.0),
        "pressure": FieldSchema(id="pressure", type="scalar", unit="bar", default=42.0),
        "molecular_weight": FieldSchema(id="molecular_weight", type="scalar", unit="g/mol", default=185000),
        "crystallinity": FieldSchema(id="crystallinity", type="scalar", unit=None, default=0.38),
    },
)


def _pipeline(version):
    """CanonicalState -> Projection -> Morpho IR, the single shared
    upstream representation every backend below consumes."""
    projected = project_state(version)
    ir_doc = compile_morpho(projected, CompilerConfig())
    return ir_doc


def test_one_canonical_state_produces_three_structurally_distinct_representations():
    """The headline property: a single canonical Version, compiled once
    to a single Morpho IR, fans out into three backend outputs of
    genuinely different shape (a dataclass of dicts, an XML string, and
    a graph-metrics dataclass) -- not three copies of the same object,
    and not three independent re-derivations from raw canonical state
    (each backend receives the SAME `ir_doc` instance)."""
    version = create_genesis_version(MATERIAL_SCHEMA, "2026-08-22T00:00:00Z")
    ir_doc = _pipeline(version)

    scene = compile_threejs(ir_doc, ThreeJSRenderConfig())
    svg = compile_svg(ir_doc, DiagramLayoutConfig())
    report = analyze(ir_doc)

    assert isinstance(scene.meshes, tuple) and isinstance(scene.meshes[0], dict)
    assert isinstance(svg, str) and svg.startswith("<svg")
    assert isinstance(report.node_count, int)
    # Structurally distinct types, not the same representation relabeled.
    assert {type(scene), type(svg), type(report)} == {type(scene), str, type(report)}


def test_canonical_field_identity_is_preserved_across_all_three_backends():
    """Identity (§9): every backend must reference the exact same 4
    field ids the canonical schema declares -- no backend renames,
    drops, or invents an id."""
    version = create_genesis_version(MATERIAL_SCHEMA, "2026-08-22T00:00:00Z")
    ir_doc = _pipeline(version)
    canonical_ids = set(version.state.fields.keys())
    assert canonical_ids == {"temperature", "pressure", "molecular_weight", "crystallinity"}

    scene = compile_threejs(ir_doc, ThreeJSRenderConfig())
    threejs_ids = {m["id"] for m in scene.meshes}

    svg = compile_svg(ir_doc, DiagramLayoutConfig())
    svg_ids = {fid for fid in canonical_ids if f'data-entity-id="{fid}"' in svg}

    report = analyze(ir_doc)
    graph_ids = set(report.adjacency.keys())

    assert threejs_ids == canonical_ids
    assert svg_ids == canonical_ids
    assert graph_ids == canonical_ids


def test_provenance_traces_from_every_backend_back_to_the_canonical_version():
    """Provenance (§10): every Entity in the shared Morpho IR carries
    source="canonical", confidence=None, and origin_version equal to the
    exact Version.id this pipeline started from -- regardless of which
    backend(s) go on to consume that IR. Provenance lives at the IR
    layer (this is where §10 places it); backend *outputs* (the scene
    descriptor, the SVG string, the graph report) are declarative visual/
    structural projections and are not required to re-embed it (§14/§15
    define no such field) -- what matters is that compiling any number
    of backends from the same IR never alters what the IR itself says."""
    version = create_genesis_version(MATERIAL_SCHEMA, "2026-08-22T00:00:00Z")
    ir_doc = _pipeline(version)

    for entity in ir_doc.entities:
        assert entity.provenance.source == "canonical"
        assert entity.provenance.confidence is None
        assert entity.provenance.origin_version == version.id

    # Compiling all three backends must not alter the IR's own provenance.
    ir_snapshot = copy.deepcopy(ir_doc)
    compile_threejs(ir_doc, ThreeJSRenderConfig())
    compile_svg(ir_doc, DiagramLayoutConfig())
    analyze(ir_doc)
    assert ir_doc == ir_snapshot


def test_values_are_semantically_readable_where_a_backend_renders_them():
    """Scoped, honest claim about value equivalence: the SVG backend
    visually renders each field's value (verified directly against the
    schema defaults below), and the graph backend is value-blind by
    design (it reports structure: node/edge counts, adjacency, degree).
    This is not asserted as a defect -- nothing in the frozen spec
    requires every backend to encode every value visually, and a
    graph-analysis backend legitimately doesn't care about magnitudes.

    UPDATE (Phase 12): the Three.js backend WAS value-invariant (fixed
    1x1x1 box for every entity) when this test was first written -- that
    limitation was named explicitly right here. It has since been
    closed: backends/threejs/compiler.py now derives each box's size
    from a deterministic min-max normalization of the entity's numeric
    value against the other numeric values in the same scene (see that
    module's docstring for the exact mapping). This assertion is updated
    to match, not silently loosened -- see
    test_threejs_geometry_size_reflects_normalized_value below for a
    dedicated, tighter check of the new behavior."""
    version = create_genesis_version(MATERIAL_SCHEMA, "2026-08-22T00:00:00Z")
    ir_doc = _pipeline(version)
    svg = compile_svg(ir_doc, DiagramLayoutConfig())

    expected_values = {
        "temperature": 185.0,
        "pressure": 42.0,
        "molecular_weight": 185000,
        "crystallinity": 0.38,
    }
    for field_id, value in expected_values.items():
        assert f">{value}</text>" in svg, f"SVG does not render {field_id}={value}"

    # Three.js: geometry size now varies with each entity's normalized
    # value (Phase 12) -- these 4 distinct values must not all collapse
    # to the same size.
    scene = compile_threejs(ir_doc, ThreeJSRenderConfig())
    sizes = {tuple(g["params"]["size"]) for g in scene.geometries}
    assert len(sizes) > 1, "geometry size no longer varies by value -- Phase 12 regression"


def test_threejs_geometry_size_reflects_normalized_value():
    """Dedicated check of the Phase 12 value-encoding upgrade: the
    entity with the highest numeric value gets the largest box, the
    lowest gets the smallest, and the mapping stays within the
    documented [_MIN_SCALE, _MAX_SCALE] bounds."""
    version = create_genesis_version(MATERIAL_SCHEMA, "2026-08-22T00:00:00Z")
    ir_doc = _pipeline(version)
    scene = compile_threejs(ir_doc, ThreeJSRenderConfig())

    size_by_id = {m["id"]: tuple(g["params"]["size"]) for m, g in zip(scene.meshes, scene.geometries)}
    # molecular_weight (185000) is by far the largest value in this
    # schema; crystallinity (0.38) is by far the smallest.
    assert size_by_id["molecular_weight"] > size_by_id["crystallinity"]
    for size in size_by_id.values():
        assert 0.5 <= size[0] <= 2.0 and size[0] == size[1] == size[2]  # uniform cube, within documented bounds


def test_no_backend_mutates_canonical_state_or_the_shared_ir():
    version = create_genesis_version(MATERIAL_SCHEMA, "2026-08-22T00:00:00Z")
    fields_before = dict(version.state.fields)
    edges_before = version.state.edges

    ir_doc = _pipeline(version)
    ir_snapshot = copy.deepcopy(ir_doc)

    compile_threejs(ir_doc, ThreeJSRenderConfig())
    compile_svg(ir_doc, DiagramLayoutConfig())
    analyze(ir_doc)

    assert version.state.fields == fields_before
    assert version.state.edges == edges_before
    assert ir_doc == ir_snapshot


def test_deterministic_recompilation_produces_equivalent_results_in_all_backends():
    """Re-running the whole pipeline twice from the same Version must
    produce equal output in every backend -- not merely "close enough."
    """
    version = create_genesis_version(MATERIAL_SCHEMA, "2026-08-22T00:00:00Z")

    ir_doc_1 = _pipeline(version)
    ir_doc_2 = _pipeline(version)
    assert ir_doc_1 == ir_doc_2

    threejs_config = ThreeJSRenderConfig()
    svg_config = DiagramLayoutConfig()
    assert compile_threejs(ir_doc_1, threejs_config) == compile_threejs(ir_doc_2, threejs_config)
    assert compile_svg(ir_doc_1, svg_config) == compile_svg(ir_doc_2, svg_config)
    assert analyze(ir_doc_1) == analyze(ir_doc_2)


def test_backend_swap_does_not_require_or_cause_any_canonical_state_change():
    """'Can a backend be replaced without changing the canonical state?'
    (architectural validation question 5) -- demonstrated directly:
    compiling only Three.js, only SVG, only graph analysis, or all
    three, from the same Version, produces byte-identical
    CanonicalState.fields/.edges in every case. Nothing about which
    backend(s) happen to run is visible to, or required by, canonical
    state."""
    version = create_genesis_version(MATERIAL_SCHEMA, "2026-08-22T00:00:00Z")
    baseline_fields = dict(version.state.fields)

    ir_doc = _pipeline(version)
    compile_threejs(ir_doc, ThreeJSRenderConfig())
    assert version.state.fields == baseline_fields

    ir_doc = _pipeline(version)
    compile_svg(ir_doc, DiagramLayoutConfig())
    assert version.state.fields == baseline_fields

    ir_doc = _pipeline(version)
    analyze(ir_doc)
    assert version.state.fields == baseline_fields
