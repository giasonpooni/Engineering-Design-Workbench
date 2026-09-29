"""Operator-preset campaigns through the existing agent host and campaign runner.

Resolve only installed model/step/observer/intervention grants. Agents select an
opaque checkpoint, source fence and named template, never a new executable plan.
Original CIW command occurrences and full campaign evidence remain authoritative.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import uuid

from .agent_api import identifier
from .agent_tools import _shape
from .control_contracts import detached, keys, number, save_new, text
from .simulation_agent_tools import EXPECTED
from .simulation_campaign import plan, run_campaign, validate_campaign
from .simulation_records import OPERATION, require
from .simulation_replay import validate_result

MAX_TEMPLATES = 8
MAX_VARIANTS = 8


def compile_grant(value: dict | None, bindings: dict, comparisons: dict) -> dict | None:
    """Freeze resolved operator presets before host output or native allocation."""
    if value is None:
        return None
    keys(value, {"max_executions", "templates"})
    require(type(value["max_executions"]) is int and 1 <= value["max_executions"] <= 512,
            "Campaign reservation budget must be 1..512")
    templates = value["templates"]
    require(type(templates) is dict and 1 <= len(templates) <= MAX_TEMPLATES,
            "Require 1..8 operator campaign templates")
    compiled = {}
    for name, spec in templates.items():
        identifier(name)
        keys(spec, {"model", "steps", "step", "observer", "quantity", "comparison", "variants"})
        for key in ("model", "step", "observer", "comparison"):
            identifier(spec[key])
        text(spec["quantity"])  # Quantity names keep the existing observation grammar.
        require(spec["model"] in bindings, "Campaign model is not operator-bound")
        require(type(spec["steps"]) is int and 1 <= spec["steps"] <= 32, "Campaign steps must be 1..32")
        policy = bindings[spec["model"]].policy
        require({"resume", "step", "observe", "pause", "stop"} <= set(policy["actions"]),
                "Campaign actions are outside the model grants")
        require(spec["step"] in policy["steps"] and spec["observer"] in policy["observers"],
                "Campaign step or observer preset is not granted")
        selected = policy["observers"][spec["observer"]]
        require(selected["channels"] == [spec["quantity"]], "Campaign observer must select exactly its compared quantity")
        require(spec["comparison"] in comparisons, "Campaign comparison policy is not granted")
        tolerance = comparisons[spec["comparison"]]
        keys(tolerance, {"atol", "rtol"})
        require(all(number(v) >= 0 for v in tolerance.values()), "Negative comparison tolerance")
        variants = spec["variants"]
        require(type(variants) is list and 2 <= len(variants) <= MAX_VARIANTS, "Campaign permits 2..8 explicit variants")
        expanded, names = [], set()
        for variant in variants:
            keys(variant, {"variant_id", "interventions"})
            identifier(variant["variant_id"])
            require(variant["variant_id"] not in names, "Duplicate campaign variant identity")
            names.add(variant["variant_id"])
            presets = variant["interventions"]
            require(type(presets) is list and len(presets) <= 16, "Variant permits at most 16 intervention presets")
            actions = []
            for preset in presets:
                identifier(preset)
                require("intervene" in policy["actions"] and preset in policy["interventions"],
                        "Campaign intervention preset is not granted")
                actions.append(detached(policy["interventions"][preset]))
            expanded.append({"variant_id": variant["variant_id"], "interventions": actions})
        require(not expanded[0]["interventions"], "First campaign variant must be the unchanged baseline")
        # Reuse the runner's fixed sequence: restore + interventions + resume +
        # steps + observe + pause + stop. No speculative optimizer/grid expansion.
        cost = sum(5 + spec["steps"] + len(v["interventions"]) for v in expanded)
        compiled[name] = {"model": spec["model"], "comparison_policy": spec["comparison"],
            "execution_cost": cost, "definition": detached(spec),
            "arguments": {"variants": expanded, "steps": spec["steps"],
                "dt": policy["steps"][spec["step"]]["dt"], "observer": selected,
                "quantity": spec["quantity"], **tolerance}}
    return detached({"max_executions": value["max_executions"], "templates": compiled})


def _selection(host, checkpoint: str, instance: str, expected: dict, campaign: str):
    model, parent = host._instances[instance]
    cp_model, checkpoint_result = host._checkpoints[checkpoint]
    view = parent.inspect()  # Captured metadata only, never a source provider call.
    require(host.inspect(instance)["expected"] == expected, "Stale campaign source fence; inspect the source instance")
    require(view["status"] in {"paused", "stopped"}, "Campaign source must be paused or stopped")
    require(model == cp_model and view["instance_id"] == checkpoint_result["data"]["after"]["instance_id"],
            "Checkpoint does not belong to the selected source instance")
    require(host.session.results.get(checkpoint_result["result_id"]) == checkpoint_result,
            "Checkpoint differs from its retained occurrence")
    boundary = [r for r in host.session.results.values() if r.get("operation_id") == OPERATION
                and r["data"]["after"] == view]
    require(len(boundary) == 1, "Campaign source fence has no unique retained boundary")
    validate_result(boundary[0])
    template = detached(host._campaign_policy["templates"][campaign])
    require(template["model"] == model, "Campaign template is bound to another model")
    # Check grants again without accepting changed data from the caller or files.
    resolved = compile_grant({"max_executions": host._campaign_policy["max_executions"],
        "templates": {campaign: template["definition"]}}, host._bindings, host.host._policies)
    require(resolved["templates"][campaign] == template, "Campaign grants changed after startup")
    declared = plan(checkpoint_result, campaign_id="agent-" + model, **template["arguments"])
    variants, cost = len(declared["variants"]), template["execution_cost"]
    require(host._campaign_reserved + cost <= host._campaign_policy["max_executions"],
            "Campaign execution reservation budget exhausted")
    require(len(host._instances) + variants <= host._max_instances
            and len(host.control._instances) + variants <= 64,
            "Insufficient fresh-owner capacity for the complete campaign")
    return model, parent, view, detached(checkpoint_result), declared, template, boundary[0]


def request_campaign(host, checkpoint: str, instance: str, expected: dict, campaign: str, attempt: str) -> dict:
    """One retryable request; original runner owns every branch/command/report."""
    require(host.campaign_enabled, "Simulation campaigns were not granted by the operator")
    for value in (checkpoint, instance, campaign, attempt):
        identifier(value)
    _shape(expected, EXPECTED)
    require(checkpoint in host._checkpoints and instance in host._instances, "Unknown checkpoint or source instance handle")
    require(campaign in host._campaign_policy["templates"], "Unknown operator campaign template")
    arguments = detached({"checkpoint": checkpoint, "instance": instance, "expected": expected,
                          "campaign": campaign, "attempt": attempt})

    def execute():
        try:
            model, parent, before, cp, declared, template, boundary = _selection(
                host, checkpoint, instance, arguments["expected"], campaign)
        except ValueError as exc:
            return {"status": "refused", "dispatch_performed": False, "source_instance": instance,
                    "refusal": {"code": "simulation_campaign_preflight", "message": str(exc)}}
        cost = template["execution_cost"]
        host._campaign_reserved += cost
        directory = host._root / ("attempt-" + attempt)
        save_new(directory / "campaign-selection.json", {
            "schema": "ciw.simulation-agent-campaign-selection.v1", "template": campaign,
            "policy_ref": host._policy_ref, "checkpoint_result_ref": cp["record_digest"],
            "source_boundary_result_ref": boundary["record_digest"], "expected": arguments["expected"],
            "plan_ref": declared["record_digest"], "reserved_executions": cost,
            "total_reserved_executions": host._campaign_reserved})
        save_new(directory / "plan.json", declared)
        handles = {}

        def branch(*args, **kwargs):
            existing = set(host.control._instances)
            try:
                return host.control.branch(*args, **kwargs)
            finally:
                new = [world for key, world in host.control._instances.items() if key not in existing]
                require(len(new) <= 1, "Campaign branch unexpectedly attached multiple owners")
                if new:
                    handle = "s-" + uuid.uuid4().hex
                    host._instances[handle] = (model, new[0])
                    handles[new[0].instance_id] = handle

        report = run_campaign(SimpleNamespace(branch=branch), cp, declared, lambda: host._fresh(model))
        validate_campaign(report)
        require(parent.inspect() == before, "Campaign changed its captured source boundary")
        require(report["summary"]["execution_count"] == cost, "Campaign execution count differs from reservation")
        save_new(directory / "campaign.json", report)
        cases = []
        for case in report["cases"]:
            results = case["results"]
            handle = handles[results[-1]["data"]["after"]["instance_id"]]
            observed = next(r for r in results if r["data"]["observations"] is not None)
            cases.append({"variant_id": case["variant_id"], "instance": handle, "view": host.inspect(handle),
                "execution_ids": [r["execution_id"] for r in results], "result_ids": [r["result_id"] for r in results],
                "observation_execution_id": observed["execution_id"], **host._observation_artifacts(observed)})
        return {"status": "completed", "dispatch_performed": True, "source_instance": instance,
            "campaign": campaign, "plan_ref": declared["record_digest"], "report_ref": report["record_digest"],
            "claim_scope": report["claim_scope"], "summary": deepcopy(report["summary"]),
            "reserved_executions": cost, "cases": cases,
            "comparisons": [{"variant_id": c["variant_id"], "baseline_variant_id": c["baseline_variant_id"],
                "policy": template["comparison_policy"], "outcome": deepcopy(c["comparison"]["outcome"])}
                for c in report["comparisons"]]}

    # Original attempt gate resolves retries before a new fence check/reservation.
    return host._attempt("net_sim_campaign", arguments, execute)
