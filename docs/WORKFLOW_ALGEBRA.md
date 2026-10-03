# Typed workflow algebra on the existing NET substrate

NET now has an optional, bounded composition compiler. It emits the original
`ciw.experiment.v1` and `ciw.production-plan.v1` records. The original Session,
operation/capability registries, graph runner, production controller, gates,
container policy and title-owned calculations remain the execution machinery.
There is no second scheduler, numerical library, proof authority or state store.

The development base is PR76, `6861862c9ea0e8280e3e0372d3d0a984b62cecb9`.
The separate DSP/GIS branches and multilingual buffer-interface compiler are not
silently merged, replaced or reimplemented by this increment.

## Run a complete example

```sh
python -m pip install -e '.[dev]'
net compose example --output-dir results/workflow-orders
net compose check results/workflow-orders/graph.json
net compose compile results/workflow-orders/graph.json --output results/graph-compiled.json
net compose inspect results/graph-compiled.json
net compose demo --output-dir results/workflow-demo
```

Use fresh destinations. `example`, `check`, `compile` and `inspect` dispatch no
operations. The explicitly selected CLI demo uses the existing synthetic
oscillator recording and installed statistics/periodogram providers. It executes
two independent analysis nodes, then the existing three-execution production
example: a failed sample-count requirement, a predeclared parameter correction,
and an unblocked dependent job. These are synthetic analyses, not physical tests.

The CLI profile is intentionally closed. Saved JSON cannot import Python, choose
a shell, select an image, install a provider, bind credentials or supply a gate.
Hosts extend it via the Python API by explicitly supplying their existing
CapabilityRegistry, operation declarations, fixed job templates and Gate objects.

## Two meanings of composition, deliberately not conflated

### 1. Typed dataflow inside an experiment

`workflow_algebra` exposes `call`, `sequence`, `parallel`, `identity` and `permute`.
A wire refines an existing `control_plane.Port` with optional declared clock and
meaning tags. Schema, unit, frame, clock, meaning and interface arity must match
exactly. None means unspecified, not a wildcard accepting a known value.

```python
from ciw import workflow_algebra as A

# These IDs must already exist in the operator's CapabilityRegistry.
# op_declarations are issued by that operator, not by a candidate's JSON.
expression = A.sequence(
    A.parallel(A.call("left_source", "example.source.v1", {"channel": "left"}),
               A.call("right_source", "example.source.v1", {"channel": "right"})),
    A.parallel(A.call("left_filter", "example.filter.v1"),
               A.call("right_filter", "example.filter.v1")),
)
# Example IDs above illustrate the API; they are not installed default providers.
compiled = A.compile_graph(expression, registry, op_declarations, live_grant,
                           experiment_id="paired-analysis", model_id="declared-model.v1")
report = A.run_compiled(session, compiled, registry, op_declarations, live_grant)
```

An operation's input/output port names are sorted to form its ordered interface;
output selectors still come from the original registered contract. `sequence`
connects outputs to the next inputs. `parallel` places interfaces side by side
and partitions wires; it does not implicitly copy a state handle. `permute`
reorders every wire exactly once. Explicit copy/discard operations, when needed,
must have their own registered and qualified contracts; they are not inferred.
`identity` and `permute` are structural and produce no engine invocation, source
record, fake result or new execution identity.

`normal_form(...)` can inspect an open diagram. A runnable experiment must close
all inputs using explicit source operations and contain at least one operation.
The compiler does not synthesize source telemetry or execute an empty identity.

The normal form preserves stable call labels and exact output selectors. It
normalizes wiring, not arbitrary graph isomorphism or scientific equivalence.
Within the accepted domain, tests check serial/parallel associativity, identity,
permutation inversion and dataflow interchange. Authored expression receipts
remain different even when their lowered experiment records are identical.
Equal numerical outputs do not erase distinct call/derivation identities.

### 2. Checked production-stage ordering

`workflow_production` exposes `stage` and `bounded_retry`; they use the same
`sequence`, `parallel` and empty `identity` syntax but compile to job barriers.
Every selected stage comes from an operator-fixed existing production job,
including its immutable acceptance checks. The expression names that stage; it
cannot replace its check, parameters, provider or permission requirement.

```python
from ciw.workflow_algebra import sequence, parallel
from ciw.workflow_production import stage, bounded_retry

expression = sequence(
    parallel(stage("terrain"), stage("mechanics")),
    stage("integration"),
    stage("package"),
)
# The named stages must be explicitly supplied as existing job templates.
```

Series here means every terminal job on the left must be accepted before roots
on the right are eligible. Parallel creates no extra dependencies. It is NOT a
claim that stage outputs are automatically passed into the next job: actual
cross-job artifact handoffs remain in the specialist provider, such as the
existing `CellOperations` capture-to-container adapter.

This distinction is observable: a global barrier between `(a parallel b)` and
`(c parallel d)` is NOT interchangeable with two independent `a;c` and `b;d`
lanes. A regression protects against optimizing that acceptance barrier away.
Do not call these two dependency graphs the same categorical wiring diagram.

Mandatory prerequisites in the original templates must be ancestors in the
compiled expression. Listing package before tests, or placing them in parallel,
refuses before dispatch. All original checks must still pass at runtime;
well-typed source cannot prove a provider honored its advertised output type.

## Effects, permissions and qualification references

