# Reaction benchmark validation

Validation date: 2026-09-26. This report covers the bounded abstract A-to-B
profile on the existing native operation. It does not qualify physical chemistry,
a generic reaction mechanism importer, heat coupling, admission or actuation.

## Revisions and exact runtime pins

- PDT increment base: `ee726715245f891cdeba176b25295a0a5c3dc39e`
  (the published curved-path study; the source tree matches local base
  `26fa16d99f6edc6e61af24d9242fca4151f66dd7`).
- SCR published revision: `7e41b5a104526929c531a069a9872cf92ab277cc`;
  tree `87d395d65a4e3ac1a7501f6ba17e61f8aefded1b`.
  The tree matches tested local commit `4a58fe12299bc788741c77ec5384dec5be87acfc`.
- Tested Windows host SHA-256:
  `22d7f9b83db130b6fc2143902c6f3e5d792c6fca5d3793dfed3e90eac3a6b6df`.
- Rust 1.96.0, MSVC 19.44.35228, CXX 1.0.202; host dependencies use the existing
  locked Cargo environment. No legacy native/Julia closure is replaced.
- CSG remains `bbc535af29c30997e56fd120320c570830676462`;
  FTR remains `dc918562cd9e351a65475d29f46963c9f2fd7db8`;
  ICRH remains `dc4d826ecd1f28c1d55b724618380ce44e58bedd`.

The machine-readable qualification is
[native-interop-runtimes.json](../src/ciw/native-interop-runtimes.json).
It checks the published SCR commit and tree, complete worker-file closure,
runtime executable and reported installed identity. Source-to-binary and complete
installed-environment attestation remain explicitly unestablished.

### Catalyst

| Artifact | SHA-256 |
| --- | --- |
| Runtime executable | `sha256:29a5cb5bde6a3f4a151f6e714591ca9344638303d9ed2a893ab31ada3de5d103` |
| [runtimes/reaction-kinetics/Project.toml](../runtimes/reaction-kinetics/Project.toml) | `sha256:4022397ae5104a018351acf83297a0f100380ba882a6c8fe1c75d18e5e18c195` |
| [runtimes/reaction-kinetics/Manifest.toml](../runtimes/reaction-kinetics/Manifest.toml) | `sha256:6e9212c6be2e65c92ad5b6985a38f1beeeb50c2b02cd10a4004058877f57281a` |
| [runtimes/reaction-kinetics/worker.jl](../runtimes/reaction-kinetics/worker.jl) | `sha256:9f38a2e740f92166d70d2c12b3cdabadb03f86e4d2fff33b963c38d7dd040355` |

Packages: `Catalyst 16.4.3`, `OrdinaryDiffEqTsit5 2.1.4`, `SciMLBase 3.56.1`, `JSON3 1.14.3`, `SymbolicIndexingInterface 0.3.55`.

### Cantera

| Artifact | SHA-256 |
| --- | --- |
| Runtime executable | `sha256:9f91cee2e1b13d9779ab252507aeee120c379e2543ffe85f63cad129b58ba230` |
| [runtimes/cantera-reaction/requirements.txt](../runtimes/cantera-reaction/requirements.txt) | `sha256:9e39e2a0f34215e77fd19f1199315ab9a8676643bff138026164b2f2a6ef38e9` |
| [runtimes/cantera-reaction/worker.py](../runtimes/cantera-reaction/worker.py) | `sha256:02cb2a77b975e8d07253115685a35b9959a5c20e2eee749edeb8a6ec45013c14` |
| extension_sha256 | `sha256:00f00749cc90b76a7266656fd02e6a7d40be82e7d7e1389472ad285123064e9d` |
| package_files_sha256 | `sha256:23f637f3754623d070a1783b92cf6068164655c692450b3ffea0ceb926cd1113` |

Packages: `cantera 3.2.0`, `numpy 2.5.3`, `ruamel.yaml 0.19.1`, `typing-extensions 4.16.0`.

## Validation record

The general Python regression completed with **1758 passed, 684 optional
external-provider skips and 38 subtests passed** in 443.06 seconds. Those skips
do not establish required provider conformance. Genuine reaction gates run
separately with explicitly supplied providers.

Completed provider gates:

