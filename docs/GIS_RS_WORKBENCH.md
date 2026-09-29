# GIS/RS are workbench operations, not a fourth room

NET retains the investigation and run history. The firm still provides verified
industrial state on **organization / site / shipment**, through **PAYLOAD /
TRADEWIND / LANDSHARK**. GIS and remote sensing are LANDSHARK/PAYLOAD sensors;
TRADEWIND can use released representations without another globe. The homepage
remains organization + synthetic globe. Games remain personal; testbeds remain
plant work; STAQNET remains LANDSHARK compilation.

| Request | Provider target | Boundary |
| --- | --- | --- |
| `spatial.map` | GSC | Compile this investigation's ESM-admitted state into spatial/temporal/relational representations. |
| `spatial.inspect` | GSV | Project one released snapshot read-only; do not compute or append unreleased layers. |
| `rs.scene.admit` | PPDA + ESM | Preserve source lineage, then request external admission. NET never admits the scene itself. |

CIW registry IDs append `.v1`. These are **interface targets, unbound by default**,
not claims of installed GSC/GSV/PPDA/ESM integrations. The existing read-only
`spatial.inspect` transport message is unchanged. No new public API is introduced.

## Author → run → observe → compare → modify → check

Request fields live in the existing sealed `ciw.experiment.v1` under
`parameters.spatial`: investigation ID, room, target entity, AOI geometry reference,
CRS definition/datum/axis order/epoch, geometry basis, scene ID/sensor/product family,
time window, licensing posture and source references. `public_official`, `licensed`
and `synthetic` remain distinct. Original `knownAt` and valid-time intervals are
retained unchanged; host execution time never replaces either.

```sh
net spatial catalog
net spatial check examples/spatial/scene-request.json
net spatial plan examples/spatial/scene-request.json --model-id synthetic-site.v1 --output scene-plan.json
```

The example contains **synthetic metadata references, not imagery or real ESM
receipts**. These commands validate declarations and author an existing experiment;
they do not execute providers or confer admission. Outputs are create-only.

Trusted process setup adds the targets to an existing `CapabilityRegistry` with
`add_spatial_routes(registry)`. To dispatch, supply explicit installed
`ProviderBinding(invoke, runtime_identity)` objects keyed by request name. The
identity must name the target provider and its implementation content reference.
Then use the original `Session`/`run_graph`; no new executor is added. No source
arrays from the Session recording are passed off as pixels. A provider receives
only the spatial request and returns `output_ref` and `provider_execution_ref`.
NET keeps those references and the original execution/result IDs, not a scene store.
A completed request can reference an externally denied admission; completion is not admission.
`open_spatial_workspace` reopens that history without binding providers.

Scene/footprint/cloud observations remain provider outputs. Numeric comparison,
warp, sampling, masking, clipping, resampling, reprojection and NDVI belong to
specialists. No such algorithms are implemented in NET. `spatial.reproject`
remains a future route; the optional pinned GSC scene/NDVI execution slice below
adds no authority to these three governance routes. GSV grows layers only from released snapshots.

## Refuse ambiguity; do not manufacture authority

The request gate refuses unresolved CRS, mixed axes/datums/epochs, incompatible
geometry/pixel/grid bases, missing `provenance.source`, unknown licensing posture,
person-yield inputs and geofence products. Building/address references are allowed;
resident inference is not. AOI selection is not a geofence-product permission.
This v1 requires matching declared raster grids; it never resamples implicitly.

Mapping selects one admitted state with its ESM admission reference, not extra raw inputs. Inspection requires a
matching ESM release/snapshot reference and no extra layers. A raw GeoTIFF cannot
become canonical state through NET. **References and labels are not proof**:
specialist adapters must resolve and authenticate the real source, licence,
collection-policy, admission and release records. NET does not classify unseen
pixels or validate legal rights from a string. Results remain `not_verified`, with
no verification occurrence, NET admission or NET release. Qualification covers
request/dispatch contracts with labelled doubles, not live imagery or provider
acceptance. GSC, GSV, ESM, PPDA, CSR and BIM-CSE retain their separate ownership.

**Executable specialist slice:** [local scene inspection and NDVI](GIS_RS_EXECUTION.md)
use a separately pinned GSC worker; the three governance routes above remain
unchanged. This adds candidate numerical observations, not imagery admission.
