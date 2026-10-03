import sys
import types

from schematics import Status, decide, quadratic_drag, run
from schematics.adapters.jspt import call_jacobian_at
from schematics.adapters.rci import bind_digest
from schematics.pins import JSPT


def test_jspt_missing_module_is_not_checked(monkeypatch):
    monkeypatch.setitem(sys.modules, "sensitivity", None)
    report = run(quadratic_drag(), call_jspt=True)
    missing = [e for e in report.events if e.tool == "jspt.jacobian_at" and e.result is Status.NOT_CHECKED and e.detail.get("mode") != "plan"]
    assert missing and JSPT["sha"] in str(missing[0].detail)
    assert [d for d in report.decisions if d.tool == "lyapunov.evaluate"][0].status is Status.NOT_ELIGIBLE


def test_jspt_adapter_with_fake_sensitivity(monkeypatch):
    fake = types.ModuleType("sensitivity")

    class Estimate:
        matrix = [[-1.0]]
        source = "analytical"

    class Model:
        def __init__(self, **kwargs):
            self.name = kwargs.get("name")

    fake.DifferentiableModel = Model
    fake.jacobian_at = lambda model, x, source="auto": Estimate()
    fake.reference_catalogue = lambda: {}
    monkeypatch.setitem(sys.modules, "sensitivity", fake)
    sch = quadratic_drag()
    event = call_jacobian_at(sch, "f")
    assert event.result is Status.SAMPLED
    assert sch.node("cert:jspt:f").get("fixture") is False
    assert [d for d in decide(sch) if d.tool == "lyapunov.evaluate"][0].status is Status.ELIGIBLE


def test_rci_bind_does_not_interpret():
    sch = quadratic_drag()
    event = bind_digest(sch, "ySensor", "rci-displacement-digest-fixture")
    assert event.result is Status.SAMPLED and event.detail["interpreted"] is False
    assert [d for d in decide(sch) if d.tool == "rci.bind"][0].status is Status.ELIGIBLE