An operator issues annotations with `declare(registry, operation_id, ...)` or
`declare_stage(job, ...)`. Each pins the exact original contract/template digest.
The compiler rejects source/runtime-port/template drift instead of using stale
bindings. The declarations remain separate from model-authored expressions.

Effects contain logical `reads`, `writes` and `unknown` fields. Unknown is the
default; omitted annotations are never interpreted as pure. Two unordered nodes
cannot overlap in write/write or read/write footprints. Hierarchical names such
as `world` and `world/material` overlap; `cell/a` and `cell/b` do not. Read/read
sharing is allowed. The checker considers all unordered nodes, not only siblings
in an explicit parallel term. It never silently inserts an order to make a
conflicting diagram pass.

These are trusted operator declarations, NOT filesystem/alias analysis, CPU
scheduling or sandbox enforcement. Incorrect footprints can defeat a static
independence assertion. Containers retain their actual OS enforcement separately.
Network/hardware/shared-state effects must be reflected in the declared footprint;
this increment does not derive them from arbitrary code.

Permissions are a set of distinct required capabilities. Possession of `release`
does not imply `execute`, and `build` does not imply `package`. Live execution
rechecks current declarations and the exact live grant; a saved compilation
cannot award itself permissions. Changed grants require explicit recompilation.

Qualification requirements are exact operator-supplied scope-to-content-reference
matches. They prevent an absent/stale reference from being silently inherited;
they do not validate a qualification report's scientific truth or authenticate its
issuer. Matching clock labels do not synchronize clocks. Matching meaning labels
do not prove calibration, covariance assumptions or applicability to a new domain.
Those claims still belong to specialist payload validators and evidence reviews.
The extra clock/meaning refinements are static declarations in this version;
runtime schema/unit/frame validation remains the existing Port/payload boundary.

## Bounded feedback, without pretending all feedback is a trace

```python
expression = sequence(
    bounded_retry("select-window", max_attempts=2),
    stage("dependent-analysis"),
)
```

This selects a prefix of already declared parameter variants. The original
production controller tries the next variant only after a definite failed check.
Missing evidence holds; refusal/error does not retry blindly. No dynamic source
rewrite, recursive agent spawning, algebraic fixed point, infinite loop or generic
categorical trace is implemented. The initial source/feedback observations remain
owned by the existing run records.

Every declared variant, even one beyond the selected prefix, must meet the
original shape/budget constraints. The new compiler additionally fixes experiment-
global parameters across variants; only declared node parameters may change.
Changing model, routes, graph edges, check policy or code revision requires a new
operator-issued template, not an automatic promotion of a candidate.

Syntax limits are 256 terms, nesting depth 10 and 64 ports/call labels/stage names.
Existing graph limits (64 nodes), production limits (64 jobs, 3 attempts/job,
256 reserved operations), and operator execution budgets remain unchanged.
A bounded input language is not a claim of unrestricted categorical closure.

## Actual workcell attachment

The existing `WorkcellHost.build` now calls `compile_workcell` for its installed
build/test/package sequence. This is not an extra planner inside the engine.
Each stage declares its existing required permission and shared cell-state effect;
its original prerequisites and fixed gate stay bound. Omitting the package grant
produces the original two-stage route, not a blocked unauthorized package job.

The compiler output is tested against the original production-plan construction
for exact equality. Execution still goes through the unchanged production runner,
Session, Docker adapter and title-owned scripts. The slot retains
`compilation-ATTEMPT.json` BEFORE native execution, including on subsequent
failure/hold. An ambiguous interrupted attempt still does not rerun automatically.

```sh
net compose inspect results/cell/compilation-ATTEMPT.json
net compose inspect-slot results/cell
```

`inspect-slot` freezes a bounded copy once using original file-inventory/read
helpers, recompiles each receipt, compares its plan with the exact native plan,
and rechecks original workcell outcomes. No engine, container or provider starts.
Its limits are the existing 1024-file/32-MiB snapshot budget and 2-MiB/file limit.
Interrupted/missing native histories refuse full audit; a receipt alone is not a
completed run. On-disk content hashes provide consistency, not signature-backed
source identity. All claims retain null formal verification ID and no ESM admission
or release authority. New receipts are specification evidence, not competing
execution/result identities.

## Qualification and remaining work

The dedicated compiler workflow runs the new law, type/effect/grant, tamper,
original Session wiring, declared retry and CLI tests on Linux and Windows, then
repeats them from an installed package outside the source checkout. The existing
native prop and title-smith workcell workflows remain the Docker/Godot tests;
they additionally recompile receipts and check native-plan correspondence.
Test-double workcells are labelled fixtures, not native isolation evidence.
Only the actual workflow reports establish which revision passed those tests.

Parallel terms are declarations of independence; the current runtime STILL runs
sequentially. There is no distributed scheduler, lease service, automatic effect
inference, temporal logic model checker, generic feedback engine, formal proof
assistant or machine-checked categorical semantics in this increment. Tests of
algebra laws are executable regression evidence, not a mathematical completeness
proof. Future scheduling/streaming extensions must retain the existing contracts.

## Mathematical references

The series/parallel wiring approach is motivated by Patterson, Spivak and Vagner,
*Wiring diagrams as normal forms for computing in symmetric monoidal categories*:
https://arxiv.org/abs/2101.12046 . For the broader applied-category context, Fong
and Spivak, *Seven Sketches in Compositionality*:
https://arxiv.org/abs/1803.05316 . These motivate the small front end, not a new
runtime dependency. No Catlab/MLIR framework is installed or copied by this work.
