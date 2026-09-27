"""First slices for the directions the product README used to over-claim."""
from pathlib import Path

import pytest

from ciw.design_manifold import apply_chart, catalog as chart_catalog
from ciw.energy_gateway import status as energy_status
from ciw.instruments import make_demo_run
from ciw.language_bindings import catalog as binding_catalog, inspect_binding
from ciw.learning import ENERGY_TOPIC, catalog as lesson_catalog, lesson
from ciw.usda_export import compare_export, export_recording
from ciw.view_render import attach_plane


def test_usda_compare_matches_retained_oscillator_points():
    run = make_demo_run()
    text = export_recording(run)
    report = compare_export(run, text)
    assert report["status"] == "matched"
    assert report["openusd_runtime"] == "not_loaded"
    assert report["point_count"] == len(run["render"]["trajectory"])


def test_usda_compare_matches_a_plane_canvas():
    panel = {"labels": ["a.x", "a.y"], "values": [1.0, 0.25], "units": ["m", "m"]}
    attach_plane(panel, frame="bench-plane", canvas_id="observed_points_m",
                 canvas_title="Observed coordinates")
    from ciw.usda_export import export_render
    text = export_render(panel["render"])
    report = compare_export(panel["render"], text)
    assert report["point_count"] == 1


def test_language_bindings_are_inspectable_without_a_chain():
    catalog = binding_catalog()
    assert catalog["required_chain"] is False
    assert [item["id"] for item in catalog["bindings"]] == [
        "python-session", "julia-oscillator", "native-interop-scr"]
    report = inspect_binding("python-session")
    assert report["status"] == "inspectable"
    refused = inspect_binding("julia-oscillator")
    assert refused["status"] == "refused"
    assert refused["runtime_launched"] is False


def test_energy_gateway_is_structured_when_a_device_is_absent():
    report = energy_status(0)
    assert report["schema"] == "ciw.energy-gateway.v1"
    assert report["authority"] == "not_a_laboratory_gateway"
    assert report["status"] in ("available", "unavailable")


def test_design_chart_refuses_to_collapse_frames():
    mapped = apply_chart("scale", [2.0, 3.0], source_frame="model",
                         target_frame="display", scales=[0.5, 2.0])
    assert mapped["target"] == [1.0, 6.0]
    with pytest.raises(ValueError):
        apply_chart("identity", [1.0], source_frame="same", target_frame="same")
    assert chart_catalog()["charts"][0]["id"] == "identity"


def test_julia_source_binding_inspects_without_julia():
    report = inspect_binding("julia-oscillator", "examples/julia/oscillator.json")
    assert report["status"] == "inspectable"
    assert report["runtime_launched"] is False


def test_energy_log_replays_without_opening_a_device():
    from ciw.energy_gateway import replay_log
    report = replay_log("examples/energy-accuracy/baseline.json")
    assert report["status"] == "replayed"
    assert report["device_opened"] is False


def test_design_charts_compose_across_three_frames():
    from ciw.design_manifold import compose
    mapped = compose("scale", "identity", [2.0, 4.0], source_frame="model",
                     mid_frame="display", target_frame="scene", first_scales=[0.5, 0.25])
    assert mapped["mid"] == [1.0, 1.0]
    assert mapped["target"] == [1.0, 1.0]
    with pytest.raises(ValueError):
        compose("identity", "identity", [1.0], source_frame="a", mid_frame="a", target_frame="b")


def test_lesson_progress_sequences_the_two_oscillator_lessons():
    from ciw.learning import progress
    state = progress()
    assert state["next"] == "oscillator-rms"
    done = progress(["oscillator-rms"])
    assert done["next"] == "oscillator-energy"
    finished = progress(["oscillator-rms", "oscillator-energy"])
    assert finished["next"] is None
