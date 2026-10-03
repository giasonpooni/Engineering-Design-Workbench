"""Fixed, data-only dispatch for two explicitly qualified synthetic fluid profiles.

Saved profile names and schemas select trusted structural validators; they never
load an arbitrary provider or activate numerical execution.
"""
from __future__ import annotations

from .control_contracts import json_tree

PROFILES = ("reservoir", "wave")
OPERATIONS = {
    "reservoir": ("fluid.reservoir.simulate.v1", "fluid.reservoir.verify.v1"),
    "wave": ("fluid.wave.simulate.v1", "fluid.wave.verify.v1"),
}


def module(profile: str):
    if type(profile) is not str or profile not in PROFILES:
        raise ValueError("Unsupported fluid profile; require reservoir or wave")
    if profile == "reservoir":
        from . import fluid_reservoir_contract as contract
    else:
        from . import fluid_wave_contract as contract
    return contract


def profile_for_request(request: dict) -> str:
    if type(request) is not dict:
        raise ValueError("Fluid request must be a strict declared object")
    for profile in PROFILES:
        if request.get("schema") == module(profile).REQUEST_SCHEMA:
            return profile
    raise ValueError("Unsupported fluid request schema")


def profile_for_operation(operation: str) -> tuple[str, str]:
    for profile, identities in OPERATIONS.items():
        if operation in identities:
            return profile, "solver" if operation == identities[0] else "verifier"
    raise ValueError("Unsupported fluid operation")


def example_request(profile: str = "reservoir") -> dict:
    return module(profile).example_request()


def validate_request(request: dict) -> dict:
    json_tree(request)
    return module(profile_for_request(request)).validate_request(request)


def validate_result(request: dict, result: dict) -> dict:
    json_tree(result)
    return module(profile_for_request(request)).validate_result(request, result)


def validate_report(request: dict, result: dict, report: dict) -> dict:
    """Validate retained report shape and bindings without a reference evaluation."""
    profile = profile_for_request(request)
    json_tree(report)
    if profile == "reservoir":
        from .fluid_reservoir_verification import validate_report as validator
    else:
        from .fluid_wave_verification import validate_report as validator
    return validator(request, result, report)


def simulate(request: dict) -> dict:
    profile = profile_for_request(request)
    if profile == "reservoir":
        from .fluid_reservoir_solver import simulate as provider
    else:
        from .fluid_wave_solver import simulate as provider
    return provider(validate_request(request))


def verify(request: dict, result: dict) -> dict:
    profile = profile_for_request(request)
    if profile == "reservoir":
        from .fluid_reservoir_verification import verify as provider
    else:
        from .fluid_wave_verification import verify as provider
    return provider(validate_request(request), result)
