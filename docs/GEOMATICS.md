# Geomatics, Earth observation and urban analysis

NET provides bounded numerical reference operations for GIS, Earth observation,
radiometry and descriptive urban analysis. These tools support selected topics in
the York courses below; they do not constitute complete syllabus coverage, course
credit, or a York-endorsed implementation.

## Run an example

Run these commands from the repository root in the project's Python environment:

```bash
PYTHONPATH=src python -m ciw.net geomatics catalog
PYTHONPATH=src python -m ciw.net geomatics example geomatics.terrain.slope.v1 --output request.json
PYTHONPATH=src python -m ciw.net geomatics run request.json --output-dir run
PYTHONPATH=src python -m ciw.net geomatics inspect run
PYTHONPATH=src python -m ciw.net geomatics replay run --output-dir replay
```

Use any operation ID returned by `catalog` in place of
`geomatics.terrain.slope.v1`. `example OP --output request.json` creates a request
template containing that operation's parameter keys, units and representative
data structures. Edit its `parameters` to explore the supported inputs. The
provider validates the accepted fields and bounds; the example is a concrete
starting point, not a complete machine-readable JSON Schema.

Output files and run directories must be new. Choose different names when
repeating the commands. Command responses are JSON. Invalid inputs are refused
with an explanation. Every generated example declares synthetic provenance.

For supplied data, use `provenance.source_kind: "operator_supplied"` and an honest
`source_ref`. A provenance declaration records what the operator supplied; it
does not establish source authenticity.

Requests are limited to 512 KiB of compact canonical JSON and 2 MiB when
serialized as indented JSON. Provider output is limited to 1 MiB of indented
JSON. These are UTF-8 byte limits; exceeding either a data-shape limit or a
serialization limit causes refusal.

## Operation inventory

| Operation ID | Numerical role |
| --- | --- |
| `geomatics.coordinates.enu.v1` | WGS84 geodetic positions to ECEF and origin-fixed ENU metres |
| `geomatics.raster.zonal.v1` | Per-zone counts, missing counts and population statistics |
| `geomatics.terrain.slope.v1` | Centered terrain gradients and slope in degrees |
| `geomatics.raster.suitability.v1` | Weighted sum of aligned criteria normalized to [0,1] |
| `geomatics.image.normalized-difference.v1` | `(a-b)/(a+b)` with declared band labels and nodata/zero-denominator masking |
| `geomatics.image.change.v1` | Aligned after-minus-before raster change with ordered acquisition times |
| `geomatics.image.classify.v1` | Nearest supplied centroid in common-unit multispectral coordinates |
| `geomatics.image.accuracy.v1` | Confusion matrix, overall accuracy and producer/user accuracy |
| `geomatics.image.focal.v1` | Clipped-window mean or population standard deviation |
| `geomatics.image.radiometry.v1` | Declared affine scale and offset with coefficient provenance |
| `geomatics.radiometry.planck.v1` | Monochromatic blackbody spectral radiance per micrometre |
| `geomatics.radiometry.brightness-temperature.v1` | Inverse Planck equivalent blackbody temperature |
| `geomatics.atmosphere.transmission.v1` | Direct-beam Beer-Lambert transmittance |
| `geomatics.atmosphere.optical-depth.v1` | Reference-path optical depth from positive transmittance |
| `geomatics.urban.indicators.v1` | Area population densities and denominator-aware event rates |
| `geomatics.urban.accessibility.v1` | Population-weighted potential accessibility from supplied travel times |

Band names, coefficients, class prototypes and reference labels are operator
declarations. Classification performs no model fitting; accuracy statistics do
not certify reference authenticity or an independent holdout split.

## Architecture and retained evidence

`src/net_geomatics/` is the numerical provider. It uses a fixed catalog of
operations; request data cannot name arbitrary Python modules or executable
paths. `src/ciw/geomatics_workflow.py` adapts those operations to the existing CIW
`Session`, operation registry and retained workspace. This is an extension of the
existing execution and evidence lifecycle, not a second evidence store.

