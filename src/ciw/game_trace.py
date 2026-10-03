"""Bounded game traces on NET's existing observations and numerical checks.

This is an observation/checking boundary, not a gameplay model, clock, ECS,
script loader, or historical truth classifier. Event IDs are capture-local.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from .control_contracts import bytes_ref, content_ref, detached, keys, number, observation, text
from .control_checks import compare, verify
from .control_plane import ObservationBus
from .core.identities import content_identity

SCENARIO = "ciw.game-scenario.v1"
TRACE = "ciw.game-trace.v1"
CAPTURE = "ciw.game-capture.v1"
MAX_SAMPLES = 1024
MAX_EVENTS = 1024
MAX_BYTES = 4 * 1024 * 1024
FAULTS = ("none", "early-knowledge", "duplicate-reward", "drop-sample")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def bounded(value: Any) -> Any:
    value = detached(value)
    require(len(json.dumps(value, allow_nan=False).encode()) <= MAX_BYTES, "Game document exceeds byte budget")
    return value


def integer(value: Any, low: int, high: int) -> int:
    require(type(value) is int and low <= value <= high, f"Require integer in {low}..{high}, not bool")
    return value


def names(value: Any, maximum: int, *, nonempty: bool = True) -> list:
    require(type(value) is list and int(nonempty) <= len(value) <= maximum, "Require bounded ID list")
    for item in value:
        text(item)
    require(len(value) == len(set(value)), "Duplicate ID")
    return value


def validate_scenario(value: dict) -> None:
    bounded(value)
    keys(value, {"schema", "project_id", "scenario_id", "model_id", "source_class", "clock", "entities", "channels", "parameters", "checks"})
    require(value["schema"] == SCENARIO, "Unsupported game scenario")
    for key in ("project_id", "scenario_id", "model_id"):
        text(value[key])
    require(value["source_class"] in {"synthetic_fixture", "authored_game"}, "Declare game source class")
    clock = value["clock"]
    keys(clock, {"id", "tick_seconds", "duration_ticks"})
    text(clock["id"])
    require(0 < number(clock["tick_seconds"]) <= 3600, "Invalid logical tick duration")
    integer(clock["duration_ticks"], 1, 255)
    names(value["entities"], 64)
    channels = value["channels"]
    require(type(channels) is dict and 1 <= len(channels) <= 16, "Require 1..16 selected channels")
    require(len(channels) * (clock["duration_ticks"] + 1) <= MAX_SAMPLES, "Scenario exceeds sample budget")
    signatures = set()
    for name, spec in channels.items():
        text(name)
        keys(spec, {"entity_id", "quantity", "unit", "frame", "perspective"})
        require(spec["entity_id"] in value["entities"], "Channel entity is undeclared")
        for key in ("quantity", "unit", "frame"):
            text(spec[key])
        require(spec["perspective"] == "world" or spec["perspective"] in value["entities"], "Unknown perspective")
        signature = (spec["entity_id"], spec["quantity"])
        require(signature not in signatures, "Ambiguous observation quantity; distinguish perspective in the quantity ID")
        signatures.add(signature)
    require(type(value["parameters"]) is dict, "Parameters must be inert JSON data")
    require(type(value["checks"]) is list and len(value["checks"]) <= 32, "Too many checks")
    ids = []
    for check in value["checks"]:
        require(type(check) is dict, "Check must be an object")
        kind = check.get("kind")
        fields = {
            "bounded": {"channel", "minimum", "maximum"},
            "final_equals": {"channel", "value"},
            "before_event_equals": {"channel", "event_kind", "value"},
            "event_sequence": {"kinds"},
        }
        require(kind in fields, "Unsupported game check kind")
        keys(check, {"id", "kind"} | fields[kind])
        ids.append(text(check["id"]))
        if "channel" in check:
            require(check["channel"] in channels, "Check refers to undeclared channel")
        if kind == "event_sequence":
            names(check["kinds"], 32)
        if kind == "bounded":
            require(number(check["minimum"]) <= number(check["maximum"]), "Reversed check bounds")
        if "value" in check:
            number(check["value"])
        if "event_kind" in check:
            text(check["event_kind"])
    require(len(ids) == len(set(ids)), "Duplicate check ID")


def validate_trace(trace: dict, scenario: dict, nonce: str) -> None:
    validate_scenario(scenario)
    bounded(trace)
    keys(trace, {"schema", "request_nonce", "scenario_digest", "engine", "engine_version", "samples", "events", "dropped_samples", "dropped_events", "complete"})
    require(trace["schema"] == TRACE and trace["request_nonce"] == text(nonce), "Trace occurrence mismatch")
    require(trace["scenario_digest"] == content_identity(scenario), "Trace scenario mismatch")
    text(trace["engine"]); text(trace["engine_version"])
    require(type(trace["complete"]) is bool, "Completeness must be boolean")
    integer(trace["dropped_samples"], 0, MAX_SAMPLES)
    integer(trace["dropped_events"], 0, MAX_EVENTS)
    end = scenario["clock"]["duration_ticks"]
    samples, events = trace["samples"], trace["events"]
    require(type(samples) is list and len(samples) <= MAX_SAMPLES, "Sample budget exceeded")
    require(type(events) is list and len(events) <= MAX_EVENTS, "Event budget exceeded")
    seen = set()
    previous = -1
    missing_value = False
    for sample in samples:
        keys(sample, {"tick", "channel", "value"})
        tick = integer(sample["tick"], 0, end)
        require(tick >= previous, "Sample ticks moved backwards")
        previous = tick
        require(sample["channel"] in scenario["channels"], "Undeclared sample channel")
        key = (tick, sample["channel"])
        require(key not in seen, "Duplicate tick/channel observation")
        seen.add(key)
        if sample["value"] is None:
            missing_value = True
        else:
            number(sample["value"])
    expected = (end + 1) * len(scenario["channels"])
    require(len(samples) + trace["dropped_samples"] == expected, "Unaccounted missing samples")
    ids = set()
    previous = -1
    for event in events:
        keys(event, {"id", "tick", "kind", "actor_id", "target_ids", "causes", "payload"})
        event_id = text(event["id"])
        require(event_id not in ids, "Duplicate capture-local event ID")
        tick = integer(event["tick"], 0, end)
        require(tick >= previous, "Event ticks moved backwards")
        previous = tick
        text(event["kind"])
        require(event["actor_id"] in scenario["entities"], "Undeclared event actor")
        names(event["target_ids"], 64, nonempty=False)
        require(set(event["target_ids"]) <= set(scenario["entities"]), "Undeclared event target")
        names(event["causes"], 32, nonempty=False)
        require(set(event["causes"]) <= ids, "Causal reference must name an earlier retained event")
        require(type(event["payload"]) is dict, "Event payload must be JSON object")
        ids.add(event_id)
    if trace["complete"]:
        require(not trace["dropped_samples"] and not trace["dropped_events"] and not missing_value,
                "Incomplete capture cannot claim completeness")


def validate_capture(value: dict) -> None:
    bounded(value)
    keys(value, {"schema", "request", "trace_utf8", "trace_sha256"})
    require(value["schema"] == CAPTURE, "Unsupported game capture")
    request = value["request"]
    keys(request, {"scenario", "scenario_digest", "nonce", "diagnostic_fault"})
    validate_scenario(request["scenario"])
    require(request["scenario_digest"] == content_identity(request["scenario"]), "Request scenario digest mismatch")
    text(request["nonce"])
    require(request["diagnostic_fault"] in FAULTS, "Unsupported diagnostic fault")
    require(type(value["trace_utf8"]) is str, "Retain exact source JSON text")
    content_ref(value["trace_sha256"])
    require(bytes_ref(value["trace_utf8"].encode()) == value["trace_sha256"], "Trace source bytes changed")
    from .session import loads_json
    validate_trace(loads_json(value["trace_utf8"]), request["scenario"], request["nonce"])


def unpack(capture: dict) -> tuple[dict, dict]:
    validate_capture(capture)
    from .session import loads_json
    return capture["request"]["scenario"], loads_json(capture["trace_utf8"])


def observations(capture: dict, execution_id: str) -> dict:
    """Project selected scalars, preserving the actual capture execution identity."""
    scenario, trace = unpack(capture)
    bus = ObservationBus(MAX_SAMPLES)
    for sample in trace["samples"]:
        spec = scenario["channels"][sample["channel"]]
        bus.publish(observation(
            identity={"model_id": scenario["model_id"], "entity_id": spec["entity_id"], "execution_id": text(execution_id)},
            clock={"id": scenario["clock"]["id"], "time_s": sample["tick"] * scenario["clock"]["tick_seconds"]},
            frame=spec["frame"], quantity=spec["quantity"], value=sample["value"], unit=spec["unit"],
            provenance={"provider": "ciw.game." + trace["engine"], "sources": [capture["trace_sha256"]], "semantics": "simulated"}))
    return bus.snapshot()


def _series(stream: dict, spec: dict) -> list[dict]:
    return [item for item in stream["observations"] if item["identity"]["entity_id"] == spec["entity_id"] and item["quantity"] == spec["quantity"]]


def _status(statuses: list[str]) -> str:
    return "FAIL" if "FAIL" in statuses else "PASS" if statuses and all(s == "PASS" for s in statuses) else "INDETERMINATE"


def audit(capture: dict, execution_id: str) -> dict:
    """Check authored rules, not the truth of a history or the quality of a game."""
    scenario, trace = unpack(capture)
    stream = observations(capture, execution_id)
    outcomes = []
    for rule in scenario["checks"]:
        status, reason, detail = "INDETERMINATE", "incomplete_capture", None
        if trace["complete"]:
            if rule["kind"] == "event_sequence":
                actual = [event["kind"] for event in trace["events"] if event["kind"] in rule["kinds"]]
                status = "PASS" if actual == rule["kinds"] else "FAIL"
                reason = "event_sequence_equal" if status == "PASS" else "event_sequence_differs"
                detail = {"expected": rule["kinds"], "actual": actual}
            else:
                spec = scenario["channels"][rule["channel"]]
                values = _series(stream, spec)
                low = rule.get("minimum", rule.get("value"))
                high = rule.get("maximum", rule.get("value"))
                if rule["kind"] == "final_equals":
                    values = values[-1:]
                elif rule["kind"] == "before_event_equals":
                    ticks = [e["tick"] for e in trace["events"] if e["kind"] == rule["event_kind"]]
                    values = [v for v in values if v["clock"]["time_s"] < min(ticks) * scenario["clock"]["tick_seconds"]] if ticks else []
                detail = verify(rule["id"], "bounded", values, minimum=low, maximum=high, unit=spec["unit"])
                status, reason = detail["outcome"]["status"], detail["outcome"]["reason"]
        outcomes.append({"id": rule["id"], "status": status, "reason": reason, "detail": detail})
    return {"schema": "ciw.game-audit.v1", "checks": outcomes, "status": _status([x["status"] for x in outcomes]),
            "claim_scope": "authored_game_rules_only", "verification_id": None, "state_admission": "not_performed"}


def _event_projection(trace: dict) -> list[dict]:
    indices = {event["id"]: i for i, event in enumerate(trace["events"])}
    return [{**{k: deepcopy(v) for k, v in e.items() if k not in {"id", "causes"}},
             "causes": [indices[cause] for cause in e["causes"]]} for e in trace["events"]]


def comparison(left: dict, right: dict, left_execution: str, right_execution: str, *, atol: float, rtol: float = 0.0) -> dict:
    """Compare retained event structure and the existing typed numerical series.

    Right is the declared reference. No interpolation, imputation, implicit unit
    conversion, or claim of cross-engine determinism. A difference is not a design verdict.
    """
    require(number(atol) >= 0 and number(rtol) >= 0, "Invalid comparison policy")
    a, ta = unpack(left); b, tb = unpack(right)
    signature = ("project_id", "scenario_id", "model_id", "source_class", "clock", "entities", "channels")
    compatible = all(a[key] == b[key] for key in signature)
    complete = ta["complete"] and tb["complete"]
    result = {"schema": "ciw.game-comparison.v1", "policy": {"atol": atol, "rtol": rtol},
              "channels": {}, "events": {"status": "INDETERMINATE", "reason": "incompatible_scenario" if not compatible else "incomplete_capture"},
              "first_divergence_tick": None, "status": "INDETERMINATE",
              "claim_scope": "declared_trace_comparison_only", "verification_id": None, "state_admission": "not_performed"}
    if not compatible or not complete:
        return result
    left_stream, right_stream = observations(left, left_execution), observations(right, right_execution)
    divergent_ticks = []
    for name, spec in a["channels"].items():
        ls, rs = _series(left_stream, spec), _series(right_stream, spec)
        check = compare(ls, rs, atol=atol, rtol=rtol)
        result["channels"][name] = check
        if check["outcome"]["status"] == "FAIL":
            # Use the SAME numerical comparator to locate the first failed sample.
            for index, (lv, rv) in enumerate(zip(ls, rs)):
                if compare([lv], [rv], atol=atol, rtol=rtol)["outcome"]["status"] == "FAIL":
                    divergent_ticks.append(index)
                    break
    ea, eb = _event_projection(ta), _event_projection(tb)
    equal = ea == eb
    result["events"] = {"status": "PASS" if equal else "FAIL", "reason": "event_structure_equal" if equal else "event_structure_differs"}
    if not equal:
        for index in range(max(len(ea), len(eb))):
            av = ea[index] if index < len(ea) else None
            bv = eb[index] if index < len(eb) else None
            if av != bv:
                divergent_ticks.append(min(v["tick"] for v in (av, bv) if v is not None))
                break
    result["first_divergence_tick"] = min(divergent_ticks) if divergent_ticks else None
    result["status"] = _status([result["events"]["status"], *[v["outcome"]["status"] for v in result["channels"].values()]])
    return bounded(result)
