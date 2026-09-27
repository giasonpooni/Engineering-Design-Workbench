#!/usr/bin/env python3
"""Create a stub teaching-sample folder (README + emit_render.py + results/.gitignore)."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # examples/


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        raise SystemExit("name must contain letters/digits")
    return slug


def scaffold(name: str) -> Path:
    slug = _slug(name)
    dest = ROOT / slug
    if dest.exists():
        raise SystemExit(f"already exists: {dest}")
    results = dest / "results"
    results.mkdir(parents=True)
    (results / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    render_name = slug.replace("-", "_") + "_render.json"
    tab_title = slug.replace("-", " ").title()
    (dest / "README.md").write_text(
        f"""# {slug} (presentation sample)

HOST teaching sample for the Godot **{tab_title}** tab.
**Does not mint a new CIW kind.**

## Non-claims

- Presentation of retained teaching values only.
- `may_authorize` stays false.

## Emit render JSON

```sh
python examples/{slug}/emit_render.py
# → examples/{slug}/results/{render_name}  (gitignored)
```

Missing file → **STALE**.
""",
        encoding="utf-8",
    )
    (dest / "emit_render.py").write_text(
        f'''#!/usr/bin/env python3
"""Emit HOST {slug} teaching presentation for Godot."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_FOR_HELPER = Path(__file__).resolve().parents[2]
if str(REPO_FOR_HELPER / "examples") not in sys.path:
    sys.path.insert(0, str(REPO_FOR_HELPER / "examples"))
from _render_json import write_render as _shared_write_render  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT_DEFAULT = ROOT / "results" / "{render_name}"


def build_payload() -> dict:
    return {{
        "schema": "ciw.host-{slug}-render.v1",
        "kind": "{slug}-presentation",
        "source": "HOST_SYNTHETIC",
        "data_source": "HOST stub — replace with published fixtures / docs language",
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "upstream_status": "HOST_SYNTHETIC",
        "caption": "Presentation of retained teaching values; meshes do not compute.",
        "selected_case_index": 0,
        "cases": [
            {{
                "id": "stub-case",
                "label": "Stub case",
                "status": "LIVE",
                "reason": "scaffold",
                "notes": ["Replace with teaching content"],
            }}
        ],
        "cards": [
            {{"title": "Stub case", "status": "LIVE", "reason": "scaffold"}}
        ],
        "presentation_only": True,
        "forbidden_claims": ["physical calibration", "state admission"],
    }}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args(argv)
    payload = build_payload()
    _shared_write_render(args.output, payload)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
