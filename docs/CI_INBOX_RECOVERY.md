# CI inbox failure recovery — 2026-09-27

The initial failure snapshot was commit `033703ad7ee5164fe2d1164f5d2956ee7b8c4dea`.
Its missing packaged Workbench fragments and corrupt compressed payload broke
source imports and installed-wheel startup. The later main commit
`d241242a06f26550a43701f44323b2c1d7ad6981` repaired those transport failures,
but its decoded source was the preceding Workbench without project-graph
registration. The checked-in project/energy tests correctly detected the loss.

## Repair

- Replace the runtime fragment reader and compressed `exec` payload with ordinary
  readable `workbench.py`. Its pre-edit source is exactly historical Git blob
  `d136f0a31be80a324db16ea591cfc3562f12f61d`. Only the six explicit project-graph
  registration edits are applied to that decoded source. Remove the obsolete
  fragments and their package-data entries.
- Restore project source dispatch, operation registration, builtin availability,
  instrument role, and declared/reproduced lifecycle participation. Preserve
  native owner algorithms, replay identities, evidence and proof boundaries.
- Group automatic CI by workflow, event and branch/PR, not a unique push run ID.
  Explicit manual runs retain separate groups. Matrix failures no longer cancel
  other platform outcomes. No test, workflow trigger or proof gate is removed.
- Wire selected-repository credentials for the private-provider jobs. The
  standard workflow token cannot read the separate private repositories.
  Missing credentials remain a failed/unqualified gate, not a passing skip.

## Operator credential boundary

Set the repository Actions secret `CIW_PROVIDER_READ_TOKEN` to a **read-only,
selected-repository** credential for the private provider repositories used by
these integration gates. Prefer a controlled GitHub App installation-token
provisioning process; a fine-grained token must be limited to Contents: read and
only the listed providers. Do not use an unrestricted classic personal token.
The helper's `PROVIDERS` set lists the permitted repository destinations; it does
not grant or attest the credential's actual permissions.

No credential was created, retrieved or granted by this repair. The secret is
not passed to pull-request jobs or ordinary feature-branch pushes. Main/tag
pushes and operator-dispatched jobs can use it. Public pull requests therefore
cannot qualify private providers through this credential path.

`scripts/ci_provider_access.py` configures only process-scoped Git transport.
Tokens are not written to Git configuration, URLs, environment files or artifacts.
The helper refuses other hosts, owners, repositories and ambiguous paths, and
never stores credentials. Explicit secondary `actions/checkout` steps also use
the selected-repository token instead of the default single-repository token.
The existing provider commits and numerical/proof checks remain unchanged.

Actual private checkout and scientific execution must still pass after this
secret is provisioned. The SP1 gate additionally retains its existing RAM/disk,
toolchain, guest-identity, genuine-proof and negative-test requirements. Native
unit-test success is not cryptographic qualification.

## Reproduction

```sh
python -m pip install -e '.[dev,openusd]'
python -m pytest -q tests/test_ci_recovery.py tests/test_project_workflow.py tests/test_energy_workflow.py
python scripts/check_ci_policy.py
python -m pytest -q
python -m pip wheel --no-deps . --wheel-dir dist
```

The focused source regressions initially changed from five project/energy
failures to 27 passes. The credential/source/CI-policy additions expand that
focused suite to 49 tests; all 49 passed locally (Linux, Python 3.13.5,
NumPy 2.3.5). Real Git credential-protocol tests use an explicitly synthetic
secret without making remote requests. They do not establish private access.
The pinned CI run separately retains its environment, JUnit reports, installed
wheel tests and real OpenUSD roundtrip. Count skips separately.

Historical failed notifications are evidence of older runs and are not erased
or relabelled. Qualification applies to an exact new commit and its runs.
