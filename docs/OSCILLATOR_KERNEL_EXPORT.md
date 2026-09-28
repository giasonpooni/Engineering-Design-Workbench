# Julia-authored oscillator kernel: first native export slice

This increment adds one bounded Julia arithmetic exporter, a checked C ABI,
Python and Rust bindings, and a native acceptance command. It is not a general
Julia-to-C/Python/Rust transpiler, an exported ODE solver, or a new runtime.

The existing Julia Tsit5 provider, analytical oscillator, CIW session/record
identities, SCR execution foundation and proof gates are unchanged. The native
RHS is an explicitly bound `backend` operation named `oscillator.rhs-native.v1`.
Its saved payload is recognized without loading a native library. The default
operation registry does not discover executables or enable the provider.

## What is exported

```text
runtimes/julia-oscillator-kernel/oscillator.jl
  -> Julia parser + bounded arithmetic check (export.jl)
  -> generated C inside the checked abi.c.in wrapper
  -> libciw_oscillator_kernel.so
       -> Python ctypes binding
       -> Rust C-ABI binding
       -> existing CIW execution/result envelopes
```

The source defines `oscillator_rhs(q, v, gamma, omega)` returning `(dq, dv)`:

```text
dq = v
dv = -2 gamma v - omega^2 q
```

The initial source subset is one short-form definition returning two scalar
expressions. It permits the four named arguments, finite Float64 literals,
addition, subtraction and multiplication. Other calls, macros, assignments,
indexing, integer literals, statement blocks, reflection and runtime dispatch
are refused. Input types are Float64 at evaluation; no algebraic rewriting or
precision reduction is performed. This small parser/emitter does not introduce
a general intermediate representation or add Symbolics as a dependency. A
future backend may use Symbolics through a separately qualified build profile.

`export.jl` parses before emitting. Its reference mode evaluates only the checked
arithmetic definition on bounded Float64 input rows. It is not a sandbox for
arbitrary Julia programs. The exporter uses Julia's standard library only;
it does not create or modify the existing Tsit5 Project/Manifest.

## ABI and ownership

`ciw_oscillator_rhs_v1` takes three buffers and their lengths: state `[q, v]`,
parameters `[gamma, omega]`, and two output scalars. State and output units are
`[m, m/s]` and `[m/s, m/s^2]`; gamma is in `1/s` and omega in `rad/s`.

The first profile accepts finite `|q|, |v| <= 1e6`,
`epsilon(Float64) <= omega <= 20`, and `0 <= gamma <= omega/2`.
These are numerical interface bounds, not physical validity or initial-condition
bounds for the existing Tsit5 profile. Mass belongs to derived energy and is not
an RHS argument. Compilation requires binary64, round-to-nearest, no fast-math
and disabled floating-point contraction. Cross-platform bitwise equality and
subnormal-environment equivalence are not asserted.

Status codes are 0 success, 1 null pointer, 2 wrong buffer length, 3 nonfinite
input, 4 profile violation, 5 nonfinite output, and 6 unsupported rounding mode.
A refusal leaves the output untouched. All inputs are read before output writes,
so input/output aliasing is supported. Callers must still provide valid aligned
storage; a length field cannot validate an arbitrary native pointer.

The library allocates no memory and retains no state or pointers. Integration
belongs to the selected caller, never simultaneously to this library and an
engine. The RK4 routine in the acceptance script is a test integrator, not a
replacement for Tsit5, engine physics or a persistent simulation instance.

## Build and qualify

Install the candidate NET package in the environment used for testing. The gate
imports that installed package; it does not prepend this checkout to Python's
module path. Bind actual executables explicitly. The first build recipe is
Linux/GCC with Rust and a declared Julia version (default `1.10.12`):

```sh
python scripts/check_oscillator_kernel.py \
  --julia /absolute/path/to/julia \
  --cc /absolute/path/to/gcc \
  --rustc /absolute/path/to/rustc \
  --julia-session /absolute/path/to/retained-julia-session.json \
  --output-dir results/oscillator-kernel-001
```

Use a new output directory for every occurrence. Obtain the retained Julia
session with the existing [Julia oscillator workflow](JULIA_OSCILLATOR.md).
Changing `--julia-version` selects another exporter build profile; it does not
change the existing provider's allowed runtime versions or environment pins.
Rust must support `unsafe extern` blocks; record the actual compiler version
from the gate rather than assuming source presence establishes compatibility.

The command requires genuine Julia generation and Rust compilation/execution.
There is no fallback to the unit-test C fixture. Its required comparisons are:

| Gate | Required evidence |
| --- | --- |
| Julia export | Real exporter self-tests and C emission from the retained Julia source. |
| Python / Julia | 1,024 identical input rows through C/ctypes and Julia evaluation. |
| Rust / Julia | Rust ABI tests and the same 1,024 rows through the linked native library. |
| Independent analytical path | Native-RHS RK4 trajectories compared with the existing CIW analytical oracle in default, mixed-state, undamped and high-frequency cases. |
| Existing CIW records | Fresh execution/result IDs, comparison of repeat outputs, retained seals, and saved-payload validation while native loading is forbidden. |
| Retained Tsit5 path | Validate a supplied Julia session with its existing validator, match the original model/grid, then compare native-RHS trajectories with its retained output. |

Omitting the retained Julia session leaves that gate `not_run`, sets overall
status `incomplete`, and exits nonzero. Missing tools or failed comparisons also
exit nonzero. A comparison with a retained session does not claim a new Tsit5
execution or prove that an untrusted uploaded record was physically measured.

The output retains source snapshots, generated C, compiler commands and logs,
compiler/executable digests, target/flags, binary identity, input/output rows,
trajectories, existing CIW envelopes and a separate build/test report. These are
qualification artifacts, not a second scientific evidence store. The result
remains `not_verified`; the gate does not assign a CIW verification identity,
admit evidence, produce an SP1 proof or authorize hardware.

## Bind through the existing operation registry

Host code explicitly constructs `OscillatorKernel` with a library path and the
expected library/source SHA-256 values from its trusted build. Register
`operation(kernel)` in the existing `OperationRegistry`. The existing runner
then consumes a structurally valid run with q/v channels and the
`oscillator-state` frame. Parameters declare `gamma_s_inv`, `omega_0_rad_s`,
`channel: "q"` and the captured half-open `interval_s`.

Saved records never select library paths, run compilers, import providers, or
register validators. Offline payload validation checks shape, units, frame,
sampling, model bindings and claim scope; it does not recompute the RHS. Artifact
hashes detect drift and link build evidence, not compiler correctness or safety
of an untrusted native library. Execute only explicitly trusted builds.

The Rust file supplies a safe wrapper and standalone bounded TSV probe without
Cargo dependencies. It is not yet a Bevy plugin. C++ and Godot adapters remain
a later increment, after the native gate is qualified.

## Validation status of this change

Local Linux/GCC/Python validation: **51 tests passed**. This includes a deliberately
hand-lowered C ABI fixture, Decimal RHS comparisons, independent matrix-exponential
trajectory comparisons, timestep convergence, unchanged-output refusals, aliasing,
concurrent calls, artifact drift, existing CIW records, and provider-free restore.
The original CIW runner, registry, core records and adapter protocol used locally
were checked byte-for-byte against their base Git blob identities.

Those tests do **not** establish genuine Julia export or Rust execution. Julia
and Rust were unavailable in the execution container, and direct downloads were
blocked. The native exporter/Rust/Tsit5 acceptance gates, installed-wheel gate,
full repository regression suite, and non-Linux qualification remain open.
No default registry entry, provider pin, license, branch protection, proof gate,
existing solver or physical claim is changed.
