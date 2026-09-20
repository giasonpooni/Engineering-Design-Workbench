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
`reserve` rechecks admission and holds the requested tokens. `settle` consumes
that reservation once, records the declared outcome and updates budget/yield state. Rank change,
similarity and composability are inputs supplied by the caller, not independently
established scientific properties. A receipt describes that budget decision.

## Reservation API (0.2)

`decide` remains advisory for spending: an `ADMIT` verdict or receipt does not
reserve budget and cannot be settled. Its explicit close/reindex commands retain
their existing meaning, but now refuse while reservations are pending.

```python
from ywir import Proposal, Settlement, open_host, reserve, settle

host = open_host("loop-a", {"ledger": 100})
proposal = Proposal("loop-a", "ledger", 20, expected_rank_delta=1)
reservation = reserve(host, proposal)  # Atomically rechecks and holds 20 tokens.
# Perform the authorized work separately; YWIR does not execute it.
record = settle(host, proposal, Settlement(15, 1, True), reservation=reservation)
```

Migration from 0.1: add `reserve` before work and pass its returned capability
as the `reservation` keyword to `settle`. Calling the old three-argument
`settle` raises `reservation_required`; it never silently creates authorization.
`settle` now returns a `SettlementRecord`. Verdict/receipt identity fields and
snapshot fields are additive; existing `does_not_claim` values remain unchanged.

- A reservation binds the host instance, loop, base, proposal content, decision
  occurrence, department and maximum spend. Identical proposals can be reserved
  twice only when both holds fit; they receive distinct reservation identities.
- Settlement spends at most its admitted cap and releases unused tokens.
  Repeated settlement raises `reservation_consumed`, even for identical retries.
- `cancel(host, reservation)` releases an unused hold and permanently consumes
  that capability. Validation/store failures preserve the pending hold for a
  corrected settlement or cancellation. Cancelling is not a refund for work
  already performed; declared outcomes still require honest external accounting.
- `snapshot` distinguishes unspent `budget`, outstanding `reserved`, and spendable
  `available`. Close/reindex requires settling or cancelling every pending hold.
- Token/budget counts and rank deltas require actual integers, not booleans or
  floats. Yield/similarity values must be finite; similarity lies in `[0, 1]`.

Atomicity is limited to API calls sharing one `HostState` in one Python process,
using its lock. Snapshots are observations, not restorable authorization ledgers.
Opening another host—even with the same loop name—does not recreate authority;
old capabilities are refused. There is no durable restart recovery, shared
cross-process budget, distributed exactly-once guarantee, or provider-billing
transaction. State fields/private ledgers must not be mutated directly or
treated as a security boundary against code running inside the same process.

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
