# Experiment scope

FSRT estimates fluid-network state and tests agreement with declared physical balances.
The [quickstart](USAGE.md) runs a two-tank reconciliation example using synthetic values
and no network access.

FSRT does not import GAT or `flat_torus`, emit RCI or torus commitments, run in an SP1
guest, or participate in the CSE experiment harness. The optional covariance adapter uses
[pinned JSPT](JSPT_PIN.md); fluid declarations and evidence remain in this repository.
