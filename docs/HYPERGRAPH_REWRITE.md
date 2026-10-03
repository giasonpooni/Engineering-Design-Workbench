# Bounded typed hypergraph rewriting

`net rewrite` is an optional computation model for constructing and auditing
evolving workflow structures. It applies a fixed set of data transformations to
a typed hypergraph and retains the successful transformations, their results,
and their causal dependencies. Numerical engines still calculate model behavior;
the existing execution substrate and containers still run those engines.

A hyperedge can connect several declared nodes. Endpoint kinds, frames and selected
node-port units must match exactly; quantity and relationship units remain
explicit. This lets a graph describe a relationship among several
sensors, models, states or constraints without reducing it to unrelated pairs.
The graph is a declaration of structure, not a running simulation.

## Run and inspect an example

From a checkout with Python 3.11 or newer:

```sh
python -m pip install -e .
net rewrite example --profile thermal --output results/thermal-request.json
net rewrite run results/thermal-request.json --output results/thermal-rewrite.json
net rewrite inspect results/thermal-rewrite.json
net rewrite verify results/thermal-rewrite.json --output results/thermal-verification.json
```

Use fresh output destinations. `example` writes a declared request. `run` applies
its ordered rules. `inspect` checks the retained structure and commitments without
replaying transformations. `verify` explicitly replays the transformations and
issues a fresh verification occurrence; it does not alter the archived record.
An intact content hash alone does not establish that a transformation was valid.

The thermal example replaces one declared thermal zone with two zones and an
interface coupling. It preserves the declared total heat capacity in `J/K` and
declares interface conductance in `W/K`. It does not calculate temperatures,
interface heat flux, or convergence. A numerical thermal model must supply those
calculations and its own qualification.

For bounded alternative paths:

```sh
net rewrite example --profile ensemble --output results/ensemble-request.json
net rewrite explore results/ensemble-request.json --output results/ensemble-exploration.json
net rewrite inspect results/ensemble-exploration.json
net rewrite verify results/ensemble-exploration.json --output results/ensemble-verification.json
```

Exploration uses breadth-first expansion with explicit state, depth and attempt
limits. Example requests allow 32 states, depth 5 and 128 attempts. The maximum
budgets are 64 states, depth 16 and 256 attempts. Each path retains its own identity
and history. Reaching a limit must be visible in the result; an incomplete search
cannot establish that all possible
paths were covered. A refused candidate remains a refused transformation rather
than an accepted graph.

`COMPLETE` means the selected bounded computation finished. `TRUNCATED` reports a
hit budget; `REFUSE` reports a refused ordered transformation. A retained
exploration can include refused candidate attempts and still be complete.
Verification can pass for a truncated history: it validates the retained
computation, not exhaustive coverage. Reports distinguish `derivation_complete`
from `exploration_complete`; the latter is true only for a complete exploration,
so scheduled-run verification reports it as false. CLI commands reporting
`TRUNCATED` or `REFUSE` return a nonzero exit code.

## Supported transformations

Requests are closed JSON declarations. They cannot load arbitrary Python,
invoke a shell, install a provider or dispatch a numerical solver. The trusted
implementation supplies these fixed rule kinds:

| Rule kind | Transformation | Main checks |
| --- | --- | --- |
| `replicate` | Add explicitly named copies of an existing node. | Source identity, unique new identifiers and graph bounds. |
| `parameter` | Change an existing declared parameter within supplied bounds. | Parameter identity, numeric bounds, declared unit and frame. |
| `couple` | Add a typed hyperedge among existing nodes. | Endpoint identity, kind, frame and selected port unit; unique edge identity. |
| `split_thermal` | Replace an uncoupled thermal zone with two zones and an interface. | Source has no incident edges; positive declared capacities preserve their sum; explicit interface conductance. |

The graph supports at most 64 nodes and 128 edges, with at most 32 declared rules.
Serialized limits are 128 KiB per graph, 2 MiB per request and 8 MiB per retained
history. Before each attempt, the engine reserves bounded space for its snapshot
and event; a `bytes` limit can conservatively truncate a computation before the
history reaches 8 MiB. Requests also bound rewrite steps and exploration.
Malformed declarations, missing sources, duplicate identifiers, endpoint
mismatches and violated invariants refuse. There is no implicit unit conversion
or frame transformation.

