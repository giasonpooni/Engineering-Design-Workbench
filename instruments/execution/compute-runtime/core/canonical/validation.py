"""Schema + constraint validation: the one legal route into a new
CanonicalState Version (§6).

    candidate
        |
        v
    1. SCHEMA VALIDATION   (types, unknown fields, required-field removal,
                             edge types)
        | fail -> reject
        v
    2. CONSTRAINT VALIDATION (min/max/enum/pattern)
        | fail -> reject
        v
    3. ACCEPT -> new Version

No backend, renderer, simulator, or neural component calls anything in
this module directly to *produce* a Version other than through this one
function. Rejection is atomic: on failure, no CanonicalState or Version is
constructed and `base` is left untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Union

from core.canonical.delta import CandidateChange, CandidateDelta, apply_changes, parse_path
from core.canonical.schema import FieldSchema, FieldValue, StateSchema
from core.canonical.state import CanonicalState
from core.canonical.version import ProvenanceInfo, Version, make_version


@dataclass(frozen=True)
class ValidationError:
    path: str
    code: str
    message: str


def _runtime_type_ok(field_schema: FieldSchema, value: FieldValue) -> bool:
    t = field_schema.type
    if t == "scalar":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "bool":
        return isinstance(value, bool)
    if t == "string":
        return isinstance(value, str)
    if t == "vector3":
        return isinstance(value, tuple) and len(value) == 3 and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
        )
    if t == "quaternion":
        return isinstance(value, tuple) and len(value) == 4 and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
        )
    return False


def _check_field_value_schema(
    schema: StateSchema, field_id: str, value: FieldValue, path: str, errors: List[ValidationError]
) -> None:
    field_schema = schema.fields.get(field_id)
    if field_schema is None:
        errors.append(ValidationError(path, "UNKNOWN_FIELD", f"no such field in schema: {field_id!r}"))
        return
    if not _runtime_type_ok(field_schema, value):
        errors.append(
            ValidationError(
                path, "TYPE_MISMATCH", f"{field_id!r} expects type {field_schema.type!r}, got {value!r}"
            )
        )


def _check_field_value_constraints(
    schema: StateSchema, field_id: str, value: FieldValue, path: str, errors: List[ValidationError]
) -> None:
    field_schema = schema.fields.get(field_id)
    if field_schema is None:
        return  # already reported as UNKNOWN_FIELD in the schema pass
    c = field_schema.constraints
    if c.min is not None and isinstance(value, (int, float)) and value < c.min:
        errors.append(ValidationError(path, "OUT_OF_RANGE", f"{value!r} < min {c.min!r}"))
    if c.max is not None and isinstance(value, (int, float)) and value > c.max:
        errors.append(ValidationError(path, "OUT_OF_RANGE", f"{value!r} > max {c.max!r}"))
    if c.enum is not None and value not in c.enum:
        errors.append(ValidationError(path, "NOT_IN_ENUM", f"{value!r} not in {c.enum!r}"))
    if c.pattern is not None and isinstance(value, str) and not re.fullmatch(c.pattern, value):
        errors.append(ValidationError(path, "PATTERN_MISMATCH", f"{value!r} does not match {c.pattern!r}"))


def _schema_validate(
    schema: StateSchema, base: CanonicalState, changes: tuple
) -> List[ValidationError]:
    errors: List[ValidationError] = []
    allowed_edge_types = {e.type for e in schema.edges}

    for change in changes:
        segments = parse_path(change.path)

        if segments[0] == "fields":
            field_id = segments[1]
            if len(segments) == 2:
                if change.operation == "add":
                    new_value = change.new_value
                    _check_field_value_schema(schema, field_id, new_value["value"], change.path, errors)
                elif change.operation == "remove":
                    field_schema = schema.fields.get(field_id)
                    if field_schema is None:
                        errors.append(
                            ValidationError(change.path, "UNKNOWN_FIELD", f"no such field: {field_id!r}")
                        )
                    elif field_schema.required:
                        errors.append(
                            ValidationError(
                                change.path,
                                "REQUIRED_FIELD_REMOVED",
                                f"{field_id!r} is required and cannot be removed",
                            )
                        )
            elif len(segments) == 3 and segments[2] == "value":
                _check_field_value_schema(schema, field_id, change.new_value, change.path, errors)
            elif len(segments) == 3 and segments[2] in ("type", "unit"):
                if field_id not in schema.fields:
                    errors.append(
                        ValidationError(change.path, "UNKNOWN_FIELD", f"no such field: {field_id!r}")
                    )
        elif segments[0] == "edges":
            if len(segments) == 2 and change.operation == "add":
                new_type = change.new_value["type"]
                if not allowed_edge_types or new_type not in allowed_edge_types:
                    errors.append(
                        ValidationError(
                            change.path,
                            "EDGE_TYPE_NOT_ALLOWED",
                            f"edge type {new_type!r} not declared in schema.edges",
                        )
                    )
            elif len(segments) == 3 and segments[2] == "type":
                if change.new_value not in allowed_edge_types:
                    errors.append(
                        ValidationError(
                            change.path,
                            "EDGE_TYPE_NOT_ALLOWED",
                            f"edge type {change.new_value!r} not declared in schema.edges",
                        )
                    )
        else:
            errors.append(ValidationError(change.path, "UNKNOWN_PATH_ROOT", f"unsupported root: {segments[0]!r}"))

    return errors


def _constraint_validate(schema: StateSchema, changes: tuple) -> List[ValidationError]:
    errors: List[ValidationError] = []
    for change in changes:
        segments = parse_path(change.path)
        if segments[0] != "fields":
            continue
        field_id = segments[1]
        if len(segments) == 2 and change.operation == "add":
            _check_field_value_constraints(schema, field_id, change.new_value["value"], change.path, errors)
        elif len(segments) == 3 and segments[2] == "value":
            _check_field_value_constraints(schema, field_id, change.new_value, change.path, errors)
    return errors


def validate_candidate(
    schema: StateSchema, base: CanonicalState, candidate: CandidateDelta
) -> Union[Version, List[ValidationError]]:
    if base.schema_version != schema.schema_version:
        return [
            ValidationError(
                "schema_version",
                "SCHEMA_VERSION_MISMATCH",
                f"base state is schema_version {base.schema_version!r}, "
                f"active schema is {schema.schema_version!r}",
            )
        ]

    schema_errors = _schema_validate(schema, base, candidate.changes)
    if schema_errors:
        return schema_errors

    constraint_errors = _constraint_validate(schema, candidate.changes)
    if constraint_errors:
        return constraint_errors

    new_state = apply_changes(base, candidate.changes)

    provenance = (
        candidate.changes[0].provenance
        if candidate.changes
        else ProvenanceInfo(author="system", transaction_id=candidate.transaction_id, source="no_op")
    )

    return make_version(
        state=new_state,
        parent=candidate.version_from,
        provenance=provenance,
        timestamp=candidate.timestamp,
    )
