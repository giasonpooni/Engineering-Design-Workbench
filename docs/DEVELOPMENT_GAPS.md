# Development-window gap audit

Audit date: 2026-09-26. This follows the native interoperability, curved-path
study and bounded Catalyst/Cantera increments. It distinguishes executable
repairs from research proposals and external qualification gates.

## Reviewed state

- PDT reaction head: `a785ab3b7836c31a46c7681aa037c43a2374120b`, tree
  `9ff0ca333b729e82b0994e499100e9125a2a3e9c`, before this follow-up.
- SCR reaction head remains `7e41b5a104526929c531a069a9872cf92ab277cc`, tree
  `87d395d65a4e3ac1a7501f6ba17e61f8aefded1b`.
- Concurrent PDT main is `209b17bd396e26a2ff387847ee40ac0b25060fc1`;
  its additional README design-space/OpenUSD clarification is preserved on main.
- The reviewed draft stack is [PDT #12](https://github.com/giasonpooni/Parametric-Design-Testbed/pull/12)
  over [#8](https://github.com/giasonpooni/Parametric-Design-Testbed/pull/8), with
  [SCR #2](https://github.com/giasonpooni/Scientific-Computation-Runtime/pull/2).
  A separately opened [PDT #11](https://github.com/giasonpooni/Parametric-Design-Testbed/pull/11)
  targets main from the same reaction branch. This audit does not merge, retarget,
  or close either review route.

## Gaps repaired

| Inconsistency | Repair and boundary |
| --- | --- |
| GitHub rejected reaction/native workflows before creating jobs | Move runner-local paths from unsupported job-level `runner.temp` expressions into initialization steps writing `GITHUB_ENV`; add version/hash-pinned actionlint checks across all workflows |
| Python provisioning requested an unavailable uv download | Use the explicitly installed Python 3.12.14 interpreter. uv 0.10.10 creates the environments but does not download that Python version. Check the resulting executable against the existing qualification before installation/execution |
| Required-provider failures lost diagnostic artifacts | Always retain job/setup state, expected and observed qualification data, JUnit if produced, and partial benchmark evidence. A job-status file cannot establish numerical qualification |
| Retained reaction metadata could contradict itself | Require the common discrepancy to equal its declared concentration metric exactly. This checks copied metadata; it does not rerun an oracle or authenticate a scientific claim |
| Benchmark fixtures were unbounded and accepted duplicate JSON keys | Apply a 256 KiB read limit, strict JSON parsing and complete per-source validation before output creation or provider consultation |
| Reports retained only a fixture digest | Retain exact `fixtures.json` bytes as well, and name both compared bundles plus replay source/result occurrences in report rows |
| Reopen gate checked only bundle count | Compare the complete serialized workbench before/after reopen, with provider dispatch and reference computation prohibited |

Provider revisions, worker/package hashes, operation identities, admission rules,
uncertainty declarations and scientific tolerances are unchanged.

## Hosted CI observations

The initial [reaction workflow record](https://github.com/giasonpooni/Parametric-Design-Testbed/actions/runs/36274574603)
had no jobs. Local actionlint independently reproduced the four unsupported
context references across reaction/native workflows. Parsing YAML alone had not
caught this Actions-specific error.

Several existing integration lanes failed during provider retrieval, before
scientific tests could run:

- [Calibrated adapter job](https://github.com/giasonpooni/Parametric-Design-Testbed/actions/runs/36274954609)
  could not authenticate the RCI clone.
- [Exchange job](https://github.com/giasonpooni/Parametric-Design-Testbed/actions/runs/36274954623)
  received `Repository not found` for its exact SET checkout.
- [Prototype PLSR job](https://github.com/giasonpooni/Parametric-Design-Testbed/actions/runs/36274954614)
  could not authenticate the pinned optional package dependency.
- [Proved-heat job](https://github.com/giasonpooni/Parametric-Design-Testbed/actions/runs/36274954704)
  could not authenticate SCR retrieval.

Repository metadata independently confirms that SCR, RCI, SET and PLSR are
private at this audit. These observations do not establish missing commits or
numerical defects. An
independently authorized provider-access mechanism must cover the exact current
and historical repositories. No credentials are synthesized, repository visibility
changed, pins advanced, or required gates skipped here. The reaction workflow now
explicitly requires `SCR_READ_TOKEN`; the broader provisioning options and access
boundaries are in [Provider Availability](PROVIDER_AVAILABILITY.md).

The same prototype run passed Linux and Windows Python 3.11/3.12, installed-wheel,
Godot bridge, native Windows service and container-deployment jobs. That is useful
integration evidence, but it does not qualify the failed provider lanes.

## Follow-up validation

- Focused contract, benchmark orchestration and retained metadata tests:
  **123 passed** from source and again from the isolated installed wheel.
- Genuine installed Cantera workflow: **9 passed**, with the nine Catalyst cases
  explicitly deselected for this follow-up. Both genuine providers' earlier
  qualification remains recorded separately in [Reaction Validation](REACTION_BENCHMARK_VALIDATION.md).
- Fresh one-fixture two-engine benchmark: **6 PASS gates**, covering Catalyst,
  Cantera, cross-engine comparison, both fresh replays and exact reopening of
  **4 bundles**. Exact fixture retention and comparison/replay report references
  were checked.
- All **10** previously qualified two-engine/replay bundles reopen with exact
  retained content, no provider/oracle execution and unchanged workspace bytes.
- Final wheel SHA-256:
  `2ae89f3237bbdd81c876d1fcb2e6cfb8c78e3267bd7da47c70197346f9bbe810`.
  All **104** packaged source/resource files match the checkout.
- actionlint **1.7.12** checks all workflow definitions successfully; shellcheck
  and pyflakes are explicitly disabled. All seven reaction PowerShell blocks also
  parse successfully. The actual embedded binding-preflight code was also
  exercised with an unavailable executable: it retained the expected closure and
  bounded failure reason without dispatching a provider. These checks do not
  execute a hosted job.
- Broad regression: **1783 passed, 688 optional-provider skips and 38 subtests
  passed** in 320.86 seconds. Four additional skips relative to the earlier
  broad run reflect the final Catalyst identifier/nonfinite parametrizations;
  their genuine worker qualification remains in the earlier separate 18-test run.

Local records are `results/development-gap-{tests,installed,cantera,regression}.xml`
and `results/development-gap-inspection.json`. They are not presented as public
Actions artifacts. The fresh one-fixture evidence is in
`work/reaction-gap-smoke-1`: report SHA-256
`a9c3b7161b5a31ef23975fac5c8af55607a6fa5ce666df2c2c9ecea59561e804`,
workspace SHA-256
`75bb8ab39b94d91bba9dd2e2db0b38a045e7f4ec9eebf2f3a906d272c73214f7`.
The previous four-fixture 15-gate benchmark remains the earlier qualification;
it has not been relabelled as a new execution.

## Remaining development sequence

| Work | Evidence needed to close it |
| --- | --- |
| Hosted reaction qualification | Valid workflow, authorized SCR access and an exact independently provisioned runtime closure, followed by required tests and the full two-engine benchmark |
| Runtime portability/attestation | Qualify additional executable/package identities and source-to-binary relationships; do not infer them from language versions |
| Shared profile/capability discovery | A data-only registry tied to existing contracts and explicit refusal when capabilities are absent; registration grants no execution authority |
| Typed composition and frames | Explicit quantity/order/unit/frame/clock compatibility, retained dependency references and declared transform uncertainty before connecting providers |
| ESM candidate handoff/invalidation | An accepted candidate contract and correction/re-evaluation demonstration, with capture remaining unadmitted |
| CSE/GSV measured spatial integration | Surveyed frame chains and representation sufficiency; quantity-only or visual outputs cannot stand in for measurement authority |
| Independent reaction conformance | A reviewed ICRH reaction profile and independent reference evidence |
| Physical or coupled chemistry | Held-out measurements, calibration/uncertainty and justified thermal/coupling semantics beyond the abstract isothermal A-to-B case |
| FPGA and equipment operation | Simulation/arithmetic qualification and separately authorized hardware commissioning; no board or actuation authority is assumed |

The [consolidation roadmap](CONSOLIDATION.md) owns the proposed cross-domain
structure. This audit fills specific implementation gaps; it does not claim that
every research direction discussed in the development window is complete.


## Exact follow-up files

- [.github/workflows/native-interop.yml](../.github/workflows/native-interop.yml)
- [.github/workflows/reaction-benchmark.yml](../.github/workflows/reaction-benchmark.yml)
- [.github/workflows/workflow-contracts.yml](../.github/workflows/workflow-contracts.yml)
- [docs/DEVELOPMENT_GAPS.md](DEVELOPMENT_GAPS.md)
- [docs/REACTION_BENCHMARK.md](REACTION_BENCHMARK.md)
- [docs/REACTION_BENCHMARK_VALIDATION.md](REACTION_BENCHMARK_VALIDATION.md)
- [docs/README.md](README.md)
- [scripts/check_reaction_benchmark.py](../scripts/check_reaction_benchmark.py)
- [src/ciw/native_interop.py](../src/ciw/native_interop.py)
- [tests/test_reaction_benchmark.py](../tests/test_reaction_benchmark.py)
- [tests/test_reaction_retained_metadata.py](../tests/test_reaction_retained_metadata.py)