A request can declare global sum invariants. Those checks apply to the quantities
and units actually declared in the graph. Preserving heat capacity is a structural
check; it is not a proof of energy conservation during a simulated process.
Replication can change a total, so a request that requires the total to remain
constant must supply transformations that satisfy that invariant.

Parameter bounds are authored constraints. Calling a range calibrated requires
separate calibration evidence; an accepted parameter rewrite supplies no such
evidence. The optional qualification reference is retained, not independently
qualified by this engine. Refinement changes representation, and greater
predictive accuracy requires numerical convergence and experimental comparison.

## History, causal dependencies and identity

Graphs, rules and branch paths have content identities. Every successful rewrite
also has fresh execution and result occurrence identities. The record retains
the before and after graph commitments and the selected rule, so a later replay
can check the declared transformation instead of trusting its reported output.

Causal parents identify actual earlier rewrite results whose produced or
overwritten graph objects are read by a later rewrite. These dependencies concern
executed data transformations. They do not establish that a numerical solver ran,
or that its outputs enabled a later scientific execution. Numerical execution
dependencies need their own retained evidence in the existing substrate.

An explicit verification attempt has a fresh verification identity. Content,
operation, execution, result and verification identities remain separate. A
successful rewrite check grants no state admission, release, equipment actuation
or provider execution authority.

Requests use `ciw.hypergraph-request.v1`; retained histories use
`ciw.hypergraph-history.v1`. A request includes the source graph, named rules,
ordered schedule, sum invariants and exploration budgets. Nodes declare an
identifier, kind, frame, named quantities with a value and unit, and named ports
with exact units. Edges declare an identifier, kind, unit, frame, named quantities
and typed endpoints, each with a node identifier, role, kind and selected port.
The selected port's unit must equal the edge's unit. Thermal-zone ports carry `W`;
the thermal interface's conductance parameter carries `W/K`. Verification requires
the retained runtime source identity to match the current implementation. Its
deterministic replay recreates graph checks, refusals and causal edges. Static
inspection checks seals, bounds, record shape, branch ancestry and path identities,
event/state bindings, and that causal parents belong to the branch's ancestry.
It rejects causal parents from sibling branches and does not apply transformations.

## Check two explicit schedules

`orders` applies two supplied sequences to the same source graph and compares
their terminal graphs. Both schedules must contain the same rule multiset. The
ensemble example contains rules `replicate`, `vary_a`, `vary_b` and `couple`.
Its two independent parameter variations can be checked in either order:

```sh
net rewrite orders results/ensemble-request.json \
  --left 'vary_a,vary_b' --right 'vary_b,vary_a' \
  --output results/ensemble-orders.json
```

The report retains both execution histories within an aggregate 8 MiB budget,
with half the budget allotted to each history. An oversized report refuses and
requires a smaller request or schedule; it does not silently truncate the
comparison. The result checks exact,
identifier-sensitive graph equality: node, edge and quantity identities matter.
Two explicitly tested schedules can be equivalent even though their event
histories differ. That result is not a proof of confluence across all schedules,
numerical reproducibility, distributed execution safety, or causal invariance in
Wolfram's sense. A refused schedule does not establish equivalence.

The Python API is in `ciw.hypergraph_rewrite`: `example_request`, `apply`, `run`,
`explore`, `inspect`, `verify` and `compare_orders`. It is independent of numerical
providers. A graph cannot implicitly lower itself into an experiment; any future
adapter must map graph declarations onto existing typed operation contracts and
preserve their qualification and execution boundaries.

## Evaluate the engineering value

Use the same bounded task with and without rewrite declarations. Record:

- Time and manual edits needed to construct an ensemble or refinement.
- Invalid variants rejected before numerical dispatch, with reasons.
- Completeness of source, rule, result and dependency reconstruction.
- Explicitly tested schedule agreements and disagreements.
- Search coverage at the declared limits, and replay time and record size.

These are proposed measurements, not reported improvements. The first useful
criterion is whether the instrument makes construction, adaptation and auditing
better on representative NET workflows.

Hypergraph rewriting is inspired by a general computation model. This instrument
does not validate Wolfram's proposed mappings to fundamental physics, derive
spacetime or gravity, or implement the Ruliad as a finite executable specification.
Those research claims require evidence separate from workflow engineering.

See [workflow algebra](WORKFLOW_ALGEBRA.md) for typed composition and
[scientific workflows](NET_SCIENTIFIC_WORKFLOWS.md) for retained numerical work.
