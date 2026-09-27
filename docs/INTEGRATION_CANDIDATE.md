# Combined integration candidate

This isolated candidate reconciles the existing native, curved-path, reaction,
interval, CI, failure-history and retained-RMS branches before adding further
features. It starts from main
`219b65ebfaacead852f051def734d3b7809573a1`; the local integration branch is
`codex/integration-qualification-v1`. This page describes the combined scope and
its evidence boundaries, not a release approval or another provider manifest.

## Reconciled inputs

These are the reviewed PR heads incorporated into the candidate. Stacked
dependencies are retained through Git ancestry. The exchange-refusal fixture
from #17 is reconciled once, including branches that already carried it.

| PR | Existing work | Incorporated head |
| --- | --- | --- |
| [#7](https://github.com/giasonpooni/Parametric-Design-Terminal/pull/7) | Native interoperability | `4f536fc04e6fc24b1b148a6ac809ed9792181ceb` |
| [#8](https://github.com/giasonpooni/Parametric-Design-Terminal/pull/8) | Retained curved-path study | `ee726715245f891cdeba176b25295a0a5c3dc39e` |
| [#12](https://github.com/giasonpooni/Parametric-Design-Terminal/pull/12) | Reaction benchmark | `9aef0494dd102785e7c804af07f6c80af98e340d` |
| [#17](https://github.com/giasonpooni/Parametric-Design-Terminal/pull/17) | Real Git fixture for exchange refusal | `11eea765c3b35cb452018e04fe9361160ba3e367` |
| [#19](https://github.com/giasonpooni/Parametric-Design-Terminal/pull/19) | Retained RMS learning path | `ff0a4de72dc3247296b2ae852ffa2c2b3046cc05` |
| [#20](https://github.com/giasonpooni/Parametric-Design-Terminal/pull/20) | Isolated genuine Cantera worker gate | `c2f68e75d525c37c4af1e8fc041f7f9bb81eb308` |
| [#21](https://github.com/giasonpooni/Parametric-Design-Terminal/pull/21) | Qualified interval requirement profile | `6638e8f26363fcf4c7cbd89d460e2e21538d3d57` |
| [#22](https://github.com/giasonpooni/Parametric-Design-Terminal/pull/22) | Conservative CI routing | `47754302451f47491b5ddcfbaa7383b2d6ec70fd` |
| [#23](https://github.com/giasonpooni/Parametric-Design-Terminal/pull/23) | Retained failed native attempts | `b9d4dea8c8eee101969e60034f20e96e19c68bef` |

Integration preserves the main overview and the accepted provider pins, runtime
file closures, numerical profiles and authority boundaries from these inputs.
The existing packaged manifests and operation constants remain authoritative;
this page does not select replacement revisions or qualify newer environments.

## Repairs at the integration boundaries

- **Read-only diagnostics:** `ciw doctor --profile ...` projects existing
  requirements and inspects explicit local bindings. Expected identities remain
  separate from observed bytes and metadata; qualification is always
  `not_performed`. See [doctor](DOCTOR.md) for supported profiles and exclusions.
- **Shared checkout inspection:** installed diagnostics and source-tree gates
  use one validator. It compares index entries with committed tree metadata and
  hashes working bytes without `git status` or worktree diff operations, which
  can execute configured clean filters. Optional index writes and lazy fetching
  are disabled. Initialized submodules receive explicit checks; empty
  uninitialized gitlinks retain their separate provisioning boundary. Operator
  filters and Git configuration are not rewritten.
- **Native failure dependencies:** restoring a retained failed native request
  reuses the existing data-only upstream dependency validation. A failed
  force/energy request cannot lose or substitute the exact trajectory/result
  it names. Restore does not launch a provider or repeat a numerical oracle.
- **Installed JuMP fixture:** synthetic invocation tests supply explicit
  synthetic runtime files instead of assuming the installed wheel sits inside
  a source checkout. Failure cases must reach their intended mocked invocation
  and reason. These tests do not qualify Julia, JuMP or HiGHS execution.
- **Cantera routing:** the existing direct-worker gate retains its positive
  path filters and complete job body. Main-only branch pushes, all tags,
  unrestricted PR targets, manual dispatch and the shared concurrency rule
  remove feature-push/PR duplication. Direct-worker contracts remain distinct
  from installed CIW replay and full reaction qualification.

Failure history retains the existing error behavior without manufacturing a
successful result. Saved workspaces and the Python API retain full immutable
failure records; live views use bounded summaries. Checkpointing or normal
server shutdown persists terminal attempts. This is not crash durability for
in-flight work. See [protocol](PROTOCOL.md) for capacity, identity and retention
rules.

## Reproduce the selected checks

Use the [development guide](DEVELOPMENT.md) for the wheel and harness setup,
[provider availability](PROVIDER_AVAILABILITY.md) for exact existing checkouts,
and each profile's operating guide for isolated runtime provisioning and
operator bindings. Provisioning is explicit and separate from doctor and from
request execution. Keep build outputs outside pinned provider source checkouts.

The following PowerShell example assumes the candidate wheel and required test
harness dependencies are already installed in a separate environment. Replace
the example paths with the selected installation and explicit bindings. Run
from an evidence directory outside the checkout; every gate output directory
must be new.

```powershell
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$checkout = 'C:/ciw/Parametric-Design-Terminal'
$python = 'C:/ciw/candidate-env/Scripts/python.exe'
$bindings = 'C:/ciw/bindings'
$evidence = 'C:/ciw/integration-evidence'
Set-Location $evidence

& $python -I -m ciw doctor --profile core
& $python -I -m ciw doctor --profile native-interop --binding "$bindings/native.json"
& $python -I -m ciw doctor --profile reaction-catalyst --binding "$bindings/catalyst.json"
& $python -I -m ciw doctor --profile reaction-cantera --binding "$bindings/cantera.json"
& $python -I -m ciw doctor --profile interval-requirement --binding "$bindings/interval.json"

& $python -I "$checkout/scripts/check_installed.py"
& $python -I -m pytest "$checkout/tests" --override-ini=pythonpath= -q -p no:cacheprovider --junitxml="$evidence/installed-tests.xml"

& $python -I "$checkout/scripts/check_native_interop.py" --run --binding "$bindings/native.json" --fixtures "$checkout/examples/native-interop/reference_fixtures.json" --output "$evidence/native"
& $python -I "$checkout/scripts/check_reaction_benchmark.py" run --catalyst "$bindings/catalyst.json" --cantera "$bindings/cantera.json" --fixtures "$checkout/examples/reaction-benchmark/fixtures.json" --output "$evidence/reaction"
& $python -I "$checkout/scripts/check_interval_requirement.py" run --binding "$bindings/interval.json" --fixtures "$checkout/examples/interval-requirement/fixtures.json" --output "$evidence/interval"

& $python -I "$checkout/scripts/check_reaction_benchmark.py" inspect --workspace "$evidence/reaction/workspace.json" --artifacts "$evidence/reaction-reopened"
& $python -I "$checkout/scripts/check_interval_requirement.py" inspect --workspace "$evidence/interval/workspace.json" --artifacts "$evidence/interval-reopened"
```

The ordinary native command above executes its selected subset. A full native
integration claim additionally requires `--require-all`, including the separate
proof and sanitizer evidence; omission does not waive those gates. General
pytest results can contain unavailable optional-provider skips. Required
profile qualification must retain its existing zero-skip checks.

The owning guides are [native interoperability](NATIVE_INTEROP.md),
[reaction benchmark](REACTION_BENCHMARK.md),
[interval requirements](INTERVAL_REQUIREMENT.md),
[curved-path study](CURVED_PATH_STUDY.md), and [retained RMS](LEARNING.md).
Their validation pages describe profile-specific evidence and limits. The
curved study and RMS commands remain independently reproducible from those
guides; the three benchmark commands above do not qualify them by association.

For routing checks, install the dev extra. It pins `PyYAML==6.0.3`. The
Workflow contracts job installs that same extra and does not carry a second pin:

```sh
python -m pip install -e '.[dev]'
python -m unittest discover -s scripts/tests -p test_ci_policy.py -v
python scripts/check_ci_policy.py
actionlint -shellcheck= -pyflakes=
```

A passing routing check validates CI selection policy only. It is not qualification.

## Validation record

The scientific benchmark wheel has SHA-256
`82f1a8c477852f432337cb756b546bf965013f1d15efcbda22ad2d31b0765593`.
The final diagnostic-fix wheel has SHA-256
`82a63816f9b708e8fc2cc90947e05468b00079c3eb395fe79023c596c0662bf6`.
The retained `wheel-comparison.json` records exactly three changed archive
members: `ciw/doctor.py`, `ciw/provider_checkouts.py`, and the distribution's
`RECORD`. Scientific implementation files, profile pins and packaged runtime
manifests are identical between those wheels. This comparison explains which
scientific evidence is transferable; it does not rename an earlier run as a
run of the final wheel. Final diagnostics and installed checks must identify
the final wheel separately.

| Evidence | Final result |
| --- | --- |
| Final installed-wheel regression and installed-package smoke | 2,044 passed, 715 optional-provider skips, 38 subtests passed (`regression-final.xml`); installed generation, analysis, RMS lesson and replay smoke passed |
| Doctor, shared checkout and integration regressions | 144 passed, zero skips (`combined-focused-final.xml`): 78 pinned curved-path checks, 25 doctor checks, 34 checkout checks, six retained-dependency checks and one genuine Cantera failure/recovery check |
| Native benchmark | 16 PASS, five NOT_RUN (`native/report.json`); native subset passed, full completion false |
| Reaction benchmark | All 15 checks passed (`reaction/report.json`): four fixtures through each real engine, four cross-engine comparisons, two fresh replays and ten-bundle offline reopen |
| Interval benchmark | Six rational-reference fixtures and explicit fresh replay passed; seven retained bundles reopened (`interval/report.json`). Requirements include holds, fails and inconclusive outcomes, each checked against its reference |
| Final-wheel provider-free reopen | Reaction: ten bundles; interval: seven bundles. `reaction-final-reopen.log` and `interval-final-reopen.log` report `fresh_execution: false`; inspection is not replay |
| Genuine Cantera worker | All 13 tests passed, zero skips (`cantera-worker-final.xml`), including numerical failure and recovery |
| Godot validation | Headless import, live protocol, channel, adapter and experiment views passed (`godot.log`) |
| Workflow policy and actionlint | 12 tests and six subtests passed (`ci-policy-final.xml`); 18-workflow event-policy check and all-workflow actionlint passed |

The [generated observation inventory](qualification/integration-2026-09-27.json)
records report hashes, benchmark rows, runtime observations and both wheel
identities. Raw logs and retained workspaces are local run artifacts, not
bundled in that summary. The 715 skips describe unavailable optional bindings
in the broad run; they are not passing qualification. The separately selected
144-test and 13-test runs had no skips.

These runs used Windows x86_64, a separate Python 3.12.14 harness with NumPy
2.4.3, Julia 1.10.12, the manifest-bound Catalyst 16.4.3 and Cantera 3.2.0
environments, and IntervalArithmetic 1.0.12. The actual source checkouts were:

| Selected path | Observed provider commit |
| --- | --- |
| Native Rust/C++/Julia | SCR `fd61efb3e0e5868d0f95ba27706b64a9afca595f` |
| Catalyst and Cantera | SCR `7e41b5a104526929c531a069a9872cf92ab277cc` |
| Interval requirement | SCR `2a144e252607546ca6b20e6dd4613d3a4146758a` |
| Curved-path study | CSG `bbc535af29c30997e56fd120320c570830676462` |

These are observations of this run, not additional allowlists. Native manifest
and runtime files are unchanged from #21. Host executable digests remain
operator bindings without source-to-binary attestation. The native benchmark's
five NOT_RUN gates are the separate exact checker, SP1 proof/fresh verification,
UBSan, legacy-worker adversarial protocol and physical validation.

The genuine Cantera recovery test observed the pinned host's `RUNTIME_FAILED`
boundary. It retained a failed attempt with no result and no captured runtime,
reopened without providers, explicitly rebound the runtime, and preserved both
the failure and earlier success after a fresh successful occurrence. It does
not relabel that outer failure as a captured inner worker response.

## Remaining acceptance gates

Private hosted provider access remains unresolved. Local exact checkouts do
not establish that Actions can fetch every required private or historical
commit. The selected trusted qualification context needs deliberately scoped
read access; untrusted PR jobs must not receive privileged credentials.
No repository visibility, secrets, branch protection or ruleset setting is
changed by this candidate.

This is a combined candidate, not a full release or a completed first-operator
acceptance exercise. Unselected providers and environments remain unqualified.
Doctor preflight, synthetic tests and retained inspection do not establish a
loaded worker or a fresh scientific execution. Numerical/reference checks do
not upgrade physical validity, calibration, SP1 verification, independent proof,
admission or equipment authority. Existing source-to-binary and environment
attestation limits remain in force.

CI routing is still the conservative #22 policy, with the separate path-scoped
Cantera worker gate. Prototype checks still include optional integration work;
the repository has not yet been split into minimal core, affected-profile and
release qualification gates. A green routing check establishes selection
behavior only. Provider qualification, release packaging and first-operator
acceptance remain distinct decisions backed by their own reports.
