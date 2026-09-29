# Agent-selected observation images

`net_sim_capture` connects the existing stateful agent interface to NET's existing
`simulation.observation-capture.v1` operation. Select a retained observation and a
camera, render one PNG, and receive its original artifact/provenance plus an MCP
image block when it fits the operator's inline budget. The source simulation is
not stepped, restored or queried for hidden coordinates.

## Enable the native profile

```sh
python -m pip install -e '.[dev]'
net agent demo-config --stateful --stateful-capture \
  --godot /absolute/path/to/godot \
  --godot-sha256 sha256:EXECUTABLE_HASH \
  --output-dir agent-images
net agent serve --profile agent-images/profile.json \
  --simulation-profile agent-images/simulation-profile.json
```

Hash the Godot executable, not its ZIP archive. The existing qualified native
profile uses Godot 4.5.2. A real graphics display is required for image creation;
Linux qualification uses Xvfb/Mesa. Profile generation and server binding check the
executable without starting a simulation or renderer process. Use fresh output
paths and register the serve command with the MCP host using absolute paths.
No account or language-model connection is configured by these commands.

Capture is an independent opt-in permission: ordinary profiles remain eleven
tools, basic stateful profiles fifteen, and enabling capture adds one. Replay and
campaign grants are independent; all three extensions together offer eighteen.
The existing `net_replay` remains analysis replay, not image production.

Native capture configuration is operator-owned:

```json
"capture": {
  "executable": "/absolute/path/to/godot",
  "sha256": "sha256:EXECUTABLE_HASH",
  "timeout_s": 60,
  "models": ["motion"],
  "cameras": ["oblique", "front"],
  "max_captures": 8,
  "max_inline_bytes": 196608
}
```

The renderer object is bound in trusted Python. Tool arguments never select an
executable, file, graphics API, timeout, observer definition or coordinate array.
This is an application boundary, not an operating-system sandbox.

## Select an observation, not world state

The native example retains scalar `position` and `delayed` presets for existing
campaigns and adds `xyz` and `xyz-delayed`. Each full XYZ preset selects the existing
point provider's `position_x`, `position_y` and `position_z` channels.

When capture is granted for a model, successful observation responses also return
an opaque `observation` handle. The handle refers to the original retained result;
it contains no checkpoint bytes or reconstructed world state. Commands, replay and
campaigns all reuse the same observation publisher. Capture still checks the
selected observation's content rather than assuming that a handle implies XYZ.

A capture call supplies:

```json
{
  "observation": "o-REPLACE_WITH_RETURNED_HANDLE",
  "camera": "oblique",
  "sample_index": 10,
  "attempt": "current-image-1"
}
```

`sample_index` addresses the selected entity's sorted acquisition timestamps,
not a render frame or current simulation tick. Set it to `null` for an explicitly
empty batch. The entity is the original bounded point-model `projectile`; it is
not freely selected from arbitrary scenes. A nonempty batch requires a valid index.

The existing image projector enforces model, frame, units, channel availability
and missingness. A partial XYZ triple has no marker. An empty batch has no sample
time or coordinates. **Scalar campaign output cannot silently supply the other
axes.** Capture a full XYZ observation separately through an approved observer.
A checkpoint handle, unrelated result ID or filesystem path is not an observation
handle. Capture can select an older observation after its source instance stops.

This is a derived visualization, not a live camera measurement. Its sample and
availability times come from the original observation, not from rendering time.
Changing the camera preserves the selected coordinates but creates a new capture
occurrence. Original float values remain evidence; visual marker precision follows
the existing renderer contract.

## Receive the image and its provenance

Successful metadata includes original observation execution/result references,
the new capture execution/result IDs, an ordinary image-artifact handle, the PNG
SHA256, size, selected sample and delivery times, camera, availability and claim
scope. The image-artifact descriptor can be inspected using existing `net_inspect`.
Full capture results/checkpoints are not copied into its agent-readable store.

