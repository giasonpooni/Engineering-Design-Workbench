# Parametric Design Terminal documentation

The root [README](../README.md) is the macro entrypoint. This index points to
the page that owns each kind of detail so status and contracts do not drift
across several copies.

The technical name is **Computational Instrumentation Workbench (CIW)**. The
Python distribution is `computational-instrumentation-workbench`; Python code
imports `ciw`, and the command-line entry point is also `ciw`.

## Start here

| Need | Page |
| --- | --- |
| Product scope, operating model and scientific workspace | [Workbench overview](WORKBENCH_OVERVIEW.md) |
| Current provider map and loose-tool collapse rule | [Systems catalog](SYSTEMS_CATALOG.md) |
| Shared profiles, typed composition and evidence boundaries | [Consolidation roadmap](CONSOLIDATION.md) |
| Executable implementation architecture | [Architecture](ARCHITECTURE.md) |
| Python, Julia, native execution and proof responsibilities | [Execution responsibilities](EXECUTION_RESPONSIBILITIES.md) |
| Bounded Rust/C++, JuliaControl and JuMP execution | [Native interoperability](NATIVE_INTEROP.md) |
| Fixed-model chemical kinetics and cross-engine references | [Reaction benchmark](REACTION_BENCHMARK.md) |
| Bounded scalar linearization error with exact reference | [Interval requirement check](INTERVAL_REQUIREMENT.md) |
| Optional providers and the next acceptance experiments | [Provider development sequence](PROVIDER_DEVELOPMENT.md) |
| Multi-provider assembly and local deployment | [Workbench assembly](WORKBENCH_ASSEMBLY.md) |
| Current executable paths and remaining gates | [Integration coverage](INTEGRATION_COVERAGE.md) |
| User-facing instruments and exact commands | [Instrument catalogue](INSTRUMENTS.md) |
| Oscillator demo, inspection and reopen commands | [Oscillator operator card](OSCILLATOR_OPERATOR.md) |
| One worked RMS calculation, retained selection and explicit replay | [Retained RMS lesson](LEARNING.md) |
| Local dependencies, exact expected identities and unperformed checks | [Read-only profile diagnostics](DOCTOR.md) |
| Retained native heading candidates and matrix contributions | [Curved-path study](CURVED_PATH_STUDY.md) |
| Equations, assumptions and bounded what-if previews | [Mathematical model exploration](MODEL_EXPLORATION.md) |

## Contracts and operations

- [Protocol and record identities](PROTOCOL.md)
- [Contract foundations and typed exchange](CONTRACT_FOUNDATIONS.md)
- [State-space transformation contract](STATE_TRANSFORMATIONS.md)
- [Workbench research context](RESEARCH_CONTEXT.md)
- [Generic adapters](ADAPTERS.md)
- [Covariance provenance and replay](COVARIANCE.md)
- [Retained telemetry](TELEMETRY.md) and [shared telemetry](SHARED_TELEMETRY.md)
- [Calibrated observable process](CALIBRATED_OBSERVABLE.md)
- [Identified and budgeted observation](IDENTIFIED_DESIGN.md)
- [Machine manifest workflow](CONTRACT_FOUNDATIONS.md#machine-manifest-operation)
- [Energy-to-accuracy bench](ENERGY_ACCURACY.md)
- [Variational free-energy sensor fusion](VARIATIONAL_FREE_ENERGY.md)
- [Geodesic references](GEODESIC_REFERENCES.md) and [geometry research](GEOMETRY_RESEARCH.md)
- [PLSR](PLSR.md), [registered heat proof](PROVED_HEAT.md), [Julia oscillator](JULIA_OSCILLATOR.md), and [Julia/SP1 direction](JULIA_SP1.md)
- [Exchange inspection](EXCHANGE.md)

## Development and availability

- [Combined integration candidate and acceptance gates](INTEGRATION_CANDIDATE.md)
- [Development guide](DEVELOPMENT.md)
- [Development-window gap audit](DEVELOPMENT_GAPS.md)
- [Provider availability and exact checkout provisioning](PROVIDER_AVAILABILITY.md)
- [Stack map](STACK.md) and [stack role](STACK_ROLE.md)
- [Diagram atlas](DIAGRAMS.md)
- [Quickstart](quickstart.md)
- [Deployment](../deploy/README.md)

Historical audits remain linked from the root for context. They do not override
the current operation catalogue, integration matrix or provider manifests.
