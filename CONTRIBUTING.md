# Contributing

Preserve the implemented admission contract:

- Admission uses declared department budgets and declared observations.
- Keep the closed department tuple, refusal vocabulary, receipt fields and
  constitution constants consistent with the tests and public contracts.
- Receipts retain `does_not_claim`. An admission decision does not certify a
  building, a mathematical certificate or the truth of an answer.
- Gauge spend remains refused. Unglued settlement remains refused without a
  debit. Do not replace refusals with clipped values.
- Keep documentation focused on implemented behavior and explicit limitations.
- Preserve concurrent contributions and do not rewrite shared history.

For library changes, run the default suite and reproducible examples:

```sh
uv run --python 3.13 --dev pytest -q
uv run --python 3.13 python examples/quickstart.py
uv run --python 3.13 python examples/mill_token_gate.py
```

Regenerate result files through their examples; do not hand-edit result values.
