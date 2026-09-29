# Approved asset worker: packet → Blender → candidate → independent acceptance

This increment attaches one **closed asset-production recipe** to the existing Foundry
packet and production infrastructure. It does not add a scheduler, agent framework,
world state, model API or automatic repository write. `net foundry asset` provides
`run`, `inspect` and `export`; existing pipeline and Foundry commands remain.

## Actual output and scope

The recipe creates an original low-poly **workshop bench**: 1.8 m long, 0.7 m deep,
0.9 m high, Y-up in glTF, ground-centered origin. The complete candidate has a top,
four legs and four lower rails: nine separate closed box meshes /108 triangles,
with a plain opaque rough nonmetal material. It is an original technical blockout,
not a surveyed Punjabi object, finished environment art, structural safety model,
weapon, construction plan or shipped 1792 asset. No historical reference is fabricated.

Blender4.5.3 creates a genuine self-contained GLB. Godot4.5.1 imports those exact
bytes in a **different process and directory**, measures the imported meshes and
casts six rays against triangle collision derived from them. Pure Python acceptance
then reads the actual GLB buffers and independently checks those observations.
The producer neither gets nor modifies that checker. An author report is provenance,
not a PASS flag. Export returns a **complete candidate source tree** plus a manifest;
it does not edit the original source or merge/release anything.

This is a parameter-driven production worker, **not a generative model invocation**.
ChatGPT authored the original recipe in this implementation; executing it calls no
coding model, image generator, paid API or remote creative agent. An external agent
host may request an allowed candidate configuration within the operator's grant.
This release does not claim free-form art synthesis or measured agent productivity.

## Existing architecture retained

- `foundry_packets` still binds the operator-selected task, baseline, selected context,
  exact write paths and byte budget. Its `rights.execute=false` is unchanged: a packet
  alone cannot launch engines. The separate operator CLI invocation supplies authority,
  source location, native executable paths/hashes, prerequisites and attempt budget.
- `production.run_production`, `Session`, `CapabilityRegistry`, `Worker`, `Gate`,
  `_graph`, `_job`, native timeout supervision and original receipt/inspection machinery
  are reused. No duplicate execution IDs or independent production ledger is invented.
- Blender owns asset authoring. Godot owns the isolated import/collision observation.
  NET retains attempts and computes acceptance. Neither engine owns 1792 state here.
- The installed sixty-task blueprint is unchanged. The existing `pipeline run`
  water recipe remains its only direct native milestone binding. The new worker is
  an **asset candidate subjob** under an existing art/tooling work package, not automatic
  completion of that package. Human art review and later game integration remain gates.
- Other projects, original tests, acceptance policies, engine/dependency versions,
  Session formats, licenses, MCP and concurrent-worker branches are not overwritten.

## Prepare a legitimate packet

Use a new bounded source/workcell snapshot rather than an entire binary asset depot.
The existing packet inventory limits still apply. Begin with a project created through
`net foundry pipeline init`. The new worker accepts packets for `art-target`,
`props-materials`, `blender-export` or `collision-lod` only, and the exact writable path:

```
assets/props/workbench.glb
```

There may be no additional write grants. A missing asset is created; a previously
existing asset at that path can be replaced in the candidate only. Original tests,
policy and source remain untouched. Existing task prerequisites must be resolved
against current source. **The native qualification script's review records are clearly
labelled TEST FIXTURES, not usable evidence that the real game's art/history was approved.**

For an `art-target` packet, supply your actual vision and historical-scope review
artifacts via the existing `pipeline review` flow, then issue:

```sh
net foundry pipeline packet results/studio/project.json \
  --source-root ../1792-workcell \
  --task art-target --assignee local-asset-host \
  --allow-write assets/props/workbench.glb --context brief.md \
  --evidence vision=results/vision-review \
  --evidence historical-scope=results/history-review \
  --output-dir results/bench-packet
```

Retain the returned packet `record_digest` independently in the operator host. Do
not replace it with an ID delivered by an untrusted candidate. The worker rereads
the original packet and current prerequisite evidence before binding any runtime.
Known secret paths and links remain refused by the existing packet boundary; the
selected context is source data, not privileged instructions. It is not interpreted
as a script by the closed authoring recipe.

## Execute the approved recipe

Install this feature branch normally (`python -m pip install -e '.[dev]'`), or use
its built wheel. The Blender producer is a packaged Python module copied as frozen
script bytes; the inspector GDScript is packaged as a constant. Installed-wheel use
does not depend on finding scripts in an uninstalled source checkout.

```sh
net foundry asset run results/studio/project.json \
  --packet results/bench-packet/packet.json \
  --packet-id sha256:OPERATOR_RETAINED_PACKET_DIGEST \
  --source-root ../1792-workcell \
  --blender /absolute/path/to/blender \
  --blender-sha256 sha256:VERIFIED_BLENDER_EXECUTABLE_DIGEST \
  --godot /absolute/path/to/godot \
  --godot-sha256 sha256:VERIFIED_GODOT_EXECUTABLE_DIGEST \
  --evidence vision=results/vision-review \
  --evidence historical-scope=results/history-review \
  --output-dir results/bench-production
```

Replace the three digest placeholders with actual `sha256:<64 lowercase hex>`
identities. Native hashes refer to **executables**, not downloaded ZIP/tar archives.
The caller, not packet data, chooses binaries and output paths. Bind only trusted
executables. Existing targets are Blender4.5.3 and Godot4.5.1 Standard; version labels
are not runtime authentication or a latest-version recommendation.

