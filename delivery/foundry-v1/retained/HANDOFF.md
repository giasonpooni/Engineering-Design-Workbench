# NET Game Foundry / 1792 — implementation bundle

This increment adds a game-owned production workload to the existing NET
Production Work Orders controller. It is not a new engine or an autonomous studio.

## Exact repository revisions

| Repository | Revision | Review |
|---|---|---|
| NET | `67225cb061560ad26218ea8473a6b70fb3ab98c1` | Draft PR #68, stacked over PR #65 |
| 1792 | `2bb8a16e63716d54de2d4e97daabc4671d3e07f4` | Draft PR #30, based on main `5b19fda` |

NET base: `98386f4dfa621f6340670755603abd229be4684f`.
1792 base: `5b19fda41a50516bc595c32a5455c07016b90212`.
No main branch was merged or changed by this increment.

Review links:
- https://github.com/giasonpooni/Notations-Engineering-Terminal/pull/68
- https://github.com/giasonpooni/1792/pull/30

## Implemented commands

`net foundry compile`, `run`, `inspect`, `report`, and `export`.
The installed recipe is `1792.water-round.v1`; compilation produces data-only,
source-locked work orders for the existing production controller. A one-trip
candidate is rejected by fixed independent acceptance, a declared two-trip
correction can succeed, and only an accepted primary job unblocks regression.
The game reducer, 180-tick clock, and pending-draw save/load stay in 1792.

All attempts are retained in the original NET Session. Inspection and reporting
need no game process. Export emits the accepted primary observation bytes with
an identity-bound manifest, not a release or a playable executable.

## Checkout and run

In existing clones, fetch the corresponding branch before selecting the exact
commits above. Alternatively use the complete source archives retained by CI in
this bundle. The patch files require their declared bases and are alternatives
to checking out the completed branches; do not apply them twice.

From the NET source directory:

```sh
python -m pip install -e '.[dev]'
net foundry compile 1792.water-round.v1 --game-root ../1792/game --output-dir results/water-order
net foundry run results/water-order --game-root ../1792/game --godot /absolute/path/to/godot --godot-sha256 sha256:YOUR_VERIFIED_EXECUTABLE_DIGEST --output-dir results/water-production
net foundry inspect results/water-production
net foundry report results/water-production
net foundry export results/water-production --destination results/accepted-water-artifact
```

On Windows, substitute quoted Windows paths for `--godot` and `--game-root`.
Use PowerShell `Get-FileHash -Algorithm SHA256` to measure your selected engine
executable. The bound digest has the form `sha256:<64 lowercase hex characters>`.
A measured hash detects drift; it does not prove that an untrusted binary is safe.
Every output directory must be new. The CI-qualified Linux executable digest is
recorded in the native qualification evidence; it is not the Windows digest.

## Verified results

NET Foundry workflow run `36529817204`: all three jobs successful.
Ubuntu and Windows each passed 329 source tests and 38 installed-wheel tests,
with no failures, errors, or skipped tests. The wheel tests ran outside checkout.
These counts are repeated executions across platforms, not 734 unique tests.

Native Godot 4.5.1 executed eight attempts across five campaigns and produced
seven captured results. Baseline and declared-correction campaigns completed.
Exhausted repair rejected, missing observations held, and native process failure
refused; all three blocked dependent work. Both diagnostic failure campaigns used
separately locked, explicitly labelled modified adapter copies.

Every native campaign was independently reopened offline with process creation
forbidden. Original records stayed byte-identical; the accepted primary export
was reproduced exactly. It is an 18,178-byte observation artifact, not a game build.

The NET CI archive captures GitHub's synthetic PR merge commit
`9f19b2c1dd6519255341e34acc6030813b42e057`, whose tree
`da84b094d3527ab5ddf47eb4f59a69da9b15d00a` equals the candidate head's tree.
The game source archive is exactly the pinned game commit above.
The game Command story checks also passed in run `36529737955`.
Other NET workflows are not all green; this is not a repository-wide CI claim.

## Evidence and scope

The `evidence` directory and qualification records distinguish non-native unit
tests from actual engine execution. The initial native trial refused a valid
request before gameplay. The follow-up changes numeric request validation in the
game adapter; NET's fixed acceptance, gameplay rules, and engine version stay
unchanged. Do not interpret the initial failure artifact as a successful run.

The adapter uses explicit completed-inquiry and pose fixtures. It does not prove
input-driven walking, visual quality, historical authenticity, frame rate, or a
complete playable build. The disposable worker directory is not an OS, container,
or network sandbox. Bind only operator-trusted game source and engine binaries.

No model API calls, autonomous source editing, remote leases, parallel worker
pool, Git merging, publication, or ESM admission are added. Human supervisory
hours, token cost, and playable minutes remain null rather than fabricated.

NET and 1792 retain their own original licences. Game source is not vendored into
NET's wheel; the source archives carry each repository's licence files.

Full architecture, command details, and qualification entry point:
`docs/NET_FOUNDRY.md`.
