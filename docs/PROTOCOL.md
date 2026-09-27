# Workbench protocol v1

## Shared experiment projection

`experiment.inspect` accepts exactly `{"bundle_id":"<retained identity>"}` and
returns `ciw.experiment-view.v1`. It projects one committed native occurrence into
ordered scientific panels and its recorded input graph, retaining full covariance,
units, time/frame context, source/evidence/result/execution identities and original
verification. Coordinate, mesh and declared-parameter panels may include an optional
presentation `render` object (`ciw.panel-render.v1`: `plane2d`, `mesh`, or `strip`)
that copies already-projected points, a declared mesh, or a retained parameter axis
for inspection clients. `plane2d` and `strip` copies keep `connect: false`;
clients must not draw a polyline between those samples. Circle overlays remain
declared-constraint copies; fitted radii are refused on detach. The canvas names
a declared circle from its retained constraint_id. Detached mesh
copies refuse path indices outside the declared vertices. Detached strip copies
refuse a nonfinite or decreasing parameter. Detached plane copies refuse
nonfinite coordinates. Jacobi views may copy declared arclength strips onto
`system_canvases` so a named companion axis remains beside mixed-unit pose
panels. Mesh-path views may also copy that mesh onto `system_render`
so a 3D canvas can outlive the selected panel. That mesh copy carries the declared
frame identity for the viewport caption. Circle and torus views copy a
declared plane onto the same field so a companion 2D canvas can keep the
constraint or quotient visible beside residual or scalar panels. When a view
declares more than one retained plane, `system_canvases` lists those copies and
`system_canvas_id` names the default. `canvas_id` is the canvas entry
(`cover_points`, `parallelogram_points`, `observed_points_m`, `separation`,
`vertex-distances`). `frame` is the declared coordinate or path frame
(`area-one-flat-quotient`, a GTE coordinate frame, a Jacobi path frame).
Those two names stay distinct once an entry id is stamped. Clients may switch copies; they must not
resample the path. It does not execute a provider or change selection/retention.
See [the complete view contract](EXPERIMENT_VIEW.md). Existing `workbench.changed`
notifications invalidate the catalog; clients fetch authoritative state and keep
replay occurrences separate from measurement samples.

## Transport

Status: first implementation contract. Python is authoritative; terminal and Godot are independent clients. Local endpoint: `ws://127.0.0.1:8765`. Text JSON only in v1; no terminal scraping.

Request: `{"protocol_version":1,"request_id":"unique-client-id","type":"session.get","payload":{}}`.
Success: `{"protocol_version":1,"request_id":"...","type":"response","payload":{...}}`.
Failure: same envelope with `type: "error"` and `payload: {"code":"...","message":"..."}`.
Broadcast after selection mutation: `{"protocol_version":1,"request_id":null,"type":"selection.changed","payload":SELECTION}`.
The native endpoint sends a `session.snapshot` event on connection with the same payload as `session.get`. Responses and broadcasts can interleave; correlate by request_id. Clients may reconnect and request a fresh snapshot.

The additive `/spatial` endpoint sends `spatial.ready` with session identity and
read-only capabilities. It accepts only `spatial.list` (`{}`) and
`spatial.inspect` (`{source_id}`), returning geographic source descriptors and
a `ciw.spatial-view.v1` packet respectively. Its only broadcast is
`workbench.changed`. Browser origins require exact host configuration via
`--spatial-view-origin` and are rejected on other paths. No-Origin access to
`/spatial` remains read-only. See [module contracts](INTEGRATED_MODULES.md).

## Commands

| Type | Payload | Response payload |
| --- | --- | --- |
| `session.get` | `{}` | `{session_id, run: RUN_METADATA, selection: SELECTION, results: [RESULT_SUMMARY]}` |
| `run.get` | `{}` | Full RUN, with backend sample values and render geometry |
| `selection.update` | `{expected_revision: integer, cursor_s?: number, interval_s?: [start,end], channel?: string}` | SELECTION; broadcast to every connected client |
| `sample.get` | `{time_s: number}` | `{run_id, evidence_id, sample_index, time_s, values: {q,v,energy}, units: {q,v,energy}}` nearest retained sample; earliest on tie |
| `analysis.stats` | `{channel?: string, interval_s?: [start,end]}` | RESULT |
| `analysis.spectrum` | `{channel?: string, interval_s?: [start,end]}` | RESULT |
| `result.get` | `{result_id: string}` | RESULT (only results from this running session) |
| `result.list` | `{}` | `{results: [RESULT_SUMMARY]}`; discover stored analyses without running them |
| `workspace.save` | `{}` | `{workspace_file: string}`; saves to the service output directory |

