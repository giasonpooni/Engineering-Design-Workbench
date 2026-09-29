"""Bounded, deterministic historical-perspective authoring contracts.

This is a qualitative authored policy, not a psychological estimator or a claim
about historical truth. World truth is operator-only. No probabilities are fitted.
"""
from __future__ import annotations

from copy import deepcopy
import json

from .control_contracts import detached, keys, text
from .core.identities import content_identity

SCHEMA = "ciw.historical-perspective.v1"
VIEW = "ciw.actor-perspective.v1"
AUDIT = "ciw.epistemic-audit.v1"
POLICY = "retain-conflicts-and-modalities.v1"
CLASSES = {"attested", "inferred", "reconstructed", "fiction"}
MAX_BYTES = 262144


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def tick(value: int) -> int:
    require(type(value) is int and 0 <= value <= 1_000_000_000, "Require a bounded integer tick")
    return value


def _rows(value: list, maximum: int, *, nonempty: bool = False) -> list:
    require(type(value) is list and int(nonempty) <= len(value) <= maximum, "Invalid collection size")
    return value


def validate(scenario: dict) -> dict:
    """Validate and detach a complete declaration before deriving anything."""
    value = detached(scenario)
    require(len(json.dumps(value, allow_nan=False).encode("utf-8")) <= MAX_BYTES, "Scenario byte budget exceeded")
    keys(value, {"schema", "project_id", "scenario_id", "source_class", "clock", "actors",
                 "propositions", "evidence", "observations", "statements"})
    require(value["schema"] == SCHEMA, "Unsupported perspective schema")
    for name in ("project_id", "scenario_id"):
        text(value[name])
    require(value["source_class"] in {"synthetic_fixture", "authored_reconstruction"}, "Declare source class")
    keys(value["clock"], {"id", "unit", "historical_binding"})
    text(value["clock"]["id"])
    require(value["clock"]["unit"] == "logical_tick", "No implicit clock conversion")
    require(value["clock"]["historical_binding"] == "unbound", "Calendar qualification is not implemented")
    actors = _rows(value["actors"], 32, nonempty=True)
    for actor in actors:
        text(actor)
    require(len(set(actors)) == len(actors), "Duplicate actor")
    props, sources, observations, statements = {}, {}, {}, set()
    for prop in _rows(value["propositions"], 64, nonempty=True):
        keys(prop, {"id", "text", "world_truth"})
        text(prop["id"]); text(prop["text"])
        require(prop["id"] not in props, "Duplicate proposition")
        require(prop["world_truth"] is None or type(prop["world_truth"]) is bool, "World truth must be nullable boolean")
        props[prop["id"]] = prop
    for source in _rows(value["evidence"], 64, nonempty=True):
        keys(source, {"id", "classification", "reference", "scope"})
        for field in ("id", "reference", "scope"):
            text(source[field])
        require(source["id"] not in sources, "Duplicate evidence reference")
        require(source["classification"] in CLASSES, "Unknown evidence classification")
        if value["source_class"] == "synthetic_fixture":
            require(source["classification"] == "fiction", "Synthetic fixtures cannot claim historical attestation")
        sources[source["id"]] = source

    def claim_fields(claim: dict) -> None:
        require(claim["proposition"] in props, "Unknown proposition")
        require(type(claim["value"]) is bool, "Claims require boolean polarity")
        require(claim["about_actor"] is None or claim["about_actor"] in actors, "Unknown attributed actor")

    for obs in _rows(value["observations"], 256):
        keys(obs, {"id", "sender", "recipient", "sent_tick", "received_tick", "minimum_delay", "parent",
                   "proposition", "value", "about_actor", "mode", "evidence_id"})
        text(obs["id"])
        require(obs["id"] not in observations, "Duplicate observation")
        require(obs["sender"] in actors and obs["recipient"] in actors, "Unknown route actor")
        require(obs["evidence_id"] in sources, "Unbound evidence reference")
        claim_fields(obs)
        require(obs["mode"] in {"report", "forecast"}, "Unknown observation modality")
        sent, delay = tick(obs["sent_tick"]), tick(obs["minimum_delay"])
        if obs["received_tick"] is not None:
            require(tick(obs["received_tick"]) >= sent + delay, "Arrival violates declared delay")
        if obs["parent"] is None:
            require(obs["sender"] == obs["recipient"] and obs["received_tick"] == sent and delay == 0,
                    "Root requires an explicit local observation")
        else:
            text(obs["parent"])
        observations[obs["id"]] = obs
    # All routes are checked, including undelivered ones. Input list order is not causality.
    for obs in observations.values():
        cursor, seen = obs, set()
        while cursor["parent"] is not None:
            require(cursor["id"] not in seen and len(seen) < 32, "Cyclic or over-deep observation lineage")
            seen.add(cursor["id"])
            require(cursor["parent"] in observations, "Missing parent observation")
            parent = observations[cursor["parent"]]
            require(parent["recipient"] == cursor["sender"], "Sender did not receive parent")
            require(parent["received_tick"] is not None and cursor["sent_tick"] >= parent["received_tick"],
                    "Cannot relay unavailable information")
            for field in ("proposition", "value", "about_actor", "mode", "evidence_id"):
                require(cursor[field] == parent[field], "Relay changed claim; author a distinct origin instead")
            cursor = parent
    for statement in _rows(value["statements"], 128):
        keys(statement, {"id", "actor", "tick", "text", "claim"})
        text(statement["id"]); text(statement["text"])
        require(statement["id"] not in statements, "Duplicate statement")
        statements.add(statement["id"])
        require(statement["actor"] in actors, "Unknown speaker")
        tick(statement["tick"])
        claim = statement["claim"]
        if claim is not None:
            keys(claim, {"proposition", "value", "about_actor", "mode", "evidence_class"})
            claim_fields(claim)
            require(claim["mode"] in {"assertion", "report", "forecast"}, "Unknown statement modality")
            require(claim["evidence_class"] in CLASSES, "Unknown presentation classification")
    return value


