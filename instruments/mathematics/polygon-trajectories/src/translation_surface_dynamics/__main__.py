"""One bounded UTF-8 JSON request on stdin; one canonical result on stdout."""
import json
import sys

from .flow import MAX_REQUEST_BYTES, canonical, run


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Nonfinite JSON value")


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if not raw or len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("Request requires 1..32768 bytes")
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        result = run(request)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        print(f"translation-surface-dynamics: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
