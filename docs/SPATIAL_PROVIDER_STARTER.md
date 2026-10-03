# Spatial provider starter: GSC -> NET -> detached scene

This first runnable slice extends the existing `ciw.Session`,
`OperationRegistry`, pinned subprocess adapter and workspace formats.
It does not create a new controller, canonical store, provider loader, simulation
clock, proof system or game engine. Existing native/SCR profiles are unchanged.

The optional command surface is `python -m ciw.spatial_workflow`. It uses the
same installed `ciw` package and Session; the core `ciw` CLI, `net` facade and
active PR #51 remain untouched. A later central CLI registration can reuse
`register_commands` without replacing any dispatch logic.

## What works in this change

`python -m ciw.spatial_workflow catalog` is a provider-free roadmap. Entries explicitly distinguish
built-in, explicit-binding, optional-export, planned and research work. It neither
installs packages nor activates agent frameworks. It is not a replacement for
`ciw capabilities`, existing native profiles, or work on the `net` facade.

The executable operation is **`gsc.local-frame.v1`**. The new worker lives in
GSC at `tools/ciw-local-frame/worker.py`; NET does not vendor it. It delegates
coordinate mathematics to PROJ through pyproj 3.7.2. It consumes explicit WGS84
longitude, latitude and ellipsoidal-height samples and an explicit origin,
then returns local east/north/up coordinates in metres. NET retains the source,
parameters, runtime identities, operation, execution, result and refusal records
through the existing Session.

This is a coordinate representation operation, not sensor acquisition, GNSS
estimation, calibration, uncertainty propagation, dynamics or state admission.
A successful operation remains `not_verified`. Missing or incomplete coordinate
samples yield missing positions; no interpolation, geoid correction, covariance
or accuracy guarantee is invented. A source marked `recorded` is a declaration,
not authentication of measurement provenance.

The default demo has six synthetic samples, one with an incomplete position.
The source is a normal `run.v1` recording with an embedded read-only manifest,
explicit source class, stable entity identity, coordinate axes and units.
No synthetic time or channel is added to represent a static database object.

## Run

Check out the companion GSC change at commit
`acc6a4c43dd1d28e3fc6890dadf5cd2b4ae40125` and use that full commit as GSC_SHA.
Use Python 3.11+; install pyproj only into the interpreter selected for GSC.

```sh
python -m pip install -e '.[dev]'
python -m pip install -r ../Geospatial-Systems-Compiler/tools/ciw-local-frame/requirements.txt
python -m ciw.spatial_workflow catalog
python -m ciw.spatial_workflow demo \
  --gsc-root ../Geospatial-Systems-Compiler --gsc-revision GSC_SHA \
  --output-dir results/local-frame-001
```

Read the returned `result.result_id`. No provider defaults are inferred from
workspace JSON, and a saved executable path never authorizes a new execution.
The `--python` argument may select an explicit GSC virtual environment.

```sh
python -m ciw.spatial_workflow inspect results/local-frame-001/workspace.json
python -m ciw.spatial_workflow export results/local-frame-001/workspace.json \
  --result-id RESULT_ID --output-dir results/local-frame-view-001
python -m ciw.spatial_workflow verify-export results/local-frame-view-001
```

Open `results/local-frame-view-001/inspector.html` for a self-contained,
script-free east/north plot and complete ENU sample table. It has no network or
provider access. The chart uses equal spatial scales and unconnected samples;
it is not an interpolated trajectory. `scene-binding.json` is the detached
engine-facing representation, not an input that mutates retained science.

For real OpenUSD SDK export, explicitly request the existing optional extra:

```sh
python -m pip install -e '.[openusd]'
python -m ciw.spatial_workflow export results/local-frame-001/workspace.json \
  --result-id RESULT_ID --output-dir results/local-frame-usd-001 --with-usd
```

The SDK creates a Z-up, metre-scale stage with one stable-identity entity and
unconnected `UsdGeomPoints`. It reopens its own self-contained layer and checks
points and IDs at float32 display precision. The retained JSON stays double
precision. There is no handwritten-USD fallback when the SDK is absent.
Native SDK verification is not a physical, scientific or cryptographic proof.

