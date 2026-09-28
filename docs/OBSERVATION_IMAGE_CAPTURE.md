# Image evidence from retained native observations

NET can render an explicitly selected XYZ observation as a real Godot viewport
PNG and retain that image as an existing `ciw.artifact.v1`. The image-producing
`simulation.observation-capture.v1` operation gets its own CIW execution/result,
linked to the original observation execution. It does not advance a simulation,
restore a checkpoint, or turn a derived image into a live camera measurement.

This extends [native campaigns](GODOT_STATEFUL_CAMPAIGNS.md) and the existing
Session. It does not replace the GSC spatial viewer, numerical comparator,
persistent Godot worker, campaign implementation or replay implementation.

## Run a complete native example

On the qualified Linux render profile, use an installed package and the explicitly
selected Godot 4.5.2 stable executable. Hash the executable, not its ZIP archive.

```sh
python -m pip install -e '.[dev]'
net simulation godot capture demo --godot /absolute/path/to/godot --godot-sha256 sha256:EXECUTABLE_HASH --output-dir results/images-001
net simulation godot capture inspect results/images-001/current
net simulation godot capture inspect results/images-001/delayed
net simulation godot capture inspect results/images-001/unavailable
```

The demo executes the existing native point provider with an asymmetric initial
position and collects current, delayed and initially unavailable XYZ observation
batches. It stops and closes that source provider **before** rendering. Each image
is then produced by a separate render-only Godot process. `summary.json` names the
PNG files and retains the original source and new capture execution identities.

A real graphics display is required; an Xvfb/Mesa display is sufficient for the
Linux qualification. The renderer deliberately does not use `--headless`, which
selects dummy rendering. No empty-image fallback is accepted.

## Select an existing observation

The source must contain a `simulation.control.v1` observation of the existing
Godot point model, with **all three position channels**: `position_x`, `position_y`
and `position_z`, in `godot/y-up/metres`, unit `m`, entity `projectile`. The older
scalar-only campaign output is insufficient for 3D capture; unobserved axes are
not inferred from its checkpoint or configuration.

```sh
net simulation godot capture create results/images-001/source/workspace.json \
  --expected-workspace-sha256 sha256:EXACT_WORKSPACE_HASH \
  --result-id result-REPLACE_WITH_ACTUAL_32_HEX \
  --entity-id projectile --sample-index 10 --camera front \
  --godot /absolute/path/to/godot --godot-sha256 sha256:EXECUTABLE_HASH \
  --output-dir results/front-image-001
```

Use the literal `result-...` ID from the workspace (the placeholder above is not a
valid ID). Sample indices address the selected observer's sorted acquisition
times, not engine frame numbers. For an empty batch, use `--unavailable` instead
of `--sample-index`. A partial XYZ triple displays no marker; retained component
values and missingness are preserved. Empty batches have no fabricated timestamp.

The two cameras are `oblique` and `front`. Camera changes alter only the image;
they cannot change the selected samples. Marker radius, grid and leader line are
visual aids, not object geometry, uncertainty, collision shapes or trajectories.
The marker uses float32 coordinates for display; original numerical values remain
in the evidence unchanged. Capture size is fixed at 1280 x 800 pixels.

## Evidence and ownership

Every successful output contains the exact `source-workspace.json`, a continued
`workspace.json` preserving previous records and adding one capture occurrence,
`capture.json` containing the existing operation-result envelope, `render.log`,
`native.json`, raw diagnostic `native-image.png`, and a content-addressed `images/SHA256.png`. Completion is written
only after the Session workspace is saved. A failed render retains its failed
execution and diagnostic output, without a successful capture result.

The renderer receives a small projection with selected position samples, observer
identity, sample/availability times and source references. It receives no native
snapshot, world configuration, velocity, queued events or executable instructions
from saved data. The full operation result and original workspaces are privileged
evidence, not a redacted export. Observer labels are not access control.

Raw diagnostic image bytes may be retained after a validation failure; their
filename does not establish a valid image or successful capture.

PNG bytes are checked for bounded size, dimensions, format, chunk CRCs, complete
compressed data and valid scanlines. The standard one-byte `sRGB` declaration
written by Godot/libpng is supported; arbitrary metadata remains outside this profile. The original artifact's SHA256 binds those
bytes. The receipt also binds the installed render script, host adapter,
operator-selected executable, native process, selected view and camera request.
These are consistency and provenance bindings, **not signatures, transitive binary
attestations, proof of an authentic sensor image or physical verification**.

`capture inspect` checks the image, source dependencies and preserved Session
history without executing either provider or renderer. It optionally accepts
`--expected-capture-sha256` for an independently retained capture-file digest.
Ordinary numerical/image outcomes remain `not_verified`, with null verification
identity and no state admission. Reinspection is not fresh reproduction.

## Boundaries and qualification

The renderer is an optional, bounded still-image capability, not a game renderer,
live synchronization system, arbitrary scene/save importer, video recorder,
new simulation clock or generalized camera-observation model. It supports the
existing point-model XYZ observation contract only. Every output is create-only;
images are limited to 4 MiB and workspace reads to 8 MiB. Timeouts and bounded
process output are not an operating-system sandbox.

Tests cover projection, partial/empty observations, exact source and occurrence
bindings, source isolation, PNG corruption, retained failures, publication order,
installed packaging and provider-free reinspection. The dedicated read-only CI
workflow also runs the actual native image path under Xvfb/Mesa and reruns the
unchanged earlier native campaign/replay qualification. Observed results are
recorded in PR #59; a workflow definition alone is not a passing qualification.

Implementation references: Godot 4.5 `Viewport.get_texture()` documentation and
`RenderingServer.frame_post_draw` define when a rendered viewport image is ready;
`Image.save_png()` writes the native image. Native capture uses those APIs, not a
Python-generated substitute.

- https://docs.godotengine.org/en/4.5/classes/class_viewport.html
- https://docs.godotengine.org/en/4.5/classes/class_renderingserver.html
- https://docs.godotengine.org/en/4.5/classes/class_image.html
- https://docs.godotengine.org/en/4.5/tutorials/editor/command_line_tutorial.html

## Link captures into a shared evidence timeline

The [offline evidence timeline](SIMULATION_EVIDENCE_TIMELINE.md) combines selected
capture bundles with existing commands, observer samples, refusals and branch
checks. It deduplicates shared history and creates no new execution or observation.
