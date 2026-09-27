"""GPU energy availability as a refused-or-present host gate.

A missing device is a structured refusal. Presence of NVML is not a laboratory
control gateway and does not admit energy readings as plant state.
"""
from __future__ import annotations

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