The initial selection is `{run_id, channel:"q", interval_s:[0,duration_s], cursor_s:0, coordinate_frame:"oscillator-state", revision:0}`. Analysis intervals are half-open `[start,end)` and independent of the playback cursor. Updates must specify the observed expected_revision; stale updates fail with `revision_conflict` and clients refresh. Analysis responses capture the selection revision and exact interval that produced them; results never mutate. Cursor updates do not recalculate analyses. Empty or reversed intervals, out-of-range cursors, unknown channels, nonfinite numbers and unsupported versions are rejected.

## Recorded run and instrument API

`RUN` has `{run_id, evidence_id, instrument, metadata, time_s: [number], channels: {q: {unit:"m",values:[number]}, v:{unit:"m/s",values:[number]}, energy:{unit:"J",values:[number]}}, render: {...}}`.
`metadata` has `{duration_s, sample_rate_hz, sample_count, coordinate_frame:"oscillator-state", model: {...}, provenance: {...}}`.
`RUN_METADATA` is `{run_id,evidence_id,instrument,metadata,channels:{q:{unit:"m"},v:{unit:"m/s"},energy:{unit:"J"}}}` (no large arrays).

Render geometry is backend-prepared, explicitly non-measurement data:
`render: {coordinate_frame:"oscillator-state", axis_labels:["q (m)","energy (J)","v (m/s)"], trajectory:[[q,energy,v],...], surface:{vertices:[[q,energy,v],...],indices:[int,...]}, sample_indices:[int,...], transform:{origin:[0,0,0],scale:[1,1,1],note:"..."}}`.
Render point k resolves through sample_indices[k] to the retained scientific record. The small demo sends every sample. Render geometry must never be used to compute a measurement.

Python instrument module `ciw.instruments` provides `make_demo_run() -> dict`, `validate_run(run) -> None`, `run_metadata(run) -> dict`, `inspect_sample(run,time_s) -> dict`, `compute_statistics(run,channel,interval_s) -> dict`, `compute_spectrum(run,channel,interval_s) -> dict`. Computation functions return operation-specific `data`; session code wraps provenance and persistence. Validate recordings at load, and validate direct computation inputs too.

Stats data: `{sample_count, mean, minimum, maximum, rms, unit}`.
Spectrum data: `{sample_count, method:"periodogram", window:"hann", detrend:"constant", scaling:"density", frequency_hz:[...], psd:[...], unit, peak_frequency_hz, sample_rate_hz}`. A one-sided Hann-window PSD uses retained float64 samples; this v1 does not claim Welch, spectrogram or streaming acquisition support.

## Results and evidence

`RESULT` is `{result_id, evidence_id, operation_id, execution_id, verification_id:null, verification_status:"not_verified", run_id, selection_revision, channel, interval_s, created_at, data}`. Operation IDs are `statistics.v1` and `spectrum.periodogram.v1`. Verification stays explicit and unclaimed. Results are persisted by the server and headless CLI in a chosen output directory. Source recordings are separate from derived results. A failed `analysis.stats` or `analysis.spectrum` calculation does not publish a RESULT. An ordinary provider failure is retained as a refused execution with no result and returned as an error. `KeyboardInterrupt` and `SystemExit` still propagate. A failure while writing a completed result remains `storage_error`.

`RESULT_SUMMARY` includes result/operation/execution IDs, channel, interval, creation time and verification status, without numerical arrays. Snapshots and `result.list` expose these so fresh clients can discover analyses restored from a workspace. New analyses do not yet produce an event; refresh the list to discover results created by another client.