The declared request becomes source evidence. The registered operation identity,
execution identity, result identity and reproduction verification identity remain
separate. Results retain model assumptions or limitations alongside numerical
outputs. The adapter does not admit canonical state or actuate hardware.

`inspect` validates retained record commitments and operation-specific output
structure without executing a numerical provider. These structural checks do
not establish numerical correctness. `replay` requires the retained
provider/runtime identity to match the installed runtime, then performs a fresh
execution and compares the exact result
payload. It writes a separate reproduction receipt in the new output directory.
The receipt states `independent: false`: agreement establishes same-runtime
numerical reproduction, not independent verification, physical validation or
truth of the input data. Physical validation and source authenticity remain
unestablished, and state admission remains unperformed.

## Raster and coordinate contract

Rasters use inline JSON with four fields:

```json
{
  "values": [[120, 130, 140], [100, 110, 120], [80, 90, 100]],
  "crs": "LOCAL_METRE:synthetic-campus",
  "transform": [0, 10, 0, 30, 0, -10],
  "unit": "m"
}
```

- `values` is a rectangular, nonempty array of at most 65,536 cells per raster.
  Request and output byte limits also apply. JSON `null` means nodata;
  zero remains an ordinary measured or declared value. NaN and infinity are not
  accepted JSON inputs.
- `transform` is `[x_origin, dx, 0, y_origin, 0, dy]`: north-up, positive `dx`,
  negative `dy`, and no rotation. Combining rasters requires exact agreement in
  CRS, transform and shape. No silent reprojection or resampling occurs.
- Metric terrain operations require an explicit `LOCAL_METRE:` frame and metre
  elevations. A CRS label is a declaration, not proof of correct georeferencing.
  Geographic degrees cannot be relabelled as metres to satisfy this contract.
- Missing-data behavior is operation-specific and appears in the result's
  assumptions. Zonal statistics omit and count missing values; terrain slopes
  leave the outer boundary and incomplete stencils null; suitability propagates
  null from every criterion, including zero-weight criteria.

WGS84 coordinate conversion accepts longitude/latitude in degrees and ellipsoid
height in metres, and returns ECEF coordinates and origin-fixed ENU displacement.
ENU displacement is not geodesic distance or a general map projection. Epochs,
geoid corrections, datum transformations and observational uncertainty are not
modeled by this reference operation.

## Course alignment

The course descriptions below were checked against official York sources. The
NET column describes selected support, not a claim that a particular operation
appears in the syllabus.

| Course | Official description scope, paraphrased | NET support |
| --- | --- | --- |
| GEOG 2340: Introduction to Geomatics | GIS, remote sensing, GPS, descriptive statistics and cartography | Coordinate frames and raster statistics |
| GEOG 3340: Fundamentals of GIS | Raster GIS for environmental problems, resource management and planning | Aligned raster summaries and weighted suitability |
| GEOG 3440: Remote Sensing for Earth Observation | Remote-sensing collection, processing and analysis, with environmental and GIS applications | Band ratios, affine radiometry and aligned change calculations |
| GEOG 4340: Spatial analysis and problem solving with GIS | Advanced raster GIS, mapping, surface analysis and interpretation | Terrain gradients, zonal summaries and declared suitability criteria |
| GEOG 4440: Processing and Analysis of Earth Observation | Image enhancement, texture, classification and GIS integration | Focal texture, nearest-centroid classification and confusion statistics |
| ESSE 4220: Remote Sensing of the Earth's Surface | Surface information from visible, SWIR, thermal IR and microwave sensing | Monochromatic radiance and brightness-temperature calculations |
| ESSE 4230: Remote Sensing of the Atmosphere | Atmospheric radiation, spectroscopy, inversion, instruments and platforms | Direct-beam transmission and optical-depth inversion |
| GEOG 3380: Urban Social Analysis | Urban social problems, state policy and evaluation of planning responses | Proposed descriptive area indicators and supplied-time accessibility support |

Official course sources:

