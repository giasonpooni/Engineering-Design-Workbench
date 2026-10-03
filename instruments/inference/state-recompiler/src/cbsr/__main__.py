"""One request on stdin, one receipt on stdout. Refusal is not an accepted solve."""

import json
import math
import sys

from .affine import ContractError, reconcile_affine_exact


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_float(literal):
    value = float(literal)
    nonzero_mantissa = any(character in "123456789" for character in literal.lower().partition("e")[0])
    if not math.isfinite(value):
        raise ContractError("JSON number overflows finite binary64")
    if value == 0 and nonzero_mantissa:
        raise ContractError("nonzero JSON number underflows binary64")
    return value


def _reject_constant(literal):
    raise ContractError(f"nonfinite JSON constant is unsupported: {literal}")


def main() -> int:
    try:
        raw = sys.stdin.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ContractError("request exceeds 1 MiB")
        request = json.loads(raw, object_pairs_hook=_no_duplicate_keys,
                             parse_float=_parse_float, parse_constant=_reject_constant)
        result = reconcile_affine_exact(request)
    except (ValueError, RecursionError) as exc:
        print(json.dumps({"error": "invalid_contract", "message": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result["status"] == "accepted" else 3


if __name__ == "__main__":
    raise SystemExit(main())