Binary transport, occupancy operations, live acquisition and spectrograms are not implemented. The additive adapter and covariance sections below specify the delivered external-provider JSON operations.

## Workspace replay

The saved JSON contains `workspace_version: 1`, the complete scientific `run`, `selection`, immutable `results`, and reserved `view_settings: {}`. Opening it validates and restores these records; it does not invoke numerical operations. A new live session identity is assigned while the existing run, evidence, result and execution identities stay intact. New analyses explicitly create new execution/result IDs. `recording_file` on results points to the separately persisted source copy; embedded workspace evidence permits portable reopening. This is a local prototype format, not yet a production persistence adapter.

The demo evidence ID is SHA256 over canonical JSON of instrument, metadata, timestamps and channels. The complete recording, including render data, has a separate content-derived filename. Replay checks both bindings and validates result semantics before writing. These hashes detect inconsistent content; they do not establish source authenticity or scientific verification.

Native local connections have no Origin header. The launcher binds `127.0.0.1` by default. Browser origins require explicit permission on the read-only spatial endpoint. The container explicitly binds `0.0.0.0` inside its network namespace, with Compose publishing only on the host's `127.0.0.1`. Remote execution/authentication are outside this prototype. Cursor requests are bounded by the first and last retained sample timestamp; interval end may equal recording duration. Integer-valued revisions are compared numerically; Python envelopes reject boolean revisions and protocol versions.

The service drains connections and saves its workspace on graceful shutdown. Windows process termination is immediate; the native controller sends `workspace.save` and verifies the response before stopping its owned process. Forced termination and power loss are not covered by an autosave guarantee.

## Additive adapter and operation slice

The legacy oscillator request/response contract above remains protocol version 1.
Generic scalar/event recordings use `run_schema: "run.v1"` and embed a strict
`ciw.instrument-manifest.v1` under `metadata.manifest`. An event record can have
one timestamp, no sample rate, arbitrary declared channels and no render data.
The manifest role distinguishes measurement adapters from instruments and
operation providers. The current Godot client explicitly declines this new
record/view contract; the terminal and structured session API expose it.

Three additive session requests are available:

| Request | Payload | Response |
| --- | --- | --- |
| `operation.list` | `{}` | Locally registered operation IDs and roles |
| `operation.execute` | `{"operation_id":"fsrt.tank-reconstruct.v1","parameters":{"model":{...}}}` | `status`, retained `execution`, and a `result` or `null` |
| `execution.list` | `{}` | Retained completed/refused execution records |

A refusal is a recorded invocation with no result, not an estimated state.
Calibration failures during acquisition/import raise `calibration_unavailable`
and do not create a calibrated run or result. Invalid protocol/configuration
requests retain the existing error envelope. Source bindings must be supplied
explicitly by the operator; opening a saved workspace cannot authorize code.

Operation results use `schema: "ciw.operation-result.v1"` and executions use
`schema: "ciw.execution.v1"`. They retain operation, run, source evidence,
selection, parameters and runtime bindings, distinct execution/result IDs, and
content-integrity digests. An execution's `result_id` is null when refused.
Verification remains `not_verified` with `verification_id: null`; no estimator
or successful replay can promote that status. Domain output schemas are
validated without executing their scientific providers during reopening.

A workspace with retained operation executions uses `workspace_version: 2` and
an `executions` array. Version 1 workspaces continue to open unchanged. Reopening
preserves identities and results; explicit replay invokes trusted local bindings
and appends fresh execution/result identities. See [ADAPTERS.md](ADAPTERS.md) for
the exact pinned single-snapshot scope, raw-byte retention, covariance mapping,
terminal commands and offline replay setup. This additive slice does not claim
streaming acquisition, binary transport, a multi-run journal or physical
validation.

## Additive covariance and calibration-serving contract

Protocol version remains 1 and workspace version remains 2. Operation IDs use
an explicit positive version suffix (`.v1`, `.v2`, ...); a syntactically valid
identity never binds code. Unregistered operations produce retained refusals.
The new trusted payload schemas are `fsrt.tank-reconstruct.v2` and
`jspt.covariance-propagate.v1`. Calibration acquisition uses `rci.calibrate.v2`.
Their exact domain versions are pinned in `adapter-runtimes.json`.

