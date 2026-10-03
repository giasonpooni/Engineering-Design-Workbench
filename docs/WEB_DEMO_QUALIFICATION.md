# NET synthetic scientific demo qualification

This report describes the implemented browser client and real Python execution
service. **The public browser journey is not fully qualified yet.** Real installed
provider execution, evidence export and numerical replay pass; desktop/mobile
rendering and principal browser interactions remain unverified because the
managed browser rejected the preview URL. No public deployment has been made.

## Architecture and baseline

The work starts from native sensor-fusion revision
`4871b306ced4ae33866de75c809c61cea5cf485f`, merged with public main
`98b7dfccec61f295d0bd0240723fb64bf0f58d17` at
`bf2d4f999751cc50ce1d31d03dc8ec7b0668e71c`. The original fusion, transport and EKF
commits remain ancestors. The newer operator-readiness main `d313351f96aad73fe40229b7d705b18c12e96b64`
was merged at `66b27e66`. Final application qualification uses the isolated,
unchanged commit `4408389e88223f22b424be4ae307fd1720ab8bd1`. Subsequent delivery
changes add documentation and retained evidence only. Twenty-one imported module histories and source
boundaries are retained; nineteen previously recorded fusion source hashes
matched. Existing licenses and imported source trees are preserved.

The demo adds a fixed synthetic configuration/catalogue, projection layer,
installed subprocess worker, bounded HTTP service and browser client. It calls
the existing EKF workflow and pinned GSIE/JSPT providers; it does not replace the
scientific algorithms. Existing linear Kalman, angular and coordinate transport
implementations remain in their declared scope. Only examples that pass actual
startup execution and numerical replay enter the browser catalogue.

Evidence, operation, execution, numerical result and verification identities
remain separate. Replay runs the providers again, requires canonical numerical
agreement and retains fresh execution/result/verification occurrences. It is
same-implementation reproducibility (`independent: false`), not independent
experimental validation or admission of canonical state.

## Recorded checks

| Check | Outcome and scope |
| --- | --- |
| Original fusion regressions | 214 passed, zero skipped: source contracts, linear/angular, coordinate transport and EKF. |
| Clean merged baseline fusion regressions | 214 passed, zero skipped at `bf2d4f99`. |
| Final frozen application fusion regressions | 214 passed, zero skipped at `4408389e`, including actual pinned-provider workflows. |
| Original workbench regression rerun | 68 passed, 38 skipped for unprovisioned external integrations. Historical retained evidence had 62 passes and 38 skips in its narrower workbench selection. |
| Final frozen interface regressions | 77 passed, 13 skipped, 33 subtests passed: subprocess adapter, protocol, workbench session/transport and JSON server boundary, at `4408389e`. Twelve skips need explicit calibrated-stack bindings and one needs identified-design bindings. |
| Final operator/provider/scientific integration | 308 passed, zero skipped at the same frozen revision: operator discovery/setup/workbench, provider provisioning/local sources, hypergraph rewrite, scientific observations and polymer operation. |
| Demo catalogue and scientific projection | 43 passed, zero skipped: exact default fixtures, parameter bounds, coherent evidence declarations, units, covariance scaling, null gaps, identities and actual provider executions at parameter extremes. |
| Demo execution service | 30 passed, zero skipped: actual execution/export/replay for all three workloads and the failure/resource controls below. |
| Fresh noneditable installation | Python 3.12.14, pinned build/runtime wheels and local native provider snapshots; wheel installation and `pip check` pass. All three installed CLI executions and fresh replay pass outside the source checkout. The final wheel passes real HTTP execution/configuration and evidence export/replay for all three examples with nondefault controls. All 370 installed modules, fixtures and browser assets match frozen source hashes at both ends of the check. |
| JavaScript and static controls | Both JavaScript files pass Node syntax checks. Static HTML inspection finds 36 unique IDs and resolves all 30 static JavaScript DOM references. This does not establish rendered accessibility. |
| Existing CI policy | Eighteen baseline workflows and thirteen adversarial policy tests passed. The new read-only CI job installs a wheel, audits preserved imports and runs relevant scientific/demo checks. Remote CI results must be checked separately. |
| Container configuration | Compose YAML parses; Docker is unavailable here. Image pull/build/start and proxy/TLS behavior were not tested. |
| Browser integration and visual QA | Incomplete. Managed Chrome blocked `http://terminal.local:4173/`; no successful browser run, replay, download, desktop/mobile screenshot or console audit is claimed. |
| Public hosting | Incomplete. Requires an authenticated Python-capable host, its operating environment and an actual domain/DNS/TLS configuration. Sites Worker hosting cannot execute these CPython subprocesses. |

