# Device and Instrument Gateway

**Status: proposed contract and implementation sequence; no gateway runtime is
delivered by this page.** PDT remains the laboratory. The gateway connects an
investigation to supported apparatus through typed capabilities, bounded
requests and retained dispatch evidence. MCP, the terminal and direct software
clients are interfaces to that boundary.

This document owns the gateway proposal. [Acceptance cases](DEVICE_GATEWAY_ACCEPTANCE.md)
define its unfinished qualification work. Existing executable coverage remains
in [Integration coverage](INTEGRATION_COVERAGE.md).

## Source baseline inspected on 2026-09-26

| Repository | Inspected revision | Established by source inspection |
| --- | --- | --- |
| PDT | `9237623d036c6ca4e0b8edf13d3b021ea000a7a4` | Retained acquisition and read-only machine-manifest paths; no general device gateway. |
| Atelier-MCP | `6a10bea78323bfdbba297774142f7c449cbc87b9` | In-process CNC simulator, observe/prepare/command/recover separation, payload-bound preview tokens. |
| CNC-Machine-MCP | `e7e184f8687f6c57fb452d18beba874c3255261d` | README, invariant-corpus declaration and corpus test; no executable CNC server in the inspected tree. |

These are audit references, not newly qualified provider pins. No runtime
allowlist or provider manifest changes accompany this proposal.

