# Stable capability semantics and replaceable engines

NST should expose **meaning**, not software topology. This layer therefore sits
above the existing CapabilityRegistry and compiles into the existing
`ciw.experiment.v1` graph. It is not a scheduler, durable workflow service,
plugin loader, evidence store, numerical library, or hardware authority.

## Categorical interpretation

The implementation uses category theory as a design discipline without claiming
formal categorical results that have not been proved.

- typed port specifications are the **objects**;
- versioned semantic capabilities are **morphisms**;
- an engine lowering is **functor-like** because it maps a semantic morphism to
  a concrete operation while preserving its declared input/output objects;
- a retained comparison between two engines is a **finite comparison witness**,
  not automatically a natural transformation.

The last distinction matters. Showing that a Julia and C++ implementation agree
on ten retained inputs does not prove a naturality law over every object and arrow.

No monad abstraction is required by this contract. Existing Session/results
already carry execution context, refusals and retention. Likewise measure theory
is not used as a synonym for data validation: schemas, units, frames, clocks and
shapes remain explicit engineering contracts.

## Headless by default

Compute morphisms can resolve only to bound headless implementations. A
representation morphism requires an explicit inspection request. Thus agents can
run large graphs using structured observations/artifacts and request pixels only
when needed.

This preserves:

`execution is headless by default; visualization is demand-driven`.

## Execution profiles are routing hints

The catalog recognizes:

- orchestration
- scientific
- coordination
- systems
- native_edge
- hardware
- external

These are policy labels, not claims that a language is incapable of other work.
A Python operation can be native/high-performance through extensions, Julia can
be AOT-deployed in some forms, and C++ can own high-level code. The operator
chooses concrete lowerings.

Typical **non-binding** mappings may be:

| Runtime family | Often useful profiles |
| --- | --- |
| Python | orchestration, scientific |
| Julia | scientific |
| Rust | systems, native_edge |
| C++/CUDA | native_edge, hardware |
| Mojo | scientific/native_edge candidate |
| Elixir/BEAM | coordination candidate |
| Zig | systems/native-edge build candidate |
| Taichi | scientific/native_edge specialist |
| Chisel/SpinalHDL/SystemVerilog/HLS | hardware specialist |

NST does not add those runtimes merely because their family names can appear in
metadata.

## Why the bonus-language list remains optional

Mojo is promising for heterogeneous CPU/GPU code and Python interoperability but
its Python-to-Mojo binding surface is still evolving. Elixir/BEAM supervision may
be useful if distributed durable coordination becomes a measured requirement; it
does not replace the current local NET controller by default. Zig's build system
and C interoperability are useful, but Zig is not treated as a memory-safety
firewall equivalent to Rust.

Taichi remains a specialist parallel-compute engine. Hardware DSLs such as Chisel
and SpinalHDL belong behind future `hardware.*` capabilities. PYNQ can be a
future FPGA/overlay execution adapter, but Apache Arrow/zero-copy behavior would
need its own explicit memory contract rather than being inferred from PYNQ.

Likewise Temporal, Arrow, gRPC, ROS2 and Zenoh are possible implementation
substrates—not architectural requirements. Adopt them only after a concrete
workload establishes the missing contract.

## Agent boundary

The semantic MCP profile has only:

- `net_semantic_catalog`
- `net_semantic_compile`

Agents name semantic capability IDs and resources. They cannot name provider
paths, images, binaries or engines in the work graph. The operator-owned registry
chooses the eligible bound lowering deterministically. Compilation explicitly
does **not** authorize execution.

Example:

```text
mandate
  ↓
analysis.statistics.v1
  ↓
analysis.spectrum.v1
  ↓
ordinary ciw.experiment.v1
```

The ordinary NET execution path remains unchanged beneath the compilation
receipt.

## Hardware direction

Future capabilities should be stable meanings such as:

```text
hardware.hdl.build.v1
hardware.hdl.simulate.v1
hardware.fpga.program.v1
sensor.acquire.v1
signal.filter.v1
state.estimate.v1
```

with Chisel, SpinalHDL, Amaranth, HLS, embedded Rust, C/C++, PYNQ, ROS2 or Zenoh
appearing as replaceable implementations only when explicitly qualified.

Physical actuation requires additional effect/authority contracts. A successful
simulation or bitstream build never implies permission to command equipment.

## First installed catalog

V1 deliberately binds only the already-qualified built-in statistics and
periodogram operations. The point is to qualify the semantic compiler itself
before registering Ceres, JuliaIntervals, DSP, GIS, game workcells, Taichi or
future hardware providers.

Run:

```sh
net semantic catalog
net semantic demo --output-dir results/semantic-demo
python -m ciw.semantic_cli serve
```

The demo writes a semantic graph, compilation receipt and ordinary NET experiment.
It performs no provider execution.
