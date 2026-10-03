"""Retained thermofluid reference calculations on NET's existing identity substrate.

Inspection checks structure/integrity only. Verification explicitly recomputes
using the same implementation; it is neither independent nor physical validation.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import platform
import re

from . import thermofluids_models as models
from . import control_contracts
from .control_contracts import bytes_ref, content_ref, json_tree, keys, number, text
from .core import identities
from .core.identities import content_identity, new_identity, validate_identity
from .operations import runner
from .operations.runner import seal, check_seal

SCHEMA = "ciw.thermofluids-run.v1"
AUTHORITY = {"physical_validation": "not_established", "state_admission": "not_performed",
             "hardware_actuation": "not_performed", "uncertainty": "not_quantified"}
_RUNTIME_FILES = {"models": models, "workflow": None, "contracts": control_contracts,
                  "identities": identities, "record_seals": runner}


def runtime_identity():
    sources = {}
    for name, module in _RUNTIME_FILES.items():
        path = Path(__file__ if module is None else module.__file__)
        sources[name] = bytes_ref(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode())
    return {"implementation": "ciw.thermofluids.python-reference.v1",
            "python_version": platform.python_version(), "source_sha256": sources}


def operation_id(profile):
    if profile not in models.PROFILES:
        raise ValueError("Unknown thermofluids profile")
    return f"ciw.thermofluids.{profile}.v1"


def catalog():
    return {"schema": "ciw.thermofluids-catalog.v1", "read_only": True,
            "authorizes_execution": False, "qualification": "not_performed_by_catalog",
            "profiles": [{"profile": name, "operation_id": operation_id(name), **deepcopy(spec)}
                         for name, spec in models.PROFILES.items()],
            "authority": deepcopy(AUTHORITY)}


def _validate_data(data, profile):
    keys(data, {"quantities", "assumptions", "limitations"})
    keys(data["quantities"], set(models.OUTPUT_UNITS[profile]))
    for name, unit in models.OUTPUT_UNITS[profile].items():
        item = data["quantities"][name]
        keys(item, {"value", "unit"})
        number(item["value"])
        if item["unit"] != unit:
            raise ValueError("Thermofluids result unit mismatch")
    for name in ("assumptions", "limitations"):
        if data[name] != models.PROFILES[profile][name]:
            raise ValueError("Thermofluids model scope mismatch")


def _validate(record):
    json_tree(record)
    keys(record, {"schema", "evidence_id", "operation_id", "execution_id", "result_id",
                  "request", "runtime", "data", "numerical_digest", "authority", "replay_of", "record_digest"})
    check_seal(record)
    if record["schema"] != SCHEMA or record["authority"] != AUTHORITY:
        raise ValueError("Thermofluids schema or authority mismatch")
    models.validate_request(record["request"])
    profile = record["request"]["profile"]
    if record["operation_id"] != operation_id(profile):
        raise ValueError("Thermofluids operation binding mismatch")
    if record["evidence_id"] != content_identity(record["request"]):
        raise ValueError("Thermofluids source binding mismatch")
    validate_identity(record["execution_id"], "execution")
    validate_identity(record["result_id"], "result")
    runtime = record["runtime"]
    keys(runtime, {"implementation", "python_version", "source_sha256"})
    if runtime["implementation"] != "ciw.thermofluids.python-reference.v1":
        raise ValueError("Unknown thermofluids implementation")
    text(runtime["python_version"])
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", runtime["python_version"]) is None:
        raise ValueError("Invalid Python version in thermofluids runtime")
    keys(runtime["source_sha256"], set(_RUNTIME_FILES))
    for ref in runtime["source_sha256"].values():
        content_ref(ref)
    _validate_data(record["data"], profile)
    if record["numerical_digest"] != content_identity(record["data"]):
        raise ValueError("Thermofluids numerical content mismatch")
    if record["replay_of"] is not None:
        parent = record["replay_of"]
        keys(parent, {"record_digest", "execution_id", "result_id"})
        content_ref(parent["record_digest"])
        for name, kind in (("execution_id", "execution"), ("result_id", "result")):
            validate_identity(parent[name], kind)
            if parent[name] == record[name]:
                raise ValueError("Replay must create new occurrence identities")


def run(request):
    request = deepcopy(request)
    models.validate_request(request)
    data = models.calculate(request)
    _validate_data(data, request["profile"])
    result = seal({"schema": SCHEMA, "evidence_id": content_identity(request),
                   "operation_id": operation_id(request["profile"]),
                   "execution_id": new_identity("execution"), "result_id": new_identity("result"),
                   "request": request, "runtime": runtime_identity(), "data": data,
                   "numerical_digest": content_identity(data), "authority": deepcopy(AUTHORITY),
                   "replay_of": None})
    _validate(result)
    return result


def inspect(record):
    """Read retained quantities without a numerical solve or verification event."""
    _validate(record)
    return {"schema": "ciw.thermofluids-inspection.v1", "record_digest": record["record_digest"],
            "profile": record["request"]["profile"], "input_semantics": record["request"]["input_semantics"],
            "evidence_id": record["evidence_id"], "operation_id": record["operation_id"],
            "execution_id": record["execution_id"], "result_id": record["result_id"],
            "data": deepcopy(record["data"]), "authority": deepcopy(AUTHORITY),
            "integrity": "PASS", "numerical_verification": "not_performed_by_inspection"}


def verify(record):
    """Fresh verification occurrence; exact same-runtime reproduction only."""
    _validate(record)
    current = runtime_identity()
    same_runtime = current == record["runtime"]
    agrees = None
    if same_runtime:
        agrees = content_identity(models.calculate(record["request"])) == record["numerical_digest"]
    return seal({"schema": "ciw.thermofluids-verification.v1",
                 "verification_id": new_identity("verification"),
                 "record_ref": record["record_digest"], "execution_ref": record["execution_id"],
                 "result_ref": record["result_id"], "evidence_ref": record["evidence_id"],
                 "runtime": current, "status": "REFUSE" if not same_runtime else "PASS" if agrees else "FAIL",
                 "checks": {"retained_integrity": True, "same_runtime": same_runtime,
                            "exact_recomputation": agrees},
                 "scope": "same_implementation_exact_recomputation", "independent": False,
                 "authority": deepcopy(AUTHORITY)})


def replay(record):
    """An explicit new execution, linked to the intact and reproducible original."""
    verification = verify(record)
    if verification["status"] != "PASS":
        raise ValueError("Replay requires an intact result reproducible with the current runtime")
    result = run(record["request"])
    result["replay_of"] = {name: record[name] for name in ("record_digest", "execution_id", "result_id")}
    seal(result)
    _validate(result)
    return result
