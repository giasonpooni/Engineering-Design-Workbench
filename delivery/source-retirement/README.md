# One engineering workspace: Notations-Systems-Terminal

**Status: the complete workspace and backups are preserved; deletion awaits native publication and merge.** Keep the old repositories available until that final verification completes.

## Use NET now

The transfer branch contains a verified recovery bundle. These commands restore the qualified 23-instrument workspace locally without fetching the old repositories:

```sh
git clone --branch transfer/source-retirement-20261003 https://github.com/atomtrapping/Notations-Systems-Terminal.git
cd Notations-Systems-Terminal
python delivery/source-retirement/restore.py
python -m pip install .
net --help
```

The restore command refuses a dirty or shallow checkout, verifies all recovery bytes, restores the original Git histories and retained labels, and runs both source audits. It switches the checkout to the native migration branch. Continue your engineering work in this NET directory.

## The 23 repositories prepared for retirement

| Original repository | Module in NET | Retained licence | Branches / PR heads |
| --- | --- | --- | --- |
| Notations-Calibration-Runtime | `mcur` | MPL-2.0 | 5 / 4 |
| Notations-ClockSync | `tbrt` | MPL-2.0 | 7 / 6 |
| Notations-Observability-Testbed | `oit` | MPL-2.0 | 4 / 3 |
| Notations-State-Inference-Engine | `gsie` | MPL-2.0 | 4 / 3 |
| Notations-State-Recompiler | `cbsr` | AGPL-3.0 | 5 / 3 |
| Notations-FaultSense-RunTime | `fdir` | MPL-2.0 | 4 / 3 |
| Notations-Estimator-Bench | `set` | Apache-2.0 | 6 / 4 |
| Notations-SensorDesign-RunTime | `edspt` | MPL-2.0 | 4 / 3 |
| Notations-Linear-Dynamics-Testbed | `sidt` | MPL-2.0 | 4 / 3 |
| Notations-Sensitivity-Testbed | `jspt` | MIT | 6 / 4 |
| Notations-Metrology-Adapter | `rci` | MIT | 10 / 7 |
| Notations-Signal-Processing-RunTime | `stfe` | MPL-2.0 | 4 / 3 |
| Polygon-Trajectory-Experiments | `tsde` | MIT | 6 / 3 |
| Notations-Surface-RunTime | `csg` | MPL-2.0 | 13 / 12 |
| Notations-Retrieval-Agent | `sra` | MIT | 5 / 3 |
| Notations-Yield-Weighted-Runtime | `ywir` | MIT | 5 / 3 |
| Notations-Estimator-for-BIM | `cse` | MIT | 40 / 46 |
| Notations-Real-Time-Globe | `gsv` | GPL-3.0 | 12 / 10 |
| Notations-FrameMapper-RunTime | `framemapper` | GPL-3.0 | 37 / 25 |
| Notations-Compute-Runtime | `scr` | Apache-2.0 | 19 / 16 |
| Notations-FlowState | `fsrt` | MIT | 9 / 6 |
| Notations-Scientific-Language-RunTIme | `nslr` | MPL-2.0 | 5 / 4 |
| Notations-Inference-Schematics-Engine | `nise` | MPL-2.0 | 5 / 4 |

## Licences stay attached to the code

NET first-party code remains **AGPL-3.0-or-later**, with its existing exceptions.
Each imported instrument retains its original grant, LICENSE, NOTICE and
attribution. Moving code into NET does not replace its licence. The 23 module
declarations comprise 11 MPL-2.0, 7 MIT, 2 Apache-2.0, 2 GPL-3.0 and 1 AGPL-3.0.

## What is ready

- All 23 source imports and original licence/notice files pass the preservation audit.
- All 219 captured branches and 178 PR heads remain native Git ancestors; namespaced tags preserve their labels.
- Issue and PR bodies, comments, review records and events are preserved in the native target; 30 open PRs and one open issue have a readable work list.
- Root provider scripts and workflows use the exact original revisions from NET history, with no remote fallback for retiring instrument aliases.
- A clean local checkout passed both source audits and 234 targeted checks. The latest main changes were merged and additional focused checks passed.
- The complete native recovery bundle below has independently passed a base-only reconstruction, all 397 object/ancestry checks and full Git integrity checking.

## What must finish before deletion

1. The guarded GitHub job must publish the native migration branch and all 397 retained tags, then that native branch must be verified and merged into NET main. **This transport PR must not be merged.**
2. **Backup complete:** all 399 original CI ZIPs are verified against their GitHub SHA-256 digests and saved in ten complete durable archives, with a saved recovery index. There are zero pending transfers and zero digest mismatches.
3. Recheck changes made to the original repositories after the captured inventory at 2026-10-03T17:07:15.818504Z. Preserve any new work before deleting its source.

GitHub has not assigned a runner to the native publication job. The FrameMapper rescue export became unnecessary after direct recovery completed. No source repository has been deleted. Unknown outside consumers, settings,
secrets, external registries and inaccessible wiki history are outside the source
audit; the audit does not certify those resources.

## Keep separate

Keep **NET itself**, Data Intake, Periodic Space, Telemetry, PLSR, State Ledger,
CNC Machine MCP, and the games/product repositories. They are not covered by this
retirement list. State Ledger and CNC Machine MCP lack the explicit public software
licences required for this import; CNC also lacks the required implementation.

## Recovery bundle

The three `native-full-final.bundle.part*` files in this directory are ordered
binary pieces of a native Git bundle, not new source imports. Combined size:
14,730,876 bytes. SHA-256:
`843eba2703ce7d19341a2906f2c59da4e2157176f4f1c66c3a63f75d86c370be`.

Native target: `235032554b9847bf88103e95c401374466f2ac51`.
Required transfer-branch ancestry: `7ca5a411e1b15befc5caace490415ce4f673f930` and its full history. The newer NET base `98b7dfccec61f295d0bd0240723fb64bf0f58d17` is included in the bundle.
The publication driver verifies every piece, reconstructs and verifies the bundle,
compares its catalog to the native target, repeats both audits and focused checks,
then publishes with an atomic push and no force.

After the native migration is merged, `docs/SOURCE_RETIREMENT.md` is the ongoing
workspace guide and `docs/retirement/OPEN_WORK.md` holds the preserved pending work.
