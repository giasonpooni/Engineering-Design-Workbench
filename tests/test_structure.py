import sys
import types

from schematics import Status, decide, quadratic_drag, run
from schematics.adapters.structure import call_local_structure
from schematics.ir import EdgeKind, Node, NodeKind
from schematics.pins import JSPT


def _with_A(fixture: bool = False):
    sch = quadratic_drag()
    sch.add(Node(id="cert:jspt:f", kind=NodeKind.CERTIFICATE, attrs={"owner": "jspt", "result": Status.SAMPLED.value, "A": [[-1.0]], "fixture": fixture}))
    sch.connect(EdgeKind.LINEARIZES, "cert:jspt:f", "f")
    return sch


def test_structure_not_eligible_without_A():
    rows = [d for d in decide(quadratic_drag()) if d.tool == "jspt.local_structure"]
    assert rows and rows[0].status is Status.NOT_ELIGIBLE


def test_fixture_A_does_not_open_structure():
    rows = [d for d in decide(_with_A(fixture=True)) if d.tool == "jspt.local_structure"]
    assert rows and rows[0].status is Status.NOT_ELIGIBLE


def test_structure_missing_module_is_not_checked(monkeypatch):
    monkeypatch.setitem(sys.modules, "sensitivity", None)
    event = call_local_structure(_with_A(fixture=False), "f")
    assert event.result is Status.NOT_CHECKED
    assert JSPT["sha"] in str(event.detail)


def test_structure_adapter_hangs_rank(monkeypatch):
    fake = types.ModuleType("sensitivity")

    class Structure:
        rank = 1
        invisible = []
        visible = [[1.0]]
        singular_values = [1.0]

    fake.local_structure = lambda A, singular_atol=1e-10: Structure()
    monkeypatch.setitem(sys.modules, "sensitivity", fake)
    sch = _with_A(fixture=False)
    event = call_local_structure(sch, "f")
    assert event.result is Status.SAMPLED
    assert event.detail["rank"] == 1
    assert event.detail["invisible_dim"] == 0
    assert sch.node("f").get("rank") == 1
    assert sch.node("cert:jspt.structure:f").get("reason") == "ker J at x_star; not Kalman observability"


def test_agent_does_not_claim_observability_from_rank():
    report = run(quadratic_drag())
    assert "unobservable" not in report.next_step.lower()
    assert "kalman" not in report.next_step.lower()