- [York EUC course listing](https://www.yorku.ca/euc/our-courses/): descriptions
  for all six GEOG courses above.
- [Lassonde Geomatics Engineering course descriptions](https://lassonde.yorku.ca/esse/academics/bachelor-of-engineering-beng-geomatics-engineering/):
  ESSE 4220.
- [Lassonde Space Science course descriptions](https://lassonde.yorku.ca/esse/academics/eats-space-science-stream/):
  ESSE 4230.
- [GEOG 2340 Winter 2023 syllabus](https://www.yorku.ca/remmelt/syllabi/GEOG2340_W2023_Syllabus.pdf)
  and [GEOG 4440 Winter 2024 syllabus](https://www.yorku.ca/remmelt/syllabi/GEOG4440_W2024_Syllabus.pdf):
  historical examples of expanded course scope, not current-term requirements.

GEOG 3380 is a critical urban-policy course. NET's aggregate indicators are
proposed analytical support rather than a computational syllabus claim. Event
rates use their declared denominators, totals use summed denominators, and zero
denominators remain undefined. Accessibility uses supplied travel times and an
inclusive cutoff; it does not compute routes, congestion or facility capacity.
Area aggregates cannot establish individual characteristics or causal policy
effects. Boundary choices and unresolved within-area variation affect their
interpretation.

## Scientific limits and sources

Planck calculations use an ideal monochromatic blackbody and spectral radiance
per micrometre (`W m^-2 sr^-1 um^-1`). Brightness temperature is an equivalent
blackbody temperature, not corrected land-surface temperature. Sensor band
response, emissivity, reflected radiance and atmospheric corrections require
additional models.

Beer-Lambert calculations describe attenuation of an unscattered direct beam.
Optical depth is defined along a reference path and `air_mass` scales that path.
This does not solve scattering into the beam, thermal atmospheric emission,
spectral line-by-line transfer or an atmospheric profile retrieval.

Relevant primary technical references:

- [USGS Landsat NDVI](https://www.usgs.gov/landsat-missions/landsat-normalized-difference-vegetation-index):
  the normalized NIR/red ratio and Landsat band conventions.
- [NASA Dark Target aerosol retrieval strategy](https://darktarget.gsfc.nasa.gov/atbd-aerosol-optics-and-retrieval-strategy):
  direct-beam attenuation and the additional complexity of satellite retrieval.
- [NOAA spectral radiance-temperature conversions](https://repository.library.noaa.gov/view/noaa/30858):
  instrument-dependent radiance/brightness-temperature relationships.

The CLI accepts bounded inline numerical data. This release does not imply
GeoTIFF or vector-file I/O, scene acquisition, calibrated satellite retrieval,
live sensor integration or a browser GIS interface. Synthetic examples exercise
the declared numerical models; they are not field observations or experimental
validation.

## Qualification of this change

Base commit: `d313351f96aad73fe40229b7d705b18c12e96b64`. Local qualification used
Python 3.12.14, NumPy 2.4.3 and pytest 9.0.2 on Linux. The final combined run
passed **391 tests**, including **279 geomatics tests** and **112 existing
operation, catalog and atmosphere-workflow regression tests**. A separate run
passed all **13 existing spatial-transport tests** with local loopback sockets
enabled. Total: **404 passing tests**.

The geomatics suite checks analytic numerical fixtures, invalid inputs, missing
data, coordinate and raster contracts, output schemas, retained refusals,
tampering, nonexecuting inspection, runtime mismatch and fresh replay identities.
All 16 synthetic examples completed and reproduced through the retained Session.
The command entry point `python -m ciw.net geomatics catalog` also passed.

```bash
python -m pytest -q tests/test_geomatics_gis.py tests/test_geomatics_eo.py tests/test_geomatics_radiometry_urban.py tests/test_geomatics_workflow.py tests/test_geomatics_audit.py
```

`.github/workflows/geomatics.yml` defines Linux and Windows qualification. Local
Linux results do not establish Windows qualification or remote CI success;
those outcomes are reported by the pull request checks.