| Gate | Result | Scope |
| --- | --- | --- |
| SCR Rust tests | 11 passed | Host validation and legacy native kernels |
| SCR Python host/protocol regression | 38 passed | Includes genuine legacy Julia across five existing profiles |
| Cantera direct worker | 13 passed | Real CVODES, independent reference, framing, refusal, identifiers and fresh execution |
| Cantera through SCR | Passed, 29.31 s | Seven persistent cases and a fresh step-limit refusal with no result |
| Catalyst direct worker | 18 passed, zero skips in 1212.31 s | Actual trajectories/rates, independent reference, state reset, numerical refusal/recovery, strict JSON and transport IDs |
| Catalyst through SCR | Passed, 253.39 s | Same scenario classes, analytical reference, identities and actual MaxIters refusal |
| Installed CIW wheel | 116 passed, zero skips in 542.75 s | Both real providers; source checkout excluded from imports; identity, corruption, offline inspection and replay checks |
| Two-engine workspace benchmark | 15 PASS gates; 10 retained bundles | Four fixtures in each engine, four cross-engine comparisons, two fresh replays and provider-free reopen |

The direct Catalyst run emitted one nonfatal pytest cache-permission warning;
its runtime and numerical checks passed. The installed gate disables that cache.

The seven-case host streams reported maximum concentration discrepancies of
`8.527345496389671e-12 mol/m³` (Catalyst) and
`5.168305450276023e-9 mol/m³` (Cantera) against the independent reference.
Their maximum conservation discrepancies were `2.220446049250313e-16` and
`6.661338147750939e-16 mol/m³`, respectively. Both reported zero sampled rate-law
discrepancy against `(-k*c_A, k*c_A)` in binary64. These checks are numerical
comparisons, not a proof or physical validation.

The retained Catalyst host dispatch times were
`[61.3306203, 0.194187, 0.0765804, 0.0651106, 0.075194, 0.0788783, 0.0746402]`
seconds. The first includes model/JIT setup; later values are warm round trips.
They exclude handshake startup and are not isolated solver timings. Cantera's
round trips were approximately 2.79–3.41 seconds and include installation-file
hashing. Initial Julia package precompilation took 1842 seconds on this machine
and is separate from all of these execution measurements.

Raw host requests, responses, handshakes and refusal frames are retained locally
under `work/reaction-host-probes-2/{catalyst,cantera}`. The general regression
log and JUnit record are under `results/reaction-regression.*` in the increment
checkout. These local artifacts are not presented as public CI artifacts.

The wheel used for the 116-test gate and full benchmark has SHA-256
`1700f6c6f863ff2c58b52c333c9d0ea7fd3c273f8953422a8fd3f866b62a7ac8`.
The final staged whitespace check removed one terminal blank line from
`reaction_runtime.py`; its Python AST was confirmed unchanged. The rebuilt
wheel has SHA-256
`a55337bff8478e0aa32a8476881a1bef2a35d5ec6123667b7c535b31a04cd783`.
All 104 packaged source/resource files match the final checkout byte-for-byte.
After reinstalling that wheel, the 98 contract/legacy tests passed again
with a workspace-local temporary directory. The first short recheck had
96 passes and two setup errors because the default Windows temporary directory
was inaccessible; no product assertion failed.
The installed test commands use Python isolated mode from outside the source
checkout and explicitly disable pytest source-path injection.

The installed benchmark retained four fixtures in each engine: baseline,
zero rate, zero reactant and reversed species order. Fresh replay added one
new bundle per engine, with distinct execution and result identities. All ten
bundles reopened while provider launch and reference computation were forbidden.
A separate installed CLI `inspect` also reported ten bundles and
`fresh_execution: false`.

Maximum cross-engine concentration discrepancy was
`6.348237047149041e-9 mol/m³`; maximum production-rate discrepancy was
`3.1741176076405253e-9 mol/m³/s`. Those quantities remain separate.

The complete local evidence is in `work/reaction-installed-run-1`:

| Artifact | SHA-256 |
| --- | --- |
| `report.json` | `82b296042c564b5a9edd8090ad7d7e987d68fcf24114825fc118414b8335b647` |
| `workspace.json` | `e1feccc035c1fd0933bc2fa5af292657b35a1da961b277db03b0e573dda24a94` |