Default candidate: four legs. To exercise rejection and its finite declared correction,
add `--legs 3 --repair`. A three-leg candidate is structurally well-formed glTF but
fails the fixed nine-part geometry and fourth-foot probe. Without `--repair` it stays
rejected and the dependent job is blocked. Repair changes only the declared parameter;
it does not change source, ownership, file permission or the acceptance threshold.
The dependent job performs a **fresh Blender export and Godot import**, not a cached
replay. The default operation budget is three possible worker attempts. Each captured
attempt contains two native calls, which are counted separately from NET executions.

The current candidate workspace is temporary; the original Session retains actual
asset bytes, request, author/import reports, logs, scope check and candidate inventory
for every captured accepted or rejected attempt. A runtime failure retains the original
refusal record and bounded diagnostic rather than fabricating an asset result. This
inherits the existing process runner's failure-log limits; it is not full forensic
capture of every failed process's filesystem.

## Independent acceptance

The Python reader admits a deliberately closed profile: embedded JSON and BIN,
flat unique root nodes, applied node scales/rotations, no textures/external URIs,
animations, skins, arbitrary extensions, cameras or lights. It bounds the file to
48 KiB; node/mesh/accessor counts and byte spans are bounded before iteration.
It decodes positions, normals and indices from actual buffers, verifies ranges,
alignment, finite data, referenced vertices, outward winding, normals and complete
six-face box topology. Declared accessor minima/maxima are checked against bytes,
not trusted as measurements. Hidden/unreferenced mesh data is refused.

Fixed semantic checks require each named component at its target envelope within
0.00001 m, the complete nine parts and108 triangles. The Godot observations must
match the same asset hash, request and measured imported part geometry. Five surface
rays must hit the top/four legs at the declared positions, and a sixth outside probe
must remain clear. A missing import report is indeterminate, never approved. These
six probes do not qualify walking, vaulting, dynamic rigid bodies, cloth, load-bearing
strength, optimized game collisions or every possible contact around a bench.

The host builds a candidate from a locked source snapshot and the actual produced
GLB, then uses the **original candidate scope checker**. Pure capture validation
also reconstructs the expected inventory and scope result: an altered unrelated
file or dishonest changed-byte summary is not accepted. The author process sees
only the fixed producer script and bounded request, not the game checkout or checker.
Godot sees only the fixed inspector, project declaration, request and candidate GLB.

## Inspect and export without rerunning engines

```sh
net foundry asset inspect results/bench-production
net foundry asset export results/bench-production \
  --source-root ../1792-workcell --output-dir results/bench-accepted
```

Inspection registers the trusted payload validator and recomputes the original
production gates without engine binaries or subprocess creation. It checks the
native worker, fixed scripts, request/packet binding, required primary/regression
sequence and original Session history. It is integrity/consistency reinspection,
not a fresh native observation or an authenticated statement about an untrusted host.

Export requires both jobs accepted. It resolves the accepted **primary** artifact
through its receipt, rechecks the source baseline, recreates a new complete candidate
and rechecks scope. A final `manifest.json` links packet, original execution/result,
production, acceptance receipt and asset/inventory identities. A partial export has
no completion manifest. Existing destinations are never replaced. There is no atomic
multi-file publication, crash recovery or automatic game import/installation.

The parent task remains awaiting its own human/integration review. Approved subjob
geometry does not satisfy the creative brief by itself. A model is not allowed to
invent reviewer names and claim authenticated art approval: current review labels
remain explicit operator attestations, as in PR72.

## Validation and limitations

```sh
python -m pytest -q tests/test_foundry_asset.py
python scripts/check_foundry_asset.py --blender /path/to/blender \
  --godot /path/to/godot --output-dir results/asset-native
LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a python scripts/render_foundry_asset.py \
  --godot /path/to/godot --qualification results/asset-native \
  --output-dir results/asset-previews
```

Unit meshes and review receipts are labelled synthetic fixtures. The native script
uses real Blender/Godot for baseline, rejected/corrected and exhausted campaigns;
reopens every original record with subprocess creation forbidden; checks exact
candidate export, nonpromotion of the parent task, source preservation and drift
refusal. It records counts rather than inventing human hours, model cost or completed
playable minutes. Preview images are generated from those actual GLBs, not substitutes
for technical results. They do not establish final artistic quality or GPU performance.

The dedicated CI workflow qualifies Python source and wheel contracts on Linux and
Windows, and native tools/preview captures on Linux. Native Windows/macOS, physical
GPUs/controllers, game integration and human playtesting are not covered. Version and
binary pins do not attest OS/shared libraries; temporary directories, native timeout
and `--disable-autoexec` are **not an OS/network sandbox or comprehensive security
boundary**. Quiescent operator-trusted sources/binaries remain required. Free-form
external agent code, parallel worktrees, model providers, semantic repair, LODs,
textures, armatures and higher-poly asset families are still separate work.

## Official API references

- Khronos glTF2.0 specification (GLB framing, accessor/stride layout and finite data):
  https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- Godot4.5 GLTFDocument (import actual bytes and generate an engine scene):
  https://docs.godotengine.org/en/4.5/classes/class_gltfdocument.html
- Blender4.5 distribution index (selected existing release, not a new core dependency):
  https://download.blender.org/release/Blender4.5/

Existing licensing and notices remain in force. No external art, photos, textures,
book scans, font files or engine binaries are added to this repository increment.
