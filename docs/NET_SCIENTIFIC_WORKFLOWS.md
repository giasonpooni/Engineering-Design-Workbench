# Scientific workflows from NET

NET's `science` commands expose the existing Session/Workbench scientific
operations. They do not replace the earlier instrument CLIs, their native
workflows, mathematical implementations or approved provider revisions.

This increment connects three useful paths:

1. Find and explicitly run an existing scientific workflow, retain its native
   bundle, reopen it without providers, or perform its original fresh replay.
2. Inspect an exact RCI/FSRT/JSPT result as a typed state with its **original full
   covariance**, source time, execution identity and held/refused diagnostics.
3. Supply NET parameter-domain candidates to the **existing CSR heading study**,
   which keeps the trajectory, sensitivity, covariance and comparison calculations.

The implementation adds three small modules and an early `science` dispatch in
`ciw.net`. It uses the existing `Session.handle`, `Workbench`, workflow registry,
source readers and replay machinery. There is no second graph engine, copied
estimator, new native operation ID, changed pin or extra mandatory dependency.

## Find the existing operations

```sh
net science catalog
net science catalog covariance
net science catalog geometry --json
net science catalog estimate --json
```

The 23 indexed routes are existing operations, not 23 newly built providers.
`instrument_highlights` gives navigation aids, **not** the exact required source
set. Each original workflow owns its required roles, source schema, pins and
qualification gates. `available` describes the current process binding, not
whether a repository exists or its science has been qualified. Catalog listing
cannot bind or launch a provider; private repositories are never scanned or cloned.

| Useful work | Existing route / instrument highlights |
| --- | --- |
| Calibrated measurements, two-reservoir state and mapped covariance | `measurement-chain`: RCI, FSRT, JSPT |
| Clock reconciliation, affine calibration, observability and diagnostics | `calibrated-observable`: TBRT, MCUR, OIT, FSRT, GSIE, CBSR, FDIR, SET |
| Model fitting, measurement candidates, budget declarations | `identified-design`: SIDT, EDSPT, YWIR above the declared upstream experiment |
| Acquisition, temporal features, estimation and evaluation | `telemetry`, `calibrated-window`, `acquired-calibrated-window`, `acquired-dataset`, `residual-monitor` |
| Schematic eligibility, sensitivities and Lyapunov conditions | `schematic-assessment`, `schematic-companions`, `identified-stability`: SRA, JSPT, PLSR |
| BIM quantity evidence | `bim-quantity`: CSE |
| Geometry and conditional covariance | `geometric-circle`, `curved-path-transfer`, `flat-torus-reference`, `covariance-geometry`, `mesh-path`, `translation-flow` |
| Existing computation/reference and exchange operations | `numerical-heat`, `native-interop`, `julia-oscillator`, `thermal-observer`, `instrument-exchange` |

`instrument-exchange` uses the existing SET contract validator. **ICRH remains an
independent conformance/replay checker**, not that provider under another name.

GSC remains the read-only representation consumer; its current retained-file
exports and browser integrations are not replaced. ESM retains admission/release
authority and is not automatically invoked by numerical success. This facade
adds no new STAQNET corpus adapter, CNC/Atelier connection, machine motion,
asset publication, provider download or permission grant. Work not indexed here
remains accessible through its existing specialist entry point.

## Run and replay an existing operation

Use an existing NET workspace as the investigation context. `net demo` provides
a runnable synthetic context when starting fresh; its oscillator recording is
not reclassified as measurement evidence for a later scientific operation.

```sh
net demo --output-dir results/context-001
net science run \
  --workspace results/context-001/workspace.json \
  --kind curved-path-transfer \
  --source examples/curved-path-study/baseline.json \
  --label "Declared constant-curvature baseline" \
  --binding csg=/absolute/path/to/approved-CSR-checkout \
  --output-dir results/curvature-001 --json
```

The existing approved CSR revision is
`bbc535af29c30997e56fd120320c570830676462`; the current public repository name is
`giasonpooni/Curved-Surface-Runtime`. The binding role remains **`csg`**, preserving
the native adapter identity. This does not change the approved source tree or
silently advance to the repository's newest code. Supply a clean exact checkout.
The installed package supports the same command via `python -m ciw.net`.

The response supplies the exact `bundle_id`. Select it explicitly for replay:

```sh
net science replay \
  --workspace results/curvature-001/workspace.json \
  --bundle '<bundle_id from the previous response>' \
  --binding csg=/absolute/path/to/approved-CSR-checkout \
  --output-dir results/curvature-replay-001 --json
```

For `measurement-chain`, use the existing
`ciw.measurement-chain-source.v1` source declaration and explicit absolute
`--binding rci=... --binding fsrt=... --binding jspt=...` paths. Original calibration,
source, uncertainty, independence and model checks remain enforced. Private
sources must be provisioned in an authorized environment; no access credential
or source-code copy is added to NET by these commands.

Workflows that require a prior bundle accept `--upstream-bundle` for that original
relationship. Telemetry alone accepts a separate `--configuration FILE`.
Residual monitoring retains its original **ordered upstream IDs in its source
request**; the facade does not substitute the newest bundles. A declaration is
not a guarantee that the required providers are available or qualified.