def _root(obs: dict, observations: dict) -> str:
    while obs["parent"] is not None:
        obs = observations[obs["parent"]]
    return obs["id"]


def _received(scenario: dict, actor: str, at: int) -> list[dict]:
    return sorted((o for o in scenario["observations"]
                   if o["recipient"] == actor and o["received_tick"] is not None and o["received_tick"] <= at),
                  key=lambda o: (o["received_tick"], o["id"]))


def compile_actor(scenario: dict, actor: str, at: int) -> dict:
    """No omniscient fallback and no copying another actor's private state."""
    scenario = validate(scenario)
    tick(at)
    require(actor in scenario["actors"], "Unknown selected actor")
    props = {p["id"]: p for p in scenario["propositions"]}
    groups = {}
    for obs in _received(scenario, actor, at):
        key = (obs["proposition"], obs["about_actor"], obs["mode"])
        groups.setdefault(key, []).append(obs)
    beliefs = []
    for (prop, about, mode), rows in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2])):
        values = {r["value"] for r in rows}
        beliefs.append({"proposition": prop, "text": props[prop]["text"], "about_actor": about, "mode": mode,
                        "status": "conflicted" if len(values) > 1 else "supports" if True in values else "opposes",
                        "receipts": [{"id": r["id"], "sender": r["sender"], "received_tick": r["received_tick"],
                                      "value": r["value"]} for r in rows]})
    # Source classifications, world_truth and the full declaration are deliberately absent.
    return {"schema": VIEW, "project_id": scenario["project_id"], "scenario_id": scenario["scenario_id"],
            "actor": actor, "at_tick": at, "clock_id": scenario["clock"]["id"], "policy": POLICY,
            "semantics": "qualitative_authored_beliefs_not_probabilities", "beliefs": beliefs}


