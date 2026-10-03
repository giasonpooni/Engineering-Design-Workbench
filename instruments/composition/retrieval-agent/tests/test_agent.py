from schematics import Status, quadratic_drag, run
from schematics import io
from schematics.project_mermaid import mermaid
from schematics.project_usd import usda


def test_agent_maps_and_asks_for_digest():
    report = run(quadratic_drag())
    assert report.schematic.node("observer").get("status") == Status.MAPPED.value
    assert "RCI digest" in report.next_step


def test_projections_roundtrip_json():
    report = run(quadratic_drag(), attach_fixture_A=True)
    again = io.loads(io.dumps(report.schematic))
    assert set(again.nodes) == set(report.schematic.nodes)
    assert "f" in mermaid(again) and "NsPlantAPI" in usda(again)
