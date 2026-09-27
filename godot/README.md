# Optional Godot viewport

Godot **4.5.2**, GDScript, desktop GL Compatibility. Start the Python service in a separate terminal, then open `project.godot` in Godot or run:

```text
godot --path godot
```

The client connects to `ws://127.0.0.1:8765`. The service remains usable if this window closes. No addons, .NET runtime, browser bridge, scientific packages, or imported assets are required in Godot.

The **Experiments** tab is the shared view of retained process, calibrated-window,
telemetry and identified-design bundles. It follows `workbench.changed`, displays
native values and full covariance, links instrument dependencies to retained
results, and marks disconnected data stale. See the [experiment view guide](../docs/EXPERIMENT_VIEW.md)
for provider setup, protocol, scientific boundaries and testing. The existing
oscillator viewport is available in the **Oscillator** tab.

The optional **Analog** tab reads a local `analog_render.json` from the pyramid-method-gap sample (default `../examples/pyramid-method-gap/results/analog_render.json`, or a path after `--`). It is file-driven presentation only: no websocket protocol and no recomputation of A or P. Cards show host JSON numerics; meshes are presentation.

The optional **Fluid balance** tab reads HOST / synthetic FSRT presentation JSON (default `../examples/fsrt-two-reservoir/results/fsrt_render.json`, or an `fsrt_render.json` path after `--`). Two-node tank schematic and guard/residual cards only; no fluid-volume operation. Caption: disagreement is not unique fault attribution. Missing file → STALE.


The optional **BIM quantity** tab reads HOST CSE quantity JSON (default `../examples/cse-bim-quantity/results/cse_bim_render.json`). Quantity cards only; no building/Revit mesh. Missing file → STALE.

The optional **Proof** tab reads HOST proved-heat JSON (default `../examples/proved-heat/results/proved_heat_render.json`). Identity/pins cards only; never draws proof bytes; Godot does not reverify. Missing file → STALE.

The optional **Geodesic path** tab reads HOST / synthetic CSG presentation JSON (default `../examples/csg-path-sensitivity/results/csg_render.json`, or a `csg_render.json` path after `--`). Path polyline + sensitivity strip attached conceptually to `ciw.curved-path-transfer.v1`; no second curved-path op. Not surveyed BIM. Missing file → STALE.



## Shared presentation kit

Provider-neutral helpers in `scripts/presentation_kit.gd` (also projected by Bevy — see
[`docs/VISUALIZATION_PROVIDERS.md`](../docs/VISUALIZATION_PROVIDERS.md)):

- Colors, unshaded `StandardMaterial3D`, panel/card/label builders
- Status vocab: `LIVE`, `STALE`, `UNAVAILABLE`, `REFUSED`, `HELD`, `RECONCILED`, `SATISFIED`, `VIOLATED`, `REQUEST_EVIDENCE`, `HISTORICAL`
- `HISTORICAL` → display `retained_runtime_report_requires_fresh_verification`
- `resolve_render_path` / `load_json` / `apply_stale` / caption constant
- **VERIFIED** only when JSON has `fresh_verifier_occurrence: true`

Tabs sharing the kit: **Analog**, **Fluid balance**, **Geodesic path**, **BIM quantity**, **Proof**.

Optional: `presentation_strip.gd` (theta vs y series), `presentation_schematic.gd` (2-node bars + residual).

### BIM quantity / Proof

- BIM: `../examples/cse-bim-quantity/results/cse_bim_render.json` — prior/posterior/disposition/ledger; ACCEPT is recommendation; STALE if missing; no building mesh
- Proof: `../examples/proved-heat/results/proved_heat_render.json` — execution/result/verification identities + pins; never draws proof bytes; HISTORICAL/UNAVAILABLE/REFUSED; STALE if missing

### Presentation smoke (Godot may be off PATH)

```text
godot --headless --path godot --script res://tests/presentation_smoke.gd
```

If `godot` is not installed, the script still lands under `godot/tests/` for CI or local use.


The phase view plots retained position and velocity samples. Click within 20 pixels of a trajectory point to move the shared playback cursor to that retained sample time. The timeline and Play button also update this cursor. Channel and half-open `[start,end)` interval are shared with terminal clients; playback never changes the interval or recomputes analyses. The 3D view displays Python-supplied energy-surface and trajectory meshes using the declared visual transform. Drag to orbit and use the mouse wheel to zoom. All three numeric cards are `sample.get` results, never values reconstructed from displayed geometry.

Selection updates carry the observed revision, coalesce at no more than 10 requests per second, and permit only one outstanding update. Responses are matched by request ID. On a revision conflict the client discards pending selection intent and refreshes authoritative state. Sample requests are also coalesced, and an obsolete response cannot replace the latest requested sample. A fresh snapshot is checked every five seconds; unanswered requests time out after eight seconds. Disconnects retain the last view with a visible STALE indication and disable shared interaction. Use Reconnect after restarting the service.

Checks, run from the repository root:

```text
godot --headless --path godot --editor --import --quit
godot --headless --path godot --script res://tests/protocol_smoke.gd
godot --headless --path godot --script res://tests/channel_generality.gd
```

The channel generality check needs no service: it supplies snapshots directly and asserts that the channel selector, the numeric cards, the selection round-trip and the phase-portrait axes all come from the record rather than from any compiled-in channel list, across records of two, three and five channels.

The protocol smoke needs a running service. It connects two clients, loads the recorded run, changes the cursor in one, observes the broadcast in the other, checks numerical inspection against the retained record, verifies the interval did not change, restores the original cursor, and verifies inspection refresh after reconnect at the same revision. It fails after 15 seconds if the service is unavailable. Do not run it during an interactive session where another user is changing the same selection.

For a repeatable visual capture with a real graphics driver and live service, run `godot --path godot --script res://tests/capture_view.gd -- /absolute/path/view.png`. This opens a render window, saves the synchronized viewport, and exits. Headless rendering does not provide a usable screenshot.

This first viewport implements no acquisition, scientific reconstruction, spectral computation, binary transport, or verification claim. Axis scaling and camera operations affect presentation only.