For `image_delivery: inline_mcp`, the tool response contains its normal text and
structured metadata **plus a standard MCP `image` block** with `mimeType: image/png`
and the exact PNG bytes encoded as base64. The image is not a URL, textual
placeholder, resized substitute or independently generated illustration. Client
support determines how a coding host displays that image; no model's visual
reasoning quality is asserted by transport qualification.

For `image_delivery: operator_bundle_only`, the PNG is valid and retained but
exceeds the configured inline byte cap. Metadata explicitly states this; no image
block is sent. The operator can inspect the original capture bundle. The artifact
limit remains 4 MiB. The inline cap is separately configurable from zero through
196,608 raw PNG bytes; binary transport does not weaken the original 64 KiB
scientific-record string limit or the bounded MCP wire envelope.

Protocol reference: MCP 2025-11-25, Tools / Image Content and Structured Content:
https://modelcontextprotocol.io/specification/2025-11-25/server/tools

## Execution, retention and failures

Capture uses the **same original stateful Session** and registers the existing
capture operation lazily once. No second Session, executor, numerical engine,
clock or world-state authority is introduced. Renderer processes are separate
from the original native simulation owner.

The existing attempt mechanism writes intent before capture work. Source selection,
model/camera permissions, PNG budget and observation shape are checked before
rendering. Preflight refusal retains an agent request/response but creates no
simulation/capture occurrence or image reservation and does not quarantine a
healthy source. Each admitted request reserves one capture; failed rendering or
storage does not refund it. Reservations are independent of replay/campaign budgets.

An actual renderer refusal is an original capture-operation refusal in Session,
not a fabricated successful image. The source simulation remains unchanged.
Unexpected publication failure blocks new stateful requests. No mutation rollback,
implicit render retry or durable restart recovery is inferred. Identical attempt
and request retries return the same receipt and inline image bytes without starting
another renderer, including after orderly host closure. A new attempt explicitly
requests new work. Altered data cannot reuse an old attempt.

Each admitted attempt uses the existing inspectable capture layout:

```text
stateful/attempt-current-image-1/
    request.json
    source-workspace.json
    capture-selection.json
    dispatch.json
    render.log
    native.json                 # when produced
    native-image.png            # diagnostic bytes, not itself acceptance
    images/<sha256>.png          # validated original artifact
    workspace.json
    capture.json                # only after workspace publication
    response.json
```

A valid `capture.json` may exist if later agent-response publication fails. That
is retained image evidence, not a successfully delivered agent response. Failed
or incomplete responses never emit inline image content. Failed native image
bytes may remain diagnostics under the original capture rules.

## Recheck and navigate

```sh
net simulation godot capture inspect \
  agent-images/agent-output/stateful/attempt-current-image-1
net simulation timeline build \
  --capture agent-images/agent-output/stateful/attempt-current-image-1 \
  --output-dir results/image-timeline
net simulation timeline inspect results/image-timeline
```

The original capture and timeline readers work unchanged. Image bytes, original
source dependencies and prior Session history revalidate without provider or
renderer execution. Hashes establish consistency, not publisher identity. Full
operator workspaces remain privileged evidence; observer labels are not access
control.

## Qualification and bounded scope

The regression suite covers original capture dispatch, source isolation, older
observations, retries, missing components, scalar rejection, grants, corruption,
publication order, image-size delivery and both small and greater-than-64-KiB
base64 transport. Renderer/source doubles are labelled as such, not native runs.

`scripts/check_simulation_agent_capture.py` uses the official test-only MCP SDK
against an installed stdio server and the original pinned Godot worker/renderer.
It checks four actual PNG deliveries, current/delayed/unavailable/front views,
original artifact inspection, retry/budget boundaries and provider-free timeline
reopening. Linux qualification requires a display. Windows covers host/package
contracts; native Windows rendering is not claimed by those tests.

Capture grants permit 1–8 renders per process and 256 disclosed observation
handles. Existing native/attempt/artifact/Session limits still apply. This is not
arbitrary scene capture, video, an optimizer, physical validation or state
admission. Ordinary records remain `not_verified` with null verification IDs.
