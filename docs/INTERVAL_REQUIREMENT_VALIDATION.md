# Interval requirement qualification

On 2026-09-27 the installed CIW wheel exercised the real Windows Julia worker
through the pinned SCR host for `scalar-square-interval.v1`. This extends
`ciw.native-interop.v1`; it adds no operation identity or admission authority.
The [operator contract](INTERVAL_REQUIREMENT.md) defines the bounded claim.

## Observed checks

| Check | Result |
| --- | --- |
| Installed-wheel interval contract, worker, workflow, benchmark and native regression tests | 139 passed, zero failures/errors/skips; 72.65 s |
| Full source regression suite | 1,877 passed, 714 skipped, 38 subtests passed; 157.03 s |
| Real framed worker tests (included in installed gate) | 16 passed, including refusal/recovery and lexical integer rejection |
| Exact Python rational reference | All six enclosures contain the exact extrema; no tolerance |
| Fresh replay | New execution and result occurrences; unchanged numerical result identity |
| Provider-free reopen and inspection | Seven bundles retained with identical serialized content; provider and oracle calls forbidden |
| Manual Windows workflow | actionlint 1.7.12, PowerShell parsing and embedded Python syntax passed; hosted execution pending |

The full-suite skips represent optional external runtimes and platform gates;
they are not qualification evidence. The installed gate had no skips. It used
Python 3.12.14, pytest 9.0.2 and the wheel's `site-packages/ciw` import with
`python -I` and pytest's source `pythonpath` override disabled. The standalone
benchmark and subsequent inspection ran outside the source checkout.

| Fixture | Retained requirement outcome |
| --- | --- |
| `dyadic-boundary` | `holds_throughout` |
| `positive-box` | `fails_throughout` |
| `mixed-box` | `inconclusive` |
| `rational-tenth-boundary` | `inconclusive` |
| `zero-width-zero-limit` | `holds_throughout` |
| `negative-box` | `fails_throughout` |

Every row passed enclosure validation. Failure of the mathematical requirement
and an inconclusive bound remain successful, retained calculations. The rational
tenth boundary illustrates why outward rounding can leave a mathematically exact
boundary inconclusive. Original process durations were 3.38–3.63 seconds per
recorded execution, including process startup; these are not kernel benchmarks.

## Exact qualification bindings

The runtime manifest retains these values alongside all earlier native families:

| Item | Revision, version or SHA-256 |
| --- | --- |
| SCR revision | `2a144e252607546ca6b20e6dd4613d3a4146758a` |
| SCR source tree | `e7c8751faec29c0e985d89df794c3a8374b704d5` |
| Observed host executable | `031f7649517c02c42dfa597fd1da20b1b4af9fcdd59ee9c7df67ba7d9b662beb` |
| Julia | `1.10.12`, `x86_64-w64-mingw32`, one thread |
| Julia executable | `29a5cb5bde6a3f4a151f6e714591ca9344638303d9ed2a893ab31ada3de5d103` |
| IntervalArithmetic / JSON3 | `1.0.12` / `1.14.3` |
| `worker.jl` | `10167228a6db63a2bdf51ae4637745f65561cffc29650592c101d1089f5f70c8` |
| `Project.toml` | `2807b18661ea382d4bb82ba4f7f00431930b45c08ff7bcdfa3bb7877e20a2936` |
| `Manifest.toml` | `f54471373c82d5b1ff993a3f13555c030fc5c90509fdd7cd16620fc84f2014e3` |

The SCR checkout's published commit object and tree were checked against GitHub
metadata; its tree also matches the previously built local SCR source tree.
This establishes the selected source identity, not source-to-binary attestation.
The host digest is an explicit operator binding and retained observation.

Execution used `JULIA_PKG_OFFLINE=true`, `JULIA_LOAD_PATH=@;@stdlib` and a
previously provisioned locked depot. Tests exposed JSON3 accepting `+1` as an
integer; the worker now checks primitive token spelling before JSON decoding.
The regression rejects alternate noncanonical integer spellings without
preventing the next valid framed request.

## Reproduction and evidence

Build/install the wheel, provision the exact runtime, and supply the binding
described in [the operator guide](INTERVAL_REQUIREMENT.md). Set
`CIW_INTERVAL_BINDING`, `CIW_TEST_INTERVAL_JULIA`, `CIW_TEST_INTERVAL_DEPOT` and
`CIW_INTERVAL_REQUIRE_JULIA=1` before running:

```powershell
python -I -m pytest tests/test_interval_contract.py tests/test_interval_worker.py tests/test_interval_workflow.py tests/test_interval_benchmark.py tests/test_native_interop.py --override-ini=pythonpath= -q --junitxml=interval-tests.xml
python -I scripts/check_interval_requirement.py run --binding interval-binding.json --fixtures examples/interval-requirement/fixtures.json --output interval-evidence
python -I scripts/check_interval_requirement.py inspect --workspace interval-evidence/workspace.json --artifacts interval-reopened
```

Use absolute script/test paths when running outside the source checkout. The
manual [qualification workflow](../.github/workflows/interval-requirement.yml)
does so and refuses skipped tests. It requires access to the exact private SCR
revision through `SCR_READ_TOKEN`; it never rewrites pins to accommodate a runner.

The local run retained `report.json`, `fixtures.json`, the seven-bundle workspace,
test JUnit and a separate provider-free inspection. Raw local output is not
committed. These hashes identify that particular run, not a reproducible build:

| Local artifact | SHA-256 |
| --- | --- |
| Tested wheel | `cde2d3f33bd7fceec85a0f7651e65a78d505679aa6ecef762da634bb94492411` |
| Benchmark report | `51079f3e9c4cce251b3632949eed6488301dad3768d21fc834f6b14368f98bd9` |
| Saved workspace | `e1e0deed12bce13caa88e1757690d995f59cf92ad40801cd0de86a377d642075` |

## Remaining gates

Hosted qualification, another operating system, complete Julia depot attestation
and source-to-binary attestation remain open. No independent ICRH profile or
SP1 proof is supplied by this increment. There is no new Godot representation,
hardware measurement, physical calibration, ESM admission or actuation. The
existing independent Python containment check establishes its declared numerical
condition only; unsigned retained hashes do not authenticate a fabricated record.
