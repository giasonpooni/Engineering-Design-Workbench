# 01 — Emit render JSON (`_render_json.write_render`)

## Helper

```python
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "examples"))
from _render_json import write_render

OUT = Path(__file__).resolve().parent / "results" / "my_sample_render.json"

payload = {
    "schema": "ciw.host-my-sample-render.v1",
    "kind": "my-sample-presentation",
    "source": "HOST_FROM_PUBLISHED_FIXTURES",  # or HOST_SYNTHETIC / …
    "data_source": "…",
    "claim_scope": "computational-integrity-only",
    "may_authorize": False,
    "operation_id": "ciw.existing-kind.v1",  # reuse — do not mint
    "upstream_status": "HOST_FROM_PUBLISHED_FIXTURES",
    "caption": "… explicit non-claims …",
    "selected_case_index": 0,
    "cases": [/* … */],
    "cards": [/* title, status, … */],
    "presentation_only": True,
    "forbidden_claims": [/* … */],
}
write_render(OUT, payload)
```

`write_render` normalizes:

- `may_authorize` → `false`
- `claim_scope` default `computational-integrity-only`
- `presentation_only` default `true`
- `fresh_verifier_occurrence` default `false`
- `status` / `source` / `cards` filled when absent

## Required / expected fields

| Field | Notes |
| --- | --- |
| `schema` / `kind` | Host presentation schema — not a new CIW viewport kind |
| `source` / `data_source` | Evidence seam label |
| `caption` | Always-on non-claims text for the tab |
| `cards` | List (or dict for legacy CSG); empty list ok |
| `cases` / `windows` / `stages` | Teaching rows the Godot tab selects |
| Series for strips | e.g. `residual_series`, `series`, `phase_series` |
| `forbidden_claims` | Explicit denylist echoed in README |

## Run

```sh
python examples/<name>/emit_render.py
# → examples/<name>/results/<name>_render.json
```

Emit must succeed with `python3` and without stack-root / private clones.
