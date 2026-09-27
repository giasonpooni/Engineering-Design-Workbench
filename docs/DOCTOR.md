# Read-only provider doctor

`ciw doctor` reports the requirements and observed local identities for one
explicit profile. It does not install packages, fetch repositories, change
configuration or pins, start a worker, execute science, or run qualification.
The JSON report goes to standard output; redirect it when a retained report is
wanted. No credentials are read or tested.

```sh
ciw doctor --profile core
ciw doctor --profile declared-workloads --stack-root /providers/declared --engine /tools/execution-cli
ciw doctor --profile native-interop --binding /bindings/native.json
ciw doctor --profile interval-requirement --binding /bindings/interval.json
ciw doctor --profile reaction-catalyst --binding /bindings/catalyst.json
ciw doctor --profile reaction-cantera --binding /bindings/cantera.json
```

Use ordinary Windows paths in PowerShell. Native profiles reuse the existing
operator binding JSON accepted by `NativeInteropWorkflow`. Paths for SCR, host,
worker executable and runtime source resolve relative to that binding file.
Julia depot lists retain the existing runtime semantics: the platform path-list
separator applies, and relative entries resolve against the current directory.
Use absolute depot paths for reproducible diagnostics. Declared workloads use
the existing `sra` and `scr` role directories. A missing binding is reported;
doctor never searches for or provisions a replacement.

## Authority and scope

| Profile | Existing requirement authority | Local checks |
| --- | --- | --- |
| `core` | Installed CIW distribution metadata | CIW metadata, required Python version and exact required distribution versions; optional extras excluded |
| `declared-workloads` | `ciw.declared_workload.PINS` | Exact source checkouts and presence/digest of the explicitly bound engine |
| `native-interop` | Packaged `native-interop-runtimes.json` | Approved SCR checkout, host/operator digest, optional complete accepted Julia source closure, executable digest and depot presence |
| `interval-requirement` | Manifest `interval_family` | Profile SCR revision/tree, host/operator digest, exact executable and worker/environment file hashes, depot presence |
| `reaction-catalyst`, `reaction-cantera` | Manifest `reaction_families` | Selected family SCR revision/tree, host/operator digest, exact executable and worker/environment file hashes; Catalyst depot presence |

There is no second provider version list. The checkout check is the same shared
read-only validator used by existing-checkout integration gates: it checks
pinned HEAD, index/working-tree state, unexpected files and committed file
bytes, with Git optional index updates disabled. Recognized runtime caches and
uninitialized gitlinks retain the validator's existing treatment. This does
not establish an operation-specific Python import closure or submodule readiness.

Report schema `ciw.doctor.v1` keeps `expected` separate from `observed` for every
check. A passing preflight exits 0. Blocked preflight exits 2 and contains one
or more fixed classifications:

- `dependency_unavailable`: an explicitly required local dependency is absent.
- `identity_mismatch`: present identity differs from its selected requirement.
- `setup_failure`: malformed binding, unreadable resource, failed local Git
  inspection, or requirement syntax outside the diagnostic's supported scope.

`preflight_passed` applies only to listed checks. Every report says
`qualification: not_performed` and lists checks not performed. A selected
provider profile does not implicitly check unrelated provider profiles or core
package metadata; use `--profile core` separately. Installed metadata describes
the installed distribution; when using a source checkout it does not attest
that checkout's package requirements.

Native family `worker_identity` appears only as an expected requirement. Doctor
does not observe a loaded worker, import Cantera or Julia packages, run a
handshake, prove that depot contents load, establish host source-to-binary
attestation, or assess scientific results. Host digests are operator assertions.
The declared-workload engine digest is reported without an independent approved
binary digest. These distinctions remain visible even when preflight passes.

## Qualification and private access

Run the existing profile gate separately in its named provisioned environment.
Its setup, execution and numerical/proof qualification outcomes remain its own
evidence; doctor does not convert them into a qualification claim. Required
qualification tests must still fail on skips. See
[provider availability](PROVIDER_AVAILABILITY.md) for local checkout layouts,
historical commits, private repository access and nested-provider limits.

Native, reaction and interval manual CI qualification already require a
separately provisioned `SCR_READ_TOKEN`. Other cross-repository checkout and pip
Git dependencies also need deliberately scoped read access in a trusted
qualification context. `contents: read` for this repository alone does not
provide access to other private repositories. Doctor neither inspects those
secrets nor attempts an authenticated request.

## Validation

`tests/test_doctor.py` covers authoritative requirement projection, profile
isolation, malformed/missing/mismatched bindings, complete closure checking,
explicit unperformed qualification, JSON exit behavior, and prohibition of
non-Git subprocesses/network/provisioning. Existing
`tests/test_provider_provisioning.py` continues to check read-only checkout reuse
and hidden source drift. Installed-wheel diagnostics must also work outside the
source checkout.
