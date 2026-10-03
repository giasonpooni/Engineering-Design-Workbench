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
commits remain ancestors. Twenty-one imported module histories and source
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
| Original workbench regression rerun | 68 passed, 38 skipped for unprovisioned external integrations. Historical retained evidence had 62 passes and 38 skips in its narrower workbench selection. |
| Existing interface regressions with demo source | 77 passed, 13 skipped, 33 subtests passed: subprocess adapter, protocol, workbench session/transport and JSON server boundary. |
| Demo catalogue and scientific projection | 43 passed, zero skipped: exact default fixtures, parameter bounds, coherent evidence declarations, units, covariance scaling, null gaps, identities and actual provider executions at parameter extremes. |
| Demo execution service | 21 passed, zero skipped: actual execution/export/replay for all three workloads and the failure/resource controls below. |
| Fresh noneditable installation | Python 3.12.14, pinned build/runtime wheels and local native provider snapshots; wheel installation and `pip check` pass. All three installed CLI executions and fresh replay pass outside the source checkout. Final-source wheel HTTP check is recorded separately when complete. |
| JavaScript and static controls | Both JavaScript files pass Node syntax checks. Static HTML inspection finds unique IDs and resolves all static JavaScript DOM references. This does not establish rendered accessibility. |
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
qualify those capabilities for this public demo. There are no skips in the 64
new demo tests or the 214 fusion baseline tests.

## Execution and failure qualification

The 21 service tests exercise installation/execution qualification gating,
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

See [installation and operating commands](WEB_DEMO.md) and the machine-readable
qualification evidence in `docs/qualification/web-demo/`.
