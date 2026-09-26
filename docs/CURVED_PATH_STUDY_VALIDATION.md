# Curved-path study validation

Validated on Windows with Python 3.12.14, NumPy 2.4.3, websockets 16.0 and
pytest 9.0.2. This increment extends the existing curved-path operation; provider
pins, operation identities, workspace format and admission rules are unchanged.

## Source and provider identities

The increment starts from local workbench `21c6691751f8f4b84a95bebe9c17ef0f9fe76caf`,
whose tree `c837ea53150aecfc9050e3e9de750b42f74f4cbb` equals published
`4f536fc04e6fc24b1b148a6ac809ed9792181ceb` on `codex/native-interop-v1`.
The checked default-branch HEAD was `37834a7e2bd9664d67fb0001267675874aae228c`.
The increment is isolated above the native interoperability work; it does not
merge other contributors' changes or replace the default-branch README.

GitHub provider HEADs and local executable pins matched on 2026-09-26:

| Provider | Revision | Source tree |
| --- | --- | --- |
| CSG | `bbc535af29c30997e56fd120320c570830676462` | `181b6eb73288d001f45c39bb149b1a80a431f34b` |
| FTR | `dc918562cd9e351a65475d29f46963c9f2fd7db8` | `1f082c6b443f2e301ac5889122912f26968ae756` |
| ICRH | `dc4d826ecd1f28c1d55b724618380ce44e58bedd` | `38d516c0797a662de3bc8a8cb0d469ae86ec8c75` |

Exact tracked bytes were checked. A separate CSG checkout was restored from its
pinned blobs after the adapter refused Windows line-ending conversion. Original
provider checkouts were left untouched. Command-scoped `safe.directory` entries
resolved the sandbox account's ownership difference; no global Git setting or pin
was relaxed. The native Python executable SHA-256 was
`9f91cee2e1b13d9779ab252507aeee120c379e2543ffe85f63cad129b58ba230`.

## Executed checks

| Check | Result and scope |
| --- | --- |
| Study source tests | 76 passed, then both added threshold/partial-failure tests passed; 78 cases total, all with the genuine pinned CSG provider |
| Broad Python regression | 1,712 passed, 637 optional cases skipped, 38 subtests passed; no failures |
| Combined installed-wheel study and geodesic tests | 190 passed, zero skips, including all 78 study cases |
| Installed terminal run / inspect / replay | Passed; four native cases, provider-free inspection and fresh replay |
| Independent ICRH study comparison | All four native original/replay pairs passed the existing constant-curvature, covariance and occurrence-binding profile |
| Existing ICRH reference fixture checks | Five pairs passed: flat, oblique flat, positive/zero/negative constant curvature |
| Output retention | Existing output directories refuse; injected second-candidate failure preserves the first completed native occurrence without a completed study |

The isolated test environment imports CIW from its installed wheel with Python
`-I`, outside the checkout and without `PYTHONPATH`. Registry installation was
unavailable offline. Exact dependency files and distribution metadata were copied
from the tested environment and hash-compared; CIW and ICRH were built and installed
as wheels. This validates the local installed-package path, not a new online
package-resolution run. The combined CI gate retains its ordinary wheel-install
path and now includes the study tests, fixtures, walkthrough and ICRH pair checks.
Use a fresh gate output directory on every invocation.

The local retained original study is
`sha256:801a96775b5aa44063cc4d68012d56305f06f1d66bf3acbb60b3e79326797aea`;
its replay is `sha256:05632e1db19103400c7bc3e61055c0491a96ade7bc7d2eedbfdb303af8c2fbe4`.
With limits 0.004 m lateral and 0.003 radian heading, the 0.004-radian candidate
exceeded both sampled limits. The baseline 0.002, smaller 0.001 and opposite
-0.002-radian cases were within both. These labels concern predicted means at the
retained samples, without uncertainty or integration-error margins.

Run-local evidence is under `results/`: `regression.xml`, `installed.xml`,
`installed-dependency-copy.json`, `terminal-{run,inspect,replay}.json`, and
`manual-gate/curved-study-icrh.json`. Generated workspaces are retained locally;
CI uploads its equivalent reference/study evidence as workflow artifacts.

## Exact changed files

- `src/ciw/curved_path_study.py`: bounded orchestration, retained comparison, inspection and replay.
- `scripts/check_curved_path_study.py`: run/inspect/replay terminal commands with fresh output directories.
- `scripts/check_geodesic_references.py`: installed study tests, terminal walkthrough, retained evidence and independent native pair checks.
- `tests/test_curved_path_study.py`: native analytic comparisons, identity/meaning tampering, bounds, failure retention, offline reopen and replay.
- `examples/curved-path-study/baseline.json`: zero-lateral baseline with explicit assumed covariance.
- `examples/curved-path-study/spec.json`: bounded heading candidates and componentwise sample limits.
- `docs/CURVED_PATH_STUDY.md`: operator contract and limitations.
- `docs/CURVED_PATH_STUDY_VALIDATION.md`: this validation record.
- `docs/README.md`: link to the operator page.
- `docs/INSTRUMENTS.md`: candidate-study link on the existing curved-path row.
- `docs/SYSTEMS_CATALOG.md`: implemented quantity-only BIM status, with surveyed geometry still pending.
- `docs/STACK.md`: correct ESM coverage to telemetry plus calibrated-observable review.

No changes to `session.py`, `workbench.py`, shared operation/execution/result
registries, provider solver implementations, runtime pin files, Julia environments,
Godot scenes, admission policies or the root README.

## Remaining gates

Native linearization validity remains heading-only; it does not establish lateral
variation validity, covariance-support coverage, nonlinear accuracy on arbitrary
surfaces, step-refinement convergence or physical calibration. Sample comparisons
provide no continuous-path or chance-constrained guarantee. `replay_of` is a
parent content reference, not authenticated standalone study-group ancestry; the
CI pair check has both supplied studies and independently checks the native pairs.

BIM design-change/observation composition, surveyed-frame clearance, an ESM mapping
for study artifacts, and a genuine GSV browser/provider test remain separate work.
The 637 optional regression skips are not passes. Hardware/FPGA, physical validation,
new MCP exposure and SP1 proof production are not exercised by this increment.
