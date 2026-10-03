"""Phase 12 §6: a synthetic-but-realistic material/process time series,
represented through the canonical system and compiled into graph, SVG,
and Three.js representations from ONE shared canonical state / Morpho
IR -- not three separate pipelines.
"""

from backends.diagram.compiler import DiagramLayoutConfig, compile_svg
from backends.graph.analysis import analyze
from backends.threejs.compiler import ThreeJSRenderConfig, compile_threejs
from core.projection.project import project_state
from morpho.compiler import CompilerConfig, compile_morpho
from tests.fixtures_time_series import CHANNELS, build_time_series_version


def test_time_series_fixture_has_the_expected_shape():
    version = build_time_series_version()
    assert len(version.state.fields) == sum(len(samples) for samples in CHANNELS.values())
    # 5 "precedes" edges per 6-sample channel.
    assert len(version.state.edges) == sum(len(samples) - 1 for samples in CHANNELS.values())
    assert version.state.fields["stress_MPa_t5"].value == 4.6


def test_time_series_compiles_once_and_feeds_all_three_backends_from_the_same_ir():
    """Not three separate pipelines: one compile_morpho() call produces
    one MorphoDocument, and that SAME object is handed to all three
    backends."""
    version = build_time_series_version()
    ir_doc = compile_morpho(project_state(version), CompilerConfig())

    report = analyze(ir_doc)
    svg = compile_svg(ir_doc, DiagramLayoutConfig())
    scene = compile_threejs(ir_doc, ThreeJSRenderConfig())

    canonical_ids = set(version.state.fields.keys())
    assert set(report.adjacency.keys()) == canonical_ids
    assert {m["id"] for m in scene.meshes} == canonical_ids
    for field_id in canonical_ids:
        assert f'data-entity-id="{field_id}"' in svg


def test_time_series_ordering_is_visible_as_graph_structure_in_every_backend():
    """The temporal ordering (temperature_t0 precedes temperature_t1
    precedes ...) is not lost -- it shows up as real graph structure in
    the graph backend's adjacency and as real relation ids in the SVG,
    both derived from the SAME canonical "precedes" edges."""
    version = build_time_series_version()
    ir_doc = compile_morpho(project_state(version), CompilerConfig())

    report = analyze(ir_doc)
    assert report.edge_count == len(version.state.edges)
    assert "temperature_C_t1" in report.adjacency["temperature_C_t0"]

    svg = compile_svg(ir_doc, DiagramLayoutConfig())
    assert 'data-relation-id="temperature_C_t0__precedes__temperature_C_t1"' in svg

    # Every "precedes" relation is a canonical, explicit fact -- not an
    # inferred one -- because it came directly from CanonicalState.edges.
    assert len(ir_doc.relations) == len(version.state.edges)
    assert all(r.is_canonical and r.inference_status == "explicit" for r in ir_doc.relations)


def test_time_series_geometry_reflects_the_process_ramp():
    """The Phase 12 §5 value-encoding upgrade applies here too, with no
    special-casing: temperature_t4 (185, near the plateau) gets a larger
    box than temperature_t0 (20, the start of the ramp) -- both entities
    from the SAME shared IR as the graph/SVG checks above."""
    version = build_time_series_version()
    ir_doc = compile_morpho(project_state(version), CompilerConfig())
    scene = compile_threejs(ir_doc, ThreeJSRenderConfig())

    size_by_id = {g["id"]: g["params"]["size"] for g in scene.geometries}
    assert size_by_id["temperature_C_t4"] > size_by_id["temperature_C_t0"]


def test_time_series_recompilation_is_deterministic():
    version = build_time_series_version()
    config = CompilerConfig()
    ir_1 = compile_morpho(project_state(version), config)
    ir_2 = compile_morpho(project_state(version), config)
    assert ir_1 == ir_2
    assert compile_threejs(ir_1, ThreeJSRenderConfig()) == compile_threejs(ir_2, ThreeJSRenderConfig())
    assert compile_svg(ir_1, DiagramLayoutConfig()) == compile_svg(ir_2, DiagramLayoutConfig())
    assert analyze(ir_1) == analyze(ir_2)
