"""1792 water-round recipe and independent checks on retained native observations.

The game reducer, clock and save implementation remain in 1792. This module
checks the fixed authored production contract; it neither simulates the game
nor accepts a worker's self-reported PASS flag.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import uuid

from .control_contracts import bytes_ref, detached, keys, number, text
from .core.identities import content_identity
from .foundry_project import PROFILE, validate_lock
from .game_workflow import make_run
from .production import Gate, Worker, plan
from .production_workflow import _graph, _job

OP = "game.water-round-1792.v1"
GATE = "game.water-acceptance-1792.v1"
MODEL = "household-water-round.v1"
POLICY = {"total": 6, "load": 3, "draw_ticks": 180, "required_trips": 2}
WORKERS = (Worker("1792-domain-worker", (OP,)),)
_REGISTERED = False


def validate_parameters(value: dict) -> None:
    keys(value, {"nonce", "trips"})
    text(value["nonce"])
    if type(value["trips"]) is not int or value["trips"] not in (1, 2):
        raise ValueError("Declare one or two complete delivery trips")


def validate_objective(value: dict) -> None:
    keys(value, {"schema", "profile", "source_lock"})
    if value["schema"] != "ciw.foundry-objective.v1" or value["profile"] != PROFILE:
        raise ValueError("Unsupported installed Foundry objective")
    validate_lock(value["source_lock"])


def source(lock: dict) -> dict:
    validate_lock(lock)
    scenario = {"schema": "ciw.game-scenario.v1", "project_id": "1792", "scenario_id": PROFILE,
        "model_id": MODEL, "source_class": "authored_game",
        "clock": {"id": "foundry-declaration-not-game-clock", "tick_seconds": 1, "duration_ticks": 1},
        "entities": ["ranjit_singh"], "channels": {"declaration": {
            "entity_id": "ranjit_singh", "quantity": "declared_objective", "unit": "1",
            "frame": "foundry-declaration", "perspective": "world"}},
        "parameters": {"schema": "ciw.foundry-objective.v1", "profile": PROFILE, "source_lock": deepcopy(lock)},
        "checks": []}
    return make_run(scenario)


def objective(run: dict) -> dict:
    value = run["metadata"]["game_scenario"]["parameters"]
    validate_objective(value)
    if run["metadata"]["game_scenario"]["model_id"] != MODEL:
        raise ValueError("Foundry objective model mismatch")
    return value


def compile_plan(run: dict, *, candidate_trips: int = 1, repair: bool = True) -> dict:
    objective(run)
    validate_parameters({"nonce": "compile", "trips": candidate_trips})
    if type(repair) is not bool:
        raise ValueError("Repair selection must be boolean")
    def graph(name, trips):
        return _graph(name, OP, {"nonce": uuid.uuid4().hex, "trips": trips}, model=MODEL)
    checks = [{"check_id": "complete-conserved-water-round", "node_id": "candidate",
               "gate_id": GATE, "policy": deepcopy(POLICY)}]
    attempts = [graph("water-candidate", candidate_trips)]
    if repair and candidate_trips == 1:
        attempts.append(graph("declared-two-trip-correction", 2))
    return plan("1792-water-round-production", project_id="1792", source_evidence_id=run["evidence_id"], jobs=[
        _job("water-round", WORKERS[0].worker_id, ["game.1792.water-round"], attempts, checks),
        _job("water-round-regression", WORKERS[0].worker_id, ["game.1792.water-round"],
             [graph("fresh-process-regression", 2)], checks, ["water-round"])])


def validate_capture(value: dict, declared: dict, parameters: dict) -> dict:
    from .session import loads_json
    validate_objective(declared)
    validate_parameters(parameters)
    detached(value)
    keys(value, {"schema", "request", "source_utf8", "source_sha256", "logs", "elapsed_wall_s"})
    if value["schema"] != "ciw.foundry-water-capture.v1":
        raise ValueError("Unsupported Foundry capture")
    expected = {"schema": "ciw.foundry-water-request.v1", **parameters,
                "source_lock_id": declared["source_lock"]["source_lock_id"]}
    if value["request"] != expected:
        raise ValueError("Native request is not bound to this operation")
    raw = value["source_utf8"]
    if type(raw) is not str or not 0 < len(raw.encode()) <= 65536 or bytes_ref(raw.encode()) != value["source_sha256"]:
        raise ValueError("Native source bytes changed or exceeded the budget")
    if number(value["elapsed_wall_s"]) < 0:
        raise ValueError("Invalid native elapsed time")
    keys(value["logs"], {"stdout.log", "stderr.log"})
    for log in value["logs"].values():
        keys(log, {"utf8", "sha256"})
        if type(log["utf8"]) is not str or len(log["utf8"].encode()) > 65536 or bytes_ref(log["utf8"].encode()) != log["sha256"]:
            raise ValueError("Native log integrity mismatch")
    data = loads_json(raw)
    detached(data)
    keys(data, {"schema", "request_nonce", "source_lock_id", "engine_version", "model_id", "clock_id", "tick_hz",
        "source_class", "trips", "samples", "water_round", "checkpoint_before", "checkpoint_after",
        "duplicate_error", "before_duplicate", "after_duplicate"})
    fixed = {"schema": "cartesian.foundry-water-observations.v1", "request_nonce": parameters["nonce"],
        "source_lock_id": expected["source_lock_id"], "model_id": MODEL, "clock_id": "1792.childhood.tick",
        "tick_hz": 60, "source_class": "authored_game_with_explicit_domain_fixture", "trips": parameters["trips"]}
    if any(type(data[k]) is not type(v) or data[k] != v for k, v in fixed.items()):
        raise ValueError("Native observation identity/model/request mismatch")
    text(data["engine_version"])
    if type(data["samples"]) is not list or len(data["samples"]) > 9:
        raise ValueError("Observation count exceeds this recipe")
    return data


def _validate_payload(operation, data, run, parameters, selection):
    validate_capture(data, objective(run), parameters)


def register_schema() -> None:
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        register_payload_validator(OP, _validate_payload)
        _REGISTERED = True


def registry(binding):
    from .adapters.protocol import InstrumentManifest
    from .control_plane import CapabilityRegistry
    from .operations.registry import Operation
    register_schema()
    result = CapabilityRegistry()
    manifest = InstrumentManifest(instrument_id="org.cartesiangraphics.1792-water-round", version="1",
        role="operation_provider", inputs=("run.v1",), outputs=("ciw.operation-result.v1",), units={}, frames=(),
        sampling={"mode": "explicit_game_domain_capture"}, normalization={"state": "game_owned"},
        supported_operations=(OP,), determinism={"claim": "none_from_declaration"},
        tolerance_policy={"policy": "fixed_authored_water_contract"},
        calibration_requirements={"status": "not_applicable_gameplay"})
    result.advertise(manifest, runtime=binding.runtime_identity(), capabilities={OP: ["game.1792.water-round"]})
    result.bind(Operation(OP, "backend", lambda run, params: binding.invoke(objective(run), params), binding.runtime_identity))
    return result


def _whole(value, low=0, high=10000000):
    return type(value) in (int, float) and low <= value <= high and float(value).is_integer()


def _policy(value):
    if type(value) is not dict or content_identity(value) != content_identity(POLICY):
        raise ValueError("The installed acceptance contract cannot be weakened by a work order")


def evaluate(result: dict | None, policy: dict) -> dict:
    _policy(policy)
    if result is None:
        return {"status": "INDETERMINATE", "detail": {"reason": "missing_result"}}
    if result["operation_id"] != OP:
        raise ValueError("Wrong operation for 1792 acceptance")
    from .session import loads_json
    data = loads_json(result["data"]["source_utf8"])
    samples = data["samples"]
    # Missing observations never authorize repair or export as a passed artifact.
    if not samples or any(s is None for s in samples):
        return {"status": "INDETERMINATE", "detail": {"reason": "missing_observations"}}
    checks = {}
    try:
        trips = data["trips"]
        checks["sample_stages"] = [s["stage"] for s in samples] == ["assigned"] + ["draw-start", "before-fill", "filled", "deposited"] * trips
        origin = samples[0]["tick"]
        checks["clock"] = _whole(origin) and data["tick_hz"] == 60
        expected_ledgers = [{"remaining": 6, "carried": 0, "stored": 0, "phase": "ready", "started_tick": -1, "completed_tick": -1}]
        expected_ticks = [origin]
        expected_events = []
        for i in range(trips):
            tick, stored = origin + i * 180, i * 3
            drawing = {"remaining": 6-stored, "carried": 0, "stored": stored, "phase": "drawing", "started_tick": tick, "completed_tick": -1}
            carrying = {"remaining": 3-stored, "carried": 3, "stored": stored, "phase": "carrying", "started_tick": -1, "completed_tick": -1}
            deposited = {"remaining": 3-stored, "carried": 0, "stored": stored+3,
                         "phase": "complete" if i == 1 else "ready", "started_tick": -1,
                         "completed_tick": tick+180 if i == 1 else -1}
            expected_ledgers.extend([drawing, drawing, carrying, deposited])
            expected_ticks.extend([tick, tick+179, tick+180, tick+180])
            expected_events.extend([(tick, "draw"), (tick+180, "filled"), (tick+180, "deposit")])
        checks["sample_clock"] = [s["tick"] for s in samples] == expected_ticks and all(_whole(s["tick"]) for s in samples)
        checks["conserved_transfers"] = [s["ledger"] for s in samples] == expected_ledgers and all(
            all(_whole(s["ledger"][k], 0, 6) for k in ("remaining", "carried", "stored")) for s in samples)
        initial = samples[0]
        checks["no_currency_or_knowledge_reward"] = all(s["money"] == initial["money"] and s["known_places"] == initial["known_places"] for s in samples)
        water = data["water_round"]
        events = water["events"]
        checks["receipt_identity"] = water["schema"] == "gujranwala-water-round.v1" and water["model_id"] == MODEL and water["origin_tick"] == origin
        checks["receipt_sequence"] = [(e["tick"], e["kind"]) for e in events] == expected_events and all(
            e["seq"] == i+1 and _whole(e["seq"], 1, 6) and _whole(e["tick"]) and e["actor_id"] == "ranjit_singh" for i, e in enumerate(events))
        checks["receipt_locations"] = all(
            type(e["position"]) is list and len(e["position"]) == 3 and
            all(type(x) in (int, float) for x in e["position"]) and
            sum((e["position"][j]-site[j])**2 for j in (0, 2)) <= 9 and abs(e["position"][1]-site[1]) <= .65
            for e in events for site in [(3, .14, 5) if e["kind"] == "deposit" else (24, .14, 15)])
        checks["final_ledger_matches"] = water["ledger"] == samples[-1]["ledger"]
        before, after = data["checkpoint_before"], data["checkpoint_after"]
        checks["saved_pending_draw_roundtrips"] = before == after and before["childhood"]["tick"] == origin+90 and before["water_round"]["ledger"] == expected_ledgers[1]
        checks["duplicate_deposit_atomic"] = type(data["duplicate_error"]) is str and bool(data["duplicate_error"].strip()) and data["before_duplicate"] == data["after_duplicate"]
        checks["duplicate_probe_matches_final"] = all(data["before_duplicate"][k] == samples[-1][k] for k in ("tick", "ledger", "money", "known_places"))
        checks["complete_assignment"] = trips == 2 and water["ledger"]["stored"] == 6 and water["ledger"]["phase"] == "complete"
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        return {"status": "INDETERMINATE", "detail": {"reason": "incomplete_observation_fields"}}
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "detail": {"checks": checks, "scope": "authored_domain_contract_not_playability_or_historical_validation"}}


def gates() -> dict[str, Gate]:
    register_schema()
    return {GATE: Gate(GATE, {"provider": "ciw.foundry.1792-independent-checks",
        "source_sha256": bytes_ref(Path(__file__).read_bytes()),
        "scope": "installed policy and independent receipt predicates; no publication authority"}, _policy, evaluate)}
