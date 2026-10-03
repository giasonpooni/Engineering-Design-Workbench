"""Bounded, data-only inventory balances on declared exact interval labels.

Integrated transfers and instant inventories share one explicit SI basis. Full
raw covariance is required; no conversion, independence inference or covariance
repair occurs at this boundary. A balance deficit does not identify its cause.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import os
from pathlib import Path
import re
import stat

from .control_contracts import content_ref, detached, keys, number as _bounded_number, text
from .core.identities import canonical_json
from .operations.runner import digest

SCHEMA = "ciw.leakage-request.v1"
RESULT_SCHEMA = "ciw.leakage-calculation.v1"
MAX_BYTES = 256 * 1024
MAX_INTERVALS = 16
MAX_RAW_SIZE = 64
PROCESSES = {"injection_molding", "extrusion_blow_molding"}
PURPOSES = {"feed", "product", "runners", "rejects", "purge", "regrind", "return", "other"}
UNITS = {"volume": "m3", "mass": "kg"}
COVARIANCE_UNITS = {"volume": "m6", "mass": "kg2"}
SUPPORT_POLICY = "declared_exact_interval_labels"
AUTHORITY = {"physical_validation": "not_established", "calibration_traceability": "not_established",
             "causal_leak_identification": "not_established", "state_admission": "not_performed",
             "hardware_actuation": "not_performed", "llm_inference": "not_performed"}
LIMITATIONS = [
    "Offline pre-reconciliation balance; no state projection or hardware action.",
    "A negative residual is an unexplained inventory deficit, not a causal leak diagnosis.",
    "Conditional on declared boundary completeness, measurement covariance and exact support labels.",
    "Clock uncertainty, unmetered transfers, constitutive flow physics and measurement bias are not inferred.",
    "Volume conservation requires a suitable incompressible inventory basis; mass is not converted to volume.",
    "Evidence and calibration references are retained declarations, not physical traceability validation.",
]


def number(value) -> float:
    numeric = _bounded_number(value)
    if type(value) is int and int(numeric) != value:
        raise ValueError("Integer readings must be exactly representable in the native binary64 profile")
    return numeric


def _refs(value) -> None:
    if type(value) is not list or not 1 <= len(value) <= 16:
        raise ValueError("Require 1..16 retained content references")
    for ref in value:
        content_ref(ref)
    if len(set(value)) != len(value):
        raise ValueError("Duplicate evidence reference")


def raw_order(request: dict) -> list[str]:
    """Inventory first, then interval-major/channel-major integrated transfers."""
    n = len(request["edges_s"]) - 1
    return ([f"inventory:{i}" for i in range(n + 1)] +
            [f"transfer:{channel['channel_id']}:{i}" for i in range(n)
             for channel in request["channels"]])


def raw_readings(request: dict) -> list[dict]:
    n = len(request["edges_s"]) - 1
    return (list(request["inventory"]["readings"]) +
            [channel["readings"][i] for i in range(n) for channel in request["channels"]])


def evidence_group(reading: dict) -> list[str]:
    return list(dict.fromkeys(reading["evidence_refs"] +
                              [reading["calibration_ref"], reading["clock_ref"]]))


def _positive_semidefinite(matrix: list[list[float]]) -> None:
    """Validate without repair. Exact binary64 elimination handles singular cases.

    Rational Schur elimination distinguishes an exactly PSD declared matrix from
    a small negative eigenvalue; no tolerance turns negative variance into zero.
    """
    rows = [[Fraction.from_float(float(v)) for v in row] for row in matrix]
    for k in range(len(rows)):
        pivot = rows[k][k]
        if pivot < 0:
            raise ValueError("Full raw covariance must be positive semidefinite; no repair")
        if pivot == 0:
            if any(rows[k][j] != 0 for j in range(k + 1, len(rows))):
                raise ValueError("Zero-variance covariance direction has nonzero cross-covariance")
            continue
        for i in range(k + 1, len(rows)):
            for j in range(i, len(rows)):
                value = rows[i][j] - rows[i][k] * rows[k][j] / pivot
                rows[i][j] = rows[j][i] = value


def validate_request(value: dict) -> dict:
    keys(value, {"schema", "identity", "process", "source_kind", "frame", "clock", "boundary_id",
                 "basis", "unit", "edges_s", "inventory", "channels", "covariance", "decision_policy"})
    detached(value)
    if len(canonical_json(value).encode()) + 1 > MAX_BYTES:
        raise ValueError("Leakage request exceeds the 256 KiB budget")
    if value["schema"] != SCHEMA or type(value["process"]) is not str or value["process"] not in PROCESSES:
        raise ValueError("Require leakage schema and supported polymer process")
    if type(value["source_kind"]) is not str or value["source_kind"] not in {"synthetic", "retained_observation"}:
        raise ValueError("Declare synthetic or retained observation evidence")
    keys(value["identity"], {"facility_id", "machine_id", "tool_id", "material_lot_id", "cycle_id", "part_id"})
    for item in value["identity"].values():
        text(item)
    text(value["frame"])
    text(value["boundary_id"])
    if type(value["basis"]) is not str or value["basis"] not in UNITS or value["unit"] != UNITS[value["basis"]]:
        raise ValueError("Require explicit volume/m3 or mass/kg basis; no implicit conversion")
    clock = value["clock"]
    keys(clock, {"id", "start_s", "end_s", "clock_ref", "support_policy"})
    text(clock["id"])
    content_ref(clock["clock_ref"])
    start, end = number(clock["start_s"]), number(clock["end_s"])
    if not 0 <= start < end or clock["support_policy"] != SUPPORT_POLICY:
        raise ValueError("Require bounded clock with declared exact interval support labels")
    edges = value["edges_s"]
    if type(edges) is not list or not 2 <= len(edges) <= MAX_INTERVALS + 1:
        raise ValueError("Require 1..16 contiguous intervals")
    for edge in edges:
        number(edge)
    if not start <= edges[0] < edges[-1] <= end or any(a >= b for a, b in zip(edges, edges[1:])):
        raise ValueError("Interval edges must increase strictly within the declared clock")
    n = len(edges) - 1

    def reading(row, expected, fields):
        keys(row, fields | {"value", "evidence_refs", "calibration_ref", "clock_ref"})
        if number(row["value"]) < 0:
            raise ValueError("Inventory and directed transfer totals must be nonnegative")
        for field, support in expected.items():
            number(row[field])
            if row[field] != support:
                raise ValueError("Each reading must match its exact declared interval support")
        _refs(row["evidence_refs"])
        content_ref(row["calibration_ref"])
        content_ref(row["clock_ref"])
        if row["clock_ref"] != clock["clock_ref"]:
            raise ValueError("Reading clock reference must match the declared aligned support clock")

    inventory = value["inventory"]
    keys(inventory, {"support", "unit", "readings"})
    if inventory["support"] != "instant" or inventory["unit"] != value["unit"]:
        raise ValueError("Require instant inventory in the declared balance unit")
    if type(inventory["readings"]) is not list or len(inventory["readings"]) != n + 1:
        raise ValueError("Instant inventory requires n+1 boundary readings")
    for i, row in enumerate(inventory["readings"]):
        reading(row, {"time_s": edges[i]}, {"time_s"})
    channels = value["channels"]
    if type(channels) is not list or not 1 <= len(channels) <= 16 or n + 1 + n * len(channels) > MAX_RAW_SIZE:
        raise ValueError("Require bounded transfer channels and at most 64 raw readings")
    ids = set()
    for channel in channels:
        keys(channel, {"channel_id", "direction", "purpose", "support", "unit", "readings"})
        sid = text(channel["channel_id"])
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", sid) or sid in ids:
            raise ValueError("Require distinct bounded channel identifiers")
        ids.add(sid)
        if (type(channel["direction"]) is not str or channel["direction"] not in {"in", "out"}
                or type(channel["purpose"]) is not str or channel["purpose"] not in PURPOSES):
            raise ValueError("Require declared channel direction and named transfer purpose")
        if channel["support"] != "integrated_total" or channel["unit"] != value["unit"]:
            raise ValueError("Only integrated transfers in the declared balance unit are supported")
        if type(channel["readings"]) is not list or len(channel["readings"]) != n:
            raise ValueError("Every transfer channel requires one total per interval")
        for i, row in enumerate(channel["readings"]):
            reading(row, {"start_s": edges[i], "end_s": edges[i + 1]}, {"start_s", "end_s"})
    covariance = value["covariance"]
    keys(covariance, {"unit", "raw_order", "matrix", "evidence_refs"})
    order = raw_order(value)
    if covariance["unit"] != COVARIANCE_UNITS[value["basis"]] or covariance["raw_order"] != order:
        raise ValueError("Full covariance requires exact raw measurement order and squared unit")
    _refs(covariance["evidence_refs"])
    matrix = covariance["matrix"]
    if type(matrix) is not list or len(matrix) != len(order):
        raise ValueError("Require complete square raw covariance, not variances or unknown uncertainty")
    for row in matrix:
        if type(row) is not list or len(row) != len(order):
            raise ValueError("Require complete square raw covariance")
        for item in row:
            number(item)
    for i, row in enumerate(matrix):
        if row[i] < 0 or any(row[j] != matrix[j][i] for j in range(len(order))):
            raise ValueError("Full covariance must be exactly symmetric with nonnegative variances")
        if row[i] == 0 and any(item != 0 for item in row):
            raise ValueError("Declared zero variance requires zero cross-covariance")
    _positive_semidefinite(matrix)
    policy = value["decision_policy"]
    keys(policy, {"loss_threshold", "coverage_factor", "threshold_ref"})
    if number(policy["loss_threshold"]) < 0 or not 1 <= number(policy["coverage_factor"]) <= 6:
        raise ValueError("Require nonnegative loss threshold and uncertainty multiplier in [1,6]")
    content_ref(policy["threshold_ref"])
    return deepcopy(value)


def load_file(path: Path) -> dict:
    """Strict bounded source JSON: no links, duplicate keys or nonzero underflow."""
    from .adapters.protocol import AdapterRefusal
    from .adapters.subprocess import _json
    try:
        path = Path(path)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError("Leakage source must be a bounded regular non-symlink file")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
                raise ValueError("Leakage source must be a bounded regular non-symlink file")
            payload = stream.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("Leakage source exceeds the 256 KiB file budget")
        value = _json(payload)
    except (OSError, AdapterRefusal) as exc:
        raise ValueError("Leakage source requires strict bounded JSON in a regular non-symlink file") from exc
    return validate_request(value)


def save_file(path: Path, request: dict) -> None:
    """Create a compact canonical source; an existing destination is never replaced."""
    payload = (canonical_json(validate_request(request)) + "\n").encode()
    if len(payload) > MAX_BYTES:
        raise ValueError("Leakage source exceeds the 256 KiB file budget")
    with Path(path).open("xb") as stream:
        stream.write(payload)


def example_request(basis: str = "volume") -> dict:
    if basis not in UNITS:
        raise ValueError("Unsupported leakage example basis")
    unit, edges = UNITS[basis], [0.0, 2.5, 5.0, 7.5, 10.0]
    clock_ref = digest({"synthetic_leakage_clock": edges})

    def row(identifier, amount, **support):
        return {**support, "value": amount, "evidence_refs": [digest({"synthetic_leakage_reading": identifier})],
                "calibration_ref": digest({"synthetic_leakage_calibration": identifier}), "clock_ref": clock_ref}

    value = {"schema": SCHEMA,
             "identity": {"facility_id": "synthetic.factory", "machine_id": "synthetic.machine.4",
                          "tool_id": "synthetic.tool.1", "material_lot_id": "synthetic.resin.lot.1",
                          "cycle_id": "synthetic.cycle.10", "part_id": "synthetic.part.10"},
             "process": "injection_molding", "source_kind": "synthetic", "frame": "polymer.machine.v1",
             "clock": {"id": "synthetic.aligned-clock", "start_s": edges[0], "end_s": edges[-1],
                       "clock_ref": clock_ref, "support_policy": SUPPORT_POLICY},
             "boundary_id": "synthetic.inventory-boundary", "basis": basis, "unit": unit, "edges_s": edges,
             "inventory": {"support": "instant", "unit": unit,
                           "readings": [row(f"inventory:{i}", 10.0 + .15 * i, time_s=t) for i, t in enumerate(edges)]},
             "channels": [{"channel_id": sid, "direction": direction, "purpose": purpose,
                           "support": "integrated_total", "unit": unit,
                           "readings": [row(f"{sid}:{i}", amount, start_s=a, end_s=b)
                                        for i, (a, b) in enumerate(zip(edges, edges[1:]))]}
                          for sid, direction, purpose, amount in [("feed", "in", "feed", 1.0),
                                                                  ("product", "out", "product", .8)]],
             "covariance": {"unit": COVARIANCE_UNITS[basis], "raw_order": [], "matrix": [],
                            "evidence_refs": [digest({"synthetic_joint_leakage_covariance": basis})]},
             "decision_policy": {"loss_threshold": .01, "coverage_factor": 2.0,
                                 "threshold_ref": digest({"synthetic_loss_threshold": basis})}}
    order = raw_order(value)
    value["covariance"]["raw_order"] = order
    value["covariance"]["matrix"] = [[(1e-4 if i < len(edges) else 1e-6) if i == j else 0.0
                                       for j in range(len(order))] for i in range(len(order))]
    return validate_request(value)
