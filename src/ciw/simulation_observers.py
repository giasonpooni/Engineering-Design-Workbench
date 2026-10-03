"""Quantity-limited observations over existing persistent oscillator checkpoints.

The source remains an opaque provider checkpoint. Observation views never carry
its hidden state, native steps or execution inputs. This is data minimisation,
not authentication or an access-control mechanism for a developer with the source.
"""
from __future__ import annotations
from copy import deepcopy
import re

from . import simulation as sim
from .control_contracts import observation, keys, text, content_ref, detached
from .operations.runner import seal, check_seal
from .telemetry import canonical

SCHEMA = "ciw.simulation-observer-view.v1"
POLICY_SCHEMA = "ciw.simulation-observer.v1"
UNITS = {"q_m": "m", "v_m_s": "m/s", "energy_j": "J"}
AUTHORITY = {"semantics": "simulated", "physical_validation": "not_performed",
             "state_admission": "not_performed", "verification_id": None,
             "uncertainty": "not_declared", "interpolation": "none"}
CLOCK = "oscillator-elapsed-time-120hz.v1"
MAX_OBSERVATIONS = 4096


def policy(observer_id: str, quantities: list[str], *, every_ticks: int = 1,
           delay_ticks: int = 0) -> dict:
    value = {"schema": POLICY_SCHEMA, "observer_id": observer_id,
             "quantities": deepcopy(quantities), "every_ticks": every_ticks,
             "delay_ticks": delay_ticks, "phase": "latest_committed_at_tick"}
    validate_policy(value)
    return value


def validate_policy(value: dict) -> None:
    keys(value, {"schema", "observer_id", "quantities", "every_ticks", "delay_ticks", "phase"})
    if value["schema"] != POLICY_SCHEMA or value["phase"] != "latest_committed_at_tick":
        raise ValueError("Unsupported observer profile or sample phase")
    text(value["observer_id"])
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", value["observer_id"]):
        raise ValueError("Observer identity is not a bounded label")
    q = value["quantities"]
    if (type(q) is not list or not 1 <= len(q) <= len(UNITS)
            or any(type(x) is not str or x not in UNITS for x in q) or len(set(q)) != len(q)):
        raise ValueError("Observer must select unique supported quantities")
    sim._integer(value["every_ticks"], 1, 120)
    sim._integer(value["delay_ticks"], 0, 24000)


def _samples(checkpoint: dict) -> dict[int, dict]:
    """Read native retained rows; use the last committed value at repeated ticks.

    Same-tick impulses remain separate events in the checkpoint. This projection
    explicitly selects their latest committed phase; it never rewrites a prior
    observer view, which remains bound to its original checkpoint digest.
    """
    initial = checkpoint["initial_state"]
    step = checkpoint["initial_force"]
    output = sim.validate_step(step, checkpoint["runtime"])
    rows = {0: {"q_m": initial["q_m"], "v_m_s": initial["v_m_s"],
                "energy_j": output["energy_j"][0]}}
    for event in checkpoint["events"]:
        if event["action"] == "restore":
            continue
        _, _, trajectory = sim._event_result(checkpoint["model"], event["before"],
            event["action"], event["command"], event["native_steps"], checkpoint["runtime"])
        for offset, (q, v, energy) in enumerate(zip(trajectory["q_m"], trajectory["v_m_s"], trajectory["energy_j"])):
            tick = trajectory["start_tick"] + offset
            rows[tick] = {"q_m": q, "v_m_s": v, "energy_j": energy}
    return rows


def project(checkpoint: dict, observer: dict, *, expected_checkpoint_id: str) -> dict:
    """Provider-free, quantity-limited view with explicit acquisition/delivery time."""
    # Checkpoint is bounded by its existing 32 MiB reader, not generic 8 MiB control JSON.
    checkpoint = deepcopy(checkpoint)
    observer = detached(observer)
    validate_policy(observer)
    content_ref(expected_checkpoint_id)
    current = sim.inspect_checkpoint(checkpoint, expected_checkpoint_id)
    now = current["state"]["tick"]
    eligible = now - observer["delay_ticks"]
    ticks = list(range(0, eligible + 1, observer["every_ticks"])) if eligible >= 0 else []
    if len(ticks) * len(observer["quantities"]) > MAX_OBSERVATIONS:
        raise ValueError("Observer output exceeds the 4096-record budget; use a slower sampling cadence")
    rows = _samples(checkpoint)
    streams = {}
    for quantity in observer["quantities"]:
        streams[quantity] = [observation(
            identity={"model_id": current["model_id"], "entity_id": "oscillator", "execution_id": None},
            clock={"id": CLOCK, "time_s": tick / sim.RATE}, frame=checkpoint["model"]["frame"],
            quantity=quantity, value=rows[tick][quantity], unit=UNITS[quantity],
            provenance={"provider": "ciw.persistent-oscillator-observer.v1",
                        "sources": [expected_checkpoint_id], "semantics": "simulated"}) for tick in ticks]
    return seal({"schema": SCHEMA, "observer": observer, "source_checkpoint_id": expected_checkpoint_id,
        "simulation_id": current["simulation_id"], "owner_id": current["owner_id"],
        "state_revision": current["revision"], "as_of_tick": now,
        "sample_ticks": ticks, "available_ticks": [t + observer["delay_ticks"] for t in ticks],
        "streams": streams, "authority": deepcopy(AUTHORITY)})


def validate_view(value: dict, checkpoint: dict) -> None:
    keys(value, {"schema", "observer", "source_checkpoint_id", "simulation_id", "owner_id",
                 "state_revision", "as_of_tick", "sample_ticks", "available_ticks", "streams",
                 "authority", "record_digest"})
    check_seal(value)
    expected = project(checkpoint, value["observer"], expected_checkpoint_id=value["source_checkpoint_id"])
    if canonical(value) != canonical(expected):
        raise ValueError("Observer view disagrees with its source, policy or authority")
