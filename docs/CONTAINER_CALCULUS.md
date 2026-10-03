# Container / Experiment Calculus V1

This formalizes a recurring NET abstraction without claiming a new physical
theory.

A computational container is treated as:

```text
Boundary + state partition + semantic operators
+ resource capacity + evidence policy + telemetry policy
```

rather than as synonymous with Docker.

The layer sits **above runtimes and below workloads**. Existing Docker workcells,
local processes, HPC jobs, cloud jobs and external simulators can all be
occurrences of one container spec.

This implements the engineering half of the container/modulator research idea:
first define measurable boundaries and telemetry, then ask whether deeper recurring
laws survive heterogeneous workloads. The speculative mathematical theory remains
separate from the infrastructure intended to test it.

## V1 objects

`ciw.container-spec.v1`
- internal / boundary / external state partition;
- typed admitted/emitted ports;
- semantic operations;
- explicit effect/network/hardware/state-admission/release limits;
- resource envelope;
- evidence retention policy;
- telemetry requirements.

`ciw.container-composition.v1`
- FLOW relations between exact schema/unit/frame-compatible ports;
- NESTED relations as an acyclic single-parent hierarchy.

`ciw.container-telemetry.v1`
- concrete backend identity;
- transport byte/item accounting;
- wall/CPU/GPU/RAM/storage/network/energy/cost/human metrics;
- residuals;
- workload-defined uncertainty proxies;
- retained-state and verified-output refs.

The spec itself never binds a runtime or authorizes execution.

## Information-theory boundary

Transport bytes are **not** Shannon information.

If a workload has a defensible uncertainty measure, it may explicitly report a
proxy such as:

```text
kind: POSTERIOR_ENTROPY
before: 5 bits
after: 2 bits
method_id: discrete-posterior-v1
```

Only then does NET report a 3-bit reduction under that exact method.

Other supported proxies include hypothesis count, feasible volume and CUSTOM.
They are never automatically collapsed into a universal information score.

## Adaptive multi-scale precision

This calculus also supports the Notation Systems methodological rule:

> use the cheapest representation with sufficient fidelity for the decision,
> rather than maximizing precision everywhere.

Scale transitions—quantum→atomistic→mesoscale→continuum→component→machine→factory,
for example—remain explicit operations between typed container boundaries.
V1 does not assume one representation spans all scales and does not claim that
greater precision is intrinsically better.

The experiment to run is whether a lower-cost representation preserves the
required outputs/invariants/epistemic distinctions and verification.

## Backend principle

`LOCAL | CONTAINER | HPC | CLOUD | EXTERNAL` are backend classes.

A cloud provider can later implement a backend adapter, but it must not become
the architecture.

## Research telemetry

The software records enough to test claims such as:

- bounded hierarchy vs loose composition;
- useful verified output per resource;
- uncertainty/hypothesis reduction per cost;
- retained-state formation;
- residual/failure behavior;
- whether recurring boundary structures survive across DSP, state estimation,
  GIS, simulation, agents and game production.

The contract explicitly says:

```text
physical_theory_established = false
fep_interpretation = false
shannon_information_inferred_from_bytes = false
```

A future mathematical theory, if any, must be supported by the accumulated
experiments rather than inferred from the software vocabulary.
