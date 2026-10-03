"""Counterfactual studies around the existing CIW persistent Simulation.

No second integrator, execution ledger, simulation clock, or world-state owner.
Uses existing SimulationSession, opaque checkpoint envelopes, typed observations
and numerical comparison. Only the already-supported oscillator is qualified.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re
import threading
import uuid

from . import simulation as sim
from .control_checkpoint import capture_checkpoint, validate_checkpoint
from .control_contracts import keys, detached, load, save_new, bytes_ref, content_ref
from .control_checks import compare, validate_comparison
from .instruments import make_demo_run
from .operations.runner import seal, check_seal
from .session import ProtocolError, envelope
from .simulation_session import SimulationSession
from .simulation_observers import policy, project, validate_policy, validate_view, UNITS
from .telemetry import canonical, digest

PLAN = "ciw.simulation-study-plan.v1"
REPORT = "ciw.simulation-study.v1"
AUTHORITY = {"physical_validation": "not_performed", "state_admission": "not_performed",
             "verification_id": None, "reproduction": "not_established_by_inspection"}


def describe() -> dict:
    return {"profile": "persistent-oscillator-study.v1", "state_owner": "existing ciw.simulation.Simulation",
        "numerical_providers": ["existing SCR/Julia motion", "existing SCR/C++ observables"],
        "clock": {"tick_hz": sim.RATE, "mode": "bounded-on-demand"},
        "capabilities": {"advance": True, "intervene_impulse": True, "observe": True,
            "checkpoint": True, "sequential_branch": True, "reproduce": True,
            "pause": "session_command_gate", "multi_rate": "observer_sampling_only",
            "autonomous_wall_clock": False, "arbitrary_parameter_mutation": False,
            "godot_world_restore": False, "bevy_world_restore": False},
        "inspection_launches_provider": False, "authority": deepcopy(AUTHORITY)}


class CheckpointAdapter:
    """Expose the existing owner through the established CheckpointProvider seam."""
    def __init__(self, simulation: sim.Simulation):
        self.simulation = simulation

    def identity(self) -> dict:
        view = self.simulation.inspect()
        return {"runtime": deepcopy(self.simulation.providers.runtime), "model_id": view["model_id"],
                "simulation_id": view["simulation_id"], "owner_id": view["owner_id"],
                "state_revision": view["revision"],
                "clock": {"id": "oscillator-elapsed-time-120hz.v1", "time_s": view["state"]["tick"] / sim.RATE}}

    def snapshot(self) -> bytes:
        selected = self.simulation.checkpoint()
        cp = sim.read_checkpoint(self.simulation.directory / selected["filename"])
        sim.inspect_checkpoint(cp, selected["checkpoint_id"])
        return canonical(cp)

    def observe(self) -> dict:
        return self.simulation.inspect()

    # Legacy Simulation restores by construction, not an in-place method. The
    # study uses that constructor explicitly instead of pretending restore() exists.


class StudySession(SimulationSession):
    """Add observer commands and a bounded pause gate to the same Session.

    Pause gates requests through this Session only. Resume does not start a
    background scheduler. Direct provider/object access is not access-controlled.
    """
    def attach_simulation(self, simulation):
        super().attach_simulation(simulation)
        self._study_lock = threading.Lock()
        self._paused = False
        self._control_revision = 0

    def _dispatch(self, kind, payload):
        if not kind.startswith("simulation.") or getattr(self, "simulation", None) is None:
            return super()._dispatch(kind, payload)
        if kind == "simulation.capabilities":
            keys(payload, set())
            return describe()
        if kind == "simulation.control":
            keys(payload, set())
            return {"paused": self._paused, "control_revision": self._control_revision,
                    "scope": "session_command_gate_only"}
        supported = {"simulation.pause", "simulation.resume", "simulation.step", "simulation.observe",
                     "simulation.advance", "simulation.impulse", "simulation.checkpoint"}
        if kind not in supported:
            return super()._dispatch(kind, payload)
        if not self._study_lock.acquire(blocking=False):
            raise ProtocolError("simulation_busy", "A study command is already in flight")
        try:
            if kind in {"simulation.pause", "simulation.resume"}:
                keys(payload, {"owner_id", "expected_control_revision"})
                if (payload["owner_id"] != self.simulation.inspect()["owner_id"]
                        or type(payload["expected_control_revision"]) is not int
                        or payload["expected_control_revision"] != self._control_revision):
                    raise ProtocolError("stale_control", "Refresh owner and control revision")
                if self.simulation.inspect()["status"] != "ready":
                    raise ProtocolError("simulation_not_ready", "Control gate requires a ready owner")
                self._paused = kind.endswith("pause")
                self._control_revision += 1
                return {"paused": self._paused, "control_revision": self._control_revision,
                        "scope": "session_command_gate_only"}
            if kind == "simulation.observe":
                keys(payload, {"observer"})
                validate_policy(payload["observer"])
                cp = sim.read_checkpoint(self.simulation.directory / self.simulation.checkpoint()["filename"])
                return project(cp, payload["observer"], expected_checkpoint_id=cp["checkpoint_id"])
            if kind == "simulation.step":
                # Explicit single-step/batch works while paused; this is not resume.
                return super()._dispatch("simulation.advance", payload)
            if self._paused and kind in {"simulation.advance", "simulation.impulse"}:
                raise ProtocolError("simulation_paused", "Resume or request explicit simulation.step")
            return super()._dispatch(kind, payload)
        finally:
            self._study_lock.release()


def _action(value: dict) -> None:
    if type(value) is not dict or value.get("action") not in {"advance", "impulse"}:
        raise ValueError("Only declared advance/impulse actions are supported")
    field = "ticks" if value["action"] == "advance" else "impulse_n_s"
    keys(value, {"action", field, "actor_id"})
    if type(value["actor_id"]) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", value["actor_id"]):
        raise ValueError("Declare a bounded actor label; it is not authentication")
    if field == "ticks":
        sim._integer(value[field], 1, 120)
    else:
        sim.contract.number(value[field], -1, 1)


def validate_plan(value: dict) -> None:
    detached(value)
    keys(value, {"schema", "model", "initial", "prefix", "branches", "observers", "compare_observer", "tolerances"})
    if value["schema"] != PLAN:
        raise ValueError("Unsupported study plan")
    sim.model(value["model"])
    initial = sim._state(value["initial"])
    if initial["tick"] != 0:
        raise ValueError("A fresh study starts at tick zero")
    if type(value["branches"]) is not list or not 2 <= len(value["branches"]) <= 8:
        raise ValueError("A study requires 2..8 branches")
    if type(value["prefix"]) is not list or len(value["prefix"]) > 64:
        raise ValueError("Prefix budget exceeded")
    for item in value["prefix"]:
        _action(item)
    names = set()
    for branch in value["branches"]:
        keys(branch, {"name", "actions"})
        name = branch["name"]
        if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", name) or name in names:
            raise ValueError("Branch names must be unique bounded labels")
        names.add(name)
        if type(branch["actions"]) is not list or not 1 <= len(branch["actions"]) <= 64:
            raise ValueError("Branch action budget exceeded")
        for action in branch["actions"]:
            _action(action)
    if type(value["observers"]) is not list or not 1 <= len(value["observers"]) <= 8:
        raise ValueError("Observer budget exceeded")
    ids = set()
    for observer in value["observers"]:
        validate_policy(observer)
        if observer["observer_id"] in ids:
            raise ValueError("Duplicate observer identity")
        ids.add(observer["observer_id"])
    if value["compare_observer"] not in ids:
        raise ValueError("Comparison must select a declared observer")
    chosen = next(p for p in value["observers"] if p["observer_id"] == value["compare_observer"])
    keys(value["tolerances"], set(chosen["quantities"]))
    for item in value["tolerances"].values():
        keys(item, {"atol", "rtol"})
        for number in item.values():
            sim.contract.number(number, 0, 1e6)
    prefix_ticks = sum(a.get("ticks", 0) for a in value["prefix"])
    for branch in value["branches"]:
        total = prefix_ticks + sum(a.get("ticks", 0) for a in branch["actions"])
        for observer in value["observers"]:
            n = max(0, (total-observer["delay_ticks"]) // observer["every_ticks"] + 1)
            if n * len(observer["quantities"]) > 4096:
                raise ValueError("Plan would exceed an observer's output budget")


def default_plan() -> dict:
    advance = lambda ticks: {"action": "advance", "ticks": ticks, "actor_id": "operator:demo"}
    return {"schema": PLAN, "model": {"omega_0_rad_s": 2., "gamma_s_inv": .1, "mass_kg": 1.},
        "initial": {"tick": 0, "q_m": 1., "v_m_s": 0.}, "prefix": [advance(24)],
        "branches": [
            {"name": "baseline", "actions": [advance(60), advance(60)]},
            {"name": "impulse", "actions": [{"action": "impulse", "impulse_n_s": .25,
                "actor_id": "operator:counterfactual"}, advance(60), advance(60)]}],
        "observers": [policy("observer:position", ["q_m"], every_ticks=12, delay_ticks=24),
                      policy("observer:diagnostic", list(UNITS), every_ticks=12)],
        "compare_observer": "observer:diagnostic",
        "tolerances": {q: {"atol": 1e-8, "rtol": 1e-8} for q in UNITS}}


def _ask(session, kind, payload):
    response = session.handle(envelope(kind, payload, uuid.uuid4().hex))
    if response["type"] == "error":
        raise ValueError(response["payload"]["message"])
    return response["payload"]


def _session(owner, directory):
    # The existing oscillator recording stays an independent legacy example.
    # It is not relabelled as a live recording or as the source of observations.
    session = StudySession(make_demo_run(), directory)
    session.attach_simulation(owner)
    return session


def _apply(session, actions, directory):
    receipts = []
    for index, action in enumerate(actions):
        before = session.simulation.inspect()
        field = "ticks" if action["action"] == "advance" else "impulse_n_s"
        command = {"command_id": "command-" + uuid.uuid4().hex, "owner_id": before["owner_id"],
                   "expected_revision": before["revision"], "at_tick": before["state"]["tick"],
                   field: action[field]}
        intent = seal({"schema": "ciw.simulation-intervention.v1", "actor_id": action["actor_id"],
            "action": action["action"], "command": command, "simulation_id": before["simulation_id"],
            "model_id": before["model_id"], "authority": deepcopy(AUTHORITY)})
        save_new(directory / f"intent-{index:03}.json", intent)
        after = _ask(session, "simulation." + action["action"], command)
        receipt = seal({"schema": "ciw.simulation-intervention-receipt.v1", "intent": intent,
            "event_id": after["last_event_id"], "state_revision": after["revision"],
            "tick": after["state"]["tick"], "authority": deepcopy(AUTHORITY)})
        save_new(directory / f"receipt-{index:03}.json", receipt)
        receipts.append(receipt)
    return receipts


def _capture(owner, directory, study_id):
    wrapper, raw = capture_checkpoint(CheckpointAdapter(owner), experiment_id=study_id)
    save_new(directory / "checkpoint.json", wrapper)
    sim.publish(directory, "payload.json", sim.loads_json(raw.decode()))
    return wrapper, sim.loads_json(raw.decode())


def run(plan: dict, binding: Path, output_dir: Path, *, reproduced_from: dict | None = None, expected_runtime: dict | None = None) -> dict:
    """Explicit native execution. One owner at a time; no checkpoint payload loader."""
    plan = detached(plan)
    validate_plan(plan)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    study_id = "study-" + uuid.uuid4().hex
    save_new(output / "plan.json", plan)
    parent = None
    active = None
    try:
        parent = sim.Simulation(plan["model"], plan["initial"], binding, output / "parent" / "native")
        if expected_runtime is not None and parent.providers.runtime != expected_runtime:
            raise ValueError("Fresh native runtime differs from the selected reproduction source")
        session = _session(parent, output / "parent" / "session")
        _apply(session, plan["prefix"], output / "parent")
        parent_envelope, parent_payload = _capture(parent, output / "parent", study_id)
        parent.close()  # Explicitly end this owner before counterfactual construction.
        branches = []
        for index, branch in enumerate(plan["branches"]):
            root = output / f"branch-{index:02}"
            active = sim.Simulation(None, None, binding, root / "native", checkpoint=parent_payload,
                                    expected_id=parent_payload["checkpoint_id"])
            session = _session(active, root / "session")
            _apply(session, branch["actions"], root)
            wrapper, payload = _capture(active, root, study_id)
            active.close()
            active = None
            views = [project(payload, obs, expected_checkpoint_id=payload["checkpoint_id"]) for obs in plan["observers"]]
            for n, view in enumerate(views):
                save_new(root / f"observer-{n:02}.json", view)
            branches.append({"name": branch["name"], "branch_id": "branch-" + uuid.uuid4().hex,
                "parent_checkpoint_id": parent_envelope["record_digest"],
                "checkpoint_id": wrapper["record_digest"], "native_checkpoint_id": payload["checkpoint_id"],
                "owner_id": wrapper["provider"]["owner_id"], "observers": views})
        comparisons = _comparisons(plan, branches)
        report = seal({"schema": REPORT, "study_id": study_id, "plan_id": digest(plan),
            "status": "completed", "parent_checkpoint_id": parent_envelope["record_digest"],
            "branches": branches, "comparisons": comparisons,
            "reproduced_from": deepcopy(reproduced_from), "authority": deepcopy(AUTHORITY)})
        # Check all retained components before publishing the completion receipt.
        _inspect_details(output, candidate_report=report)
        save_new(output / "study.json", report)
        return report
    except Exception as exc:
        save_new(output / "failure.json", seal({"schema": "ciw.simulation-study-failure.v1",
            "study_id": study_id, "status": "failed", "code": type(exc).__name__,
            "authority": deepcopy(AUTHORITY)}))
        raise
    finally:
        if active is not None:
            active.close()
        if parent is not None and parent.inspect()["status"] != "closed":
            parent.close()


def _comparisons(plan, branches):
    def selected(branch):
        return next(v for v in branch["observers"] if v["observer"]["observer_id"] == plan["compare_observer"])
    reference = selected(branches[0])
    return [{"left_branch_id": branch["branch_id"], "right_branch_id": branches[0]["branch_id"],
        "checks": {q: compare(selected(branch)["streams"][q], reference["streams"][q], **tolerance)
                   for q, tolerance in plan["tolerances"].items()}} for branch in branches[1:]]


def _load_cp(directory, study_id):
    wrapper = load(directory / "checkpoint.json")
    raw = _raw(directory / "payload.json", sim.MAX_CHECKPOINT_BYTES)
    validate_checkpoint(wrapper, raw)
    if wrapper["experiment_id"] != study_id:
        raise ValueError("Checkpoint belongs to another study")
    cp = sim.loads_json(raw.decode())
    view = sim.inspect_checkpoint(cp)
    expected = {"runtime": cp["runtime"], "model_id": cp["model_id"], "simulation_id": cp["simulation_id"],
        "owner_id": view["owner_id"], "state_revision": view["revision"],
        "clock": {"id": "oscillator-elapsed-time-120hz.v1", "time_s": view["state"]["tick"] / sim.RATE}}
    if canonical(wrapper["provider"]) != canonical(expected):
        raise ValueError("Opaque checkpoint envelope contradicts the native source")
    return wrapper, cp


def _raw(path, maximum):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Select a regular retained file")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("Retained source exceeds byte budget")
    return raw


def _check_actions(directory, actions, events):
    if len(actions) != len(events):
        raise ValueError("Accepted event count differs from the declared plan")
    for index, (action, event) in enumerate(zip(actions, events)):
        intent = load(directory / f"intent-{index:03}.json")
        receipt = load(directory / f"receipt-{index:03}.json")
        check_seal(intent); check_seal(receipt)
        expected = seal({"schema": "ciw.simulation-intervention.v1", "actor_id": action["actor_id"],
            "action": action["action"], "command": event["command"], "simulation_id": event["simulation_id"],
            "model_id": event["model_id"], "authority": deepcopy(AUTHORITY)})
        expected_receipt = seal({"schema": "ciw.simulation-intervention-receipt.v1", "intent": expected,
            "event_id": event["event_id"], "state_revision": event["revision"], "tick": event["after"]["tick"],
            "authority": deepcopy(AUTHORITY)})
        field = "ticks" if action["action"] == "advance" else "impulse_n_s"
        if (event["action"] != action["action"] or canonical(event["command"].get(field)) != canonical(action[field])
                or canonical(intent) != canonical(expected) or canonical(receipt) != canonical(expected_receipt)):
            raise ValueError("Intervention/source/actor binding mismatch")


def _inspect_details(directory: Path, *, candidate_report: dict | None = None) -> tuple:
    """Reopen checkpoints, observations and comparisons. No execution or oracle call."""
    root = Path(directory)
    plan = load(root / "plan.json")
    report = load(root / "study.json") if candidate_report is None else detached(candidate_report)
    validate_plan(plan)
    keys(report, {"schema", "study_id", "plan_id", "status", "parent_checkpoint_id", "branches",
                  "comparisons", "reproduced_from", "authority", "record_digest"})
    check_seal(report)
    if (report["schema"] != REPORT or report["status"] != "completed"
            or not re.fullmatch(r"study-[0-9a-f]{32}", report["study_id"])
            or report["plan_id"] != digest(plan) or canonical(report["authority"]) != canonical(AUTHORITY)):
        raise ValueError("Unsupported study or authority")
    reproduction = report["reproduced_from"]
    if reproduction is not None:
        keys(reproduction, {"study_id", "record_digest"})
        content_ref(reproduction["record_digest"])
        if (not re.fullmatch(r"study-[0-9a-f]{32}", reproduction["study_id"])
                or reproduction["study_id"] == report["study_id"]):
            raise ValueError("Invalid reproduction lineage")
    parent_wrapper, parent = _load_cp(root / "parent", report["study_id"])
    if (parent_wrapper["record_digest"] != report["parent_checkpoint_id"]
            or canonical(parent["model"]["parameters"]) != canonical(plan["model"])
            or canonical(parent["initial_state"]) != canonical(plan["initial"])):
        raise ValueError("Parent source differs from the study plan")
    _check_actions(root / "parent", plan["prefix"], parent["events"])
    if type(report["branches"]) is not list or len(report["branches"]) != len(plan["branches"]):
        raise ValueError("Branch list differs from the plan")
    owners, ids = {parent_wrapper["provider"]["owner_id"]}, set()
    for index, (declared, branch) in enumerate(zip(plan["branches"], report["branches"])):
        keys(branch, {"name", "branch_id", "parent_checkpoint_id", "checkpoint_id", "native_checkpoint_id", "owner_id", "observers"})
        target = root / f"branch-{index:02}"
        wrapper, cp = _load_cp(target, report["study_id"])
        if (branch["name"] != declared["name"] or branch["parent_checkpoint_id"] != parent_wrapper["record_digest"]
                or branch["checkpoint_id"] != wrapper["record_digest"] or branch["native_checkpoint_id"] != cp["checkpoint_id"]
                or branch["owner_id"] != wrapper["provider"]["owner_id"] or branch["owner_id"] in owners
                or not re.fullmatch(r"branch-[0-9a-f]{32}", branch["branch_id"]) or branch["branch_id"] in ids):
            raise ValueError("Branch lineage or owner binding mismatch")
        owners.add(branch["owner_id"]); ids.add(branch["branch_id"])
        prefix = len(parent["events"])
        for key in ("runtime", "model", "model_id", "simulation_id", "initial_state", "initial_force", "initial_owner_id", "configuration"):
            if canonical(cp[key]) != canonical(parent[key]):
                raise ValueError("Branch changed its selected parent/model/runtime")
        if (canonical(cp["events"][:prefix]) != canonical(parent["events"])
                or len(cp["events"]) <= prefix or cp["events"][prefix]["action"] != "restore"
                or cp["events"][prefix]["command"]["checkpoint_id"] != parent["checkpoint_id"]):
            raise ValueError("Branch did not restore the exact parent checkpoint")
        _check_actions(target, declared["actions"], cp["events"][prefix + 1:])
        if type(branch["observers"]) is not list or len(branch["observers"]) != len(plan["observers"]):
            raise ValueError("Observer count differs")
        for n, (spec, observed) in enumerate(zip(plan["observers"], branch["observers"])):
            validate_view(observed, cp)
            if canonical(observed["observer"]) != canonical(spec) or canonical(load(target / f"observer-{n:02}.json")) != canonical(observed):
                raise ValueError("Observer policy or retained copy differs")
    if canonical(report["comparisons"]) != canonical(_comparisons(plan, report["branches"])):
        raise ValueError("Comparison contradicts the typed observations")
    summary = {"status": "retained_study_checked", "study_id": report["study_id"],
            "record_digest": report["record_digest"], "branches": len(report["branches"]),
            "provider_execution": "not_performed", "authority": deepcopy(AUTHORITY)}
    return summary, plan, report, parent


def inspect(directory: Path) -> dict:
    return _inspect_details(directory)[0]


def reproduce(source: Path, binding: Path, output: Path, *, expected_report_digest: str) -> dict:
    verified, plan, original, parent = _inspect_details(source)
    content_ref(expected_report_digest)
    if verified["record_digest"] != expected_report_digest:
        raise ValueError("Study digest differs from the independently selected report")
    # Same installed code and explicitly bound native runtime are required. The
    # newly created parent below is checked against the source before any branch.
    expected_runtime = parent["runtime"]
    from .native_interop import NativeInteropWorkflow
    _, runtime = NativeInteropWorkflow()._adapters({"runtime": str(binding)})
    if runtime != expected_runtime:
        raise ValueError("Reproduction runtime differs from the original provider closure")
    fresh = run(plan, binding, output, reproduced_from={"study_id": original["study_id"], "record_digest": expected_report_digest}, expected_runtime=expected_runtime)
    result = _reproduction_record(plan, original, fresh)
    save_new(Path(output) / "reproduction.json", result)
    return result


def _reproduction_record(plan, original, fresh):
    pairs = []
    index = next(i for i, p in enumerate(plan["observers"]) if p["observer_id"] == plan["compare_observer"])
    for old, new in zip(original["branches"], fresh["branches"]):
        pairs.append({"branch_name": old["name"], "checks": {q: compare(new["observers"][index]["streams"][q],
            old["observers"][index]["streams"][q], **tol) for q, tol in plan["tolerances"].items()}})
    return seal({"schema": "ciw.simulation-study-reproduction.v1", "source_report_digest": original["record_digest"],
        "fresh_report_digest": fresh["record_digest"], "scope": "numerical_same_plan_same_runtime",
        "checks": pairs, "authority": deepcopy(AUTHORITY)})


def inspect_reproduction(source: Path, fresh: Path) -> dict:
    """Recheck both retained studies and comparison bindings; never reproduce implicitly."""
    _, plan, original, old_parent = _inspect_details(source)
    _, new_plan, new_report, new_parent = _inspect_details(fresh)
    old_owners = {old_parent["initial_owner_id"], *(b["owner_id"] for b in original["branches"])}
    new_owners = {new_parent["initial_owner_id"], *(b["owner_id"] for b in new_report["branches"])}
    if (canonical(plan) != canonical(new_plan) or old_parent["runtime"] != new_parent["runtime"]
            or old_parent["model_id"] != new_parent["model_id"]
            or old_parent["simulation_id"] == new_parent["simulation_id"]
            or not old_owners.isdisjoint(new_owners)
            or new_report["reproduced_from"] != {"study_id": original["study_id"], "record_digest": original["record_digest"]}):
        raise ValueError("Reproduction changed the plan/runtime or reused an owner/lineage")
    observed = load(Path(fresh) / "reproduction.json")
    expected = _reproduction_record(plan, original, new_report)
    if canonical(observed) != canonical(expected):
        raise ValueError("Reproduction receipt contradicts the retained studies")
    statuses = [check["outcome"]["status"] for pair in observed["checks"] for check in pair["checks"].values()]
    return {"status": "retained_reproduction_checked", "source_report_digest": original["record_digest"],
            "fresh_report_digest": new_report["record_digest"], "numerical_outcomes": statuses,
            "provider_execution": "not_performed", "authority": deepcopy(AUTHORITY)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe")
    p = commands.add_parser("view"); p.add_argument("directory", type=Path)
    p.add_argument("--observer", required=True); p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("inspect-reproduction"); p.add_argument("source", type=Path); p.add_argument("fresh", type=Path)
    p = commands.add_parser("plan"); p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("inspect"); p.add_argument("directory", type=Path)
    p = commands.add_parser("run"); p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--binding", type=Path, required=True); p.add_argument("--output-dir", type=Path, required=True)
    p = commands.add_parser("reproduce"); p.add_argument("directory", type=Path)
    p.add_argument("--expected-report-digest", required=True); p.add_argument("--binding", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "describe": result = describe()
        elif args.command == "view":
            from .simulation_study_view import write
            result = write(args.directory, args.observer, args.output)
        elif args.command == "plan":
            result = default_plan(); save_new(args.output, result)
        elif args.command == "inspect": result = inspect(args.directory)
        elif args.command == "inspect-reproduction": result = inspect_reproduction(args.source, args.fresh)
        elif args.command == "run": result = run(load(args.plan), args.binding, args.output_dir)
        else: result = reproduce(args.directory, args.binding, args.output_dir, expected_report_digest=args.expected_report_digest)
        print(canonical(result).decode())
        return 0
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        print(canonical({"status": "refused", "message": str(exc)}).decode())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
