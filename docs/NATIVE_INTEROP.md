# Native interoperability

`ciw.native-interop.v1` registers bounded computational profiles in the shared
Workbench. Python owns source, execution, result and verification records. The
external Scientific Computation Runtime (SCR) owns the compiled Rust host and
CXX bridge. Julia evaluates package-backed models. No equipment interface is
exposed by this operation.

## Profiles and mathematical scope

| Profile | Executing provider | Independent check |
| --- | --- | --- |
| `affine-binary64.v1` | Rust/C++ or Rust/Julia | Python affine reference, componentwise tolerance |
| `affine-d256.v1` | Rust/C++ or Rust/Julia | Python integer reference, exact numerators |
| `oscillator-force-energy.v1` | Rust/C++ | Python force, acceleration and energy equations |
| `oscillator-tsit5.v1` | Rust/Julia, OrdinaryDiffEqTsit5 | Python underdamped analytic solution |
| `control-oscillator.v1` | Rust/Julia, ControlSystemsBase.lsim | Analytic solution and separately executed Tsit5 |
| `design-qp.v1` | Rust/Julia, JuMP and HiGHS | Recomputed objective, feasibility and projected-gradient residual |

The affine profiles use row-major wire arrays with dimensions 1 through 8.
The exact profile represents every input as an integer numerator over 256,
with magnitude at most 4096. Outputs retain denominator 65536; shifted state
numerators may reach 8192. The binary64 profile remains a separate calculation.
It is never rounded into an exact claim.

The quadratic objective is `0.5*||y0-target+J*d||^2 + 0.5*lambda*||d||^2`,
with explicit box bounds and positive regularization in dimensionless
coordinates. Solver success is followed by a numerical check, not an optimality
proof. The existing educational finite-candidate and scalar exact-certificate
studies retain their separate contracts.

Control uses state order `[q,v]`, a declared uniform simulation-time grid and
zero external force. Its continuous state matrix is not used as a finite-time
transition. The force profile evaluates supplied states; it does not integrate
another trajectory. Its C++ domain requires mass and frequency strictly above
`1e-12`; this does not narrow the existing Julia oscillator profile. An optional upstream reference binds it to an exact
retained Julia trajectory and the same model parameters.

Units, frame and clock declarations are fixed by each profile. Covariance and
calibration are not applicable to these synthetic calculations; physical
uncertainty is not established. Numerical checks neither admit a scientific
claim nor authorize actuation.

## Runtime binding and execution

Build SCR's `crates/execution-provider-host` in its owner repository, with build
outputs outside the immutable source checkout. Its README owns compiler,
CXX, memory-ownership and sanitizer instructions. The Workbench's
[native runtime manifest](../src/ciw/native-interop-runtimes.json) lists accepted
SCR revisions and exact Julia source/environment digests. Julia files must match
one complete current or historical closure; hashes cannot be mixed between
versions. Historical adapter manifests and the direct Julia oscillator operation
remain available. See the [validation report](NATIVE_INTEROP_VALIDATION.md) for
the distinct retained Windows and committed LF worker identities.

The operator supplies a separate JSON binding file:

```json
{
  "scr": "/approved/SCR-checkout",
  "host": "/built/scr-provider-host",
  "host_sha256": "sha256:<actual executable digest>",
  "julia": "/julia-1.10.12/bin/julia",
  "julia_runtime": "/approved/workbench-checkout",
  "julia_depot": "/preprovisioned/julia-depot"
}
```

The three Julia fields are supplied together, or omitted for C++ only. Relative
runtime paths resolve beside the binding file; use absolute depot paths. Depot
lists use the platform path separator. A saved source contains none of these
paths and cannot request installation, imports, code evaluation or new profiles.

Provision the two Julia environments before serving requests. Their committed
Manifest files were generated with Julia 1.10.12; the native environment includes
ControlSystemsBase 1.22.0, JuMP 1.31.2, HiGHS.jl 1.25.4, native HiGHS 1.15.1,
OrdinaryDiffEqTsit5 1.12.0, SciMLBase 2.155.2 and JSON3 1.14.3. Request execution
uses one Julia thread, a disabled startup file and offline package resolution.
Package-directory contents and source-to-binary correspondence are not remotely
attested by recording these identities.

```python
from ciw.native_interop_contract import make_source
from ciw.telemetry import canonical
import base64

session.workbench.bind_workflow("native-interop", {"runtime": binding_file})
source = make_source("affine-binary64.v1", "cpp", {
    "rows": 2, "columns": 3,
    "a_row_major": [2, 1, -1, -1, 3, 2], "b": [5, -2],
    "x0": [3, 4, 2], "delta_x": [0.25, -0.5, 0.125]
})
record = session.workbench.add_source({
    "kind": "native-interop", "label": "Rectangular affine response",
    "bytes_b64": base64.b64encode(canonical(source)).decode()
})
result = session.workbench.execute({
    "operation_id": "ciw.native-interop.v1", "source_id": record["source_id"]
})
session.save_workspace(workspace_file)
```

The operation executes a fresh reproduction before retaining success. Inspection
and reopen validate retained structures and bindings without starting providers
or repeating the numerical reference calculation. Explicit replay requires the
original runtime and produces new execution/result occurrences.

## Transport and identity

Frames use a four-byte big-endian length, strict JSON field sets, bounded pipes
and a single in-flight request per worker. The Rust host supports persistent
A/B/A requests and kills/reaps a failed child. CIW currently launches a fresh
host for each execution; its timing includes startup. Cancellation is explicitly
unsupported. Stdout carries frames and stderr carries bounded diagnostics.

Each retained step contains exact handshake, request, response and stderr bytes.
The SCR program binds the profile and actual runtime identity; its specification
binds the arithmetic, semantic configuration and original payload bytes. CIW
checks SCR commitments using the existing encoding. Transport and parent
execution IDs are occurrence references, not content identities.

Raw SCR output-byte identity includes any returned timing or inner request
metadata. A separately named `numerical_result_id` hashes a projection that
removes `request_id` and `solver.solve_seconds`. Original bytes are preserved.
Binary64 replay compares the projected numerical values under the declared
componentwise tolerance; it does not promise cross-platform bit identity.
Exact D256 replay requires integer equality.

The host executable, Julia executable, worker, included oscillator worker,
Project and Manifest digests are linked to the handshake and each execution.
The compiler, strict floating-point flags and CXX version are retained. These
checks identify an operator-approved runtime; they are not an OS sandbox or a
cryptographic source-to-binary attestation.

## Validation and outstanding gates

The [validation report](NATIVE_INTEROP_VALIDATION.md) distinguishes actual native
runs from protocol doubles, lists commands and reports missing gates. The
readiness/integration script does not provision runtimes or turn missing
required dependencies into passing tests.

A separate exact-affine checker and SP1 guest belong to SCR. A successful Python
integer comparison or native checker does not establish an SP1 proof. This
Workbench operation records `sp1_verification: not_performed`. Genuine affine
proof production, independent fresh verification and corruption/claim-swapping
gates must pass before that status can change under a separately reviewed
proof integration. Existing heat proof meanings and guest registrations remain
unchanged.

## Additive reaction provider families

`reaction-a-to-b.v1` uses isolated `catalyst` and `cantera` worker families on
the same native operation and SCR commitment path. Legacy `cpp`/`julia` profiles
and runtime closures are preserved. Each new family requires its own qualified
closure; see [reaction benchmark](REACTION_BENCHMARK.md) for the model, units,
engine gates and limitations. No generic chemistry importer is enabled.
