from schematics import NodeKind, Status, decide, eligible, quadratic_drag, run
from schematics.ir import Node


def test_quadratic_drag_jspt_eligible_plsr_not():
    rows = decide(quadratic_drag())
    assert [d for d in rows if d.tool == "jspt.jacobian_at"][0].status is Status.ELIGIBLE
    assert [d for d in rows if d.tool == "lyapunov.evaluate"][0].status is Status.NOT_ELIGIBLE
    assert [d for d in rows if d.tool == "rci.bind"][0].status is Status.NOT_ELIGIBLE


def test_unknown_class_blocks_jspt():
    sch = quadratic_drag()
    node = sch.node("f")
    sch.replace(Node(id="f", kind=NodeKind.FUNCTION, attrs={**dict(node.attrs), "class": "unknown", "model_ref": ""}))
    assert eligible(sch, "jspt.jacobian_at") == []


def test_fixture_A_does_not_open_lyapunov():
    report = run(quadratic_drag(), attach_fixture_A=True)
    lyap = [d for d in report.decisions if d.tool == "lyapunov.evaluate"]
    assert lyap[0].status is Status.NOT_ELIGIBLE
    cert = report.schematic.node("cert:jspt:f")
    assert cert.get("fixture") is True
