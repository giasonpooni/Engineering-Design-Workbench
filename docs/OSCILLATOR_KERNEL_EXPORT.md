# Julia-authored oscillator kernel: first native export slice

This increment adds one bounded Julia arithmetic exporter, a checked C ABI,
Python and Rust bindings, and a native acceptance command. It is not a general
Julia-to-C/Python/Rust transpiler, an exported ODE solver, or a new runtime.

The existing Julia Tsit5 solver, analytical oscillator, CIW session/record
identities, SCR execution foundation and proof gates are unchanged. Qualification
added a missing Julia package entry file, described below, without changing the
solver worker or its Project/Manifest. The native RHS is an explicitly bound
`backend` operation named `oscillator.rhs-native.v1`. Its saved payload is
recognized without loading a native library. The default operation registry
does not discover executables or enable the provider.

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
qualification artifacts, not a second scientific evidence store. The native
operation result remains `not_verified`; the gate does not assign it a CIW
verification identity, admit evidence, produce an SP1 proof or authorize hardware.

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
outside this increment.

## Validation status

### Historical local fixture checks

The first local Linux/GCC/Python run passed **51 tests**. It used a deliberately
hand-lowered C fixture for ABI, Decimal, trajectory, convergence, refusal,
aliasing, concurrency, artifact-drift and CIW-retention checks. These tests alone
do not establish Julia generation or Rust execution. Local Julia/Rust downloads
were unavailable; the real acceptance path was subsequently run on GitHub Actions.

### Real native acceptance: passed on Linux x86-64

On **2026-09-28**, [run 36387268087](https://github.com/giasonpooni/Notations-Engineering-Terminal/actions/runs/36387268087),
job `108815176766`, completed successfully for code commit
`61547022037b029ebf55d6408d7c555a3c32e58b`. The dedicated
[workflow](../.github/workflows/oscillator-kernel-native.yml) used **Julia 1.10.12,
GCC 13.3.0, Rust 1.90.0 and Python 3.12.14** on Ubuntu 24.04 x86-64.
It built and installed a candidate wheel, verified that CIW was imported from
site-packages, and ran the focused suite with the real Julia provider enabled:
**58 passed, 0 failed, 0 skipped**. The separate initial 51-test fixture run is a
subset, not 51 additional unique tests.

The native stages used actual Julia-generated C, not the hand-lowered fixture:

| Check | Observed outcome |
| --- | --- |
| Julia exporter and refusal self-tests | Passed; generated source compiled into the native library. |
| Python/C against direct Julia evaluation | 1,024 samples passed; max absolute errors `[0.0, 0.0]` for `[dq, dv]`. |
| Rust/C against direct Julia evaluation | 1,024 samples passed; max absolute errors `[0.0, 0.0]`; Rust ABI tests passed. |
| Native-RHS RK4 against existing analytical oracle | Default, mixed, undamped and high-frequency cases passed under the existing `2e-8` absolute/relative policy. |
| Existing CIW retention and offline inspection | Passed; distinct execution/result IDs and detached saved validation preserved. |
| Genuine Tsit5 execution and explicit replay | Passed using the existing worker and validators; original and replay have distinct execution IDs. |
| Native-RHS RK4 against retained Tsit5 | 129 samples passed under the existing `5e-8` absolute/relative policy. |

Maximum absolute errors against the retained Tsit5 trajectory were:

| Quantity | Maximum absolute error |
| --- | ---: |
| Position q (m) | `1.9215962154817134e-11` |
| Velocity v (m/s) | `9.940448464362817e-11` |
| Energy (J) | `3.596349884560368e-10` |

These are observed errors for these fixtures, not global bounds on the model
or a cross-platform determinism guarantee. Direct Julia evaluation shares the
exported source; the existing analytical trajectory is the independent check.
The retained Tsit5 reference was genuinely executed earlier in the same job;
the final comparison reads those retained bytes rather than secretly executing
Tsit5 again.

Original Tsit5 execution: `execution-f7cb205cdea548dda09702225c33bcfa`.
Explicit replay execution: `execution-a0c37cfa9cd542e987370c61a3d31014`.
Retained reference SHA-256:
`8480cec99468377b83c730a256bf2ed9e343edb7d85f4c223212aa8992de1511`.
Complete gate report digest:
`sha256:4f6de166a034f4505dacb2a86c08b2f1c23ca8239e04f337977b926b37127fb0`.

### Packaging failure found and corrected

The [first real run 36386957446](https://github.com/giasonpooni/Notations-Engineering-Terminal/actions/runs/36386957446)
passed the native stages but failed precompiling the existing named Julia
project because `src/CIWJuliaOscillatorRuntime.jl` was absent. Its initial
installed-wheel suite reported 57 passes and one not-yet-enabled genuine-provider
skip; this was not counted as complete qualification.

The fix adds the missing empty package entry module under
`runtimes/julia-oscillator/src/`. Importing it neither launches the worker nor
solves an ODE. The existing worker, Project/Manifest versions, equations,
compiler expressions and comparison tolerances were not changed. The workflow
then enabled the genuine provider test and asserted zero skipped tests.

Tsit5 dependencies are provisioned in a separate clean Git worktree. The job
retains that runtime's commit, Project and Manifest alongside its sessions;
its local qualification-only commit is not pushed to a repository branch.
The existing checked-in Manifest is instantiated, not replaced by a manually
written lockfile.

### Retained evidence and remaining scope

[Evidence artifact 10955107123](https://github.com/giasonpooni/Notations-Engineering-Terminal/actions/runs/36387268087/artifacts/10955107123)
contains 99 files, including generated C and native binaries, source snapshots,
compiler logs, candidate wheel, JUnit reports, runtime environment files,
original/replayed Tsit5 sessions and both gate reports. The `native-only` report
intentionally remains `incomplete` without a supplied reference; the `complete`
report passed. ZIP SHA-256:
`c4cc9fe5d2740182a474833353b76dc394ca1f83c8048eb47f4a6c23c8f77fcf`.
The artifact is subject to the workflow's 30-day retention setting.

This qualifies the exercised Linux x86-64 build and comparisons, not every
supported input, operating system, compiler or deployment. Windows/macOS,
C++/Godot adapters, Bevy integration, full repository qualification and physical
validation remain outside this result. Repository-wide CI is not declared green;
private-provider qualification still has separate access requirements. No token,
access policy, branch protection, license, default registry entry, proof gate,
solver or physical claim was changed. The PR remains unmerged.
