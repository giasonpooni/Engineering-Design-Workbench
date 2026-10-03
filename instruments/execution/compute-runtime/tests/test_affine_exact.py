"""Provider-free goldens for the exact affine/SP1 statement contract."""

from __future__ import annotations

import struct

import pytest

from execution.affine import (
    AFFINE_DESCRIPTOR,
    AFFINE_OPERATION,
    AFFINE_PROFILE,
    DENOMINATOR,
    MAX_NUMERATOR,
    AffineRefusal,
    check_statement,
    encode_statement,
    evaluate,
    make_input,
    statement_from_provider,
)


def golden_input():
    # The visible mathematical values are A=[[2,1,-1],[-1,3,2]], b=[5,-2],
    # x0=[3,4,2], delta=[1/4,-1/2,1/8]. The exact wire carries all of them
    # as numerators over D=256.
    return make_input(
        2,
        3,
        [512, 256, -256, -256, 768, 512],
        [1280, -512],
        [768, 1024, 512],
        [64, -128, 32],
    )


def test_golden_2x3_exact_affine_result():
    value = golden_input()
    output = evaluate(value)
    assert output.baseline_output == (851_968, 720_896)
    assert output.contributions == (32_768, -32_768, -8_192,  -16_384, -98_304, 16_384)
    assert output.predicted_delta == (-8_192, -98_304)
    assert output.predicted_output == (843_776, 622_592)
    assert output.model_output == output.predicted_output
    assert output.residual == (0, 0)
    assert output.denominator == DENOMINATOR * DENOMINATOR


def test_statement_round_trip_and_identity_separation():
    statement = encode_statement(golden_input())
    checked = check_statement(statement)
    assert checked.statement_bytes == statement
    assert checked.input_commitment != checked.output_commitment
    assert checked.operation_commitment != checked.profile_commitment
    assert len(checked.input_commitment) == 64
    assert len(checked.output_commitment) == 64


def test_provider_json_is_widened_to_i128_wire_and_exactly_checked():
    value = golden_input()
    exact = evaluate(value)
    payload = {
        "rows": exact.rows,
        "columns": exact.columns,
        "denominator": exact.denominator,
        "baseline_output": list(exact.baseline_output),
        "contributions": list(exact.contributions),
        "predicted_delta": list(exact.predicted_delta),
        "predicted_output": list(exact.predicted_output),
        "model_output": list(exact.model_output),
        "residual": list(exact.residual),
    }
    statement = statement_from_provider(value, payload)
    assert check_statement(statement).output == exact
    payload["model_output"] = [0, 0]
    with pytest.raises(AffineRefusal, match="exact affine result"):
        statement_from_provider(value, payload)
    payload["model_output"] = list(exact.model_output)
    payload["rows"] = 2.0
    with pytest.raises(AffineRefusal, match="rows must be an integer"):
        statement_from_provider(value, payload)


def test_candidate_output_bytes_are_part_of_the_checked_statement():
    value = golden_input()
    exact = evaluate(value)
    statement = bytearray(encode_statement(value, exact))
    statement[-1] ^= 1
    with pytest.raises(AffineRefusal, match="candidate output|canonical"):
        check_statement(bytes(statement))


def test_affine_guest_is_pending_until_sp1_build_gate_closes():
    """The source guest has a build path, but no unverified registry claim."""

    from execution.build import affine_build_gate, pending_guest_builds
    from execution.guest_registry import GUESTS

    descriptor, backend, crate, name = pending_guest_builds()[0]
    assert descriptor == AFFINE_DESCRIPTOR
    assert (backend, crate, name) == ("sp1", "zk/guest-affine", "sp1-affine")
    assert all(
        entry.get("recipe") != "zk/recipes/sp1-affine.recipe"
        for backends in GUESTS.values()
        for entry in backends.values()
    )
    # In this checkout the external SP1 fork is intentionally absent.  The
    # gate must fail with an actionable refusal rather than writing a hash.
    with pytest.raises(Exception, match="affine SP1 build gate unavailable"):
        affine_build_gate()


@pytest.mark.parametrize(
    "field, replacement",
    [
        ("operation", b"ciw.affine-d256.v0"),
        ("profile", b"binary64"),
    ],
)
def test_operation_and_profile_revisions_are_bound(field, replacement):
    # Rebuild through the public canonical helper rather than mutating a
    # length-prefixed field in place; this also tests that a changed field
    # cannot retain the original statement identity.
    from execution.commitments import canonical
    from execution.affine import encode_input, encode_output

    value = golden_input()
    statement = canonical(
        "scout.native.affine-d256-statement.v1",
        [
            replacement if field == "operation" else AFFINE_OPERATION,
            replacement if field == "profile" else AFFINE_PROFILE,
            struct.pack("<I", DENOMINATOR),
            struct.pack("<I", MAX_NUMERATOR),
            encode_input(value),
            encode_output(evaluate(value)),
        ],
    )
    with pytest.raises(AffineRefusal, match="operation or profile"):
        check_statement(statement)


def test_wrong_row_order_is_rejected_by_exact_values():
    value = golden_input()
    swapped = make_input(
        value.rows,
        value.columns,
        [value.a_row_major[1], value.a_row_major[0], *value.a_row_major[2:]],
        value.b,
        value.x0,
        value.delta_x,
    )
    # The swapped candidate is a valid affine statement for a different
    # matrix, but it is not interchangeable with the retained result.
    checked = check_statement(encode_statement(swapped))
    assert checked.output.predicted_output != evaluate(value).predicted_output


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(rows=0, columns=1, a_row_major=[], b=[], x0=[0], delta_x=[0]),
        dict(rows=1, columns=1, a_row_major=[], b=[0], x0=[0], delta_x=[0]),
        dict(rows=1, columns=1, a_row_major=[MAX_NUMERATOR + 1], b=[0], x0=[0], delta_x=[0]),
    ],
)
def test_profile_bounds_refuse(kwargs):
    with pytest.raises(AffineRefusal):
        make_input(**kwargs)


def test_shifted_state_at_declared_limit_is_accepted():
    value = make_input(
        rows=1,
        columns=1,
        a_row_major=[MAX_NUMERATOR],
        b=[MAX_NUMERATOR],
        x0=[MAX_NUMERATOR],
        delta_x=[MAX_NUMERATOR],
    )
    assert evaluate(value).model_output == (MAX_NUMERATOR * (2 * MAX_NUMERATOR) + MAX_NUMERATOR * DENOMINATOR,)


def test_malformed_canonical_payloads_refuse():
    raw = encode_statement(golden_input())
    with pytest.raises(AffineRefusal):
        check_statement(raw[:-1])
    with pytest.raises(AffineRefusal):
        check_statement(raw + b"trailing")
