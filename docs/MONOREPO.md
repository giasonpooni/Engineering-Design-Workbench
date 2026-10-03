# Incremental engineering monorepo

This draft migration brings selected engineering instruments into the
Notations Systems Terminal repository while retaining independently runnable
packages and explicit provider bindings. Repository location becomes a shared
development boundary; it does not combine evidence, operation, execution,
result, verification, admission or device-control authority.

The implementation is on the local branch
`feat/engineering-monorepo-wave2-20261003`, awaiting native Git transfer. This
cumulative branch extends the first measurement wave. It
has not been published as a GitHub pull request or merged into the default
branch.

The existing [cross-system architecture](CONSOLIDATION.md),
[execution responsibilities](EXECUTION_RESPONSIBILITIES.md) and
[integration coverage](INTEGRATION_COVERAGE.md) remain the governing descriptions
of those boundaries. This page records the migration and its qualification
requirements; it does not replace the scientific contracts.

## First import wave

The first wave contains two public measurement instruments:

| Directory | Original repository | Imported source revision |
| --- | --- | --- |
| `instruments/measurement/calibration` | [Notations-Calibration-Runtime](https://github.com/giasonpooni/Notations-Calibration-Runtime) | `e41f61cf5909e58a1a2e60612308ccffe0bfe7de` |
| `instruments/measurement/clocksync` | [Notations-ClockSync](https://github.com/giasonpooni/Notations-ClockSync) | `13c5fe75c7e829c24bae12fcf8386d4831224d4e` |

## Second import wave

The second wave adds five public instruments, bringing the cumulative total to
seven independently packaged modules:

| Directory | Original repository | Imported source revision |
| --- | --- | --- |
| `instruments/mathematics/observability` | [Notations-Observability-Testbed](https://github.com/giasonpooni/Notations-Observability-Testbed) | `9d22326c9e230f0d8d21b00ce210e10e72e968fd` |
| `instruments/inference/state-inference` | [Notations-State-Inference-Engine](https://github.com/giasonpooni/Notations-State-Inference-Engine) | `4ec062bb72caa76ce1405f2851766589cee9d160` |
| `instruments/inference/state-recompiler` | [Notations-State-Recompiler](https://github.com/giasonpooni/Notations-State-Recompiler) | `fb01b4a702ba9314b211f933eda800a1e3e9efed` |
| `instruments/inference/faultsense` | [Notations-FaultSense-RunTime](https://github.com/giasonpooni/Notations-FaultSense-RunTime) | `00a3f3537964374efbf72d82e4188db002457cd8` |
| `instruments/verification/estimator-bench` | [Notations-Estimator-Bench](https://github.com/giasonpooni/Notations-Estimator-Bench) | `928ae6a76d4f853aa8306fef8207f81244b7066f` |

Each import uses a non-squashed subtree merge. The original revision and all its
ancestor history remain reachable with their original commit SHAs. The subtree
contains the exact original source tree at that revision, including package
metadata, tests, workflow files, licences and notices. Module-internal paths
remain unchanged beneath the import directory.

The retained history includes ancestors of each imported default-branch
revision; this is not a claim to import every remote draft branch or tag.

Preserving a module's `.github/workflows` files retains its source configuration.
GitHub does not discover nested workflow directories as root workflows; the
monorepo gate separately executes the imported checks. Each module retains its
package, interfaces, test suite and release identity. This migration does not
publish a new module release or change the original repositories' status.

## Source history and executable bindings

An imported current source tree and a qualified executable source revision are
different identities. Existing NET contracts continue to bind these historical
provider revisions:

| Provider role | Existing NET source revision |
| --- | --- |
| `mcur` — calibration | `49405ecd623474ddf601989b0a8195be401544e0` |
| `tbrt` — clock synchronization | `40507060ca7a9126a9d641999b994a757eef3bfd` |
| `oit` — observability | `db4c564bddbe1911f96585bd18f58659a0026fb7` |
| `gsie` — state inference | `5241eee6dab434533bdf0cf0e824bc43b4a79831` |
| `cbsr` — state reconciliation | `daf43fc870ba926289c3bc4908db784691c7addd` |
| `fdir` — fault diagnostics | `29e4b306492b793487d47a96b97a56548217aa12` |
| `set` — calibrated-observable replay verification | `5e7bda36f521a5c1b0082b512f35e29803bffafc` |

These are the existing
[`calibrated-observable` runtime declarations](../src/ciw/calibrated-observable-runtimes.json).
Other workflows retain their own pins. In particular, the original measurement
gate's SET exchange-contract dependency remains at
`bd261a765281a95312f7c91a3857233476294c5b`; the GSIE exchange checker uses SET
`542e672be512bf43b61253f2b2a43cd967cb3062`. These separate bindings are not
silently substituted with the latest imported SET revision.

The eight-provider calibrated-observable loop also uses the public
[Notations-FlowState](https://github.com/giasonpooni/Notations-FlowState)
repository, retaining its `fsrt` role and original package interfaces, at
`d7c181fb9967883e085b3728d38096f59e54efbd`. FlowState is externally provisioned;
its source tree and history are not imported or included in the cumulative
migration bundle.

The `provider_worktrees` helper in `scripts/monorepo.py` materializes temporary
standalone detached worktrees at those original revisions from the retained Git
history. The migration gate uses this helper. These are ordinary provider
checkouts with the expected module-internal paths and exact Git `HEAD` during
the declared execution; existing external checkouts can still be supplied to
the stack-root interfaces.

`PinnedSubprocessAdapter` remains unchanged. It checks the original qualified
revision and uses the existing subprocess protocol. A provider binding does
not silently execute the imported current source tree, a dirty checkout, or the
monorepo's `HEAD`. Updating a runtime pin requires a separate compatibility
change and qualification of the affected compositions.

Existing public and private provider routes remain available. Co-locating
source does not remove external checkout support, require all providers in one
process, or grant a provider authority over another module's state.

## Packaging and checks

The root wheel continues to package `ciw`. It does not bundle imported provider
packages into the NET installation. Each of the seven instruments retains its
own package metadata and is built and installed as a separate wheel.

Audit the migration's source trees and retained history from the repository
root:

```sh
python scripts/monorepo.py
```

Run the original measurement migration gate:

```sh
python scripts/check_monorepo.py
```

The measurement gate retains its configured Python 3.11 and 3.12 CI matrix.

The gate builds and installs the current imported module wheels independently
and runs their unchanged test suites. It separately prepares the older exact
NET provider worktrees from retained history and exercises a clock-to-calibration
composition through the existing pinned adapter. Source-tree tests and the
qualified historical execution therefore have separate source identities.
Use `--output-dir /path/to/results` to select the retained gate output location.

The first-wave measurement qualification keeps its existing SET contract
binding at `bd261a765281a95312f7c91a3857233476294c5b`. The second wave retains
that revision in the imported SET history, allowing the same standalone
checkout to be materialized without a new external source import. An existing
exact checkout can still be supplied through the original option:

```sh
python scripts/check_monorepo.py --set-root /path/to/qualified-set --output-dir /path/to/results
```

Run the second-wave gate with Python 3.12 or later, matching the pinned public
FlowState package's requirement. Its configured CI matrix uses Python 3.12 and
3.13:

```sh
python scripts/check_monorepo_inference.py --output-dir /path/to/inference-results
```

By default, the gate provisions FlowState from its public repository. To reuse
a standalone FlowState repository containing both declared historical commits:

```sh
python scripts/check_monorepo_inference.py --flowstate-root /path/to/flowstate --output-dir /path/to/inference-results
```

This gate builds the independent instrument wheels and runs their unchanged
suites, with explicit optional dependency bindings. It also executes the
existing complete calibrated-observable workflow through the seven imported
providers at their historical NET pins and the actual external FlowState
generator. The original `create_session` and `replay_session` functions,
fixtures, runtime manifest and scientific adapters remain unchanged. The
result is an actual eight-provider session and replay, with the original SET
content-binding and numerical-replay receipt. SET records `independent: false`;
admission remains `not_performed`. This exercises FlowState's declared generator
and the two separate public CBSR comparisons; it does not qualify FlowState's
complete test suite.

The synthetic fixture retains device times `[1005, 2004]` and raw values
`[51000, 45000]`. Clock mapping produces event times `[5, 5]`; calibration gives
`[52, 46]` with covariance `[[1, 0.25], [0.25, 1]]`. OIT requires the exact GSIE
model, rank 2 and condition number 1. GSIE produces posterior means
`[607/12, 589/12]` and retains innovation `[2, -4]` with covariance
`[[1.25, 0.25], [0.25, 1.25]]`. CBSR accepts the declared total of 100 kg and
produces `[50.75, 49.25]`. FDIR uses the retained prior innovation and its full
covariance, obtaining NIS `58/3` and a tank-2 bias nomination within the declared
signature set. These are the unchanged fixture's analytic expectations, not
physical measurement results.

The full-session tests exercise unknown calibration covariance, missing clock
authority, expired calibration and refused observability states. Held CBSR
results retain the candidate; unknown FDIR cross-covariance retains detection
but prevents a unique nomination. Rehashed content substitutions and forged
numerical output cannot pass the corresponding retained-content and actual
recomputation checks. Fresh replay occurrences have different session,
execution and result identities while matching numerical identities.

Independent module tests retain their earlier exchange dependencies rather
than relying on a coincidentally compatible latest installation. The gate uses
separate current and legacy SET contract environments, the exact GSIE SET
checker, and the historical Terminal revision
`1ec11eb46bcf19ec57b40603dcd5921d284307ff` for GSIE's existing CLI comparison.
These are recorded test dependencies, separate from the eight-provider session
runtime identities.

Two optional CBSR comparisons depend on the private geometric telemetry
provider and remain explicitly unqualified:

- `test_gte_pinned_fixture_tangent_at_basepoint_has_same_covariance_projection`
- `test_affine_tangent_is_not_silently_promoted_to_global_circle_projection`

The gate retains these exact skipped cases in its report. It requires the
remaining declared tests to pass and rejects unexpected skips. CBSR's separate
public FlowState comparisons use their original
`56a2bea58ad2657e5aacf0181fe2d0b982b09f3b` pin and file hashes; that dependency
is distinct from the generator used by the full calibrated-observable loop.

Observed qualification on Linux with Python 3.12.14 passed 677 provider tests,
retaining exactly the two named GTE comparisons as unqualified skips, executed
11 unchanged examples, and passed all 45 original calibrated-observable tests.
The retained original and replay sessions have matching numerical results and
fresh occurrence identities. Separate runs passed 13 migration tests and 105
measurement tests; the 105 measurement cases also occur in the provider run and
are not additional unique tests. The CI matrices are configured but have not
been remotely executed for this migration.

Passing these checks establishes packaging, source-history preservation,
declared provider compatibility and the exercised computational behavior. It
does not establish numerical improvement, new scientific scope, calibrated
physical measurements, physical validation, canonical admission or permission
to actuate a machine. The existing synthetic fixtures retain their original
scope and uncertainty assumptions.

## Remaining staged groups

The following groups retain the staged architecture map. The status column
distinguishes imported members from the remaining migration backlog.

| Area | Existing or staged projects | Migration status | Boundary to preserve |
| --- | --- | --- | --- |
| Terminal and composition | Systems Terminal, Scientific Language Runtime, Inference Schematics Engine, Retrieval Agent | Terminal remains the substrate; other members deferred | Workflow composition and operation dispatch |
| Evidence and execution | State Ledger, Data Intake, Compute Runtime | Deferred | Separate evidence, operation, execution and verification identities |
| Measurement | Metrology, Calibration, ClockSync, Signal Processing | Calibration and ClockSync imported; other members deferred | Raw observations, calibration lineage and uncertainty |
| Inference and diagnostics | State Inference, State Recompiler, FaultSense, Estimator Bench | All four imported in the second wave | Candidate estimates remain separate from admitted state |
| Mathematical instruments | Observability, SensorDesign, Sensitivity, Linear Dynamics, Surface, Periodic Space, Polygon Trajectories | Observability imported; other members deferred | Explicit mathematical scope and numerical limitations |
| Domain tools and views | FlowState, Estimator for BIM, FrameMapper, Real-Time Globe | FlowState remains an external provider; source imports deferred | Domain authority and representation authority remain explicit |
| Resource and device adapters | Yield-Weighted Runtime, CNC Machine MCP | Deferred | Budget settlement and machine execution retain their own gates |

Several candidates are deliberately deferred:

- Private `Notations-Data-Intake` and `Periodic-Space` remain outside the public
  migration. Import requires an explicit visibility decision or a retained
  private boundary.
- The currently README-only Scientific Language Runtime and Inference
  Schematics Engine repositories are not executable import candidates in this
  wave.
- State Ledger is public, but its missing licence must be resolved before an
  import or combined distribution is proposed.
- `1792` and `A Man of Two Worlds` remain independent game-product repositories
  consuming declared, versioned Notations interfaces. Their content, assets,
  game state and release lifecycle remain product-owned.

Before each additional import, record the exact original repository identity,
visibility, source revision and tree; verify that retained history includes the
qualified runtime pins; preserve licence files, notices and package metadata;
identify the current consumers, release identity and ownership; and declare
the intended subtree path without altering module-internal paths.

Qualify each imported package independently, then execute at least one actual
composed workflow through its existing interfaces. Check refused and held
cases where the composition depends on those states. Any changed contract,
runtime pin, package route or authority boundary requires its own review and
checks. Record qualification against exact source and execution identities
before expanding the next wave.

## Licences and transition

Calibration, ClockSync, Observability, State Inference and FaultSense retain
their original MPL licence files and notices where supplied. State Recompiler
retains its AGPL licence; Estimator Bench retains its Apache licence. Original
package metadata is preserved, including differing licence field forms and
fields that were not declared by a source package. The root NET package retains
its existing AGPL terms. Import does not replace module terms with a blanket
repository
licence, remove upstream attribution, or determine the terms of a future
combined distribution. Distribution decisions require a separate assessment
of the components and how they are packaged and used.

Keep the original repositories available during the transition. This draft
does not archive repositories, change releases, merge the migration into the
default branch, or redirect consumers. Those are separate steps after consumer
migration and the relevant checks have been completed.

## Native Git transfer

The migration can be transferred in a Git bundle containing the native import
commits and retained original histories. Verify the bundle and fetch its branch
into an authenticated checkout of the Terminal repository, then push that
branch:

```sh
git bundle verify /path/to/migration.bundle
git fetch /path/to/migration.bundle refs/heads/feat/engineering-monorepo-wave2-20261003:refs/heads/feat/engineering-monorepo-wave2-20261003
git push origin feat/engineering-monorepo-wave2-20261003
```

Review the resulting branch before a default-branch merge. Use a merge commit
when merging the migration so the original source commits remain ancestors of
the resulting branch. A squash or rebase merge would lose that ancestry and
would not satisfy this migration's history-preservation requirement. Recreating
the imported files through a file-content API also does not preserve the
original commits.