`covariance-artifact.v1` carries `covariance_id`, ordered `quantity_ids` and
`units`, `frame`, `reference_values`, full `matrix`, `method`, `basis`,
`provenance` and `assumptions`. Its content identity includes every field except
`covariance_id`; matrix entry (i,j) has units `units[i] * units[j]`. Numerical
values are never silently symmetrized, clipped, diagonalized or reordered by
CIW validation. A positive semidefinite singular matrix is a valid artifact;
a specific operation can still refuse it under its numerical requirements.
See [COVARIANCE.md](COVARIANCE.md) for the exact artifact and input contracts.

`session.get`, `result.list` and `result.get` accept optional `evaluated_at`,
a timezone-aware ISO timestamp including seconds. Omission means current UTC.
For an RCI-backed run, session snapshots and list responses carry `calibration`
next to their other payload fields. A `result.get` success carries `calibration`
as a sibling of `payload` in the response envelope: the payload remains the
exact immutable saved result. Oscillator responses add no calibration field.
A connection snapshot evaluates serving time at connection, and never changes
historical acquisition evidence.

Each calibration status contains source/profile identities and validity bounds,
`acquisition {observed_at, applicable_at_acquisition, valid_from, valid_until,
basis, provenance}`, and `serving {evaluated_at, expired, not_yet_valid,
current_applicability}`. Acquisition provenance is `persisted.v2` for the new
RCI record or explicitly `derived.legacy-v1` for older records. Serving metadata
is not persisted into, or hashed as, the scientific evidence/result. Present
expiry does not invalidate a historically applicable observation.

JSPT `operation.execute` parameters retain `source_result_id`, `source_artifact`,
the exact `source_covariance`, and the declared map fields. The CLI resolves
these from a retained FSRT/JSPT result; live clients may reuse those exact
parameters with an explicitly bound `--jspt-repo`. The service checks source
links before execution. Reopening checks retained dependencies and rejects
missing, mismatched or cyclic references before writing a destination.

A saved runtime is executable only if its revision/module is on the built-in
current-or-historical allowlist and the operator supplies that exact clean
checkout and matching interpreter/dependencies. A saved file cannot extend
this allowlist. An invocation with no bound runtime cannot be silently replayed
using the latest engine; it requires an explicit new execution.

## Additive geometric reconciliation contract

The additive GTE operation `gte.project-circle.v1` uses the same operation and
workspace envelopes. Bind an operator-supplied checkout with `serve --gte-repo`
or the `geodesic create/replay` commands. Its complete retained batch is the
scientific scope; the selected interval must contain all retained samples or
the operation refuses without a result (`selection_scope`). Only explicit
whole-object `constraint` and `policy` overrides are accepted as parameters;
observations, covariance, frame and acquisition time remain bound to evidence.
The existing `backend` role identifies this geometric result within the generic
enum and does not claim state-estimator semantics. Read-only source
and result validation is built into CIW, so reopening needs no GTE runtime.
See [GTE.md](GTE.md) for exact inputs, statuses, covariance meaning and limits.

## Failed native workflow attempts

Shared `operation.execute` and `bundle.replay` calls reserve storage before
entering a native workflow. If that attempt raises an exception, the workbench
retains a `ciw.workflow-failure.v1` record and preserves the existing error
behavior. The same path covers every native workflow; it does not change a
provider's numerical record or invent a partial successful bundle.

The record binds a fresh `workflow-execution:` occurrence to the operation,
retained source/evidence, exact detached request and its canonical digest. A
replay request binds the original bundle. It also records aware wall-clock start
and finish times, `dispatch` or `retention` phase, and a bounded failure reason.
These are software history timestamps, not measurement clocks. An explicit
adapter refusal has status `refused`; other caught exceptions have status
`failed`. `scope` is `workflow_attempt`, `runtime` is null with
`runtime_status: not_captured`, and both `result_id` and `bundle_id` are null.
The wrapper cannot infer whether a native process ran or which partial steps
completed. No replay-success receipt or verification claim is created.

