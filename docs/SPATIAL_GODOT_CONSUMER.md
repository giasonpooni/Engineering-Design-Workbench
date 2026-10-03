# Retained spatial results in Godot

This additive consumer extends the local-frame provider starter. It does not
replace the existing Godot workbench client, connect to a service, own a physics
clock, or rerun GSC. It prepares a self-contained Godot project from a validated
CIW workspace and one explicitly selected local-frame result.

## Working boundary

GSC/PROJ still owns the geodetic calculation. Existing CIW Session records own
the retained investigation. The viewer displays detached samples. Sample/time
selection, plan/oblique camera, rotation and zoom are inspection state only.
There is no live connection, hidden interpolation, scientific verification,
state admission, provider dispatch or device operation.

The source ENU frame is right-handed, Z-up, metre-scale. Godot display coordinates
are **X=east, Y=up, Z=-north**, a proper rotation (determinant +1). All three axes
retain the same scale. This mapping is tested in Python and independently in
Godot. Rendered Vector3 coordinates use float32; labels read the retained values.
Missing samples have no marker, selecting them hides the selection cursor, and
all-missing data is a valid empty scene. Marker radius and grid are display aids,
not physical geometry, collision shapes or a declared material model.

OpenUSD remains a sibling scene representation from the previous exporter. This
consumer reads the validated `display.json` derived from the same retained
binding. It **does not implement general USD import**, layered USD, or glTF.
A stable scientific entity ID, source result, source execution, scene prim path,
and process-local Godot node/instance identity remain distinct. Actual runtime
IDs appear only in the engine observation report, never in the source record.

## Prepare and inspect without Godot

Install this feature branch (not main); use an existing successful spatial result:

```sh
python -m pip install -e .
python -m ciw.spatial_workflow godot prepare results/local-frame-001/workspace.json \
  --result-id RESULT_ID --output-dir results/godot-view-001
python -m ciw.spatial_workflow godot verify results/godot-view-001
```

`--expected-workspace-sha256 sha256:HEX` optionally binds operator-known source
bytes; `--marker-radius 0.25` sets the visual marker radius in metres. Neither
command imports PROJ or USD, starts Godot, or requires an AI subscription.
Outputs must be new directories. `manifest.json` is written last; an interrupted
write without a complete manifest is not a completed bundle.

The generated project contains trusted `view.gd` and `self_test.gd` templates,
`project.godot`, `main.tscn`, the exact source workspace, display JSON, and a
hash-bound manifest. Verification regenerates **all** project files from the
copied workspace and installed templates, so merely resealing a modified script
or translated coordinate is not sufficient. Digests check consistency, not
signer authenticity or historical truth. Use the same installed consumer version
when verifying a bundle; template changes are deliberately detected.

## Open the interactive viewer

Godot **4.5.2 Standard** is the qualification target, matching the existing
repository's Godot check. Launch the project explicitly:

```sh
/path/to/godot --path results/godot-view-001
```

Choose a sample from the selector. The displayed ENU values, time, source result
and source execution are retained values. The amber marker identifies selection;
teal markers are available samples. The plan, oblique, rotate, zoom and reset
buttons change only the camera. No trajectory is fabricated between samples.

Verify before manually opening a project from another source. A Godot project
contains executable scripts; this feature is not an operating-system sandbox.
Godot may create its own editor/import cache in the project directory. The NET
source workspace is a copy and is not supplied as a writable service.

## Run the actual engine checks

Select an absolute executable and its operator-verified SHA-256, prefixed by
`sha256:`. `check` verifies the package before launching only the shipped test
script in a temporary project copy; it never launches code named by source data.
The check report is a consumer observation, not a new scientific result.

```sh
python -m ciw.spatial_workflow godot check results/godot-view-001 \
  --godot /absolute/path/to/godot --godot-sha256 sha256:HEX \
  --output-dir results/godot-check-001
```

For a render-capable desktop session, add `--render`; this retains `capture.png`.
On Linux CI the graphical case uses Xvfb and software OpenGL; a headless check
alone does not establish rendering. Evidence directories are create-only, and
failed engine runs retain `godot.log` and `check.json`. Engine execution is bounded
by a 90-second timeout. No expensive runtime is installed automatically by these
commands. The CI provisioning step separately downloads the fixed release and
records its observed archive/binary digests; this is not a signature check.

## Tests and qualification

`tests/test_spatial_godot.py` adds 33 Python cases covering frame rotation,
invalid numbers, create-only writes, expected source hashes, provider-free
inspection, artifact tampering, resealed code/projection changes, authority
promotion, binary pin refusal and retained spawn failure. Existing starter and
Session/operation/USDA tests remain unchanged.

`.github/workflows/spatial-godot.yml` provisions the exact GSC commit from the
starter, actual PROJ and OpenUSD, and Godot 4.5.2. It requires all 72 focused tests
to run without skips. It then builds/installs the wheel outside the checkout and
runs mixed, all-missing and single-sample inputs through actual GSC and Godot,
with separate headless and rendered reports. The engine checks selection,
missingness, coordinate mapping, camera changes, seven malformed payloads and
unchanged source bytes. Python separately checks the returned node bindings and
float32 positions. Consult retained CI reports: the workflow definition itself
is not evidence of a pass. No Bevy/Blender or cross-platform qualification is
inferred from this Linux campaign.

Primary API references used in implementation:
- https://docs.godotengine.org/en/4.5/tutorials/editor/command_line_tutorial.html
- https://docs.godotengine.org/en/4.5/classes/class_viewport.html
- https://docs.godotengine.org/en/4.5/classes/class_image.html
