"""Command-line gate for the exact affine statement.

This is intentionally provider-free.  It checks the canonical statement
before a native or SP1 provider is invoked and emits only identities and
declared shape, never a measurement or an execution occurrence.  Use either
``python -m execution.affine_check --statement-hex HEX`` or
``python -m execution.affine_check --statement-file PATH``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .affine import AffineRefusal, check_statement

MAX_STATEMENT_BYTES = 65_536


def _statement(args: argparse.Namespace) -> bytes:
    if (args.statement_hex is None) == (args.statement_file is None):
        raise AffineRefusal("choose exactly one of --statement-hex or --statement-file")
    if args.statement_hex is not None:
        if not args.statement_hex.isascii() or any(
            character not in "0123456789abcdefABCDEF" for character in args.statement_hex
        ):
            raise AffineRefusal("statement hex must contain only ASCII hexadecimal digits")
        if len(args.statement_hex) // 2 > MAX_STATEMENT_BYTES:
            raise AffineRefusal("statement exceeds the 65536-byte gate")
        try:
            return bytes.fromhex(args.statement_hex)
        except ValueError as exc:
            raise AffineRefusal(f"statement hex is invalid: {exc}") from exc
    try:
        path = Path(args.statement_file)
        if path.stat().st_size > MAX_STATEMENT_BYTES:
            raise AffineRefusal("statement exceeds the 65536-byte gate")
        value = path.read_bytes()
        if len(value) > MAX_STATEMENT_BYTES:
            raise AffineRefusal("statement exceeds the 65536-byte gate")
        return value
    except OSError as exc:
        raise AffineRefusal(f"cannot read statement file: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--statement-hex")
    source.add_argument("--statement-file")
    args = parser.parse_args(argv)
    try:
        checked = check_statement(_statement(args))
    except (AffineRefusal, ValueError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "accepted",
                "profile": "affine-d256.v1",
                "arithmetic": "exact-d256",
                "rows": checked.input.rows,
                "columns": checked.input.columns,
                "input_commitment": checked.input_commitment,
                "output_commitment": checked.output_commitment,
                "operation_commitment": checked.operation_commitment,
                "profile_commitment": checked.profile_commitment,
                "statement_bytes": len(checked.statement_bytes),
                "input_bytes": len(checked.input_bytes),
                "output_bytes": len(checked.output_bytes),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
