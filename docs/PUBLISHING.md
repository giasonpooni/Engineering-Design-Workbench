# ClockSync 0.1.0 publishing checklist

This document is a release procedure, not a claim of publication. The current change set prepares a release candidate. No tag, PyPI project registration, publisher authorization or environment protection is implied by committing these files.

## Artifact gate

Run the `tests` workflow on the exact release commit. It tests installed packages on Linux/Python 3.11–3.13, Windows/Python 3.12, macOS/Python 3.12, NumPy 1.24.0, and the separately installed immutable SET exchange dependency. `distributions` depends on every test job.

The resulting `clocksync-release-bundle` contains one wheel, one source distribution and `release-evidence.json`. The checker installs the wheel in a clean virtual environment outside the checkout, rebuilds/installs the sdist, exercises the bundled examples and console entry point, checks package metadata and license files, and hashes the artifacts. The manifest identifies the actual checked-out commit; a pull-request run can identify GitHub's merge-test commit rather than the PR head. Publishing rebuilds and checks the approved tag rather than treating an older PR artifact as a release artifact.

Build evidence, execution identity and numerical verification are different things. This manifest is not an independent scientific certificate. PyPI publishing attestations, when produced, attest publishing provenance, not the correctness of a physical clock model.

## Maintainer setup

1. Protect `main`, require pull requests and the `distributions` check, and prohibit force pushes/deletion. The publish workflow refuses an unprotected `main`. Avoid requiring an unavailable second reviewer on a solo-maintainer repository.
2. Review/merge the release PR and confirm the exact merged commit passes CI. This preparation does not merge or change branch-protection settings.
3. Create GitHub environments `testpypi` and `pypi`. Restrict their deployment refs to release tags and configure the desired reviewer approval. Do not store a long-lived PyPI token in the repository.
4. Register pending/existing Trusted Publishers separately in TestPyPI and PyPI. Confirm project-name availability and account authority rather than assuming the name is reserved.

Use these publisher fields:

| Field | Value |
|---|---|
| Project | `notations-clocksync` |
| GitHub owner | `giasonpooni` |
| Repository | `Notations-ClockSync` |
| Workflow filename | `publish.yml` |
| GitHub environment | `testpypi` on TestPyPI; `pypi` on PyPI |

The existing MPL-2.0 license and `Copyright 2026 Bespoke Polymer Inc.` notice remain authoritative. Dependencies keep their own licenses. `tbrt` remains the implementation import; the older distribution must not be installed alongside the new one.

## Tag and dry run

After review and successful CI, update the release-candidate status text and changelog date as part of the approved release commit, then create an annotated `v0.1.0` tag at that commit. Do not move an existing release tag. The version in `pyproject.toml` must match the tag exactly.

Dispatch `publish.yml` **on the tag**, choosing TestPyPI first:

```sh
gh workflow run publish.yml --ref v0.1.0 -f index=testpypi -f confirmation=publish-v0.1.0
```

The workflow must exist on the default branch before manual dispatch is available. It refuses the wrong repository, branch refs, version/tag mismatch, incorrect confirmation, unprotected main, or a tag whose commit is not an ancestor of main. It reuses the full test/build workflow, verifies bundle hashes, and only then enters the selected publishing environment. `id-token: write` is limited to the publishing job. Only the already-tested wheel/sdist are uploaded; no rebuild occurs in that job.

Install the TestPyPI candidate in a new environment. Install runtime dependencies from normal PyPI first, then install ClockSync with `--no-deps` from TestPyPI, avoiding a mixed-index dependency search:

```sh
python -m pip install 'numpy>=1.24'
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps notations-clocksync==0.1.0
clocksync --version
clocksync --example correlated | clocksync - --compact
```

TestPyPI and PyPI are separate indices. A successful TestPyPI publication is not production publication. A partially successful upload should be inspected before retrying; the workflow does not silently skip existing files.

## Final publication

After reviewing TestPyPI behavior, dispatch the same tag with `index=pypi` and `confirmation=publish-v0.1.0`, then approve the `pypi` environment if required. A second invocation rebuilds/rechecks the same source; use its own manifest to identify the exact published bytes. Do not claim byte-for-byte identity between separate builds without comparing hashes.

Finally install `notations-clocksync==0.1.0` from normal PyPI in another clean environment, verify `clocksync --version`, run all three examples, and attach the approved release bundle, source commit, checksums and changelog to the GitHub release. If a published version is defective, document the issue and follow PyPI's version/yanking procedure; do not overwrite a published version or silently retag source.

## References

- PyPI Trusted Publishing: https://docs.pypi.org/trusted-publishers/using-a-publisher/
- Pending publisher setup: https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
- PyPA release workflow guide: https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/
- Direct-URL dependency restriction: https://setuptools.pypa.io/en/latest/userguide/dependency_management.html#direct-url-dependencies

The source-pinned SET requirement moved to `requirements-exchange.txt` because PyPI does not accept direct-URL dependencies in published package metadata. The optional adapter and pin are retained; `.[exchange]` is now a compatibility marker, not a dependency installer.
