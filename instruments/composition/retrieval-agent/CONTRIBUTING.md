# Contributing

Preserve the public schematic and adapter contracts:

- The function graph and factor graph are the canonical store; USD is a
  projection.
- Preserve typed edges and explicit eligibility/refusal annotations. Do not
  infer edges from names, proximity or render geometry.
- Keep companion kernels behind their explicit adapters. Missing kernels remain
  `NOT_CHECKED`; fixture matrices do not establish PLSR eligibility.
- Do not change a refusal into a successful sample or a physical claim.
- Keep documentation limited to implemented behavior and explicit limitations.
- Preserve concurrent contributions and do not rewrite shared history.

For library changes, run the default tests and quickstart:

```sh
uv run --python 3.13 --dev pytest -q
uv run --python 3.13 python examples/quickstart.py
```

For companion-adapter changes, also run the documented live-kernel tests with
all pinned dependencies installed:

```sh
uv run --python 3.13 --dev --extra kernels pytest -q -m live
```
