# Engineering instruments

These 21 public modules retain their original package paths beneath each import
directory, licences, tests and release identities. Python packages, native
release builders and the two npm applications keep separate build boundaries.

[`manifest.json`](manifest.json) owns exact repository, source-tree and historical
execution identities. The [superrepo guide](../docs/MONOREPO.md) maps every role
to its directory and records operator commands, selected snapshots and
qualification scope. Run `python scripts/superrepo.py list` or
`python scripts/superrepo.py audit` from the repository root.

Builds and tests run in temporary copies or exact detached provider worktrees.
Keep imported source trees byte-identical to their manifest revisions; a module
change requires an explicit new source identity and compatibility review.