def audit(scenario: dict) -> dict:
    """Check explicit annotations, NOT the semantics of free-form dialogue."""
    scenario = validate(scenario)
    sources = {s["id"]: s for s in scenario["evidence"]}
    observations = {o["id"]: o for o in scenario["observations"]}
    checks = []
    for statement in scenario["statements"]:
        claim = statement["claim"]
        check = {"statement_id": statement["id"], "status": "INDETERMINATE", "reason": "unannotated_text",
                 "receipt_ids": [], "evidence_ids": [], "distinct_origin_count": 0}
        if claim is not None:
            mode = "forecast" if claim["mode"] == "forecast" else "report"
            rows = [r for r in _received(scenario, statement["actor"], statement["tick"])
                    if (r["proposition"], r["about_actor"], r["mode"]) ==
                       (claim["proposition"], claim["about_actor"], mode)]
            matching = [r for r in rows if r["value"] == claim["value"]]
            check["receipt_ids"] = [r["id"] for r in matching]
            check["evidence_ids"] = sorted({r["evidence_id"] for r in matching})
            check["distinct_origin_count"] = len({_root(r, observations) for r in matching})
            if not matching:
                check.update(status="FAIL", reason="no_available_matching_observation")
            elif claim["evidence_class"] != "fiction" and any(
                    sources[r["evidence_id"]]["classification"] != claim["evidence_class"] for r in matching):
                check.update(status="FAIL", reason="unsupported_evidence_reclassification")
            elif claim["mode"] == "assertion" and any(r["value"] != claim["value"] for r in rows):
                check.update(status="INDETERMINATE", reason="unresolved_conflicting_reports")
            else:
                check.update(status="PASS", reason="annotation_supported_within_declared_model")
        checks.append(check)
    states = {c["status"] for c in checks}
    status = "FAIL" if "FAIL" in states else "INDETERMINATE" if not checks or "INDETERMINATE" in states else "PASS"
    return {"schema": AUDIT, "scenario_digest": content_identity(scenario), "policy": POLICY,
            "status": status, "checks": checks, "verification_id": None, "state_admission": "not_performed",
            "historical_authentication": "not_performed", "dialogue_semantics_checked": False}


def example() -> dict:
    """Original fiction. This is not an incident or quotation from either game."""
    def observation(oid, sender, recipient, sent, received, parent=None, *, value=True,
                    prop="route_open", about=None, mode="report", delay=0):
        return {"id": oid, "sender": sender, "recipient": recipient, "sent_tick": sent,
                "received_tick": received, "minimum_delay": delay, "parent": parent,
                "proposition": prop, "value": value, "about_actor": about, "mode": mode, "evidence_id": "fiction"}
    def statement(sid, at, *, mode="assertion", prop="route_open", about=None):
        return {"id": sid, "actor": "commander", "tick": at, "text": "Original annotated test line.",
                "claim": {"proposition": prop, "value": True, "about_actor": about, "mode": mode,
                          "evidence_class": "fiction"}}
    return {"schema": SCHEMA, "project_id": "net-reference", "scenario_id": "three-perspectives",
            "source_class": "synthetic_fixture", "clock": {"id": "authored-local-clock", "unit": "logical_tick", "historical_binding": "unbound"},
            "actors": ["commander", "scout", "quartermaster"],
            "propositions": [{"id": "route_open", "text": "The route is open.", "world_truth": True},
                             {"id": "reinforcements_arrive", "text": "Reinforcements will arrive.", "world_truth": None},
                             {"id": "private_fact", "text": "Operator-only unobserved fact.", "world_truth": True}],
            "evidence": [{"id": "fiction", "classification": "fiction", "reference": "fixture:three-perspectives",
                          "scope": "Original software test fiction; no historical attestation."}],
            "observations": [observation("scout-sees", "scout", "scout", 1, 1),
                observation("quartermaster-hears", "quartermaster", "quartermaster", 1, 1, value=False),
                observation("scout-report", "scout", "commander", 1, 4, "scout-sees", delay=3),
                observation("quartermaster-report", "quartermaster", "commander", 2, 6, "quartermaster-hears", value=False, delay=4),
                observation("forecast", "commander", "commander", 2, 2, prop="reinforcements_arrive", mode="forecast"),
                observation("attribution", "scout", "scout", 2, 2, about="quartermaster"),
                observation("attribution-report", "scout", "commander", 2, 5, "attribution", about="quartermaster", delay=3)],
            "statements": [statement("too-early", 3), statement("received", 4), statement("conflict", 6),
                           statement("attributed-report", 6, mode="report"),
                           statement("forecast-is-not-fact", 3, prop="reinforcements_arrive"),
                           statement("permitted-forecast", 3, mode="forecast", prop="reinforcements_arrive"),
                           statement("bounded-attribution", 5, about="quartermaster")]}