`execution.list` and the snapshot's `failed_executions` array expose bounded
`ciw.workflow-failure-summary.v1` projections. They retain the request digest,
full-record digest reference, failure reason and replay target but omit the
potentially large request body. Exact records are available in the saved
workspace and Python `workbench.list_failed_executions()` API. A summary's
`record_sha256` identifies the full record, not the summary. A retained failure
increments workbench revision and triggers
`workbench.changed` even when the request returns an error or its handler
closes. Inspection/reopening never invokes providers or rechecks a proof.
Retry requires a new explicit execute/replay request and creates a new
occurrence; an earlier failed attempt remains immutable.

Workspaces containing these records retain outer workspace format 3 and use
`ciw.retained-workbench.v3` internally, with `candidates` and `failed_executions`
arrays. Workbenches without failures retain their existing v1/v2 encoding.
Historical encodings remain readable. Restore checks content digests, source,
operation and replay-target bindings, strict field sets, identity collisions,
revision counts and storage limits. The combined completed-bundle/failed-attempt
limit is 128; total retained bytes remain bounded by 64 MiB. Requests and failure
overhead are reserved before dispatch, so repeated refusals consume capacity.

Malformed pre-dispatch requests, missing host bindings and capacity rejection
do not create attempts. This increment covers the shared native workflow path,
not standalone provider calls or ESM candidate actions. Checkpointing or normal
server shutdown persists terminal attempts; crash recovery of in-flight work is
not implemented. Unsigned digests detect inconsistent changes, not coherent
fabrication or deletion of an entire history. No physical or admission authority
follows from a failure record.

## Shared measurement, geometry and stability operations

The additional shared kinds `measurement-chain`, `geometric-circle` and
`identified-stability` use the same `source.add`, `operation.execute`,
`bundle.replay` and `experiment.inspect` surfaces. Their operation IDs are
`ciw.measurement-chain.v1`, `ciw.geometric-circle.v1` and
`ciw.identified-stability.v1`. All take an exact retained `source_id`;
identified stability additionally selects an `upstream_bundle_id` whose kind
is `identified-design`. Its source binds the selected native model and state
result/execution identities. The measurement chain's unchanged FSRT and JSPT
results and execution IDs are also exposed through `result.*`, `execution.list`
and instrument inspection, alongside the outer RCI operation. Replays create
fresh occurrences and preserve the original evidence. These objects have typed
object context and do not create or implicitly merge fusion contexts. See
[shared module operations](REMAINING_MODULES.md) for input contracts and bindings.

## Shared acquired-window and residual-monitor operations

These operations use the shared workbench catalog in workspace format 3;
protocol version remains 1. Bind the eight exact provider checkouts with
`serve --acquired-stream-stack-root /path/to/providers`. The
[acquired stream guide](ACQUIRED_STREAM.md) contains the complete declarations,
pins, runnable client and refusal conditions.

`source.add` accepts kinds `acquired-calibrated-window` and `residual-monitor`
with their versioned source schemas. `operation.execute` uses
`ciw.acquired-calibrated-window.v1` with parameters
`{source_id, upstream_bundle_id}`. The upstream must be a retained
`acquired-dataset` occurrence. Every selected PPDA observation, record, document
and first-acquisition snapshot row is bound explicitly. Native calibrated-window
steps retain their child bundle identity and SET receipt; the outer mapping has
its own verification scope.

`ciw.residual-monitor.v1` takes `{source_id}`. Its source declares an ordered
`window_bundle_ids` list of retained calibrated windows, including acquired
windows. The monitor consumes their exact GSIE innovations and covariance.
It retains native OIT/FDIR results, unknown cross-window covariance and separate
reference priors. Replayed windows cannot count as additional observations.
OIT-held rows retain detection results but do not advance CUSUM. Threshold
crossings cannot grant statistical alarm authority or unique fault isolation.

Both paths use `bundle.get`, `bundle.replay`, `experiment.inspect` and
`workbench.changed` in the existing live session. Replay creates fresh execution
and result occurrences while preserving the selected upstream evidence.
Inspection and reopening neither execute providers nor admit canonical state.
