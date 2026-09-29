from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry, experiment, run_graph
from ciw.instruments import make_demo_run
from ciw.needle import (
    candidate_experiment,
    delta_projection,
    dependency_closure,
    execute_needle,
    plan_from_spec,
    validate_delta,
    validate_needle_run,
)
from ciw.session import Session


def graph():
    return experiment(
        "needle-oscillator-v1",
        model_id="analytic-damped-oscillator.v1",
        nodes=[
            {
                "node_id": "statistics",
                "operation_id": "statistics.v1",
                "parameters": {"channel": "q"},
                "inputs": {},
                "depends_on": [],
            },
            {
                "node_id": "spectrum",
                "operation_id": "spectrum.periodogram.v1",
                "parameters": {"channel": "q"},
                "inputs": {},
                "depends_on": ["statistics"],
            },
            {
                "node_id": "energy_statistics",
                "operation_id": "statistics.v1",
                "parameters": {"channel": "energy"},
                "inputs": {},
                "depends_on": [],
            },
        ],
    )


def spec():
    return {
        "needle_id": "q-to-v",
        "target": {
            "kind": "NODE_PARAMETER",
            "node_id": "statistics",
            "parameter": "channel",
        },
        "replacement": "v",
        "propagation": {
            "relation": "DEPENDENCY",
            "scope": "DESCENDANTS_INCLUSIVE",
        },
    }


def baseline(tmp_path):
    registry = builtin_registry(bind=True)
    source = make_demo_run()
    session = Session(source, tmp_path / "session", operations=registry.operations)
    run = run_graph(session, graph(), registry)
    assert run["status"] == "completed"
    return registry, source, session, run


def test_dependency_closure_is_target_plus_declared_descendants_only():
    assert dependency_closure(graph(), "statistics") == ["statistics", "spectrum"]
    assert dependency_closure(graph(), "energy_statistics") == ["energy_statistics"]


def test_candidate_is_immutable_and_changes_only_target_parameter(tmp_path):
    _, _, _, run = baseline(tmp_path)
    before = deepcopy(run)
    plan = plan_from_spec(run, spec())
    candidate = candidate_experiment(run, plan)
    assert run == before
    nodes = {node["node_id"]: node for node in candidate["nodes"]}
    assert nodes["statistics"]["parameters"]["channel"] == "v"
    assert nodes["spectrum"]["parameters"]["channel"] == "q"
    assert nodes["energy_statistics"]["parameters"]["channel"] == "energy"
    assert candidate["record_digest"] != run["experiment"]["record_digest"]


def test_selective_recompute_reuses_independent_branch(tmp_path):
    registry, _, session, run = baseline(tmp_path)
    baseline_execution_count = len(session.executions)
    plan = plan_from_spec(run, spec())
    needled = execute_needle(session, run, plan, registry)
    validate_needle_run(needled, run)
    assert needled["dependency_closure"] == ["statistics", "spectrum"]
    assert needled["rerun_nodes"] == ["statistics", "spectrum"]
    assert needled["reused_nodes"] == ["energy_statistics"]
    assert len(session.executions) == baseline_execution_count + 2
    reused = needled["nodes"]["energy_statistics"]
    assert reused["baseline_result_id"] == run["nodes"]["energy_statistics"]["result"]["result_id"]


def test_delta_exposes_changed_and_unchanged_descendant_effects(tmp_path):
    registry, _, session, run = baseline(tmp_path)
    needled = execute_needle(session, run, plan_from_spec(run, spec()), registry)
    delta = delta_projection(run, needled)
    validate_delta(delta)
    rows = {row["node_id"]: row for row in delta["nodes"]}
    assert rows["statistics"]["recomputation"] == "RERUN"
    assert rows["statistics"]["data_changed"] is True
    assert rows["statistics"]["delta"]["changed_numeric_leaf_count"] > 0
    assert rows["spectrum"]["recomputation"] == "RERUN"
    assert rows["spectrum"]["data_changed"] is False
    assert rows["energy_statistics"]["recomputation"] == "REUSED"
    assert rows["energy_statistics"]["data_changed"] is False
    assert delta["summary"] == {
        "reused_nodes": 1,
        "rerun_nodes": 2,
        "changed_output_nodes": 1,
        "unchanged_output_nodes": 2,
        "unresolved_output_nodes": 0,
    }
    assert delta["claims"]["causal_effects_established"] is False


def test_needled_statistics_really_switch_channel_q_to_v(tmp_path):
    registry, _, session, run = baseline(tmp_path)
    needled = execute_needle(session, run, plan_from_spec(run, spec()), registry)
    baseline_stats = run["nodes"]["statistics"]["result"]["data"]
    candidate_stats = needled["nodes"]["statistics"]["result"]["data"]
    assert baseline_stats["unit"] == "m"
    assert candidate_stats["unit"] == "m/s"
    assert baseline_stats != candidate_stats


def test_plan_refuses_absent_parameter_or_noop(tmp_path):
    _, _, _, run = baseline(tmp_path)
    bad = spec()
    bad["target"]["parameter"] = "missing"
    with pytest.raises(ValueError, match="existing node parameter"):
        plan_from_spec(run, bad)
    same = spec()
    same["replacement"] = "q"
    with pytest.raises(ValueError, match="differ"):
        plan_from_spec(run, same)


def test_plan_refuses_structural_edit_in_v1(tmp_path):
    _, _, _, run = baseline(tmp_path)
    bad = spec()
    bad["target"]["kind"] = "NODE_OPERATION"
    with pytest.raises(ValueError, match="NODE_PARAMETER"):
        plan_from_spec(run, bad)


def test_plan_is_bound_to_exact_baseline(tmp_path):
    registry, _, session, run = baseline(tmp_path)
    plan = plan_from_spec(run, spec())
    other = run_graph(session, graph(), registry)
    with pytest.raises(ValueError, match="different baseline"):
        execute_needle(session, other, plan, registry)


def test_cli_plan_execute_and_delta(tmp_path):
    registry = builtin_registry(bind=True)
    source = make_demo_run()
    baseline_session = Session(source, tmp_path / "baseline-session", operations=registry.operations)
    run = run_graph(baseline_session, graph(), registry)

    source_path = tmp_path / "source.json"
    baseline_path = tmp_path / "baseline.json"
    spec_path = tmp_path / "spec.json"
    plan_path = tmp_path / "plan.json"
    run_path = tmp_path / "needle-run.json"
    delta_path = tmp_path / "delta.json"
    source_path.write_text(json.dumps(source))
    baseline_path.write_text(json.dumps(run))
    spec_path.write_text(json.dumps(spec()))

    subprocess.run([
        sys.executable, "-m", "ciw.net", "needle", "plan",
        str(baseline_path), str(spec_path), "--output", str(plan_path),
    ], cwd=tmp_path, check=True)
    subprocess.run([
        sys.executable, "-m", "ciw.net", "needle", "execute",
        str(source_path), str(baseline_path), str(plan_path),
        "--session-dir", str(tmp_path / "needle-session"),
        "--run-output", str(run_path),
        "--delta-output", str(delta_path),
    ], cwd=tmp_path, check=True)
    delta = json.loads(delta_path.read_text())
    assert delta["schema"] == "ciw.needle-delta.v1"
    assert delta["summary"]["reused_nodes"] == 1
    assert delta["summary"]["rerun_nodes"] == 2
