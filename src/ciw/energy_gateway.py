"""GPU energy availability as a refused-or-present host gate.

A missing device is a structured refusal. Presence of NVML is not a laboratory
control gateway and does not admit energy readings as plant state.
"""
from __future__ import annotations

from pathlib import Path

SCHEMA = "ciw.energy-gateway.v1"


def status(device_index=0):
    from .energy_bench import probe
    try:
        reading = probe(device_index)
    except Exception as exc:
        return {
            "schema": SCHEMA,
            "status": "unavailable",
            "device_index": device_index,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1024],
            "authority": "not_a_laboratory_gateway",
            "state_admission": "not_performed",
        }
    return {
        "schema": SCHEMA,
        "status": "available",
        "device_index": device_index,
        "sensor": reading.get("sensor"),
        "authority": "not_a_laboratory_gateway",
        "state_admission": "not_performed",
    }


def replay_log(path):
    """Recompute a retained energy log. No device is opened."""
    from .energy_records import SCHEMA as LOG_SCHEMA, analyze
    payload = __import__("json").loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != LOG_SCHEMA:
        raise ValueError("Energy gateway replay requires a retained energy-accuracy log")
    report = analyze(payload)
    return {
        "schema": SCHEMA,
        "status": "replayed",
        "authority": "not_a_laboratory_gateway",
        "state_admission": "not_performed",
        "device_opened": False,
        "analysis": report,
    }


def measure(device_index=0):
    """One NVML identity/counter read. Not actuation and not a workload."""
    report = status(device_index)
    report["mode"] = "measurement_only"
    report["actuation"] = "not_performed"
    return report
