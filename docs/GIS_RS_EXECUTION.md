# Local scene inspection and NDVI through GSC

NET now dispatches `rs.scene.inspect.v1` and `rs.index.ndvi.v1` to a separately
pinned GSC checkout. GSC's `tools/ciw-rs` worker owns STAC parsing, raster IO,
window selection, radiometric scaling and NDVI. NET retains the request and the
original Session execution/result; it does not implement those algorithms.

These operations extend, rather than bind or replace, `rs.scene.admit.v1`,
`spatial.map.v1` and `spatial.inspect.v1`. Numerical output remains a candidate
observation. PPDA/ESM acquisition/admission and released GSV layers are not supplied
by this slice. No homepage, globe, fourth room or canonical scene store is added.

## Run the generated reference scene

Use the companion GSC branch and the exact commit in
`examples/spatial/rs-provider-pin.json`. Check out that commit in a separate,
clean repository. The existing subprocess adapter refuses a dirty/wrong checkout.
Install the specialist dependencies in the explicitly selected Python runtime:

```sh
python -m pip install -e '.[dev]'
python -m pip install -r /absolute/path/GSC/tools/ciw-rs/requirements.txt
python /absolute/path/GSC/tools/ciw-rs/fixture.py --output-dir /absolute/path/rs-scene
```

The generator writes real COG bytes with **synthetic** reflectance and quality
codes. It prints the scene-manifest SHA256. Its output must be outside the pinned
GSC repository. It is a software test scene, not acquired Sentinel/Landsat imagery.
Use an existing CIW host recording or create the existing synthetic host example:

```sh
python -c "from pathlib import Path; from ciw.instruments import make_demo_run; from ciw.control_contracts import save_new; save_new(Path('host-recording.json'),make_demo_run())"
net spatial raster run /absolute/path/rs-scene/ndvi-request.json \
  --run host-recording.json \
  --gsc-repo /absolute/path/GSC --gsc-revision FULL_PINNED_COMMIT \
  --bundle /absolute/path/rs-scene/scene.json --bundle-sha256 sha256:MANIFEST_HASH \
  --output-dir results/ndvi-001
net spatial raster inspect results/ndvi-001/workspace.json
```

For metadata only, select the generated `inspect-request.json`. `--python-executable`
can point to a separate specialist environment. GDAL/Rasterio are not NET's
mandatory dependencies. All output paths are create-only. Startup/source-pin
failure is not mislabelled as an executed scientific operation; a refusal reached
through the Session is retained there without a successful result.

The host recording is the Session's existing evidence anchor. Its arrays are
neither forwarded as raster pixels nor relabelled as measurements of the scene.
The operation explicitly binds its separate scene manifest, item and asset hashes.

## Scene inputs and supported profile

The companion GSC guide specifies `gsc.rs-scene.v1`: an operator-selected local
STAC Item, exact red/NIR and optional categorical-mask asset descriptors, file
hashes, source lineage, collection-policy and radiometric references, licensing
posture and literal `knownAt`. STAC's valid acquisition instant/interval is kept
separately. The full declaration is **not an authentication of those claims**.
A trusted operator must obtain eligible data and resolve real rights/policy records;
relabeling data or hashing a manifest cannot make it eligible or admitted.

The first executable profile is deliberately narrow: STAC 1.0.0 Item metadata,
single-band local GeoTIFF/COG files, WGS84 UTM EPSG 32601–32660/32701–32760,
matching north-up affine grids and declared area/point sampling. All selected
bands must have the same actual CRS, shape, transform and pixel basis. Red/NIR
require explicit STAC scale, offset and dimensionless reflectance unit. The
worker applies `reflectance = DN * scale + offset` before computing NDVI;
conflicting non-default TIFF radiometry refuses. Nodata is masked before scaling.

The AOI is a content reference plus an operator-declared integer pixel window,
not an automatically intersected parcel polygon. Actual native window bounds
and affine metadata are returned. STAC's CRS84 footprint remains a declared,
unverified footprint, not the native UTM grid or proof of a facility's location.
There is no reprojection, datum shift, resampling, interpolation, geofence or
hidden coordinate fill. Unsupported profiles refuse rather than being guessed.

Asset URLs and collection links are never followed. The caller binds regular
local files; their bytes are checked and opened as in-memory GTiff data. Known
unbound sidecars, VRT/VSI inputs, traversal and symlink paths refuse. These are
application guards, not an OS sandbox for malicious native files or same-user
filesystem races. Native-library security remains the deployment operator's duty.

## Read results without overstating them

The NDVI result preserves row-major values with `null` for missing pixels, valid
and total counts, mutually exclusive nodata/mask/nonfinite/zero-denominator counts,
and min/mean/max (all null when no valid data remain). Explicit `quality: none`
means no categorical quality mask. `declared_mask` uses the pinned policy's
`keep_codes`; it does not infer sensor-specific cloud meanings. Scene cloud
percentage is separate metadata and can be null. It is not a measured cloud
fraction over the selected window.

NDVI is `(scaled_nir-scaled_red)/(scaled_nir+scaled_red)`. Values are not clipped
to [-1,1]; out-of-range values are counted. No crop health, material identity,
resident count, land-use change or physical accuracy is inferred. A COG layout
marker is recorded, not promoted to a COG conformance certificate.

The existing typed comparator can compare exported window means:

```sh
net spatial raster observations results/ndvi-001/workspace.json \
  --result-id result-RETURNED_ID --output results/ndvi-001/mean.json
net compare results/ndvi-002/mean.json results/ndvi-001/mean.json \
  --atol 1e-12 --rtol 0 --output results/comparison.json --json
```

The exported sample retains the original NET execution, scene acquisition time,
entity, unit and source hashes. Its comparison basis includes native grid, window,
AOI, radiometric reference, declared mask and **actual valid-pixel support**.
Changed support therefore yields INDETERMINATE, not a misleading same-population
mean comparison. Different acquisition times are not implicitly aligned. Interval
scenes require a specialist temporal operator; no midpoint instant is invented.
The original comparator is unchanged and no covariance model is fabricated.

## Qualification and limits

`tests/test_rs_operations.py` uses labelled contract doubles around the real
Session; it is not native-raster evidence. The GSC worker's tests generate and read
actual COGs. `scripts/check_rs_pipeline.py` runs the actual pinned external worker,
checks independent synthetic pixel/mean references, distinct reproduction IDs,
changed-input FAIL, changed-support INDETERMINATE, input preservation and retained
refusals. Workspaces reopen with process creation forbidden. Dedicated CI runs
these with installed NET outside the checkout on Linux and Windows.

Bounds: 256 KiB input JSON, 32 MiB per local raster, 4,096 selected pixels,
40,000 pixels per raster dimension, 1,048,576 pixels per storage block, 30-second
worker invocation deadline and 1 MiB combined stdout/stderr. All asset bytes are
hashed/read first; this is not remote range streaming or large-scene performance
qualification. No external source, sensor calibration, admission service or GSV
rendering is tested by synthetic COG qualification. Observed versions/results
belong to the retained run, not to the existence of a workflow file.

Primary implementation references:
- https://rasterio.readthedocs.io/en/stable/topics/windowed-rw.html
- https://rasterio.readthedocs.io/en/stable/topics/masks.html
- https://gdal.org/en/stable/drivers/raster/cog.html
- https://github.com/stac-extensions/raster/tree/v1.1.0
- https://www.usgs.gov/landsat-missions/landsat-normalized-difference-vegetation-index
