# Foundry v1 repository delivery

The current repository is **giasonpooni/Notations-Systems-Terminal** (GitHub
repository ID 1377790873), renamed from Notations-Engineering-Terminal. Historical
source archives and evidence keep their original names and bytes.

## Code and complete handoff

The implementation is in this branch, not only in a downloadable archive:
`src/ciw/foundry_project.py`, `foundry_water.py`, `foundry_workflow.py`,
`tests/test_foundry.py`, and `scripts/check_foundry.py`. See
[NET_FOUNDRY.md](NET_FOUNDRY.md) for the runnable commands.

The complete original handoff is retained in Git under
[delivery/foundry-v1/retained](../delivery/foundry-v1/retained/):

- [Complete 131-file bundle](../delivery/foundry-v1/retained/NET_Foundry_1792_v1.zip):
  the installable wheel, both exact source snapshots with their own licences,
  applicable patches, documentation, source locks, every native campaign and
  its original failed attempts, original local and CI test reports, and checksums.
- [Preservation receipt](../delivery/foundry-v1/retained/publication.json): input
  artifact identities, output ZIP digest, and verified original-file count.
- [Original qualification](../delivery/foundry-v1/retained/qualification.json)
  and [original setup handoff](../delivery/foundry-v1/retained/HANDOFF.md).

The ZIP is a deterministic **repack**, not a byte-identical copy of the original
chat ZIP. All 131 original enclosed files, including the original checksum
inventory, are retained byte-for-byte. The checksum inventory digest is
`eaaa9fd64dc1d80b91ea61c5a5ce696ef0b03d74769f868fae5c56b228bd3fac`.
Once the retained files are committed, normal clone/fetch retrieves them without
needing the original Actions artifacts or chat session.

## Runtime qualification versus retention

The native qualification belongs to NET runtime revision
`67225cb061560ad26218ea8473a6b70fb3ab98c1` and game runtime revision
`2bb8a16e63716d54de2d4e97daabc4671d3e07f4`, from Foundry workflow
[36529817204](https://github.com/giasonpooni/Notations-Systems-Terminal/actions/runs/36529817204).
The repository-retention increment does not modify or requalify that runtime,
acceptance policy, game reducer, clock, save API, or executable pin.

The scope remains the explicit game-domain/pose-fixture workload, not a played
route, visual-quality validation, autonomous studio, or complete playable build.
Git retention is not ESM state admission, publication authority, or a product
release. Neither feature branch is automatically merged into main.

## Preservation process

`scripts/preserve_foundry_delivery.py` reconstructs the handoff from four
SHA256-pinned CI artifacts and the seven local-only files in
`delivery/foundry-v1/local-overlay.tar.xz`. Each input digest is checked before
parsing; archive paths, expansion limits, member types, exact inventory and every
original file checksum are checked before writing. No archived game or runtime
code executes. Git is invoked locally only to reproduce the original two patches.

The narrowly scoped `Preserve Foundry delivery` workflow runs only for the
same-repository Foundry PR #68/branch. Its job token has Actions read and Contents
write for that repository, not a user credential or global permission change.
It runs the preservation tests, reconstructs and verifies the bundle, checks
that the branch has not advanced concurrently, then makes a non-force commit
of only the retained deliverables and a README link on that feature branch.
It never writes main, merges pull requests, publishes a release, or runs providers.

A failed transport/inventory/concurrency check aborts rather than weakening the
checks or claiming a successful push. Existing retained output is checked and
left unchanged. `publication.json` records byte retention, not a fresh native test.
