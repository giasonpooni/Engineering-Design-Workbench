# Kernel

Import `ywir`. Catalog short name **YWIR**.

The kernel owns admission. Plants own world-claims.

1. `decide` returns an advisory letter and citeable, non-owning receipt.
2. `reserve` rechecks a spend proposal and holds its admitted cap for this
   host/loop/base, returning a one-use reservation.
3. The caller performs work separately; YWIR does not execute a model.
4. `settle(..., reservation=...)` consumes the hold, debits actual spend, updates
   yield and records a new morphism. `cancel` releases an unused hold instead.

Proposal identity names content. Decision, reservation and settlement identities
name distinct occurrences. A settlement record retains its admitted base and cap.
Receipts and snapshots cannot substitute for a pending reservation. Replay raises
`reservation_consumed`; pending holds prevent close/reindex. Atomicity and replay
protection are process-local, not persistent or distributed.

`A`, `V`, IFC belief, and mill kinematics are inputs to *other*
kernels. This repository does not form them.

Similarity, rank-delta, glue, and plant refuses are **declared**.
The kernel does not embed the burst. A missing glue on settlement
is `H1_NO_GLUE`, not a quality footnote.

Do not import this package into `gat` or `lyapunov`. Consumers pin a
git SHA and cite receipts. They do not share a digest.
