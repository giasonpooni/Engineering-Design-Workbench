# About NET

## Repository description

Scientific and engineering monorepo for composing instruments, models, simulations, typed workflow graphs and evidence into inspectable, reproducible investigations.

## Project

Notations Systems Terminal (NET) is the programmable scientific and engineering
workbench developed by Notation Systems Inc. It brings modular computational
instruments into a shared repository and connects measurement, state estimation,
physical modelling, simulation, geometry and interactive-world development.

An optional bounded hypergraph rewrite model describes evolving ensembles and
workflow structure through typed replication, parameter variation, coupling and
thermal refinement. Retained rewrite histories, invariant checks, finite branch
exploration and explicit schedule comparisons support construction and auditing.
Numerical models calculate behavior, and the existing substrate governs provider
execution; a structural check does not establish physical accuracy.

NET retains the investigation around those tools: declared inputs and parameters,
execution history, observations, comparisons and explicit verification. Its
Python package remains `ciw`, with `net` providing the composition and control
interface. Domain engines and applications keep their own implementations and
live state.

Evidence, operation, execution and verification identities remain separate.
Scientific claims require the validation appropriate to their scope; shared
software does not grant machinery authority or make game state industrial evidence.

See the [README](../README.md) for entry points, the
[module guide](MONOREPO.md) for repository structure, and
[integration coverage](INTEGRATION_COVERAGE.md) for implemented capabilities
and qualification boundaries. The [rewrite guide](HYPERGRAPH_REWRITE.md) describes
the optional computation model and its limits.
