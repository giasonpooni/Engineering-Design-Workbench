"""The bounded exact affine checker and its canonical wire format.

This module is deliberately independent of the native Rust/C++ and SP1
implementations.  It is the Python reference used to prepare a statement,
check a candidate before proving, and check the result of a provider.  It
does not create an execution occurrence or claim that the values came from a
measurement.

The exact profile is intentionally small:

* profile ``affine-d256.v1`` and arithmetic ``exact-d256``;
* fixed input denominator ``D = 256`` and output denominator ``D**2``;
* dimensions from 1 through 8 and input numerators bounded by 4096;
* input arrays are signed i64 little-endian, output arrays signed i128
  little-endian, and all flat matrices are row-major;
* the candidate result is checked against an independently evaluated affine
  map.  A residual of zero is a consequence of this exact affine profile; it
  is not a nonlinear optimality or physical-validity claim.

The outer statement binds the operation/profile revision, scale, bound,
canonical input bytes, and candidate output bytes.  Keeping the inner bytes
available is important: commitments identify exactly what the guest checked,
while this module retains the bytes needed to reproduce that check.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Iterable, Mapping, Sequence

from execution.commitments import INPUT_TAG, OUTPUT_TAG, canonical, commit_hex


AFFINE_OPERATION = b"ciw.affine-d256.v1"
AFFINE_PROFILE = b"exact-d256"
AFFINE_INPUT_TAG = "scout.native.affine-d256-input.v1"
AFFINE_OUTPUT_TAG = "scout.native.affine-d256-output.v1"
AFFINE_STATEMENT_TAG = "scout.native.affine-d256-statement.v1"
AFFINE_PROFILE_TAG = "scout.execution.affine-profile.v1"
AFFINE_DESCRIPTOR = (
    b"scout.native.affine-d256-kernel.v1\n"
    b"profile: affine-d256.v1; arithmetic: exact-d256; denominator: 256\n"
    b"input: [rows u32 LE][columns u32 LE][A rows*columns i64 LE row-major]"
    b"[b rows i64 LE][x0 columns i64 LE][delta_x columns i64 LE]\n"
    b"bounds: 1<=rows,columns<=8; every input numerator abs<=4096;"
    b" shifted numerator abs<=8192\n"
    b"output: denominator 65536; baseline, contributions, predicted_delta,"
    b" predicted_output, model_output, residual as i128 LE row-major\n"
    b"faults: 2=malformed, 3=dimensions, 4=numerator bound,"
    b" 5=checked arithmetic, 6=candidate mismatch"
)

DENOMINATOR = 256
OUTPUT_DENOMINATOR = DENOMINATOR * DENOMINATOR
MAX_DIMENSION = 8
MAX_NUMERATOR = 4096
MAX_SHIFTED_NUMERATOR = MAX_NUMERATOR * 2
I64_MIN = -(1 << 63)
I64_MAX = (1 << 63) - 1
I128_MIN = -(1 << 127)
I128_MAX = (1 << 127) - 1


class AffineRefusal(ValueError):
    """The statement is malformed, out of profile, or the candidate fails."""


@dataclass(frozen=True)
class AffineInput:
    """Decoded, validated exact affine input."""

    rows: int
    columns: int
    a_row_major: tuple[int, ...]
    b: tuple[int, ...]
    x0: tuple[int, ...]
    delta_x: tuple[int, ...]


@dataclass(frozen=True)
class AffineOutput:
    """The exact result fields, all represented as integer numerators."""

    rows: int
    columns: int
    baseline_output: tuple[int, ...]
    contributions: tuple[int, ...]
    predicted_delta: tuple[int, ...]
    predicted_output: tuple[int, ...]
    model_output: tuple[int, ...]
    residual: tuple[int, ...]
    denominator: int = OUTPUT_DENOMINATOR


@dataclass(frozen=True)
class AffineChecked:
    """A checked statement and the commitments the proof must bind."""

    statement_bytes: bytes
    input_bytes: bytes
    output_bytes: bytes
    input: AffineInput
    output: AffineOutput
    input_commitment: str
    output_commitment: str
    operation_commitment: str
    profile_commitment: str


def _require_int(value: object, label: str) -> int:
    if type(value) is not int:  # bool is deliberately not an integer here.
        raise AffineRefusal(f"{label} must be an integer")
    return value


def _require_dimension(value: object, label: str) -> int:
    value = _require_int(value, label)
    if not 1 <= value <= MAX_DIMENSION:
        raise AffineRefusal(f"{label} must be between 1 and {MAX_DIMENSION}")
    return value


def _checked_i128(value: int, label: str) -> int:
    if not I128_MIN <= value <= I128_MAX:
        raise AffineRefusal(f"{label} exceeds signed i128")
    return value


def _checked_product(left: int, right: int, label: str) -> int:
    return _checked_i128(left * right, label)


def _checked_sum(values: Iterable[int], label: str) -> int:
    total = 0
    for value in values:
        total = _checked_i128(total + value, label)
    return total


def _validate_numerators(values: Sequence[object], label: str) -> tuple[int, ...]:
    checked = tuple(_require_int(value, f"{label}[{at}]") for at, value in enumerate(values))
    for at, value in enumerate(checked):
        if not I64_MIN <= value <= I64_MAX:
            raise AffineRefusal(f"{label}[{at}] does not fit signed i64")
        if abs(value) > MAX_NUMERATOR:
            raise AffineRefusal(f"{label}[{at}] exceeds numerator bound {MAX_NUMERATOR}")
    return checked


def make_input(
    rows: int,
    columns: int,
    a_row_major: Sequence[int],
    b: Sequence[int],
    x0: Sequence[int],
    delta_x: Sequence[int],
) -> AffineInput:
    """Validate and construct an exact affine input."""

    rows = _require_dimension(rows, "rows")
    columns = _require_dimension(columns, "columns")
    a_row_major = _validate_numerators(a_row_major, "a_row_major")
    b = _validate_numerators(b, "b")
    x0 = _validate_numerators(x0, "x0")
    delta_x = _validate_numerators(delta_x, "delta_x")
    if len(a_row_major) != rows * columns:
        raise AffineRefusal("a_row_major length does not match rows*columns")
    if len(b) != rows or len(x0) != columns or len(delta_x) != columns:
        raise AffineRefusal("affine vector length does not match dimensions")
    for at, (left, right) in enumerate(zip(x0, delta_x)):
        shifted = left + right
        if abs(shifted) > MAX_SHIFTED_NUMERATOR:
            raise AffineRefusal(f"x0+delta_x[{at}] exceeds shifted-state bound")
    return AffineInput(rows, columns, a_row_major, b, x0, delta_x)


def _i64_bytes(values: Sequence[int]) -> bytes:
    try:
        return b"".join(struct.pack("<q", value) for value in values)
    except struct.error as exc:
        raise AffineRefusal(f"input numerator does not fit signed i64: {exc}") from exc


def _i128_bytes(values: Sequence[int]) -> bytes:
    out = bytearray()
    for at, value in enumerate(values):
        _checked_i128(value, f"output[{at}]")
        out.extend(value.to_bytes(16, "little", signed=True))
    return bytes(out)


def encode_input(value: AffineInput) -> bytes:
    """Encode the canonical exact input (not JSON and not a float view)."""

    return canonical(
        AFFINE_INPUT_TAG,
        [
            struct.pack("<I", value.rows),
            struct.pack("<I", value.columns),
            _i64_bytes(value.a_row_major),
            _i64_bytes(value.b),
            _i64_bytes(value.x0),
            _i64_bytes(value.delta_x),
        ],
    )


def encode_output(value: AffineOutput) -> bytes:
    """Encode the canonical candidate/result fields."""

    return canonical(
        AFFINE_OUTPUT_TAG,
        [
            struct.pack("<I", value.rows),
            struct.pack("<I", value.columns),
            _i128_bytes(value.baseline_output),
            _i128_bytes(value.contributions),
            _i128_bytes(value.predicted_delta),
            _i128_bytes(value.predicted_output),
            _i128_bytes(value.model_output),
            _i128_bytes(value.residual),
            struct.pack("<I", value.denominator),
        ],
    )


def output_from_provider(payload: Mapping[str, object]) -> AffineOutput:
    """Convert a typed native-provider JSON result to exact output bytes.

    JSON is only a transport representation here.  Every scalar must already
    be an integer (booleans and binary64 values are rejected), and the
    canonical serializer widens the values to signed i128 little-endian
    fields.  The provider's result remains a result identity; this function
    does not create an execution occurrence or measurement record.
    """

    rows = _require_int(payload.get("rows"), "rows")
    columns = _require_int(payload.get("columns"), "columns")
    denominator = _require_int(payload.get("denominator"), "denominator")

    def values(label: str) -> tuple[int, ...]:
        raw = payload.get(label)
        if not isinstance(raw, (list, tuple)):
            raise AffineRefusal(f"{label} must be an integer array")
        return tuple(_require_int(item, f"{label}[{at}]") for at, item in enumerate(raw))

    return AffineOutput(
        rows=rows,
        columns=columns,
        baseline_output=values("baseline_output"),
        contributions=values("contributions"),
        predicted_delta=values("predicted_delta"),
        predicted_output=values("predicted_output"),
        model_output=values("model_output"),
        residual=values("residual"),
        denominator=denominator,
    )


def statement_from_provider(value: AffineInput, payload: Mapping[str, object]) -> bytes:
    """Serialize a native-provider candidate and run the exact gate.

    A provider can supply only the candidate values.  The independent exact
    checker remains authoritative before those bytes are handed to SP1.
    """

    candidate = output_from_provider(payload)
    statement = encode_statement(value, candidate)
    check_statement(statement)
    return statement


def encode_statement(value: AffineInput, candidate: AffineOutput | None = None) -> bytes:
    """Encode a statement; absent candidate means use the exact reference."""

    result = evaluate(value) if candidate is None else candidate
    input_bytes = encode_input(value)
    output_bytes = encode_output(result)
    return canonical(
        AFFINE_STATEMENT_TAG,
        [
            AFFINE_OPERATION,
            AFFINE_PROFILE,
            struct.pack("<I", DENOMINATOR),
            struct.pack("<I", MAX_NUMERATOR),
            input_bytes,
            output_bytes,
        ],
    )


def evaluate(value: AffineInput) -> AffineOutput:
    """Compute the exact affine candidate independently of any solver."""

    baseline = []
    contributions = []
    predicted_delta = []
    predicted_output = []
    model_output = []
    residual = []
    for row in range(value.rows):
        row_a = value.a_row_major[row * value.columns : (row + 1) * value.columns]
        row_products = [
            _checked_product(row_a[col], value.delta_x[col], "contribution")
            for col in range(value.columns)
        ]
        contributions.extend(row_products)
        baseline_value = _checked_sum(
            [_checked_product(row_a[col], value.x0[col], "baseline") for col in range(value.columns)]
            + [_checked_product(value.b[row], DENOMINATOR, "offset")],
            "baseline",
        )
        delta_value = _checked_sum(row_products, "predicted_delta")
        predicted_value = _checked_i128(baseline_value + delta_value, "predicted_output")
        model_value = _checked_sum(
            [
                _checked_product(row_a[col], value.x0[col] + value.delta_x[col], "model")
                for col in range(value.columns)
            ]
            + [_checked_product(value.b[row], DENOMINATOR, "offset")],
            "model_output",
        )
        baseline.append(baseline_value)
        predicted_delta.append(delta_value)
        predicted_output.append(predicted_value)
        model_output.append(model_value)
        residual.append(_checked_i128(model_value - predicted_value, "residual"))
    return AffineOutput(
        value.rows,
        value.columns,
        tuple(baseline),
        tuple(contributions),
        tuple(predicted_delta),
        tuple(predicted_output),
        tuple(model_output),
        tuple(residual),
    )


def _parse_fields(raw: bytes, tag: str, count: int) -> list[bytes]:
    if len(raw) > 1 << 20:
        raise AffineRefusal("canonical payload exceeds 1 MiB")
    at = 0

    def take(length: int, label: str) -> bytes:
        nonlocal at
        if length < 0 or at + length > len(raw):
            raise AffineRefusal(f"truncated {label}")
        value = raw[at : at + length]
        at += length
        return value

    def u64(label: str) -> int:
        return struct.unpack("<Q", take(8, label))[0]

    tag_bytes = take(u64("tag length"), "tag")
    if tag_bytes != tag.encode():
        raise AffineRefusal(f"unexpected canonical tag {tag_bytes!r}")
    if u64("field count") != count:
        raise AffineRefusal("unexpected canonical field count")
    fields = [take(u64("field length"), f"field {index}") for index in range(count)]
    if at != len(raw):
        raise AffineRefusal("trailing bytes after canonical payload")
    return fields


def _u32(raw: bytes, label: str) -> int:
    if len(raw) != 4:
        raise AffineRefusal(f"{label} must be four bytes")
    return struct.unpack("<I", raw)[0]


def _decode_i64(raw: bytes, count: int, label: str) -> tuple[int, ...]:
    if len(raw) != count * 8:
        raise AffineRefusal(f"{label} has wrong byte length")
    return tuple(struct.unpack_from("<q", raw, at * 8)[0] for at in range(count))


def _decode_i128(raw: bytes, count: int, label: str) -> tuple[int, ...]:
    if len(raw) != count * 16:
        raise AffineRefusal(f"{label} has wrong byte length")
    return tuple(int.from_bytes(raw[at * 16 : (at + 1) * 16], "little", signed=True) for at in range(count))


def decode_input(raw: bytes) -> AffineInput:
    """Decode and validate the canonical input bytes."""

    fields = _parse_fields(raw, AFFINE_INPUT_TAG, 6)
    rows = _require_dimension(_u32(fields[0], "rows"), "rows")
    columns = _require_dimension(_u32(fields[1], "columns"), "columns")
    return make_input(
        rows,
        columns,
        _decode_i64(fields[2], rows * columns, "a_row_major"),
        _decode_i64(fields[3], rows, "b"),
        _decode_i64(fields[4], columns, "x0"),
        _decode_i64(fields[5], columns, "delta_x"),
    )


def decode_output(raw: bytes) -> AffineOutput:
    """Decode output bytes without accepting a derived float representation."""

    fields = _parse_fields(raw, AFFINE_OUTPUT_TAG, 9)
    rows = _require_dimension(_u32(fields[0], "rows"), "rows")
    columns = _require_dimension(_u32(fields[1], "columns"), "columns")
    return AffineOutput(
        rows,
        columns,
        _decode_i128(fields[2], rows, "baseline_output"),
        _decode_i128(fields[3], rows * columns, "contributions"),
        _decode_i128(fields[4], rows, "predicted_delta"),
        _decode_i128(fields[5], rows, "predicted_output"),
        _decode_i128(fields[6], rows, "model_output"),
        _decode_i128(fields[7], rows, "residual"),
        _u32(fields[8], "denominator"),
    )


def check_statement(statement_bytes: bytes) -> AffineChecked:
    """Check a candidate statement and return the exact linked identities."""

    fields = _parse_fields(statement_bytes, AFFINE_STATEMENT_TAG, 6)
    if fields[0] != AFFINE_OPERATION or fields[1] != AFFINE_PROFILE:
        raise AffineRefusal("operation or profile revision is not affine-d256.v1")
    if _u32(fields[2], "scale") != DENOMINATOR:
        raise AffineRefusal("statement scale is not D=256")
    if _u32(fields[3], "bound") != MAX_NUMERATOR:
        raise AffineRefusal("statement numerator bound is not 4096")
    input_value = decode_input(fields[4])
    expected = evaluate(input_value)
    candidate = decode_output(fields[5])
    if candidate != expected:
        raise AffineRefusal("candidate output does not equal the exact affine result")
    input_bytes = bytes(fields[4])
    output_bytes = bytes(fields[5])
    return AffineChecked(
        statement_bytes=bytes(statement_bytes),
        input_bytes=input_bytes,
        output_bytes=output_bytes,
        input=input_value,
        output=candidate,
        input_commitment=commit_hex(INPUT_TAG, [input_bytes]),
        output_commitment=commit_hex(OUTPUT_TAG, [output_bytes]),
        operation_commitment=commit_hex(AFFINE_PROFILE_TAG, [AFFINE_OPERATION]),
        profile_commitment=commit_hex(AFFINE_PROFILE_TAG, [AFFINE_PROFILE]),
    )
