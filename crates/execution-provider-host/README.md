# Bounded native provider host

`execution-provider-host` is an outer `std` workspace. It depends on SCR's
existing `execution-core` facade; the frozen dependency-free identity crates
remain unchanged. It is an execution adapter, not an evidence store or proof
verifier.

The host provides genuine typed CXX calls to C++ for:

- `affine-binary64.v1`: 1–8 by 1–8 row-major affine response, with finite inputs
  bounded by 1e6 in dimensionless coordinates.
- `affine-d256.v1`: the same response with signed integer input numerators
  bounded by 4096, input denominator 256, and authoritative output denominator
  65536. Checked sums/products include shifted states up to 8192. No rounding
  back to the input grid occurs.
- `oscillator-force-energy.v1`: pointwise SI force, acceleration and energy on
  1–4096 declared simulation samples. This is not a second trajectory solver.

The Julia backend forwards the same affine profiles plus `oscillator-tsit5.v1`,
`control-oscillator.v1` and `design-qp.v1` to an explicitly bound Julia worker.
The latter profiles are supplied by the workbench's `runtimes/native-interop`
environment. Their package execution is distinct from the Rust process host.

## Build and required native gate

Use Rust 1.96.0 and a C++17 compiler. `Cargo.lock` pins CXX 1.0.202 and all outer
host dependencies. Set `CARGO_TARGET_DIR` outside the immutable source checkout.

```sh
cargo build --locked --manifest-path crates/execution-provider-host/Cargo.toml
cargo test --locked --manifest-path crates/execution-provider-host/Cargo.toml
SCR_NATIVE_REQUIRED=1 SCR_PROVIDER_HOST="$CARGO_TARGET_DIR/debug/scr-provider-host" \
  python -m pytest -q tests/test_native_provider_host.py -k 'not genuine_julia'
```

On Windows, the binary ends in `.exe`; set environment variables with PowerShell
syntax. Local conformance was exercised with Rust 1.96.0, MSVC 19.44 and CXX
1.0.202. The handshake retains the actual compiler version, compiler path,
flags, native source commitment and executable SHA-256. Builds disable
fast-math (`/fp:strict` or `-fno-fast-math`). A binary hash does not authenticate
all dynamically loaded library behavior.

For genuine Julia integration, provision and instantiate the workbench's pinned
Julia environment first. No package installation occurs while serving requests.
Set `SCR_JULIA_EXE`, `SCR_JULIA_PROJECT`, and the explicit `JULIA_DEPOT_PATH`, then:

```sh
SCR_NATIVE_REQUIRED=1 SCR_NATIVE_REQUIRE_JULIA=1 \
  python -m pytest -q tests/test_native_provider_host.py -k genuine_julia
```

Set `SCR_NATIVE_EVIDENCE_DIR` to retain the exact framed streams and linked
numerical check report. This gate exercises real Julia affine, Tsit5,
ControlSystemsBase and JuMP/HiGHS computations, then evaluates the retained
trajectory through the real C++ kernel. It does not produce an SP1 proof.

## Transport and ownership

The trusted caller launches one of:

```text
scr-provider-host --provider cpp
scr-provider-host --provider julia --julia EXE --project DIR --worker FILE --timeout-ms 300000
scr-provider-host --provider catalyst --julia EXE --project DIR --worker FILE --timeout-ms 300000
scr-provider-host --provider cantera --python EXE --project DIR --worker FILE --timeout-ms 300000
scr-provider-host --provider intervals --julia EXE --project DIR --worker FILE --timeout-ms 300000
```

Runtime paths are host configuration, never fields accepted from saved data.
Requests and child responses use a four-byte big-endian length prefix, with a
1 MiB limit. Outer responses allow 4 MiB because they retain exact nested
bytes as hex. Diagnostics are bounded to 64 KiB. One request is in flight;
request IDs must be unique within the bounded 256-request stream. JSON object
keys must be unique, including nested objects. Arrays and dimensions are
bounded before computation.