`verify-export` checks exact retained artifact hashes, source bindings and
regenerated non-USD view semantics without loading a provider or SDK. A retained
producer SDK claim is not rerun or promoted to independent verification.
Checksums detect inconsistency, not authenticity against a resealing attacker.

## Replay and external source

```sh
python -m ciw.spatial_workflow replay results/local-frame-001/workspace.json \
  --result-id RESULT_ID --gsc-root ../Geospatial-Systems-Compiler \
  --gsc-revision GSC_SHA --output-dir results/local-frame-002
python -m ciw.spatial_workflow run --source recording.json \
  --origin -79.7 44.0 250.0 --gsc-root ../Geospatial-Systems-Compiler \
  --gsc-revision GSC_SHA --output-dir results/local-frame-003
```

Replay is an explicit fresh execution with new execution/result identities,
not playback. This CLI only replays full-source selections; it refuses a saved
subinterval rather than silently widening it. Direct Session operation selection
supports half-open intervals. Output directories must be new. Failed provider
executions are retained; provisioning failures are explicitly pre-execution and
retain source/workspace plus a separate provisioning-refusal record.

## Invariants and scope

- Scientific evidence identity, operation identity, execution occurrence,
  result identity, verification identity, stable entity ID, scene prim path,
  local frame ID and runtime entity ID are distinct. Runtime entity ID is null
  until an engine adapter actually establishes it. Prim paths are not durable
  scientific identities.
- GSC owns the spatial adapter. PROJ owns the coordinate calculation. NET owns
  investigation retention. The scene is only a derived representation. SCR,
  estimators and mathematical checkers retain their existing responsibilities.
- WGS84 ellipsoidal height only; no MSL/orthometric-height conversion. Up to
  4096 samples, 20 km Euclidean local radius, 2 MiB worker IO limit, 4 MiB retained
  reader limit, existing subprocess deadline. No Earth-scale physics or arbitrary
  coordinate-system input is supported by this first profile.
- Pinned checkout/interpreter/source checks detect drift; installed dependency
  binaries remain trusted. No security-sandbox guarantee or arbitrary provider
  execution is implied.

## Still planned

Godot/Bevy/Blender consumer import and live synchronization, glTF delivery,
layered USD composition, terrain/routing/PDAL/PostGIS providers, CRS/geoid/epoch
conversion, covariance propagation, scientific solvers and agent workers remain
separate integrations. The catalogue is not evidence that these were exercised.
No AI API call, paid service, dataset download, hardware action or cloud
resource is required for this slice.

## Qualification

Run provider-free tests normally. Set `GSC_LOCAL_FRAME_ROOT` to a clean checkout
containing the companion worker to run real pinned subprocess integration.
The GSC tests include independent analytic/ECEF numerical oracles. The NET
shape fixtures are explicitly not native numerical evidence.

```sh
python -m pytest tests/test_spatial_provider.py -q
GSC_LOCAL_FRAME_ROOT=../Geospatial-Systems-Compiler \
  python -m pytest tests/test_spatial_provider.py -q
python -m pytest ../Geospatial-Systems-Compiler/tools/ciw-local-frame/test_worker.py -q
```

The optional native USD test is skipped only when the actual SDK is unavailable;
the explicit USD export itself refuses instead. The focused CI gate installs
that SDK and requires both GSC and USD to be present.

Primary references: pyproj Transformer API and OpenUSD UsdGeomPoints/linear
units documentation. The user-supplied provider and OpenUSD architecture guided
the responsibility boundaries; capabilities in the broad catalogue remain
proposals until implemented and qualified.

## Qualification workflow

`.github/workflows/spatial-provider.yml` requires the actual public GSC checkout
at the commit above, pyproj 3.7.2 and the existing OpenUSD 25.11 extra. The new
39-case NET suite and 14-case GSC suite must have zero skips. It separately runs
existing regressions and exercises a built wheel outside the source checkout.
A workflow definition is not a passed run; consult its retained reports.

The local development environment ran real PROJ, but did not have the OpenUSD
SDK. Its SDK test was explicitly skipped. Local worker fixtures contain the
exact worker files in their own clean Git checkout; their revision identity is
distinct from the full published GSC repository. Remote qualification uses the
full published checkout rather than relabelling local fixture evidence.
