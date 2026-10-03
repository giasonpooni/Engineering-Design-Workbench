"""Trusted, read-only payload schemas, independent of executable runtime bindings.

Persisted files cannot register or import validators. New providers register a
schema in trusted process setup, alongside their executable operation binding.
"""
from __future__ import annotations

from collections.abc import Callable

from ..core.records import finite_tree
from .registry import valid_operation_id

_VALIDATORS: dict[str, Callable] = {}


def validate_role(operation_id: str, role: str) -> None:
    expected = {"statistics.v1": "analysis", "spectrum.periodogram.v1": "analysis",
                "fsrt.tank-reconstruct.v1": "state_estimator",
                "fsrt.tank-reconstruct.v2": "state_estimator",
                "ciw.simulated-fsrt.v1": "state_estimator",
                "jspt.covariance-propagate.v1": "backend",
                "gte.project-circle.v1": "backend",
                "gsc.local-frame.v1": "backend",
                "oscillator.rhs-native.v1": "backend",
                "legibility.compile.v1": "backend",
                "legibility.fixture-summary.v1": "backend",
                "impact.spring-contact.v1": "backend",
                "impact.spring-contact-verify.v1": "verification",
                "impact.crush-contact.v1": "backend",
                "impact.crush-contact-verify.v1": "verification",
                "impact.plate-contact.v1": "backend",
                "impact.plate-contact-verify.v1": "verification",
                "system.compile.v1": "backend", "system.simulate.v1": "backend",
                "system.verify.v1": "verification", "system.compare.v1": "backend",
                "system.study.v1": "backend",
                "atmosphere.compile.v1": "backend",
                "atmosphere.verify.v1": "verification"}.get(operation_id)
    if expected is not None and role != expected:
        raise ValueError("Operation role contradicts the declared payload contract")


def register_payload_validator(operation_id: str, validator: Callable) -> None:
    if not valid_operation_id(operation_id) or not callable(validator):
        raise ValueError("A payload schema requires a versioned operation and callable validator")
    if operation_id in _VALIDATORS or operation_id in {
        "statistics.v1", "spectrum.periodogram.v1", "fsrt.tank-reconstruct.v1",
        "fsrt.tank-reconstruct.v2", "jspt.covariance-propagate.v1", "gte.project-circle.v1", "legibility.compile.v1",
        "legibility.fixture-summary.v1", "gsc.local-frame.v1",
        "oscillator.rhs-native.v1", "ciw.simulated-fsrt.v1",
        "system.compile.v1", "system.simulate.v1",
        "system.verify.v1", "system.compare.v1", "system.study.v1"
    }:
        raise ValueError("Payload schema already registered")
    _VALIDATORS[operation_id] = validator


def validate_payload(operation_id: str, data: dict, run: dict, parameters: dict, selection: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("Operation data must be an object")
    finite_tree(data, "operation data")
    if operation_id in {"statistics.v1", "spectrum.periodogram.v1"}:
        from ..adapters.oscillator_records import validate_payload as validator
    elif operation_id == "fsrt.tank-reconstruct.v1":
        from ..adapters.fsrt_records import validate_payload as validator
    elif operation_id == "fsrt.tank-reconstruct.v2":
        from ..adapters.covariance_records import validate_fsrt_payload as validator
    elif operation_id == "ciw.simulated-fsrt.v1":
        from ..simulated_fsrt import validate_payload as validator
    elif operation_id == "jspt.covariance-propagate.v1":
        from ..adapters.covariance_records import validate_jspt_payload as validator
    elif operation_id == "gte.project-circle.v1":
        from ..adapters.gte_records import validate_payload as validator
    elif operation_id == "legibility.compile.v1":
        from ..legibility_workflow import validate_payload as validator
    elif operation_id == "legibility.fixture-summary.v1":
        from ..legibility_workflow import validate_fixture_payload as validator
    elif operation_id in {"impact.spring-contact.v1", "impact.spring-contact-verify.v1",
                          "impact.crush-contact.v1", "impact.crush-contact-verify.v1",
                          "impact.plate-contact.v1", "impact.plate-contact-verify.v1"}:
        from ..impact_workflow import validate_payload as validator
    elif operation_id == "gsc.local-frame.v1":
        from ..spatial_records import validate_payload as validator
    elif operation_id == "oscillator.rhs-native.v1":
        from ..adapters.oscillator_kernel import validate_payload as validator
    elif operation_id in {"system.compile.v1", "system.simulate.v1", "system.verify.v1", "system.compare.v1", "system.study.v1"}:
        from ..system_workflow import validate_payload as validator
    elif operation_id in {"atmosphere.compile.v1", "atmosphere.verify.v1"}:
        from ..atmosphere_workflow import validate_payload as validator
    else:
        validator = _VALIDATORS.get(operation_id)
        if validator is None:
            raise ValueError(f"No trusted saved-payload schema for {operation_id}")
    validator(operation_id, data, run, parameters, selection)
