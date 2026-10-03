"""Prepare declared atmospheric measurement artifacts from bounded SI CSV.

Preparation preserves the supplied declarations and uses the existing reference,
acceptance-policy and evidence contracts. It does not acquire measurements,
authenticate an instrument, evaluate calibration or execute a physical provider.
Static validation binds retained inputs without replaying their CSV mapping.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from decimal import Decimal, InvalidOperation
import io
import re

from .atmosphere_comparison_contract import (
    FIELD_UNITS, MAX_OBSERVATIONS, MAX_SCALARS, POLICY_SCHEMA, REFERENCE_SCHEMA,
    RULE, make_reference_source, validate_policy, validate_reference,
)
from .control_contracts import MAX_BYTES, bytes_ref, content_ref, json_tree, keys, number
from .operations.runner import check_seal, digest, seal

DECLARATION_SCHEMA = "ciw.atmosphere-measurement-import.v1"
PREPARATION_SCHEMA = "ciw.atmosphere-reference-preparation.v1"
CSV_FIELDS = (
    "sample_index", "height_m", "quantity", "value", "unit",
    "uncertainty_kind", "absolute_bound", "coverage_factor", "uncertainty_ref",
    "instrument_ref", "calibration_ref",
)
NORMALIZATION = {
    "encoding": "utf-8", "utf8_bom": "optional_removed_for_parsing",
    "csv_header": "exact", "numeric_syntax": "finite_ascii_decimal",
    "row_order": "sample_index_then_quantity", "units": "exact_SI_no_conversion",
    "coordinate_transform": "none", "uncertainty_transform": "none",
    "height_interpolation": "none",
}
AUTHORITY = {
    "physical_validation": "not_established", "calibration_validation": "not_established",
    "measurement_authenticity": "not_established", "reference_independence": "not_established",
    "state_admission": "not_performed", "hardware_actuation": "not_performed",
}
MAX_CELL_CHARS = 512
MAX_NUMERIC_CHARS = 128
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", re.ASCII)
_INDEX = re.compile(r"(?:0|[1-9][0-9]{0,2})", re.ASCII)
_PREPARATION_KEYS = {
    "schema", "csv_content_digest", "declaration_digest", "reference", "policy",
    "reference_evidence_id", "observation_count", "scalar_count", "normalization",
    "authority", "record_digest",
}


def _bounded_bytes(csv_bytes: bytes) -> None:
    if type(csv_bytes) is not bytes or not 1 <= len(csv_bytes) <= MAX_BYTES:
        raise ValueError("Measurement CSV must be nonempty bytes inside the 8 MiB budget")


def _declaration(declaration: dict) -> dict:
    json_tree(declaration)
    keys(declaration, {"schema", "provenance", "context", "thresholds"})
    if declaration["schema"] != DECLARATION_SCHEMA:
        raise ValueError("Unsupported atmospheric measurement import declaration")
    keys(declaration["provenance"], {"kind", "source_ref", "source_url", "independent_of_candidate"})
    if declaration["provenance"]["kind"] != "declared_measurements":
        raise ValueError("Measurement CSV preparation requires declared_measurements provenance")
    keys(declaration["context"], {"frame", "height_origin_m", "valid_time_utc", "humidity_convention"})
    if type(declaration["thresholds"]) is not dict:
        raise ValueError("Declare explicit comparison thresholds for every imported quantity")
    return deepcopy(declaration)


def _decimal(value: str, label: str) -> float:
    if len(value) > MAX_NUMERIC_CHARS or _DECIMAL.fullmatch(value) is None:
        raise ValueError(f"{label} requires a bounded finite ASCII decimal")
    try:
        parsed = float(value)
        exact = Decimal(value)
    except (ValueError, InvalidOperation) as exc:
        raise ValueError(f"{label} requires a representable finite ASCII decimal") from exc
    number(parsed)
    # Do not turn a supplied nonzero uncertainty or scalar into an exact zero.
    if parsed == 0.0 and exact != 0:
        raise ValueError(f"Nonzero {label} underflows binary64")
    # Equivalent zero-height rows must not choose an evidence identity by order.
    return 0.0 if parsed == 0.0 else parsed


def _quotes(text: str) -> None:
    # csv.reader(strict=True) still accepts quotes inside unquoted fields.
    # Reject those ambiguous rows while retaining ordinary RFC-style escaping.
    state = "start"
    for character in text:
        if state == "quoted":
            if character == '"':
                state = "after_quote"
        elif state == "after_quote":
            if character == '"':
                state = "quoted"
            elif character in ",\r\n":
                state = "start"
            else:
                raise ValueError("Malformed measurement CSV quoting")
        elif character in ",\r\n":
            state = "start"
        elif character == '"':
            if state != "start":
                raise ValueError("Malformed measurement CSV quoting")
            state = "quoted"
        else:
            state = "unquoted"
    if state == "quoted":
        raise ValueError("Malformed measurement CSV quoting")


def _observations(csv_bytes: bytes) -> list[dict]:
    _bounded_bytes(csv_bytes)
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Measurement CSV must use UTF-8, with an optional initial BOM") from exc
    if "\x00" in text:
        raise ValueError("Measurement CSV cannot contain NUL characters")
    _quotes(text)
    observations = {}
    declared_heights = {}
    cell_count = 0
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        if next(reader, None) != list(CSV_FIELDS):
            raise ValueError("Measurement CSV requires the exact eleven-column header")
        for row in reader:
            cell_count += 1
            if cell_count > MAX_SCALARS:
                raise ValueError("Measurement CSV exceeds the 774 scalar-row budget")
            if len(row) != len(CSV_FIELDS):
                raise ValueError("Every measurement row requires exactly eleven cells")
            if any(len(cell) > MAX_CELL_CHARS for cell in row):
                raise ValueError("Measurement CSV cell exceeds the bounded text budget")
            cells = dict(zip(CSV_FIELDS, row))
            index_text = cells["sample_index"]
            if _INDEX.fullmatch(index_text) is None:
                raise ValueError("sample_index requires an explicit decimal integer from 0 to 128")
            index = int(index_text)
            if index >= MAX_OBSERVATIONS:
                raise ValueError("sample_index requires an explicit decimal integer from 0 to 128")
            height = _decimal(cells["height_m"], "height_m")
            field = cells["quantity"]
            if field not in FIELD_UNITS:
                raise ValueError("Measurement quantities must name an existing atmospheric SI field")
            if index not in observations:
                observations[index] = {"sample_index": index, "height_m": height, "quantities": {}}
                declared_heights[index] = Decimal(cells["height_m"])
            observation = observations[index]
            if declared_heights[index] != Decimal(cells["height_m"]):
                raise ValueError("Measurement rows for one sample_index must declare the same height")
            if field in observation["quantities"]:
                raise ValueError("Duplicate measurement sample_index and quantity")
            coverage = cells["coverage_factor"]
            observation["quantities"][field] = {
                "value": _decimal(cells["value"], "value"), "unit": cells["unit"],
                "uncertainty": {
                    "kind": cells["uncertainty_kind"],
                    "absolute_bound": _decimal(cells["absolute_bound"], "absolute_bound"),
                    "coverage_factor": None if coverage == "" else _decimal(coverage, "coverage_factor"),
                    "reference": cells["uncertainty_ref"],
                },
                "instrument_ref": cells["instrument_ref"],
                "calibration_ref": None if cells["calibration_ref"] == "" else cells["calibration_ref"],
            }
    except csv.Error as exc:
        raise ValueError("Malformed measurement CSV") from exc
    if not observations:
        raise ValueError("Measurement CSV requires at least one scalar observation")
    return [
        {"sample_index": index, "height_m": observations[index]["height_m"],
         "quantities": {field: observations[index]["quantities"][field]
                        for field in sorted(observations[index]["quantities"])}}
        for index in sorted(observations)
    ]


def prepare(csv_bytes: bytes, declaration: dict) -> dict:
    """Map explicit corrected SI rows to sealed reference and policy artifacts."""
    declaration = _declaration(declaration)
    reference = validate_reference(seal({
        "schema": REFERENCE_SCHEMA, "provenance": deepcopy(declaration["provenance"]),
        "context": deepcopy(declaration["context"]), "observations": _observations(csv_bytes),
    }))
    policy = validate_policy(reference, seal({
        "schema": POLICY_SCHEMA, "rule": RULE, "thresholds": deepcopy(declaration["thresholds"]),
    }))
    preparation = seal({
        "schema": PREPARATION_SCHEMA, "csv_content_digest": bytes_ref(csv_bytes),
        "declaration_digest": digest(declaration), "reference": reference, "policy": policy,
        "reference_evidence_id": make_reference_source(reference)["evidence_id"],
        "observation_count": len(reference["observations"]),
        "scalar_count": sum(len(row["quantities"]) for row in reference["observations"]),
        "normalization": deepcopy(NORMALIZATION), "authority": deepcopy(AUTHORITY),
    })
    return validate_preparation(csv_bytes, declaration, preparation)


def validate_preparation(csv_bytes: bytes, declaration: dict, preparation: dict) -> dict:
    """Validate retained declarations and bindings without replaying CSV mapping.

    Fresh preparation is required to check that the reference values were mapped
    from the retained CSV correctly. Static inspection establishes no new
    measurement, calibration, verification or physical-validation authority.
    """
    _bounded_bytes(csv_bytes)
    declaration = _declaration(declaration)
    json_tree(preparation)
    keys(preparation, _PREPARATION_KEYS)
    if preparation["schema"] != PREPARATION_SCHEMA:
        raise ValueError("Unsupported atmospheric reference preparation schema")
    for name in ("csv_content_digest", "declaration_digest", "reference_evidence_id"):
        content_ref(preparation[name])
    if (preparation["csv_content_digest"] != bytes_ref(csv_bytes)
            or preparation["declaration_digest"] != digest(declaration)):
        raise ValueError("Preparation input content differs from its retained bindings")
    reference = validate_reference(preparation["reference"])
    policy = validate_policy(reference, preparation["policy"])
    if (digest(reference["provenance"]) != digest(declaration["provenance"])
            or digest(reference["context"]) != digest(declaration["context"])
            or digest(policy["thresholds"]) != digest(declaration["thresholds"])):
        raise ValueError("Preparation declarations differ from the retained reference or policy")
    if preparation["reference_evidence_id"] != make_reference_source(reference)["evidence_id"]:
        raise ValueError("Preparation reference evidence differs from the canonical reference Run")
    counts = {
        "observation_count": len(reference["observations"]),
        "scalar_count": sum(len(row["quantities"]) for row in reference["observations"]),
    }
    for name, expected in counts.items():
        if type(preparation[name]) is not int or preparation[name] != expected:
            raise ValueError("Preparation counts differ from retained scalar observations")
    if (preparation["normalization"] != NORMALIZATION or preparation["authority"] != AUTHORITY):
        raise ValueError("Preparation normalization or authority contradicts its fixed profile")
    check_seal(preparation)
    return deepcopy(preparation)
