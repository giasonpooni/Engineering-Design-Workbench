"""Bounded counterfactual campaigns on the existing SimulationControl.

No provider discovery, new executor, world state, search policy or numerical
comparator. A caller explicitly supplies a trusted fresh-provider factory.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Callable

from .control_checks import compare
from .control_contracts import (
    MAX_BYTES, bytes_ref, content_ref, detached, keys, number, save_new, text,
)
from .simulation_control import SimulationControl, SimulationProvider, completed
from .simulation_records import packed, projected_samples, require, unpack, validate_observer, validate_request
from .simulation_replay import validate_result

PLAN = "ciw.simulation-campaign-plan.v1"
REPORT = "ciw.simulation-campaign.v1"
SCOPE = "declared intervention alternatives from one checkpoint; not optimization or physical validation"
MAX_VARIANTS = 16
MAX_STEPS = 32


def _bounded(value: dict) -> dict:
    value = detached(value)
    require(len(json.dumps(value, ensure_ascii=True, allow_nan=False).encode()) <= MAX_BYTES,
            "Campaign record exceeds 8 MiB")
    return value


def _checkpoint(value: dict) -> None:
    validate_result(value)
    event = value["data"]
    require(event["checkpoint"] is not None and event["after"]["status"] == "paused",
            "Campaign requires an explicitly paused checkpoint result")


def _intervention(value: dict) -> None:
    # Reuse the existing data-only command validator; this is not execution.
    validate_request({"instance_id": "plan-only", "command_id": "plan-only",
        "expected": {"owner_id": "plan-only", "revision": 0, "state_revision": 0},
        "action": "intervene", "arguments": value})


def plan(checkpoint: dict, *, campaign_id: str, variants: list[dict], steps: int,
         dt: float, observer: dict, quantity: str, atol: float, rtol: float = 0.0) -> dict:
    """First variant is the unchanged baseline; alternatives are interventions.

    No Cartesian product is silently expanded. Write out the bounded alternatives
    so their order, cost and requested changes remain inspectable before execution.
    """
    _checkpoint(checkpoint)
    value = packed(PLAN, campaign_id=campaign_id, checkpoint_result_ref=checkpoint["record_digest"],
                   variants=variants, steps=steps, dt=dt, observer=observer, quantity=quantity,
                   policy={"atol": atol, "rtol": rtol})
    validate_plan(value)
    return value


def validate_plan(value: dict) -> None:
    _bounded(value)
    unpack(value, PLAN, {"campaign_id", "checkpoint_result_ref", "variants", "steps", "dt",
                        "observer", "quantity", "policy"})
    text(value["campaign_id"])
    content_ref(value["checkpoint_result_ref"])
    require(type(value["steps"]) is int and 1 <= value["steps"] <= MAX_STEPS, "Campaign permits 1..32 steps")
    require(0 < number(value["dt"]) <= 3600, "Step duration must be in (0, 3600] seconds")
    validate_observer(value["observer"])
    text(value["quantity"])
    require(value["observer"]["channels"] == [value["quantity"]], "Campaign observer must select exactly the compared quantity")
    keys(value["policy"], {"atol", "rtol"})
    require(all(number(x) >= 0 for x in value["policy"].values()), "Negative comparison tolerance")
    variants = value["variants"]
    require(type(variants) is list and 2 <= len(variants) <= MAX_VARIANTS, "Campaign permits 2..16 variants including baseline")
    names = set()
    for variant in variants:
        keys(variant, {"variant_id", "interventions"})
        name = text(variant["variant_id"])
        require(name not in names, "Duplicate variant identity")
        names.add(name)
        actions = variant["interventions"]
        require(type(actions) is list and len(actions) <= 16, "Variant permits at most 16 interventions")
        for action in actions:
            _intervention(action)
    require(variants[0]["interventions"] == [], "First variant must be an unchanged baseline")


def _commands(value: dict, variant: dict) -> list[tuple[str, dict]]:
    return ([("intervene", item) for item in variant["interventions"]]
            + [("resume", {})] + [("step", {"dt": value["dt"]}) for _ in range(value["steps"])]
            + [("observe", {"observer": value["observer"]}), ("pause", {}), ("stop", {})])


def _restore_arguments(checkpoint: dict) -> dict:
    event = checkpoint["data"]
    return {"source": event["after"], "checkpoint": event["checkpoint"],
            "snapshot_b64": event["snapshot_b64"], "source_result_ref": checkpoint["record_digest"],
            "source_execution_id": checkpoint["execution_id"]}


def _derive(value: dict, checkpoint: dict, cases: list[dict]) -> tuple[list[dict], dict]:
    """Recompute meaning from retained commands and the original comparator."""
    validate_plan(value)
    _checkpoint(checkpoint)
    require(value["checkpoint_result_ref"] == checkpoint["record_digest"], "Plan/checkpoint binding mismatch")
    require(type(cases) is list and len(cases) == len(value["variants"]), "Incomplete campaign cannot be reported completed")
    source = checkpoint["data"]["after"]
    instances, owners = {source["instance_id"]}, {source["provider"]["owner_id"]}
    executions, results = {checkpoint["execution_id"]}, {checkpoint["result_id"]}
    observations = []
    common_runtime = None
    for variant, case in zip(value["variants"], cases):
        keys(case, {"variant_id", "results"})
        require(case["variant_id"] == variant["variant_id"], "Variant order/identity changed")
        sequence = [("restore", _restore_arguments(checkpoint)), *_commands(value, variant)]
        require(type(case["results"]) is list and len(case["results"]) == len(sequence), "Incomplete variant command history")
        previous, command_ids = None, set()
        observed = None
        for index, (result, (action, arguments)) in enumerate(zip(case["results"], sequence)):
            validate_result(result)
            event = result["data"]
            request = event["request"]
            require(request["action"] == action and request["arguments"] == arguments, "Executed commands differ from declared campaign")
            require(result["execution_id"] not in executions and result["result_id"] not in results, "Campaign reused an occurrence identity")
            executions.add(result["execution_id"])
            results.add(result["result_id"])
            require(request["command_id"] not in command_ids, "Variant reused a command identity")
            command_ids.add(request["command_id"])
            if common_runtime is None:
                common_runtime = result["runtime"]
            require(result["runtime"] == common_runtime, "Campaign control binding changed")
            if index == 0:
                current = event["after"]
                require(current["instance_id"] not in instances and current["provider"]["owner_id"] not in owners,
                        "Variants require independent fresh instances and owners")
                require(current["provider_id"] == source["provider_id"], "Variant changed provider label")
                require(current["experiment_id"] == value["campaign_id"], "Campaign experiment identity mismatch")
                instances.add(current["instance_id"])
                owners.add(current["provider"]["owner_id"])
            else:
                require(event["before"] == previous, "Variant history is discontinuous")
            previous = event["after"]
            if action == "observe":
                observed = result
        require(observed is not None, "Variant omitted selected observation")
        observations.append(observed)
    baseline = projected_samples(observations[0], quantity=value["quantity"])
    comparisons = []
    for variant, result in zip(value["variants"][1:], observations[1:]):
        # Preserve comparator direction: candidate is left, baseline is the
        # right-hand reference for atol + rtol * abs(reference).
        candidate = projected_samples(result, quantity=value["quantity"])
        comparison = compare(candidate, baseline, **value["policy"])
        comparisons.append({"variant_id": variant["variant_id"], "baseline_variant_id": value["variants"][0]["variant_id"],
                            "comparison": comparison})
    counts = {status: sum(item["comparison"]["outcome"]["status"] == status for item in comparisons)
              for status in ("PASS", "FAIL", "INDETERMINATE")}
    summary = {"status": "completed", "variant_count": len(cases),
               "execution_count": sum(len(case["results"]) for case in cases),
               "comparison_counts": counts, "ranking": "not_performed"}
    return comparisons, summary


def validate_campaign(value: dict) -> None:
    _bounded(value)
    unpack(value, REPORT, {"plan", "checkpoint", "cases", "comparisons", "summary", "claim_scope",
                          "verification_id", "verification_status", "state_admission"})
    require(value["claim_scope"] == SCOPE and value["verification_id"] is None
            and value["verification_status"] == "not_verified" and value["state_admission"] == "not_performed",
            "Campaign report cannot grant scientific authority")
    comparisons, summary = _derive(value["plan"], value["checkpoint"], value["cases"])
    require(value["comparisons"] == comparisons and value["summary"] == summary, "Campaign verdict contradicts retained evidence")


def run_campaign(control: SimulationControl, checkpoint: dict, declared: dict,
                 provider_factory: Callable[[], SimulationProvider]) -> dict:
    """Execute sequential fresh-owner variants in the supplied existing Session.

    A failure stops the campaign; the Session retains all completed commands and
    refusals. No complete report is emitted. The caller is responsible for saving
    its Session also on failure (as the CLI does). No provider is selected by data.
    """
    checkpoint, declared = detached(checkpoint), detached(declared)
    _checkpoint(checkpoint)
    validate_plan(declared)
    require(declared["checkpoint_result_ref"] == checkpoint["record_digest"], "Plan/checkpoint binding mismatch")
    require(callable(provider_factory), "Explicit trusted provider factory required")
    cases = []
    for variant in declared["variants"]:
        child = None
        provider = provider_factory()
        try:
            child, receipt = control.branch(checkpoint, provider, experiment_id=declared["campaign_id"])
            retained = [completed(receipt)]
            for action, args in _commands(declared, variant):
                retained.append(completed(child.command(action, **args)))
            cases.append({"variant_id": variant["variant_id"], "results": retained})
        except BaseException:
            # Do not dispatch into an incompatible unattached object. For an
            # attached failure, try to release resources without inventing rollback.
            if child is not None:
                try:
                    if child.inspect()["status"] == "refused":
                        child.discard()
                    elif child.inspect()["status"] != "stopped":
                        child.command("stop")
                except Exception:
                    pass  # Keep the original exception and its Session evidence.
            raise
    comparisons, summary = _derive(declared, checkpoint, cases)
    report = packed(REPORT, plan=declared, checkpoint=checkpoint, cases=cases, comparisons=comparisons,
                    summary=summary, claim_scope=SCOPE, verification_id=None,
                    verification_status="not_verified", state_admission="not_performed")
    validate_campaign(report)
    return report


def read_campaign(path: Path, *, expected_sha256: str | None = None) -> dict:
    """Freeze one bounded read; optional external byte digest is not a signature."""
    from .session import loads_json
    with Path(path).open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "Campaign file exceeds 8 MiB")
    if expected_sha256 is not None:
        require(bytes_ref(raw) == content_ref(expected_sha256), "Campaign file digest mismatch")
    value = loads_json(raw.decode("utf-8"))
    validate_campaign(value)
    return value


def reference_demo(output_dir: Path) -> dict:
    """Four actually executed variants of the declared synthetic reference model."""
    from .instruments import make_demo_run
    from .session import Session
    from .simulation_records import observer
    from .simulation_reference import PROVIDER_ID, ReferenceMotion
    output_dir.mkdir(parents=True, exist_ok=False)
    session = Session(make_demo_run(), output_dir)
    control = SimulationControl(session)
    parent = control.attach(ReferenceMotion(), provider_id=PROVIDER_ID, experiment_id="campaign-source")
    try:
        completed(parent.command("start"))
        for _ in range(2):
            completed(parent.command("step", dt=1))
        completed(parent.command("pause"))
        checkpoint = completed(parent.command("checkpoint"))
        variants = [{"variant_id": "baseline", "interventions": []}]
        for delta in (-2, 2, 4):
            variants.append({"variant_id": f"impulse-{delta:+d}", "interventions": [{
                "actor_id": "experimenter", "operation": "motion.queue-impulse.v1", "target": "body-1",
                "parameters": {"at_tick": 3, "delta_v": delta}}]})
        declared = plan(checkpoint, campaign_id="impulse-alternatives", variants=variants,
            steps=4, dt=1, observer=observer("position-debugger", kind="debugger", channels=["position"]),
            quantity="position", atol=0, rtol=0)
        save_new(output_dir / "plan.json", declared)
        before = parent.inspect()
        report = run_campaign(control, checkpoint, declared, ReferenceMotion)
        require(parent.inspect() == before, "Campaign changed its parent instance")
        save_new(output_dir / "campaign.json", report)
        return deepcopy(report["summary"])
    finally:
        session.save_workspace(output_dir / "workspace.json")


def run_reference(workspace: Path, declared_path: Path, output_dir: Path) -> dict:
    """Explicit built-in reference route; saved files never name executable code."""
    from .control_contracts import load
    from .simulation_control import open_workspace
    from .simulation_reference import ReferenceMotion
    declared = load(declared_path)
    validate_plan(declared)
    output_dir.mkdir(parents=True, exist_ok=False)
    session = open_workspace(workspace, output_dir=output_dir)
    try:
        matches = [r for r in session.results.values() if r["record_digest"] == declared["checkpoint_result_ref"]]
        require(len(matches) == 1, "Plan must select exactly one retained checkpoint result")
        checkpoint = matches[0]
        _checkpoint(checkpoint)
        source = checkpoint["data"]["after"]
        control = SimulationControl(session)
        # The operator explicitly selected the reference route, not a provider
        # identifier found inside untrusted data. Branch checks the exact runtime.
        factory = lambda: ReferenceMotion(seed=source["configuration"]["seed"],
                                          simulation_id=source["provider"]["simulation_id"])
        save_new(output_dir / "plan.json", declared)
        report = run_campaign(control, checkpoint, declared, factory)
        save_new(output_dir / "campaign.json", report)
        return deepcopy(report["summary"])
    finally:
        session.save_workspace(output_dir / "workspace.json")
