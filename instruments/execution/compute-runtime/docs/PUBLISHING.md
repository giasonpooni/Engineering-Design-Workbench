# Publishing the two distributions

Everything below the upload step has been run and is checked by CI. The
upload itself needs credentials this repository does not hold, and is
the one irreversible step: a filename on PyPI can never be reused, even
after deletion.

## What has been verified, and where

| layer | how it is checked | where |
|---|---|---|
| source -> emitted tree | imports parsed, machine paths, empty selection, derived suite | `build.py --check`, both releases |
| emitted tree -> wheel | declared packages vs actual, asset package-data | `_check_packaging_covers_the_tree`, `_check_assets_are_packaged` |
| wheel -> installed | every module imports with no source on the path; the renderer's importmap resolves | CI `installs` |
| emitted tree -> sdist | MANIFEST.in covers tests and assets | `_check_sdist_carries_the_suite` |
| sdist -> its own suite | unpacked, `pytest tests/` must pass | CI `sdist` |
| sdist -> wheel | the packager's path, renderer included | CI `sdist` |
| metadata | `twine check` on all four artefacts | CI `sdist` |
| build requirement | built at the DECLARED minimum, `--no-build-isolation` | CI `sdist` |
| interpreters | 3.10-3.13 on Linux, macOS, Windows | shipped `ci.yml`, both releases |

Measured on this machine at the time of writing: both sdists and both
wheels pass `twine check`; `canonical-state` runs 100 tests inside its
unpacked sdist and `provenance-pool` 557; all 21 `canonical-state`
modules import on 3.10, 3.11, 3.12 and 3.13 and produce a byte-identical
content-addressed version id on all four.

## The steps

```bash
# 1. derive both, refusing rather than emitting something broken
python3 release/provenance_pool/build.py --out dist/provenance-pool
python3 release/canonical_state/build.py  --out dist/canonical-state

# 2. build both artefacts for each, at the declared minimum and WITHOUT
#    build isolation -- isolation resolves `setuptools>=77` to whatever
#    is newest, which is how an understated pin stays hidden
python3 -m pip install "setuptools==77.0.1" "packaging>=24.2" wheel twine
for tree in dist/provenance-pool dist/canonical-state; do
  (cd "$tree" && python3 -c "
import setuptools.build_meta as b
b.build_sdist('dist'); b.build_wheel('dist')")
done

# 3. the gate PyPI applies
python3 -m twine check dist/*/dist/*

# 4. TestPyPI first. The name is claimed permanently on the real index,
#    so a mistake here costs nothing and a mistake there costs the name.
python3 -m twine upload --repository testpypi dist/canonical-state/dist/*
python3 -m pip install --index-url https://test.pypi.org/simple/ \
                       --no-deps canonical-state

# 5. and only then
python3 -m twine upload dist/canonical-state/dist/*
```

## What still needs a person

**A PyPI account and an API token.** Use a project-scoped token rather
than an account-wide one, and prefer Trusted Publishing (OIDC from
GitHub Actions) over a long-lived secret if these get their own repos.
Both names were free when checked; neither is reserved until uploaded.

**Whether the two distributions get their own repositories.** They are
derived from this one and their `Source` URLs point here, which is
accurate today. If they move, the URLs move with them, and the lock in
`tests/test_release_canonical_state.py` requiring both to name the same
repository is the thing to update -- deliberately, not by deleting it.

**A version policy.** Both are `0.1.0`. The identity scheme in
`canonical-state` is content-addressed and stable across interpreters,
so its version is about API compatibility only; `provenance-pool`'s
evidence classes are a public contract and changing one is a major
version, not a minor one.
