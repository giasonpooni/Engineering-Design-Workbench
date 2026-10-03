# Incremental engineering monorepo

This draft migration brings selected engineering instruments into the
Notations Systems Terminal repository while retaining independently runnable
packages and explicit provider bindings. Repository location becomes a shared
development boundary; it does not combine evidence, operation, execution,
result, verification, admission or device-control authority.

The first wave and its audit corrections are developed on
`feat/engineering-monorepo-wave1-audit-20261002`. Review and scoped qualification
remain separate from a default-branch merge.

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
packages into the NET installation. Calibration and clock synchronization have
their own package metadata and are built and installed as separate wheels.

Audit the migration's source trees and retained history from the repository
root:

```sh
python scripts/monorepo.py
```

Run the migration gate:

```sh
python scripts/check_monorepo.py
```

The gate builds and installs the current imported module wheels independently
and runs their unchanged test suites. It separately prepares the older exact
NET provider worktrees from retained history and exercises a clock-to-calibration
composition through the existing pinned adapter. Source-tree tests and the
qualified historical execution therefore have separate source identities.
Use `--output-dir /path/to/results` to select the retained gate output location.

The gate binds NET's tracked source bytes and index to the reported commit
before building, and rechecks them after execution. Ignored or untracked
executable sources are refused. The first wave deliberately freezes imported
subtrees at their original import trees; subsequent module development must
add a separately identified current-source qualification while retaining the
original import commit and qualified historical runtime pins.

The optional SET exchange-contract dependency remains external. Its public source
is available through the
[Notations-Estimator-Bench](https://github.com/giasonpooni/Notations-Estimator-Bench)
repository alias at the qualified revision
`bd261a765281a95312f7c91a3857233476294c5b`. The gate requires that exact checkout
to run all optional exchange tests without skips; it does not import SET into
this first wave or perform independent scientific verification.
Its source revision, runtime route and verification scope remain explicit.

```sh
python scripts/check_monorepo.py --set-root /path/to/qualified-set --output-dir /path/to/results
```

Passing these checks establishes packaging, source-history preservation,
declared provider compatibility and the exercised computational behavior. It
does not establish numerical improvement, new scientific scope, calibrated
physical measurements, physical validation, canonical admission or permission
to actuate a machine. The existing synthetic fixtures retain their original
scope and uncertainty assumptions.

## Remaining staged groups

The following groups describe a migration backlog. Inclusion in this table
does not mean a repository is already imported or qualified.

| Area | Candidate projects | Boundary to preserve |
| --- | --- | --- |
| Terminal and composition | Systems Terminal, Scientific Language Runtime, Inference Schematics Engine, Retrieval Agent | Workflow composition and operation dispatch |
| Evidence and execution | State Ledger, Data Intake, Compute Runtime | Separate evidence, operation, execution and verification identities |
| Measurement | Metrology, Calibration, ClockSync, Signal Processing | Raw observations, calibration lineage and uncertainty |
| Inference and diagnostics | State Inference, State Recompiler, FaultSense, Estimator Bench | Candidate estimates remain separate from admitted state |
| Mathematical instruments | Observability, SensorDesign, Sensitivity, Linear Dynamics, Surface, Periodic Space, Polygon Trajectories | Explicit mathematical scope and numerical limitations |
| Domain tools and views | FlowState, Estimator for BIM, FrameMapper, Real-Time Globe | Domain authority and representation authority remain explicit |
| Resource and device adapters | Yield-Weighted Runtime, CNC Machine MCP | Budget settlement and machine execution retain their own gates |

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

The calibration and clock synchronization directories retain their MPL licence
files and notices. The root NET package retains its existing AGPL terms.
Import does not replace either module's terms with a blanket repository
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
git fetch /path/to/migration.bundle refs/heads/feat/engineering-monorepo-wave1-audit-20261002:refs/heads/feat/engineering-monorepo-wave1-audit-20261002
git push origin feat/engineering-monorepo-wave1-audit-20261002
```

Review the resulting branch before a default-branch merge. Use a merge commit
when merging the migration so the original source commits remain ancestors of
the resulting branch. A squash or rebase merge would lose that ancestry and
would not satisfy this migration's history-preservation requirement. Recreating
the imported files through a file-content API also does not preserve the
original commits.
