# Qualifying private providers without a cross-repository secret

The existing `CIW_PROVIDER_READ_TOKEN` route remains supported. It is not the
only source-provisioning mechanism, and it must not be required by numerical
code. This increment adds an operator-local transport and demonstrates a
provider-owned CI route. Neither route disables the existing qualification gates.

## 1. Run a single-provider gate in the provider's own private repository

The private repository checks out its own approved revision with its ordinary
read-only Actions token and the public Notations revision by exact commit.
Build from temporary copies, install both wheels in a fresh environment, then
run the original terminal tests and installed replay check. No additional PAT,
App key or cross-repository secret is needed. Keep provider source, binaries and
raw logs in private artifacts. Public PRs must not execute against this workspace.

This route is implemented in PLSR PR #1 (`ci/notations-local-qualification`),
commit `8bb41f139c98d64ff53cc6db402a2cc2912861db`. It uses:

- Notations: `9f60b8333d299afa1631e002bc48cdca7265b9d6`.
- PLSR: `19ea6967060166ba09db6cd4563bd87bd6b3d196` (the existing approved pin).
- Original `tests/test_plsr.py`, `tests/test_plsr_engine.py`, and
  `scripts/check_plsr_installed.py` without changing assertions.

Run `36357157788` passed **60 tests with zero skips on each of Windows and
Ubuntu**, followed by installed CLI import/evaluate/inspect/replay. The runner
compares all executed JUnit case identities with the preceding full collection;
an empty suite, missing case or skipped test cannot qualify it. Original source
checkouts are byte-validated before and after the run.

Downloaded artifact ZIP checksums were independently checked:

| Platform | Artifact | SHA-256 |
| --- | --- | --- |
| Linux | 10943967835 | `95d65be11c79029213a000029d4600693f3223be792bc6c2707cfa29bf65ac05` |
| Windows | 10944502471 | `ad484d07f5029ed54d7d7fd9c733bfc7f94bfec9be8c8f86145cad9719aaa232` |

This is installed PLSR integration, not SP1 verification, physical validation or
admission. The two OS runs repeat the same tests. Wheel hashes are retained
separately; cross-platform byte-identical builds are not claimed.

## 2. Run multi-provider gates from local pinned checkouts

An operator workstation or private runner can already hold the required source
checkouts. `scripts/local_provider_sources.py` makes those sources available to
existing gate scripts without changing their clone URLs or source pins.

An operator-owned JSON manifest declares exact local sources. For example,
this single-provider manifest illustrates the format (replace the path with an
actual clean checkout of the specified commit):

```json
{
  "schema": "ciw-local-provider-sources-v1",
  "providers": [{
    "repository": "giasonpooni/Parameterized-Lyapunov-Stability-Runtime",
    "revision": "19ea6967060166ba09db6cd4563bd87bd6b3d196",
    "path": "/private/providers/plsr"
  }]
}
```

Use a separate, complete manifest for a multi-provider gate. For acquisition,
include the eight providers and required vendor gitlink at the exact revisions
read by `scripts/check_acquired_stream.py`. A single PLSR source is not sufficient.
Repository names must use the spelling of the gate's HTTPS URLs. The manifest
associates a name with a local pin; it is an operator assertion, not a signature.
The existing gate still checks its own approved revisions and executable bytes.

```sh
python scripts/local_provider_sources.py \
  --manifest /private/acquired-stream-sources.json \
  --report /private/results/source-transport.json \
  -- python scripts/check_acquired_stream.py \
     --output-dir /private/results/acquisition
```

The launcher strictly parses the bounded manifest, reuses the existing checkout
validator, and creates temporary bare snapshots containing the declared commits.
Git HTTPS URLs are mapped to those snapshots with process-only configuration.
Git network protocols are disabled; an omitted provider or vendor cannot silently
fall back to remote authentication. The original repositories are not checked
out, rewritten or cleaned, and are revalidated after command execution. Snapshots
are removed on exit. Existing report files are never overwritten.

Known GitHub/provider token environment variables and inherited Git credential
configuration are removed from the child environment. No token is put in a URL,
gitconfig, manifest or report. This is **local-only Git transport, not a network
sandbox**: pip/Cargo package downloads and the selected operator command still
have their usual capabilities. Preprovision package/toolchain dependencies for
an actually offline deployment. Never use this on an untrusted PR or attach a
public PR runner to private provider checkouts.

The transport report says `command_succeeded` or `command_failed`; it does not
infer mathematical or cryptographic validity from exit code zero. Original
native/proof gates remain responsible for complete test execution, source pins,
proofs, and their own retained evidence. No generic mock-provider mode is added.

## Current evidence and remaining work

The launcher has 33 local regression cases covering real Git clones, SHA-1 and
SHA-256 commit preservation, wrong pins, dirty/staged/untracked files, source
mutation during execution, bounded and duplicate-key parsing, disabled network
fallback, credential stripping, failure propagation and report non-overwrite.
Local environment: Linux/Python 3.13.5, pytest 9.0.2; Windows qualification of this
new launcher is separate from PLSR's completed Windows integration.

Multi-provider scientific suites have not all been rerun through the launcher.
Their full pinned checkout sets still need provisioning. This is a concrete
alternative to supplying a cross-repository credential, not a way to obtain
private source without authorization. Repository-local CI cannot read other
private repositories merely because they have the same owner.

The existing private SCR proof route separately avoids cross-repository source
authentication but still needs its declared RAM/disk and genuine-proof gates.
No resource guard, source pin, test threshold or proof requirement is lowered.
A public workflow that still selects the token route remains unqualified until
that route is provisioned or its qualification is deliberately migrated and
bound to the exact tested revisions. Historical failures are not rewritten.
