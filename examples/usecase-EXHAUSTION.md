# Use-case corpus exhaustion

Generated locally on 2026-09-27; full sample dirs are regenerable and not required in git.

| Metric | Value |
| --- | --- |
| Industries × verbs (product) | 376 × 24 = 9024 |
| Hand-authored extras | 50 |
| Total sample dirs | 9074 |
| Renders | 9074 / 9074 |
| remaining_unused | 0 |
| exhausted | true |

Regenerate:

```bash
python3 examples/workflows/generate_usecase_corpus.py
python3 examples/workflows/emit_all_usecases.py
```

Evidence seam for data access: https://github.com/giasonpooni/Evidence-and-State-Management (UNADMITTED candidate retention only; `canonicalAdmission: false`).
