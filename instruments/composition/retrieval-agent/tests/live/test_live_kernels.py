"""Explicit live runs must exercise the declared kernels, never skip them."""
import json
from importlib.metadata import distribution

import pytest

from schematics import Status, quadratic_drag, run
from schematics.adapters.jspt import call_jacobian_at, load_sensitivity
from schematics.adapters.plsr import load_lyapunov
from schematics.adapters.rci import load_instrument_chain
from schematics.pins import JSPT, PLSR, RCI
from schematics.eligibility import _written_A
from schematics.ir import Node
from schematics.adapters.covariance import call_first_order_covariance
from schematics.adapters.plsr import call_evaluate
from schematics.adapters.montecarlo import call_monte_carlo_covariance

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


def test_live_bound_covariance_path_and_stale_operating_point_refusal():
    sch = quadratic_drag()
    node = sch.node("f")
    sch.replace(Node(node.id, node.kind, {**dict(node.attrs), "sigma_x": [[0.04]]}))
    event = call_jacobian_at(sch, "f")
    assert event.result is Status.SAMPLED
    assert _written_A(sch, "f") is not None
    cov = call_first_order_covariance(sch, "f")
    assert cov.result is Status.SAMPLED
    assert cov.detail["sigma_y"][0][0] == pytest.approx(0.04)
    assert sch.node("cert:jspt.cov:f").get("source_result_ref") == event.detail["result_ref"]
    node = sch.node("f")
    sch.replace(Node(node.id, node.kind, {**dict(node.attrs), "x_star": [2.0]}))
    assert call_first_order_covariance(sch, "f").result is Status.NOT_ELIGIBLE
    assert call_evaluate(sch, "f").result is Status.NOT_ELIGIBLE
    assert call_jacobian_at(sch, "f").result is Status.SAMPLED
    fresh = call_first_order_covariance(sch, "f")
    assert fresh.result is Status.SAMPLED
    assert fresh.detail["sigma_y"][0][0] == pytest.approx(0.16)


def test_live_stale_downstream_results_remain_inspectable_not_current():
    sch = quadratic_drag(with_digest=True)
    node = sch.node("f")
    sch.replace(Node(node.id, node.kind, {**dict(node.attrs), "sigma_x": [[0.04]]}))
    run(sch, call_jspt=True, call_plsr=True)
    ids = ["cert:jspt:f", "cert:jspt.cov:f", "cert:jspt.structure:f", "cert:lyapunov:f"]
    assert all(sch.node(i).get("result") == "SAMPLED" for i in ids)
    old_P = sch.node("cert:lyapunov:f").get("P")
    node = sch.node("f")
    sch.replace(Node(node.id, node.kind, {**dict(node.attrs), "x_star": [2.0]}))
    report = run(sch)
    for i in ids:
        assert sch.node(i).get("result") == "NOT_ELIGIBLE"
        assert sch.node(i).get("historical_result") == "SAMPLED"
        assert sch.node(i).get("currentness") == "stale"
    assert sch.node("cert:lyapunov:f").get("P") == old_P
    assert "not yet sampled" in report.next_step


def test_live_removed_covariance_invalidates_old_covariance_not_jacobian():
    sch = quadratic_drag()
    node = sch.node("f")
    sch.replace(Node(node.id, node.kind, {**dict(node.attrs), "sigma_x": [[0.04]]}))
    assert call_jacobian_at(sch, "f").result is Status.SAMPLED
    assert call_first_order_covariance(sch, "f").result is Status.SAMPLED
    attrs = dict(sch.node("f").attrs)
    del attrs["sigma_x"]
    sch.replace(Node("f", node.kind, attrs))
    run(sch)
    assert _written_A(sch, "f") is not None
    cov = sch.node("cert:jspt.cov:f")
    assert cov.get("result") == "NOT_ELIGIBLE"
    assert cov.get("currentness") == "stale"
    assert cov.get("sigma_x") == [[0.04]]


def test_live_monte_carlo_changed_covariance_marks_old_experiment_stale():
    sch = quadratic_drag()
    node = sch.node("f")
    sch.replace(Node(node.id, node.kind, {**dict(node.attrs), "sigma_x": [[0.04]]}))
    assert call_jacobian_at(sch, "f").result is Status.SAMPLED
    assert call_monte_carlo_covariance(sch, "f", samples=100).result is Status.SAMPLED
    node = sch.node("f")
    sch.replace(Node(node.id, node.kind, {**dict(node.attrs), "sigma_x": [[0.09]]}))
    run(sch)
    assert _written_A(sch, "f") is not None
    mc = sch.node("cert:jspt.mc:f")
    assert mc.get("result") == "NOT_ELIGIBLE"
    assert mc.get("currentness") == "stale"
    assert mc.get("sigma_x") == [[0.04]]
