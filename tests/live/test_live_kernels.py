"""Explicit live runs must exercise the declared kernels, never skip them."""
import json
from importlib.metadata import distribution

import pytest

from schematics import Status, quadratic_drag, run
from schematics.adapters.jspt import call_jacobian_at, load_sensitivity
from schematics.adapters.plsr import load_lyapunov
from schematics.adapters.rci import load_instrument_chain
from schematics.pins import JSPT, PLSR, RCI

pytestmark = pytest.mark.live


@pytest.mark.parametrize("name,pin", [
    ("jacobian-sensitivity-propagation-testbed", JSPT),
    ("parameterized-lyapunov-stability-runtime", PLSR),
    ("retrofitted-computational-instrumentation", RCI),
])
def test_installed_kernel_matches_declared_commit(name, pin):
    source = json.loads(distribution(name).read_text("direct_url.json"))
    assert source["url"] == f"https://github.com/{pin['repo']}.git"
    assert source["vcs_info"]["commit_id"] == pin["sha"]


def test_sensitivity_imports_at_pin():
    assert hasattr(load_sensitivity(), "jacobian_at")


def test_lyapunov_imports_at_pin():
    assert hasattr(load_lyapunov(), "plant_from_jacobian")


def test_instrument_chain_imports_at_pin():
    mod = load_instrument_chain()
    assert hasattr(mod, "Quality")
    assert hasattr(mod, "Assembly")


def test_live_jacobian_samples_A():
    event = call_jacobian_at(quadratic_drag(), "f")
    assert event.result is Status.SAMPLED
    assert event.detail["pin"] == JSPT


def test_live_jacobian_to_lyapunov_path():
    report = run(quadratic_drag(), call_jspt=True, call_plsr=True)
    for tool in ["jspt.jacobian_at", "jspt.sweep_perturbation_scale",
                 "jspt.local_structure", "lyapunov.evaluate"]:
        events = [e for e in report.events if e.tool == tool and e.result is Status.SAMPLED]
        assert len(events) == 1, [(e.tool, e.result, e.detail) for e in report.events]
    assert report.schematic.node("cert:jspt:f").get("fixture") is False
    assert report.schematic.node("cert:lyapunov:f").get("verdict") == "certified"