Source bytes are read once with a 2 MiB outer limit; stricter native source budgets
still apply. Existing workspaces are frozen once with an 8 MiB limit and validated
before creating a new execution directory. Output directories must not exist.
The original workspace remains unchanged. Successfully retained operations and
original failure records are saved in the new workspace even when an operation
fails. This is not a power-loss-tested transaction across an entire campaign.

## Inspect without launching providers

```sh
net science inspect --workspace results/curvature-001/workspace.json
net science inspect --workspace results/curvature-001/workspace.json \
  --bundle '<exact bundle_id>' --json
```

Add `--instrument` with an instrument identity from the retained inspection to
select that instrument's existing panel. Inspection uses the original workspace
and native readers in temporary scratch storage. It does not bind providers from
saved runtime paths, advance a simulation, re-run a solver or confer admission.

Native operations retain their existing execution/result/verification records.
They are **not** wrapped in a duplicate `ciw.operation-result.v1` to fit the newer
generic DAG. A same-runtime reproduction keeps its original non-independent
scope. The standalone assertions introduced with NET's control primitives still
remain ordinary numerical checks; neither kind becomes physical validation.

## RCI / FSRT / JSPT typed state selection

```sh
net science state \
  --workspace results/measurement/workspace.json \
  --bundle '<measurement-chain bundle_id>' \
  --result '<exact inner FSRT result_id>' \
  --stage posterior \
  --entity 'plant-A/two-reservoir-assembly' --json
```

Omit `--bundle` for an existing root RCI/FSRT investigation workspace. Choose
`prior`, `posterior` or `reconciled` for `fsrt.tank-reconstruct.v2`. Choose
`output_covariance` for an original `jspt.covariance-propagate.v1` result.
The original instrument inspection exposes the inner result identities.

The response contains a standard `ciw.state.v1` plus native context. The state
retains **the original full covariance artifact**, not just variances, including
quantity order, units, frame, reference values, matrix, assumptions, lineage and
covariance ID. Original execution identity is preserved; no new estimate or
verification occurrence is allocated. The context retains the selected result,
stage, provider runtime, acquisition instant and native diagnostics.

A held reconciliation remains `model_inconsistent` in that context. Refused
executions have no selectable result and cannot emit a fabricated state. This
path deliberately rejects simulation-source observations rather than creating
RCI calibration claims. The existing separate synthetic-source reader remains
responsible for those observations.

`prior` is labelled a reference; posterior/reconciled values are estimates.
**JSPT output reference values are caller-declared, not computed means.** They
remain `reference` semantics even though the covariance was propagated. Model
identity for FSRT uses the selected native result's model; mapped state identity
binds the declared map and the selected source covariance, not an unrelated
workspace default.

Time is the original simultaneous RCI acquisition instant with a scoped
`rci-snapshot:<instant>` clock at zero. This is not a sampling rate or a temporal
fusion model. Entity names are caller declarations, not inferred cross-source
matching. The outer `scientific-state-selection` object is a read-only response,
not an independently authoritative saved-state schema: retain the original
workspace and reproduce the projection from that source. Retain the accompanying
native diagnostics when consuming its typed state.

## Parameter-space connection to CSR

```sh
net science study \
  --workspace results/curvature-001/workspace.json \
  --bundle '<exact baseline bundle_id>' \
  --binding csg=/absolute/path/to/approved-CSR-checkout \
  --headings 0.001 -0.001 \
  --sample-index 4 \
  --max-lateral 0.01 --max-heading 0.01 --length-unit m \
  --study-id heading-comparison-001 \
  --output-dir results/heading-study-001 --json

net science inspect \
  --workspace results/heading-study-001/workspace.json \
  --study results/heading-study-001/study.json --json
```

The CLI declares an outer `initial_heading_radian` interval of [-0.1, 0.1]. The
original study applies the **stricter retained native validity bound**, checks
zero lateral displacement and exact units, and validates all candidates before
binding or execution. Python callers can supply a narrower `ParameterSpace` to
`scientific.heading_request` and execute with `scientific.heading_study`.
One to eight distinct explicit candidates are allowed. This is a bounded
comparison, not an optimizer or global parameter search.

All calculations and replay stay in `curved_path_study` and its original CSR
provider. The stored report retains its original schema and full native bundle
references. Its independent coordinate is **arclength, not time**; NET does not
mislabel it as an observation-bus timestamp. Covariance remains conditional on
the declared starting covariance; joint covariance across samples/candidates is
not invented. If a later candidate fails, prior native runs remain retained and
no complete study is published. Full study replay remains the existing
`curved_path_study.replay_study` operation, not a new save/restore implementation.

## Qualification and scope

Local contract tests execute the existing thermal Python reference and use
explicitly labelled FSRT/JSPT wire fixtures for narrow projection tests. Those
fixtures do not qualify native calibration or estimation. The separate mandatory
`validation/scientific_native.py` campaign requires an actual approved public
CSR checkout; it has no mock or skip fallback. It executes the installed NET
wheel through `net science run/replay/study/inspect`, then uses the existing
independent curved-geometry oracle and unchanged tolerances. New and original
regression suites run together, and JUnit gates require every expected case.

This qualifies the combinations actually exercised, not every listed private
workflow or a platform-wide green build. Private-provider gates, wider native
campaigns, ICRH independent profiles, GSC visual handoffs and physical validation
remain separately scoped. No main merge, release, deployment, private-source
publication, licence/visibility change or machine actuation is performed here.
