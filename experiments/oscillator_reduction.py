"""Real same-task representation-reduction experiment on the built-in oscillator.

Baseline: execute a broader eight-operation analysis graph.
Candidate: use NISE to select the two operations structurally relevant to the
declared query, compile them through the NET handoff/semantic plane, and execute.

The experiment requires the same accepted statistics + periodogram data. It then
records measured operation count, graph/representation size and wall time through
ciw.investigation-efficiency.v1. It does not claim a universal multiplier.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter
import json

from nise.compiler import compile_schematic

from ciw.control_contracts import save_new
from ciw.control_plane import builtin_registry, experiment, run_graph
from ciw.core.identities import content_identity
from ciw.instruments import make_demo_run
from ciw.investigation_efficiency import compare_trials, trial_from_spec
from ciw.nise_handoff import compile_handoff
from ciw.semantic_capabilities import builtin_semantic_registry
from ciw.session import Session


def canonical_bytes(value) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def full_catalog() -> dict:
    operation_nodes = [
        ("op.statistics", "analysis.statistics.v1"),
        ("op.spectrum", "analysis.spectrum.v1"),
        ("op.extra-statistics-1", "analysis.statistics.v1"),
        ("op.extra-spectrum-1", "analysis.spectrum.v1"),
        ("op.extra-statistics-2", "analysis.statistics.v1"),
        ("op.extra-spectrum-2", "analysis.spectrum.v1"),
        ("op.extra-statistics-3", "analysis.statistics.v1"),
        ("op.extra-spectrum-3", "analysis.spectrum.v1"),
    ]
    return {
        "schema": "nise.system-catalog.v1",
        "catalog_id": "oscillator-reduction-v1",
        "nodes": [
            {
                "node_id": "oscillator",
                "kind": "ENTITY",
                "label": "Damped oscillator",
                "status": "DECLARED",
                "attributes": {"model_id": "analytic-damped-oscillator.v1"},
                "evidence_refs": [],
            },
            *[
                {
                    "node_id": node_id,
                    "kind": "OPERATION",
                    "label": capability,
                    "status": "DECLARED",
                    "attributes": {"semantic_capability": capability},
                    "evidence_refs": [],
                }
                for node_id, capability in operation_nodes
            ],
        ],
        "edges": [
            {
                "edge_id": "edge.statistics",
                "source": "oscillator",
                "target": "op.statistics",
                "relation": "relevant_operation",
                "status": "DECLARED",
                "directional": False,
                "evidence_refs": [],
                "attributes": {},
            },
            {
                "edge_id": "edge.spectrum",
                "source": "oscillator",
                "target": "op.spectrum",
                "relation": "relevant_operation",
                "status": "DECLARED",
                "directional": False,
                "evidence_refs": [],
                "attributes": {},
            },
        ],
        "metadata": {
            "scope": "real NET built-in oscillator reduction experiment",
            "extra_operation_nodes": 6,
        },
    }


def query() -> dict:
    return {
        "schema": "nise.query.v1",
        "query_id": "oscillator-required-analysis",
        "question": "Return the retained oscillator statistics and periodogram.",
        "focus_node_ids": ["oscillator"],
        "requested_capabilities": [],
        "max_hops": 1,
        "node_budget": 16,
        "include_hypotheses": False,
    }


def baseline_graph() -> dict:
    nodes = [
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
    ]
    for index in range(1, 4):
        nodes.extend([
            {
                "node_id": f"extra_statistics_{index}",
                "operation_id": "statistics.v1",
                "parameters": {"channel": "q"},
                "inputs": {},
                "depends_on": [],
            },
            {
                "node_id": f"extra_spectrum_{index}",
                "operation_id": "spectrum.periodogram.v1",
                "parameters": {"channel": "q"},
                "inputs": {},
                "depends_on": [f"extra_statistics_{index}"],
            },
        ])
    return experiment(
        "oscillator-full-analysis-v1",
        model_id="analytic-damped-oscillator.v1",
        nodes=nodes,
    )


def binding(schematic: dict) -> dict:
    return {
        "schema": "ciw.nise-binding-plan.v1",
        "binding_id": "oscillator-reduced-binding-v1",
        "schematic_id": schematic["schematic_id"],
        "graph_id": "oscillator-reduced-analysis-v1",
        "model_id": "analytic-damped-oscillator.v1",
        "nodes": [
            {
                "nise_node_id": "op.statistics",
                "node_id": "statistics",
                "parameters": {"channel": "q"},
                "inputs": {},
                "depends_on": [],
                "resources": ["cpu"],
                "acceptance": {},
                "inspection": False,
            },
            {
                "nise_node_id": "op.spectrum",
                "node_id": "spectrum",
                "parameters": {"channel": "q"},
                "inputs": {},
                "depends_on": ["statistics"],
                "resources": ["cpu"],
                "acceptance": {},
                "inspection": False,
            },
        ],
    }


def required_data(graph_run: dict) -> dict:
    return {
        "statistics": graph_run["nodes"]["statistics"]["result"]["data"],
        "spectrum": graph_run["nodes"]["spectrum"]["result"]["data"],
    }


def measurement_ref(method: str, metric: str, value) -> str:
    return content_identity({
        "experiment": "oscillator-representation-reduction-v1",
        "method": method,
        "metric": metric,
        "value": value,
    })


def known(value, unit: str, method: str, metric: str, provenance="MEASURED"):
    return {
        "value": value,
        "unit": unit,
        "provenance": provenance,
        "source_ref": measurement_ref(method, metric, value),
    }


def unknown(unit: str):
    return {"value": None, "unit": unit, "provenance": "UNKNOWN", "source_ref": None}


def metrics(method: str, *, source_run: dict, graph: dict, graph_run: dict, wall_seconds: float) -> dict:
    calls = len([
        node for node in graph_run["nodes"].values()
        if type(node) is dict and node.get("status") == "completed"
    ])
    return {
        "raw_evidence_bytes": known(canonical_bytes(source_run), "bytes", method, "raw_evidence_bytes"),
        "retrieved_evidence_bytes": known(canonical_bytes(source_run), "bytes", method, "retrieved_evidence_bytes"),
        "instrument_input_bytes": known(canonical_bytes(graph), "bytes", method, "instrument_input_bytes"),
        "agent_context_tokens": unknown("tokens"),
        "input_tokens": unknown("tokens"),
        "output_tokens": unknown("tokens"),
        "deterministic_operation_calls": known(calls, "count", method, "deterministic_operation_calls"),
        "reused_operation_calls": known(0, "count", method, "reused_operation_calls"),
        "recomputed_operation_calls": known(calls, "count", method, "recomputed_operation_calls"),
        "local_model_calls": known(0, "count", method, "local_model_calls"),
        "remote_model_calls": known(0, "count", method, "remote_model_calls"),
        "compute_wall_seconds": known(wall_seconds, "seconds", method, "compute_wall_seconds"),
        "human_active_seconds": unknown("seconds"),
        "human_interventions": known(0, "count", method, "human_interventions"),
        "accepted_outputs": known(2, "count", method, "accepted_outputs"),
        "rejected_outputs": known(0, "count", method, "rejected_outputs"),
        "errors": known(0, "count", method, "errors"),
        "retries": known(0, "count", method, "retries"),
        "model_cost_usd": known(0.0, "usd", method, "model_cost_usd", provenance="DECLARED"),
    }


def trial_spec(method: str, *, catalog: dict, selected_ref: str, selected_count: int,
               source_run: dict, graph: dict, graph_run: dict, wall_seconds: float,
               preservation_refs: dict[str, str]) -> dict:
    return {
        "task_id": "oscillator-statistics-periodogram-v1",
        "domain": "PHYSICAL_SYSTEM",
        "method": method,
        "acceptance_policy_id": "same-required-statistics-periodogram-data-v1",
        "outcome_class": "accepted-identical-required-data",
        "accepted": True,
        "representation": {
            "source_representation_ref": content_identity(catalog),
            "selected_representation_ref": selected_ref,
            "source_item_count": len(catalog["nodes"]),
            "selected_item_count": selected_count,
            "reduction_method": "explicit-NISE-query-conditioned-graph-selection"
            if method == "NET" else "full-declared-analysis-graph",
            "required_preservation_checks": [
                {"check_id": "required-output-data", "kind": "OUTPUT", "status": "PASS",
                 "source_ref": preservation_refs["output"]},
                {"check_id": "operation-contracts", "kind": "INVARIANT", "status": "PASS",
                 "source_ref": preservation_refs["invariant"]},
                {"check_id": "source-evidence-identity", "kind": "EPISTEMIC", "status": "PASS",
                 "source_ref": preservation_refs["epistemic"]},
                {"check_id": "runtime-provenance", "kind": "PROVENANCE", "status": "PASS",
                 "source_ref": preservation_refs["provenance"]},
            ],
        },
        "metrics": metrics(method, source_run=source_run, graph=graph,
                           graph_run=graph_run, wall_seconds=wall_seconds),
        "evidence_refs": [
            source_run["evidence_id"],
            *preservation_refs.values(),
        ],
        "notes": (
            "Real built-in oscillator provider experiment. No token/human-time "
            "advantage is claimed because those quantities were not measured."
        ),
    }


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)

    source_run = make_demo_run()
    registry = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(registry)

    catalog = full_catalog()
    q = query()
    schematic = compile_schematic(catalog, q)
    selected_ids = {node["node_id"] for node in schematic["P_q"]}
    if selected_ids != {"op.statistics", "op.spectrum"}:
        raise AssertionError(f"unexpected NISE operation selection: {sorted(selected_ids)}")

    handoff = compile_handoff(schematic, binding(schematic), semantic)
    candidate_graph = handoff["semantic_compilation"]["experiment"]
    baseline = baseline_graph()

    baseline_session = Session(source_run, output_dir / "baseline-session", operations=registry.operations)
    start = perf_counter()
    baseline_run = run_graph(baseline_session, baseline, registry)
    baseline_wall = perf_counter() - start

    candidate_session = Session(source_run, output_dir / "candidate-session", operations=registry.operations)
    start = perf_counter()
    candidate_run = run_graph(candidate_session, candidate_graph, registry)
    candidate_wall = perf_counter() - start

    if baseline_run["status"] != "completed" or candidate_run["status"] != "completed":
        raise AssertionError("both graphs must complete")
    baseline_required = required_data(baseline_run)
    candidate_required = required_data(candidate_run)
    if baseline_required != candidate_required:
        raise AssertionError("reduced representation changed required statistics/periodogram data")

    baseline_contracts = {
        name: baseline_run["contracts"][operation]
        for name, operation in {
            "statistics": "statistics.v1",
            "spectrum": "spectrum.periodogram.v1",
        }.items()
    }
    candidate_contracts = {
        name: candidate_run["contracts"][operation]
        for name, operation in {
            "statistics": "statistics.v1",
            "spectrum": "spectrum.periodogram.v1",
        }.items()
    }
    if baseline_contracts != candidate_contracts:
        raise AssertionError("required operation contracts changed under reduction")

    if baseline_run["source_evidence_id"] != candidate_run["source_evidence_id"]:
        raise AssertionError("source evidence identity changed under reduction")

    baseline_runtime = {
        name: baseline_run["nodes"][name]["execution"]["runtime"]
        for name in ("statistics", "spectrum")
    }
    candidate_runtime = {
        name: candidate_run["nodes"][name]["execution"]["runtime"]
        for name in ("statistics", "spectrum")
    }
    if baseline_runtime != candidate_runtime:
        raise AssertionError("required provider runtime changed under reduction")

    preservation = {
        "output": content_identity({
            "kind": "required-output-equivalence",
            "baseline": baseline_required,
            "candidate": candidate_required,
        }),
        "invariant": content_identity({
            "kind": "required-contract-equivalence",
            "baseline": baseline_contracts,
            "candidate": candidate_contracts,
        }),
        "epistemic": content_identity({
            "kind": "source-evidence-equivalence",
            "source_evidence_id": baseline_run["source_evidence_id"],
        }),
        "provenance": content_identity({
            "kind": "runtime-provenance-equivalence",
            "baseline": baseline_runtime,
            "candidate": candidate_runtime,
        }),
    }

    baseline_trial = trial_from_spec(trial_spec(
        "CONVENTIONAL",
        catalog=catalog,
        selected_ref=content_identity(catalog),
        selected_count=len(catalog["nodes"]),
        source_run=source_run,
        graph=baseline,
        graph_run=baseline_run,
        wall_seconds=baseline_wall,
        preservation_refs=preservation,
    ))
    candidate_trial = trial_from_spec(trial_spec(
        "NET",
        catalog=catalog,
        selected_ref=schematic["schematic_id"],
        selected_count=sum(len(schematic[key]) for key in ("V_q", "M_q", "C_q", "O_q", "P_q")),
        source_run=source_run,
        graph=candidate_graph,
        graph_run=candidate_run,
        wall_seconds=candidate_wall,
        preservation_refs=preservation,
    ))
    comparison = compare_trials(baseline_trial, candidate_trial)

    operation_ratio = comparison["metric_comparisons"]["deterministic_operation_calls"]["candidate_over_baseline"]
    if operation_ratio != 0.25:
        raise AssertionError(f"expected 2/8 operation-call ratio, got {operation_ratio}")
    if comparison["candidate_derived"]["representation_fraction"] >= 1:
        raise AssertionError("candidate representation was not reduced")

    summary = {
        "schema": "notations.oscillator-representation-reduction-experiment.v1",
        "task_id": baseline_trial["task_id"],
        "source_evidence_id": source_run["evidence_id"],
        "baseline_graph_nodes": len(baseline["nodes"]),
        "candidate_graph_nodes": len(candidate_graph["nodes"]),
        "source_catalog_nodes": len(catalog["nodes"]),
        "candidate_schematic_nodes": candidate_trial["representation"]["selected_item_count"],
        "required_outputs_identical": True,
        "required_contracts_identical": True,
        "source_evidence_identical": True,
        "provider_runtime_identical": True,
        "operation_call_ratio_candidate_over_baseline": operation_ratio,
        "representation_fraction_candidate": comparison["candidate_derived"]["representation_fraction"],
        "wall_time_ratio_candidate_over_baseline": comparison["metric_comparisons"]["compute_wall_seconds"]["candidate_over_baseline"],
        "unknown_metrics": {
            "baseline": sorted(name for name,row in baseline_trial["metrics"].items() if row["value"] is None),
            "candidate": sorted(name for name,row in candidate_trial["metrics"].items() if row["value"] is None),
        },
        "claims": {
            "same_task_required_outputs_preserved": True,
            "query_conditioned_reduction_observed": True,
            "general_scientific_equivalence": False,
            "causal_productivity_claim": False,
            "multi_scale_precision_hypothesis_tested": False,
        },
    }

    artifacts = {
        "catalog.json": catalog,
        "query.json": q,
        "schematic.json": schematic,
        "candidate-handoff.json": handoff,
        "baseline-experiment.json": baseline,
        "candidate-experiment.json": candidate_graph,
        "baseline-run.json": baseline_run,
        "candidate-run.json": candidate_run,
        "baseline-trial.json": baseline_trial,
        "candidate-trial.json": candidate_trial,
        "comparison.json": comparison,
        "summary.json": summary,
    }
    for name, value in artifacts.items():
        save_new(output_dir / name, value)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.output_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
