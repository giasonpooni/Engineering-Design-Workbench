#!/usr/bin/env python3
"""Emit every local usecase-* presentation render JSON with progress.

Generated wrappers are invoked through the shared template library in this
batch process so the ten owned payload builders are cached; hand-authored
folders still run their own wrappers unchanged.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1]
WORKFLOWS = EXAMPLES / "workflows"
if str(WORKFLOWS) not in sys.path:
    sys.path.insert(0, str(WORKFLOWS))
from usecase_templates import EMIT_FUNCTIONS  # noqa: E402

INDEX = EXAMPLES / "usecase-index.json"


def main() -> int:
    started = time.monotonic()
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    entries = index.get("entries", [])
    failures: list[str] = []
    total = len(entries)
    for number, entry in enumerate(entries, 1):
        folder = EXAMPLES / ("usecase-" + str(entry["slug"]))
        family = str(entry.get("family", ""))
        try:
            if entry.get("generated") and family in EMIT_FUNCTIONS:
                relative = str(entry.get("render_path", ""))
                output = EXAMPLES.parent / relative if relative else folder / "results" / (str(entry["slug"]) + "_render.json")
                EMIT_FUNCTIONS[family](output, entry)
            else:
                emitter = folder / "emit_render.py"
                if not emitter.is_file():
                    raise RuntimeError("missing emit_render.py")
                result = subprocess.run(
                    [sys.executable, str(emitter)],
                    cwd=EXAMPLES.parent,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode:
                    raise RuntimeError(f"exit {result.returncode}: {result.stderr.strip()[-400:]}")
        except Exception as exc:  # keep the batch exhaustive and report all misses
            failures.append(f"{folder.name}: {exc}")
        if number == 1 or number % 250 == 0 or number == total:
            elapsed = time.monotonic() - started
            print(f"progress={number}/{total} emitted={number - len(failures)} failures={len(failures)} elapsed={elapsed:.1f}s", flush=True)
    elapsed = time.monotonic() - started
    print(f"emitted={total - len(failures)} discovered={total} elapsed={elapsed:.2f}s")
    if failures:
        print("failures:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