Atelier's [runtime](https://github.com/giasonpooni/Atelier-MCP/blob/6a10bea78323bfdbba297774142f7c449cbc87b9/src/atelier_mcp/runtime.py)
returns a preview token to the requesting client and accepts it on a subsequent
request. Its [token implementation](https://github.com/giasonpooni/Atelier-MCP/blob/6a10bea78323bfdbba297774142f7c449cbc87b9/src/atelier_mcp/tokens.py)
checks action, payload digest, expiry and single use in process memory. This
establishes request binding, not a separately authenticated human approval or a
durable dispatch journal. The payload includes the job ID and pass arguments,
but does not bind every field of the job configuration shown in the preview.

The [simulator](https://github.com/giasonpooni/Atelier-MCP/blob/6a10bea78323bfdbba297774142f7c449cbc87b9/src/atelier_mcp/adapters/sim.py)
updates its state in process; it supplies no physical completion evidence.
Retain Atelier's current interface and restrictions as the CNC profile. Extract
reusable lifecycle machinery additively; a wrapper must not broaden its command
surface or treat its preview token as the new authorization mechanism.

## Responsibilities and paths

```text
Operator -> terminal / direct API / optional MCP -> PDT investigation
                                                   |
                                          Device and Instrument Gateway
                                          registry, preparation, authorization,
                                          ownership, durable jobs and receipts
                                                   |
                                       qualified device-specific adapter
                                                   |
                                          existing device controller
                                                   |
                                 retained observations and controller receipts
                                                   |
                             existing acquisition / calibration / inference
                                                   |
                                  investigation history and ESM handoff
```

The gateway coordinates eligibility and dispatch. Drivers implement device
communication. Scientific providers interpret measurements. ESM admission and
physical operating permission remain distinct from retention and calculation.

The supervisory path carries compact requests and status. The measurement path
carries bounded recordings, images and waveforms with retained references.
Deadline-critical loops remain in qualified controllers. Closing an MCP client
must neither discard a recording nor determine controller behavior.

## Proposed common contract

The following are conceptual record requirements, not registered wire schemas,
CIW operation IDs or executable endpoints. Concrete encodings and limits must be
fixed with their tests before the first implementation is admitted.

| Record area | Required meaning |
| --- | --- |
| Device binding | Stable registered identity; model; firmware; adapter revision; explicit simulated, recorded or physical origin; device identity evidence. A transport address is not identity. |
| Configuration binding | Content-bound channel setup, firmware/bitstream, tool/payload where relevant, frames, clocks and operating limits; original source bytes and revision. |
| Capability | Versioned, allowlisted operation and strict argument/result schemas; quantity meanings, numeric bounds, prerequisites, effects, completion evidence, cancellation support and disconnect policy. |
| Observation | Sample identity and sequence; raw value or explicit missing reason; quantity, units and coordinate order; frame; sampling support; source clock and acquisition time; receipt time; quality and applicable calibration references. |
| Uncertainty | Declared uncertainty model, full applicable correlations and dependencies, or explicit unknown/not applicable. Do not invent covariance from quality flags or duplicate a common source as independent evidence. |
| Prepared plan | Exact typed arguments, device/configuration/capability bindings, prerequisites, operating envelope and expiry. Preparation itself does not send a device action. |
| Authorization | Trusted issuer and subject, permitted capability/device/configuration, exact plan or bounded standing policy, limits, expiry, revocation and evidence of the authorization decision. |
| Ownership | Resource scope, exclusive writer policy, allowed concurrent reads, owner identity, lease generation and enforceable fencing or an explicit unsupported takeover state. |
| Execution history | Durable job and attempt identities, ordered events, requested bytes, adapter/controller responses, observed configuration, deadlines, receipt references and unresolved outcome. |
| Scientific checks | Separate scoped checks and their supporting observations; no controller acknowledgement, digest or successful dispatch is itself physical validation or admission. |

A reading request that triggers excitation, moves an instrument or consumes a
sample is an action even if its return value is a measurement. Profiles classify
effects; an MCP read-only annotation does not supply this classification.

Device discovery only finds candidates. Registration requires an explicit
supported binding. Missing units, unresolved frames or unknown clock alignment
cannot acquire plausible defaults. Configuration settings and metrological
calibration records remain separate. Historical calibration applicability is
evaluated at acquisition; present expiry does not rewrite old observations.

## Identity and retention

CIW's [protocol](PROTOCOL.md) remains authoritative for its operation,
execution, evidence and result identities. A gateway capability identifies a
defined operation; a durable job identifies one requested occurrence. An
idempotency key identifies submission retries in a declared principal/device
namespace. None of these is a measurement identity or a CIW result identity.

Each permitted dispatch attempt has its own retained identity. Network retries
of one accepted submission return the same job; changing the request under the
same key is refused. Creating a new key does not bypass a consumed plan's
single-dispatch rule. Repeating an experiment deliberately requires a new plan
and authorization evaluation, execution and observations.

Gateway receipts become referenced source artifacts through a reviewed CIW
adapter. They must not be inserted as successful scientific results. Existing
CIW refusals still retain an execution with no result; protocol errors and
gateway dispatch events do not silently change that convention. Raw or partial
observations may survive an unsuccessful device job without implying that the
requested scientific operation succeeded.

PDT's [machine manifest](CONTRACT_FOUNDATIONS.md#machine-manifest) is accepted
for read-only interpretation. It is not a device-operation permit. The existing
[acquisition lane](ACQUIRED_STREAM.md) consumes retained finite snapshots.
Connecting a new recording to it requires a qualified producer and explicit
mapping of original sample, source, clock, frame and calibration identities;
renaming a gateway receipt as a PPDA result does not establish that connection.

## Preparation, authorization and dispatch

1. Validate the registered profile and typed inputs. Retain the complete plan
   and all prerequisites without changing apparatus state.
2. Evaluate an independently attributable approval or a host-configured standing
   authorization. Returning a preview token to its caller is insufficient.
3. Acquire the required ownership. Recheck device identity, configuration,
   controller session, current conditions, authorization and expiry immediately
   before dispatch.
4. Durably reserve the submission key and plan, append a dispatch-intent event,
   then invoke the adapter. A journal failure prevents new dispatch.
5. Retain acknowledgement, progress, controller-reported completion and
   observations independently. Perform scientific checks through their existing
   operation boundaries.

The plan binds all fields that can change the meaning of the action, including
CNC stock and tool, robot frame and payload, and acquisition clock or FPGA
bitstream. A changed binding requires a new plan. Freshness checks and dispatch
must be protected by the ownership/controller mechanism; a preflight read alone
does not eliminate a check-to-use race.

A standing authorization has explicit duration, quantity and repetition limits.
Consumption of those limits must be atomic with dispatch reservation. Neither a
model output nor a client-supplied identity establishes the issuer's authority.
Expiry uses a declared time basis; restart or clock rollback cannot silently
renew an expired plan or lease.

A lease alone cannot fence a paused former writer. The adapter/controller must
enforce the generation, or the profile must refuse automatic ownership transfer
until the prior writer is demonstrably excluded. Cancellation privileges and
independent protective controls are not blocked by a normal job lease.

## Recovery and physical outcomes

```text
request accepted
    != controller acknowledgement
    != controller-reported completion
    != independently established physical outcome
```

Use separate status dimensions. Dispatch may be not sent, possibly sent or
acknowledged. Controller execution may be running, reported completed, reported
failed, reported cancelled or unknown. Physical outcome retains the scope and
evidence of any assessment, or remains unknown. Do not compress these into one
success flag.

Append events before updating a derived status view. After a crash between
dispatch intent and acknowledgement, treat the attempt as possibly sent.
Reconcile against the controller's job identity/session and retained observations.
Do not automatically resend a motion, dispense or excitation. A durable journal
does not prove exactly-once physical execution; a controller without deduplication
and reconciliation support leaves a stricter recovery gate.

Cancellation is a separate request with its own receipt. Cancellation requested
is not cancellation confirmed; confirmation does not erase effects already
performed. Preserve completion/cancellation races and partial recordings. A
software stop command is not evidence of an independent emergency stop.

Each profile must declare behavior on client loss, adapter loss, deadline,
storage failure, device restart and partial completion. Stop, hold or continue
cannot be selected generically across equipment. The offline pilot has no live
fallback claim. Cross-device orchestration records each job separately; a
failed acquisition after positioning does not roll the motion back automatically.

## Reopen, replay and re-experiment

Reopening validates retained records and reconstructs views without contacting
devices, invoking providers, loading saved executable paths or restoring active
authority. A saved grant, lease or prepared plan is historical evidence.

Historical playback reads the event/observation stream. Explicit simulation
replay uses a qualified simulator and fresh execution identities while retaining
the original origin label. Reprocessing retained samples through CIW creates
new computation occurrences, not new physical samples. A physical repetition
is a newly authorized experiment and must never be hidden behind workspace
reopen or numerical replay.

## Pilot sequence

1. **Recorded sensor and gateway journal.** Implement strict bindings, finite
   observation records, deduplication and crash recovery with a fault-injecting
   simulator. Retain missing samples and demonstrate provider-free reopening.
2. **Atelier CNC simulation.** Wrap the existing simulator while preserving its
   API, material/envelope/stepdown restrictions and command-off default.
   Demonstrate full configuration binding and the separate authorization path.
3. **Robot middleware simulation.** Qualify a bounded joint-state and prepared
   trajectory profile against an actual pinned robotics middleware setup.
   Distinguish a local test double, middleware mock and dynamics simulator.
4. **Shared investigation.** Retain declared sample locations, simulated
   positioning, observation timing and source lineage; feed qualified finite
   records into an existing PDT comparison or estimation operation.
5. **One physical read-only instrument.** Qualify the specific device, adapter,
   timing and calibration boundary against independent observations. Live
   motion, dispensing, machining and FPGA programming require separate gates.

The first runtime patch belongs in an additive transport-independent package
inside Atelier, with recorded/simulated profiles only. PDT supplies the retained
source adapter after the producer contract is executable. Do not create another
platform repository or a second estimation implementation.

## Interface precedents and later adapters

[W3C WoT Thing Description 1.1](https://www.w3.org/TR/wot-thing-description11/)
separates properties, actions, events, schemas and security metadata.
[SiLA 2](https://sila-standard.com/standards/) exposes laboratory functionality
through features with commands and properties. Reuse those distinctions; this
proposal does not claim conformance or implement either protocol.

The [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
supports structured results and resource links, and treats annotations from
untrusted servers as untrusted. Proposed gateway tool families are
`device_list`, `device_inspect`, `observation_read`, `acquisition_prepare`,
`action_prepare`, `prepared_execute`, `operation_status`,
`operation_cancel` and `record_inspect`. These are design names, not available
PDT endpoints. Capability-specific validation remains in the shared service;
native command strings and executable selection remain inside reviewed bindings.

Evaluate ROS 2/ros2_control/MoveIt, PyVISA, OPC UA, SiLA and board-specific
protocols as separate adapter projects when a pilot requires them. Their names
are not hardware-support claims or selected dependency versions. In particular,
[ros2_control mock components](https://control.ros.org/rolling/doc/ros2_control/hardware_interface/doc/mock_components_userdoc.html)
exercise interface plumbing; passing that gate cannot establish a physical
trajectory, sensor model or robot calibration.