A handshake is `{schema: "ciw.native-interop-handshake-request.v1", request_id}`.
An execution request has exactly `schema`, `request_id`, `parent_execution_id`,
`profile`, `arithmetic`, `semantics` and `payload`. Its schema is
`ciw.native-interop-request.v1`. The parent reference identifies the workbench
execution; the request ID identifies transport. Neither is an input commitment.
The corresponding response echoes those references and profile, with status
`ok` and `data`, or `refused` and `refusal`, plus a `host` record.

Affine payload fields are `rows`, `columns`, `a_row_major`, `b`, `x0`,
`delta_x`. Force payload fields are `model`, `time_s`, `q_m`, `v_m_s`; model
fields are `mass_kg`, `omega_0_rad_s`, `gamma_s_inv`. The fixed semantics are:

| Profile family | Layout | Input/output units | Frame | Clock |
| --- | --- | --- | --- | --- |
| Affine and QP | row-major | dimensionless | declared-cartesian | not-applicable |
| Oscillator/control/force | row-major | SI | one-dimensional-inertial | declared-simulation-time |

CXX borrows immutable Rust slices only for the duration of a call. C++ returns
owned vectors; no borrowed buffer escapes. C++ validates dimensions and domains
again. Exceptions become `Result` errors through CXX. There is no unchecked C
ABI or arbitrary dynamic-library loading. Returned arrays are checked for
shape and arithmetic representation before a successful output is committed.

Julia source, Project, Manifest and the reused oscillator source are copied
into a fresh sibling runtime layout under the executable directory's
`.ciw-provider-runs` directory. The copied bytes are the retained runtime
bindings. They are removed after the worker is killed and reaped. The executable
directory must therefore be writable for the Julia backend. Only one configured
worker runs per host. Timeout covers blocked input writes as well as response
reads. Any child timeout, crash, stale response or stream violation terminates
and reaps that worker and closes the host; subsequent work requires a fresh
host occurrence. Cancellation is explicitly unsupported.

The additive `catalyst` and `cantera` families each expose only
`reaction-a-to-b.v1` with binary64 arithmetic. The legacy `julia` family keeps
its five profiles and sibling oscillator snapshot unchanged. Catalyst snapshots
exactly `worker.jl`, `Project.toml` and `Manifest.toml`; Cantera snapshots exactly
`worker.py` and `requirements.txt`. No packages are installed or resolved by the
host. The Cantera launcher uses `python -I -u worker.py`; the Julia launcher
disables startup/history files, sets one Julia thread and enables package
offline mode. These are trusted executable/project bindings, not code or paths
loaded from the request. Python isolated mode is not an operating-system sandbox.

The reaction profile is a closed, homogeneous, constant-volume, prescribed
temperature mathematical benchmark with irreversible first-order `A => B`.
Its fixed declarations use time-major arrays, mol/m^3 concentrations,
mol/m^3/s production rates, seconds, kelvin, m^3, the
`homogeneous-control-volume` frame and `declared-simulation-time` clock.
Species labels are abstract model species, not a claim about hydrogen chemistry.
The worker owns engine evaluation; the host checks bounded inputs, exact model
and species declarations, grid echo, finite N-by-2 output arrays, solver settings,
and mechanism format/UTF-8 bytes/hash before committing an output. Negative
numerical samples are retained without clamping. These checks do not establish
analytical agreement, conservation within tolerance or physical applicability.

Reaction worker handshakes bind exact source/environment file hashes to the
snapshot. Cantera additionally reports an extension digest and a digest of
installed distribution file bytes; those reported digests identify artifacts,
not binary attestation. The caller must independently qualify and pin the
installation/package identities. Catalyst mechanism bytes must hash to the
snapshotted worker source. Catalyst uses `julia_executable_sha256`; Cantera uses
`python_executable_sha256`. Both retain the worker identity and per-file hashes,
without adding a legacy oscillator dependency.

