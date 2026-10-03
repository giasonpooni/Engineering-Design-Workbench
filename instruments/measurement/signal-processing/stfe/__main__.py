# SPDX-License-Identifier: MPL-2.0
"""One JSON request on stdin; one receipt on stdout; refusals on stderr."""

from decimal import Decimal
import json
import math
import sys

from .window import ContractError, canonical, window_mean

MAX_REQUEST_BYTES = 1_048_576


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON object key")
        result[key] = value
    return result


def _constant(value):
    raise ContractError(f"nonfinite JSON constant {value} is unsupported")


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ContractError("JSON number overflows binary64")
    if number == 0.0 and not Decimal(value).is_zero():
        raise ContractError("JSON nonzero number underflows binary64")
    return number


def main() -> int:
    try:
        data = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(data) > MAX_REQUEST_BYTES:
            raise ContractError("request exceeds the 1 MiB input bound")
        request = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                             parse_constant=_constant, parse_float=_float)
        result = window_mean(request)
    except (ValueError, UnicodeError, RecursionError) as exc:
        print(canonical({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
