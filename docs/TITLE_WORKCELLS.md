# Title-owned executable workcells and native visual feedback

This extends PR74's existing supervisor, container binding, MCP transport and
production graph. It does not introduce another scheduler, game state or numerical
implementation. The original `godot-prop.v1` recipe/four tools remain available.
The original scientific MCP host also retains its existing eleven tools.

## First real-title recipe

`1792.smith.v1` attaches the existing Home smith art and finite commission reducer.
The companion title capsule selects thirteen exact source files, including its
original licence. Two are candidate-editable: the workshop presentation/geometry
and the commission reducer. The nine original rule/presentation dependencies are
not modified in the title baseline. The new title-owned bake adapter and probes
reuse those modules; they are not copies of the game implementation inside NET.

The flow remains build -> test -> package under the original production runner.
A bounded installed `Recipe` descriptor supplies the input/output sets, operation
IDs and independent checks. Saved JSON can select only installed recipe IDs, not
import a module, choose a shell command, change an image or replace its tests.

The build produces `smith.scn` with baked descendants/resources. A fresh container
loads that scene, tests the actual reducer and rebinds the original animation,
then produces `daylight.png` and `evening.png` at the same fixed camera and tick.
The package job creates `smith.pck`, and a separate engine process loads only the
packaged resources and reaches readiness at inspection tick 600.

This is an isolated title-owned asset/commission inspection fixture, not a player
journey in the full Home world. Home saves, player movement, historical placement,
DLC and the main menu are not changed. The package retains the title's original
licence; NET software licensing does not replace game-content rights.

## Agents can see actual rendered images

The title recipe adds **net_cell_preview(attempt, view)** to the existing four
workcell tools. Views are only `daylight` and `evening`; there is no path argument.
The response contains native MCP image content plus structured metadata bound to
the original candidate, execution and result. A vision-capable MCP host can pass
those pixels to its model, rather than making it reason from filenames or a PASS
string. No render occurs on preview: it rechecks retained evidence and returns
those exact bytes.

Technically rejected work can still be inspected. The image response retains the
rejected job status and does not promote the candidate. Compiler errors, blocked
stages and missing captures cannot acquire invented pictures. These images are
inspection cameras, not normal player views or independently approved artwork.

A bounded stdlib PNG reader verifies CRCs, dimensions, decompressed extent, row
filters and opaque RGB/RGBA pixels. A nonblank-scene check excludes the caption
region. This measures presence/variation of pixels, **not artistic quality**.
Unknown formats, malformed buffers and decompression expansion refuse. No native
image decoder or new mandatory package is introduced for offline inspection.

## Fixed technical checks and remaining artistic review

The host checks expected commission quantities, original purse/treasury behavior,
refund custody, duplicate/early-action refusal, JSON ledger equality, compiled
scene binding and original hammer pose. Geometry must preserve four collider
positions/sizes and stay inside the declared workshop envelope. Budgets are 256
nodes, 96 meshes, 50,000 triangles, 24 materials and 160 observed draw calls.
Each existing container retains its one-CPU/512MiB/64PID/resource/deadline policy.
Observed end-to-end stage time is also retained and checked against 55 seconds.
These are engineering bounds for this fixture, not a measured 60FPS gameplay or
physical-GPU qualification. Missing observations remain INDETERMINATE.

Both technical PASS and an existing operator package grant are required for
assembly. No weighted score hides a critical failure. Human composition/material
review, high-fidelity art, animation feel, audio, normal-player camera, acquired
geography, physical GPU frame-time/memory profiling and release approval remain
separate. The prototype is not presented as reaching the user's final visual
reference. Model tokens/cost and accepted output per human hour remain unmeasured.

## Operator setup

Provision the image using `tools/workcell-godot/Dockerfile`. Its context now also
contains the installed title runner/config and Xvfb for isolated software
rendering. The original recipe continues to use the same protected runner.
Provisioning can fetch dependencies; candidate execution cannot. The exact final
local image ID, not an image tag selected by an agent, is bound to the slot.

With the companion title checkout and its exact manifest:

```sh
net workcell title-configure \
  --title-root /absolute/path/1792/game \
  --source-profile /absolute/path/1792/tools/net/smith-workcell.profile.json \
  --profile-sha256 sha256:EXACT_MANIFEST_DIGEST \
  --docker /usr/bin/docker --image-id sha256:EXACT_LOCAL_IMAGE_ID \
  --allow-package --output-dir results/smith-profile
python -I -m ciw.workcell_cli serve --profile /absolute/path/results/smith-profile/profile.json
```

The command verifies the manifest and every selected file before creating the
slot. It freezes source into a separate capsule, preserving the live checkout.
The selected MCP host uses the same stdio command. Omit `--allow-package` for a
build/test-only slot: successful tests do not invent assembly authority.

A direct non-MCP call remains `net workcell run --profile ... --changes ...`.
On technical success the run exports `smith.pck` plus both checked PNGs. Inspect
using `net workcell inspect ATTEMPT_DIR`; this starts no provider. The matching
Godot 4.5.1 can open the PCK with `--main-pack`. It is not a standalone engine
executable or whole1792 release.

## Qualification

`test_workcell_smith.py` uses labelled fixtures for contracts, PNG handling and
orchestration; those tests are not native runtime evidence. The dedicated
`check_smith_workcell.py` uses an actual official MCP SDK client, Docker, Godot
and Xvfb to exercise baseline, incorrect tool output, correction with a changed
art material, an oversized workplace, denied protected edits, native image
retrieval and a separately authorized test-only slot. This is a deterministic
client, not a claim of actual LLM creativity or exponential throughput.

The legacy workcell and scientific MCP workflows remain independent regression
gates. Every source/installed count and native outcome must come from actual
reports for the specific revision. Existing private-provider failures are not
made green by the new recipe. No main merge, deployment or release is implied.

References: MCP image content is defined in the 2025-11-25 tools specification;
Godot4.5 Viewport/Performance/PCKPacker provide native captures, counters and pack
loading; Docker resource constraints define the existing runtime quotas. These
interfaces do not by themselves guarantee aesthetic quality or real-time behavior.
