"""Fixed, data-only dispatch for explicitly bounded synthetic fluid profiles.

Saved profile names and schemas select trusted structural validators; they never
load an arbitrary provider or activate numerical execution.
"""
from __future__ import annotations

from importlib import import_module

from .control_contracts import json_tree

PROFILES = ("reservoir", "wave")
OPERATIONS = {
    "reservoir": ("fluid.reservoir.simulate.v1", "fluid.reservoir.verify.v1"),
    "wave": ("fluid.wave.simulate.v1", "fluid.wave.verify.v1"),
}
# Keep the original public collection stable for downstream legacy fixtures.
# New callers select the full additive catalog explicitly.
EXTENDED_PROFILES = ("molecular", "sph", "fsi")
ALL_PROFILES = PROFILES + EXTENDED_PROFILES
EXTENDED_OPERATIONS = {
    profile: ("fluid." + profile + ".simulate.v1", "fluid." + profile + ".verify.v1")
    for profile in EXTENDED_PROFILES
}
ALL_OPERATIONS = {**OPERATIONS, **EXTENDED_OPERATIONS}
_MODULES = {profile: "ciw.fluid_" + profile for profile in ALL_PROFILES}


def provider_module(profile: str, kind: str):
    """Only the fixed installed catalog can name an executable module."""
    if type(profile) is not str or profile not in _MODULES or type(kind) is not str or kind not in {"contract", "solver", "reference", "verification"}:
        raise ValueError("Unsupported fluid profile or provider kind")
    return import_module(_MODULES[profile] + "_" + kind)


def module(profile: str):
    return provider_module(profile, "contract")


def profile_for_request(request: dict) -> str:
    if type(request) is not dict:
        raise ValueError("Fluid request must be a strict declared object")
    for profile in ALL_PROFILES:
        if request.get("schema") == module(profile).REQUEST_SCHEMA:
            return profile
    raise ValueError("Unsupported fluid request schema")


def profile_for_operation(operation: str) -> tuple[str, str]:
    for profile, identities in ALL_OPERATIONS.items():
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
    return provider_module(profile, "verification").validate_report(request, result, report)


def simulate(request: dict) -> dict:
    profile = profile_for_request(request)
    return provider_module(profile, "solver").simulate(validate_request(request))


def verify(request: dict, result: dict) -> dict:
    profile = profile_for_request(request)
    return provider_module(profile, "verification").verify(validate_request(request), result)
