# Yield-Weighted Inference Runtime

Part of **Notation Systems' computational instrumentation and evidence infrastructure** for industrial and cyber-physical systems.

[Stack map](https://github.com/giasonpooni/Computational-Instrumentation-Workbench/blob/main/docs/STACK.md) · [Component role and interfaces](docs/STACK_ROLE.md)

An experimental runtime for admission and settlement of inference-token budgets.
It evaluates caller-declared proposals, reuse opportunities and yield observations
against explicit departmental budgets, then returns a decision and receipt.

Short name **YWIR**. The reusable library import is `ywir`.

The package owns the budget decision. Scientific claims and physical decisions
remain with their domain engines. It does not run a language model, measure
semantic quality independently or control machinery.

**In development.** Checked-in results are scoped development samples. See
[development status](docs/DEVELOPMENT.md).

## Decision flow

`decide` classifies the supplied proposal, checks available budget and returns
admission, refusal, composition, evidence-request, reindexing or closure status.
`settle` records the declared outcome and updates budget/yield state. Rank change,
similarity and composability are inputs supplied by the caller, not independently
established scientific properties. A receipt describes that budget decision.

## What is in the first slice

| Responsibility | What the runtime demonstrates |
| --- | --- |
| Department budget | `ledger`, `evidence`, `exploration`, `gauge`. |
| Letters | `ADMIT`, `COMPOSE`, `REQUEST_EVIDENCE`, `REINDEX`, `CLOSE_BUDGET`. |
| Spill taxonomy | Rank-flat, gauge similarity, unglued settlement, meta-precision. |
| Composition store | Caller-declared morphisms; compose instead of reprint. |
| Receipts | Citeable, non-owning. `does_not_claim` is frozen. |

Similarity, rank-delta, and glue are declared observations. This
package does not embed text and does not run a judge model.

## Install and run

Python 3.12 or 3.13. [uv](https://docs.astral.sh/uv/) is the
supported runner; a plain virtual environment also works.

```bash
git clone https://github.com/giasonpooni/Yield-Weighted-Inference-Runtime.git
cd Yield-Weighted-Inference-Runtime
uv run --python 3.13 python examples/quickstart.py
uv run --python 3.13 python examples/mill_token_gate.py
uv run --python 3.13 --with pytest pytest -q
```

Without uv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . pytest
PYTHONPATH=src python examples/quickstart.py
PYTHONPATH=src pytest -q
```

The quickstart writes `results/quickstart.md`.

## Relationship to scientific instruments

YWIR can supply a bounded caller with a spend decision. Domain engines retain
responsibility for their numerical results and dispositions. The example token
gate demonstrates budget logic; it does not establish a hardware connection or
authority to move a machine. This package does not import the scientific kernels.

See [kernel boundary](docs/KERNEL.md) and [stack role](docs/STACK_ROLE.md).

## Scope and limits

Admission on explicit department budgets and declared observations.
No embeddings, no cascade router, no energy accounting as the
objective, no Lyapunov V on the budget dynamics.

See [docs/SCOPE.md](docs/SCOPE.md), [docs/METHODS.md](docs/METHODS.md),
and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

Contributor requirements: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