The additive `intervals` family exposes only `scalar-square-interval.v1` with
`outward-binary64` arithmetic. It snapshots exactly `worker.jl`, `Project.toml`
and `Manifest.toml`, with no legacy oscillator or reaction dependency. It uses
the same bounded Julia launcher and process lifetime controls. Its separate
`ciw.interval-julia-identity.v1` handshake declares Julia 1.10.12, one thread,
platform and exactly the IntervalArithmetic/JSON3 package versions. File hashes
must match the snapshot; package and executable qualification remains a caller
duty. The host neither installs packages nor attests to their binaries.

This profile evaluates the scalar-square linearization remainder requirement
`u^2 - error_limit <= 0` on a declared closed variation interval. Inputs are
reduced rational numerator/denominator objects, never decimal coercions. The
host checks their integer/domain bounds exactly before child dispatch. It checks
finite, ordered IEEE754 binary64 endpoint bit patterns (16 lowercase hex digits),
`com` decoration, the guaranteed flag, the fixed configuration and the enclosure
classification. The declarations are scalar, dimensionless (`input_unit` and
`output_unit` are `"1"`), frame `dimensionless-cartesian`, clock
`not_applicable`, with covariance and calibration explicitly not applicable.
`holds_throughout` requires an upper endpoint at most zero; `fails_throughout`
requires a strictly positive lower endpoint; otherwise the result is
`inconclusive`. The host does not recompute the exact extremum: independent
rational enclosure validation belongs to the workbench oracle. A completed
transport record is not a physical claim, proof, admission or authorization.

The compiled-host interval tests use an explicitly synthetic scripted child:

```sh
SCR_NATIVE_REQUIRED=1 SCR_PROVIDER_HOST="$CARGO_TARGET_DIR/debug/scr-provider-host" \
  python -m pytest -q tests/test_interval_provider_host.py
```

Those tests cover closure, exact byte/occurrence bindings and protocol/domain
refusals; they do not qualify IntervalArithmetic execution. The genuine worker
and installed-provider gates are separate workbench checks.

Windows uses a kill-on-close JobObject after process creation, and its kill
behavior is tested. A very short creation-to-job-assignment interval remains;
this is not a general OS sandbox. Linux sets a parent-death signal before exec.
The Linux-specific path requires its own platform execution gate.

## Identities and retained inspection

`host` retains exact program, configuration, input and output bytes as hex, plus
SCR's existing program/input/output/specification/computation commitments.
Program bytes encode `{profile, runtime}`. Configuration bytes encode
`{arithmetic, semantics}`. Input bytes are the original payload token bytes,
including solver policy. Existing SCR domain separators and canonical framing
are reused; JSON is not substituted for SCR's commitment encoding.

Occurrences come from `ExecutionTrace` and are scoped to the host process.
Child process/occurrence references and exact Julia request/response bytes are
retained separately. A completed output has an output identity; a halted
execution has none. No proof identity is minted.

Byte identity is intentionally distinct from numerical-content identity.
The legacy Tsit5 data includes a request ID, and QP diagnostics include solver
time. Exact output byte commitments retain those facts and can differ across
occurrences. A workbench may derive a separately identified numerical projection
for replay comparisons; it must not relabel that projection as the raw provider
output. Provider-free reopening checks bindings without launching this host.

## Sanitizers and limitations

For MSVC AddressSanitizer, set both `SCR_NATIVE_SANITIZE=address` and
`CXXFLAGS=/fsanitize=address` so the generated bridge, CXX runtime and kernels
use compatible instrumentation; include the MSVC runtime DLL directory on
`PATH`. Use a separate target directory. The Windows address-sanitized native
unit gate passed. MSVC does not supply the required undefined-behavior gate.

On Linux with Clang, use `SCR_NATIVE_SANITIZE=address,undefined`,
`CXXFLAGS=-fsanitize=address,undefined` and a compatible sanitizer linker.
The workflow supplies that configuration; a workflow definition is not evidence
of a completed Linux run. Native conformance and scoped exact checking do not
establish proof-system verification, physical validation or actuation authority.