Strict imported-source audits deliberately refused a development checkout while
other agents were adding untracked files. Repeating the fusion baseline in a
clean isolated worktree passed all 214 tests. The source audit was kept intact.
Backend cleanup tests also required adapting the test harness to this managed
kernel's namespace/proc visibility; they now first observe live descendants and
then verify their termination rather than treating invisible processes as gone.

Skipped existing integration checks require separately provisioned calibration,
identified-design, ESM or shared-telemetry sources/runtime bindings. They do not
qualify those capabilities for this public demo. There are no skips in the 73
new demo tests or the 214 fusion baseline tests.


The frozen wheel SHA-256 is
`1ac09c9b75b7a0630278a5b47a8a0cdb6c350ab0cf36e4975c74d7c67dcb93cf`.
The retained installed HTTP report records package versions, exact application
commit, all module/asset hashes, original/fresh execution identities and download
hashes. Its three configuration downloads and six native evidence bundles are
in `docs/qualification/web-demo/installed/`. They contain synthetic data only.

Merging current operator readiness exposed a genuine integration defect: its
single-provider fallback omitted the companion provider for coordinate transport
and EKF, aborting operator discovery. Explicitly projecting both original pins
fixes that defect and preserves the read-only catalogue's authority. Two focused
regressions check the complete exact pins and forbid runtime probing/execution.
The before-fix selection had 303 passes and three discovery failures; all 308
final integration cases pass after the fix, with no skips.

Concurrent browser-asset edits and shared disk exhaustion interrupted development
qualification. These attempts are retained separately and are not counted as
passing runs. Interrupted Python imports left temporary bytecode files that the
strict source gate correctly refused. Final regressions use a fresh detached
checkout of the same native commit with temporary work in memory-backed storage;
no source gate, provider check or scientific algorithm was weakened. The final
installed HTTP check uses an isolated source checkout and confirms source/asset
equality both before and after real execution.

## Execution and failure qualification

The 30 service tests exercise installation/execution qualification gating,
invalid configuration and oversized requests, provider refusal, malformed worker
output, evidence/source integrity, exact-origin and CSRF protection, private
session ownership, parallel sessions, per-session serialization, queue/job/session
and HTTP connection capacity, retention, output bounds, wall deadline,
cancellation, Linux CPU/address-space/file-size limits and process-group cleanup.
A real CLI startup SIGTERM test verifies that active provider descendants are
killed. Test-only fault workers are a trusted constructor seam, never accepted
from HTTP clients. Successful scientific integration tests use real Python
providers, not simulated numerical responses.

The service bounds fixed trusted operations; it is not a general sandbox for
visitor-supplied programs. Linux resource limits and group cleanup supplement
schema/size limits and sanitized worker environments. The supplied container
configuration adds host-level restrictions but remains untested here. Sessions
and evidence are ephemeral, private, bounded and lost on service restart;
visitor downloads are the durable retention path.

## Product scope and remaining acceptance work

The client implements example selection, readable problem declarations,
validated controls with units/help/defaults/reset, queued/running/completed/error
status, cancellation, observations alongside estimates, marginal/predictive
uncertainty, residual plots and diagnostics, expandable identity/provenance
inspection, configuration/evidence downloads and fresh replay controls. The onyx
layout includes responsive styling, native controls, skip navigation, visible
focus and live status. These are implementation/source-review findings; they
await real rendered browser verification.

Before publishing a public preview, run the documented service in a browser-
reachable environment and complete all three configure → execute → inspect →
export → replay journeys at desktop and mobile widths. Check keyboard/focus,
status announcements, console/network errors, plot axes/bands/gaps, cancelled
runs and actionable failure messages. Build/run the actual container and verify
health, HTTPS origin/session behavior and operating limits on the target host.
Record those results and the deployed revision here. Wire the homepage's
“Launch Terminal” link only after the chosen HTTPS origin works.

This synthetic demonstration does not establish physical model validity,
empirical uncertainty coverage, live-device safety, persistent archival service,
production readiness or industrial-control readiness. Installation, tests,
source publication and hosting are separately scoped outcomes.

The retained reports identify the tested application revision. The final
delivery commit adds this report and synthetic execution evidence; installed
application source remains identical to that tested revision. Remote CI is a
separate check and is not assumed to have passed from local results.

See [installation and operating commands](WEB_DEMO.md) and the machine-readable
qualification evidence in `docs/qualification/web-demo/`.