The installed JUnit/log, separate inspection response and direct Julia completion
record are under `results/reaction-installed-tests.*`, `results/reaction-inspect.json`
and `results/reaction-julia-worker.md`. See the
[operator commands](REACTION_BENCHMARK.md#operator-commands) to reproduce the gate.
No public CI success is claimed by these local artifacts.

The subsequent [development-window audit](DEVELOPMENT_GAPS.md) records hosted
workflow findings and follow-up repairs. The test counts above remain the original
qualification record.

## Scope and remaining gates

- Windows x86-64 is the qualified reaction platform. New Linux/macOS reaction
  execution and fresh CI-run qualification remain separate gates.
- The manual [CI workflow](../.github/workflows/reaction-benchmark.yml) requires
  the declared providers, installed-wheel tests with zero skips, and the complete
  benchmark. Its definition is not evidence of a completed workflow run.
- This first-order, isothermal equal-property model does not qualify stiffness,
  higher-order combinatorial conventions, nonzero reaction enthalpy or coupled
  thermochemical integration.
- Physical measurements, calibration, measurement uncertainty, independent ICRH
  reaction conformance, SP1 proofs, evidence admission and equipment authority
  are not established by these numerical checks.
- General profile/capability discovery, typed composition and cross-domain
  evidence/frame integration remain [consolidation work](CONSOLIDATION.md).


## Exact changed files

PDT (relative to the published curved-path study):

- [.github/workflows/reaction-benchmark.yml](../.github/workflows/reaction-benchmark.yml)
- [README.md](../README.md)
- [docs/CONSOLIDATION.md](../docs/CONSOLIDATION.md)
- [docs/INSTRUMENTS.md](../docs/INSTRUMENTS.md)
- [docs/INTEGRATION_COVERAGE.md](../docs/INTEGRATION_COVERAGE.md)
- [docs/NATIVE_INTEROP.md](../docs/NATIVE_INTEROP.md)
- [docs/REACTION_BENCHMARK.md](../docs/REACTION_BENCHMARK.md)
- [docs/REACTION_BENCHMARK_VALIDATION.md](../docs/REACTION_BENCHMARK_VALIDATION.md)
- [docs/README.md](../docs/README.md)
- [examples/reaction-benchmark/fixtures.json](../examples/reaction-benchmark/fixtures.json)
- [runtimes/cantera-reaction/requirements.txt](../runtimes/cantera-reaction/requirements.txt)
- [runtimes/cantera-reaction/worker.py](../runtimes/cantera-reaction/worker.py)
- [runtimes/reaction-kinetics/Manifest.toml](../runtimes/reaction-kinetics/Manifest.toml)
- [runtimes/reaction-kinetics/Project.toml](../runtimes/reaction-kinetics/Project.toml)
- [runtimes/reaction-kinetics/worker.jl](../runtimes/reaction-kinetics/worker.jl)
- [scripts/check_reaction_benchmark.py](../scripts/check_reaction_benchmark.py)
- [src/ciw/native-interop-runtimes.json](../src/ciw/native-interop-runtimes.json)
- [src/ciw/native_interop.py](../src/ciw/native_interop.py)
- [src/ciw/native_interop_contract.py](../src/ciw/native_interop_contract.py)
- [src/ciw/reaction_contract.py](../src/ciw/reaction_contract.py)
- [src/ciw/reaction_runtime.py](../src/ciw/reaction_runtime.py)
- [tests/test_reaction_cantera_worker.py](../tests/test_reaction_cantera_worker.py)
- [tests/test_reaction_contract.py](../tests/test_reaction_contract.py)
- [tests/test_reaction_julia_worker.py](../tests/test_reaction_julia_worker.py)
- [tests/test_reaction_workflow.py](../tests/test_reaction_workflow.py)

SCR (relative to the native-interop branch):

- [crates/execution-provider-host/README.md](https://github.com/giasonpooni/Scientific-Computation-Runtime/blob/7e41b5a104526929c531a069a9872cf92ab277cc/crates/execution-provider-host/README.md)
- [crates/execution-provider-host/src/main.rs](https://github.com/giasonpooni/Scientific-Computation-Runtime/blob/7e41b5a104526929c531a069a9872cf92ab277cc/crates/execution-provider-host/src/main.rs)
- [crates/execution-provider-host/src/process.rs](https://github.com/giasonpooni/Scientific-Computation-Runtime/blob/7e41b5a104526929c531a069a9872cf92ab277cc/crates/execution-provider-host/src/process.rs)
- [crates/execution-provider-host/src/reaction.rs](https://github.com/giasonpooni/Scientific-Computation-Runtime/blob/7e41b5a104526929c531a069a9872cf92ab277cc/crates/execution-provider-host/src/reaction.rs)
- [tests/reaction_protocol_fixture.py](https://github.com/giasonpooni/Scientific-Computation-Runtime/blob/7e41b5a104526929c531a069a9872cf92ab277cc/tests/reaction_protocol_fixture.py)
- [tests/test_reaction_provider_host.py](https://github.com/giasonpooni/Scientific-Computation-Runtime/blob/7e41b5a104526929c531a069a9872cf92ab277cc/tests/test_reaction_provider_host.py)
