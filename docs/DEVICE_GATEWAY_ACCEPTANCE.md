# Device gateway acceptance plan

**Status: specified, not executed.** These cases qualify the proposed
[Device and Instrument Gateway](DEVICE_GATEWAY.md). They are not test results,
registered CIW operations or evidence that any physical device is supported.

## Evidence required for a gate run

Retain the exact profile, adapter/controller/simulator revisions, dependency
environment, fixture bytes and expected outcomes before running. Record each
case's actual events and dispatch count, source/observation identities, receipts,
failure output and assertions. Capture full saved workspace equality on reopen,
then check fresh occurrence identities on explicit replay. Required cases that
are skipped leave the gate open.

A source checkout reference is not a qualified provider pin. Runtime registration
requires the actual executable/artifact identity and installed-package tests.
Successful simulator tests establish the declared software behavior only.

The test harness owns the fault injector and dispatch counter independently of
the gateway's reported status. A gateway report saying "not sent" cannot alone
prove that no dispatch happened. Keep simulator acknowledgements, controller
completion and physical assessment separate in the expected record.

## Contract and authority cases

| Case | Stimulus | Required observable outcome |
| --- | --- | --- |
| DG-01 | Discover an endpoint without a registered profile or complete quantity/frame/clock binding. | It remains an unresolved candidate; zero dispatches and no fabricated measurement semantics. |
| DG-02 | Supply unknown fields, nonfinite values, unsupported units, executable paths or raw vendor commands. | Bounded validation refusal before dispatch; valid typed control case still works. |
| DG-03 | Prepare a valid operation under observe-only policy. | Inspectable plan where permitted, zero apparatus changes; execution remains refused. |
| DG-04 | Submit a preview token without separately established approval or standing authorization. | No dispatch; preview identity is not attributed to a human approver. |
| DG-05 | Change stock/tool, frame/payload, sampling clock, firmware or bitstream after preparation while retaining the same device/job name. | Stale plan refused; no reuse of the old authorization. Unchanged control fixture can proceed. |
| DG-06 | Expire or revoke authorization; exceed a standing duration/count limit; race two submissions for the final allowance. | Only an eligible reservation may dispatch; no overspend or silently renewed grant. |
| DG-07 | Competing writers, expired lease and a paused old writer resuming after takeover. | At most the currently fenced writer may dispatch; unsupported fencing blocks takeover. Authorized recovery remains available according to profile policy. |
| DG-08 | Mark an excitation-producing measurement tool read-only, or call the direct API instead of MCP. | Profile effects and shared policy still govern eligibility; presentation metadata and frontend choice cannot bypass it. |

## Durability and recovery cases

| Case | Stimulus | Required observable outcome |
| --- | --- | --- |
| DG-09 | Submit the same key and exact plan concurrently, then repeat after gateway restart. | One durable job and at most one dispatch for that accepted plan; each caller retrieves the same history. |
| DG-10 | Reuse a key with altered arguments, or reuse a consumed plan under a new key. | Conflict/refusal with no second dispatch. A deliberately repeated experiment needs a fresh plan and authorization evaluation. |
| DG-11 | Fail durable storage before dispatch intent commits. | Zero device dispatches; retain/report failure where storage permits and require recovery before new dispatch. |
| DG-12 | Crash after durable intent before send; separately lose acknowledgement after the simulator applies the action. | Both recover conservatively as possibly sent until evidence distinguishes them. No blind resend; the second fixture's physical side-effect counter remains one. |
| DG-13 | Disconnect or reboot the controller after acknowledgement. | Retain the original controller session and unknown execution outcome; later status must reconcile the correct job/session. A fresh idle status is not proof the action never happened. |
| DG-14 | Request cancellation, lose its acknowledgement, and race completion with cancellation. | Preserve both histories and partial effects; do not report confirmed cancellation from the request alone or erase completed action. |
| DG-15 | Close the MCP client while acquisition runs, and separately exhaust the configured recording quota. | Follow the declared bounded continuation/stop policy; retain completed chunks, explicit gaps and final/unknown outcome. No unlimited recording or loss of already retained records. |
| DG-16 | Roll back the wall clock or restart across plan/lease expiry. | No extension of expired authority. Ambiguous clock continuity blocks reuse until revalidated. |
| DG-17 | Position successfully but fail the following acquisition. | Separate positioning and acquisition outcomes and partial evidence; no automatic compensating motion or false whole-investigation success. |

## Observation, identity and replay cases

