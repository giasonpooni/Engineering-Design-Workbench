#!/usr/bin/env python3
"""Coverage report builder entrypoint.

The full implementation lives in this repo as the laboratory operator tool.
If you only see this stub on an incomplete push, copy the complete
`_build_coverage_report_impl.py` from a complete checkout or regenerate reports:

  python3 examples/workflows/build_coverage_report.py

Published artifacts (do not invent numbers):
  - examples/workflows/coverage_report.md
  - examples/workflows/coverage_report.json
  - examples/workflows/computational_profiles.json

Freeze: do not create usecase folder 9075. Catalog exhausted ≠ experiments exhausted.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

COMPLETE = Path(__file__).with_name("_build_coverage_report_impl.py")


def main() -> int:
    if COMPLETE.is_file():
        sys.argv[0] = str(COMPLETE)
        runpy.run_path(str(COMPLETE), run_name="__main__")
        return 0
    print(
        "complete builder missing: expected",
        COMPLETE,
        file=sys.stderr,
    )
    print(
        "Reports may already exist beside this file; do not invent coverage counts.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
