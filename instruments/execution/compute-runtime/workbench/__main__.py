"""`python -m workbench` -- launches the interactive REPL."""

from __future__ import annotations

import sys

from workbench.cli import main

if __name__ == "__main__":
    sys.exit(main())