| Case | Stimulus | Required observable outcome |
| --- | --- | --- |
| DG-18 | Missing/out-of-order samples, duplicate arrival, device counter reset and uncertain cross-device timing. | Preserve source identities, declared order, acquisition/receipt clocks and missing reasons; no synthetic alignment or double counting. |
| DG-19 | Unknown uncertainty, shared calibration error and two derived streams from the same sample. | Keep unknowns and dependency/full covariance information; no independent-evidence duplication or invented confidence. |
| DG-20 | A calibration was applicable at acquisition but is expired at inspection. | Preserve historical applicability and current serving status separately; a stale current plan is still rejected. |
| DG-21 | Controller acknowledges, then reports completion without an independent physical observation. | Distinct accepted/acknowledged/completed events; physical outcome remains unestablished. A simulated pose is labelled simulated. |
| DG-22 | Save and reopen a recording/history with all adapters unavailable and dispatch/provider entry points replaced by failing sentinels. | Full retained identities and bytes restored; zero provider/device calls, no active authority and no new measurements. |
| DG-23 | Replay the retained event stream; explicitly rerun its qualified simulation; separately request a physical repetition. | Playback has no dispatch; simulation creates fresh execution identities with simulated origin; physical repetition requires a new plan and observations. |
| DG-24 | Tamper with source bytes, configuration, event order, receipt links or CIW evidence/result bindings. | Structural/integrity refusal without executing an adapter; earlier valid workspace remains available. |
| DG-25 | Import the producer's finite recording through the installed PDT acquisition adapter, save, reopen offline and explicitly reprocess. | Exact original sample/source lineage plus distinct CIW operation/execution/result identities; reprocessing creates no physical sample and no automatic verification or admission. |
| DG-26 | Use a saved workspace to request a different executable, profile allowlist entry or restored live grant. | Refuse executable/authority escalation; host bindings remain authoritative. |

## Profile gates and delivery order

| Gate | Required additions | Current status |
| --- | --- | --- |
| G0: contract | Strict serializable schemas, explicit budgets, deterministic validation, event-transition tests and all record meanings fixed. | Proposed in the gateway contract; not implemented. |
| G1: recorded sensor | Finite raw recording, explicit missing samples, durable journal, fault injection and provider-free reopen. | Pending implementation and tests. |
| G2: Atelier simulation | Existing Atelier regressions plus full configuration binding, external authorization evaluation and durable recovery. | Existing tests inspected, not executed in this increment; new behavior pending. |
| G3: robot middleware simulation | One pinned middleware/controller setup, bounded joint-state/trajectory profile and timeout/cancellation tests. | No middleware installed or qualified by this increment. |
| G4: shared PDT investigation | Qualified acquisition producer/importer, linked positioning and samples, installed-package comparison/estimation, save/reopen/replay with zero required skips. | Pending; existing acquisition support is not this gateway connection. |
| G5: physical observation | One named instrument, read-only adapter qualification, independent timing/calibration/reference evidence and held-out measurement check. | Not performed. |
| G6: physical action | Device-specific authority, commissioning, reconciliation, protective boundaries and independently observed outcomes. | Not performed; simulation cannot close this gate. |

Retain Atelier's command-off default, material/extraction, envelope, stepdown,
payload mismatch, forged-token and handoff cases while introducing the wrapper.
The existing tests do not cover every new gateway obligation.

## Decisions to close before runtime registration

- Select a durable journal and specify atomic reservation, event order, restart
  recovery, quota and retention behavior. Do not describe an in-memory map as
  durable or promise exactly-once physical effects.
- Fix canonical encodings, units, identity/digest scope, size/count/time limits,
  and ownership of the device/profile registry.
- Bind an actual trusted authorization issuer and policy revision; implement
  the recorded/simulated pilot without enabling live apparatus.
- Select the exact sensor recording and robot simulator/middleware, then qualify
  their versions. The source audit revisions are not sufficient.
- Map gateway source artifacts into the existing CIW envelopes and prove both
  provider-free reopen and explicit fresh replay before registering the adapter.

## Validation of this documentation increment

Source inspection covered the pinned Atelier runtime, tokens, policy, guard
lattice, simulator and existing tests, the CNC seed tree, and PDT's acquisition,
manifest and protocol documentation. It was not an execution test.

Local shell/process startup fails with `helper_unknown_error: apply deny-read ACLs`.
No gateway unit, installed-package, middleware or physical tests were run.
Documentation structure, acceptance-case uniqueness, relative link targets,
scope of changed files and published-content equality are checked separately;
those checks do not close G0 through G6.
