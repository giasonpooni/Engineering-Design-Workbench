# Weather science tools

`net weather` adds twelve bounded atmospheric, hydrometeorological and
cryosphere calculation profiles to NET's existing Session evidence and operation
records. It is a local numerical workbench for declared inputs. It does not
establish acquired observations, experimental validation, operational forecast
skill or admitted physical state. The existing `net atmosphere` workload remains
separate; see [ATMOSPHERIC_ENGINE.md](ATMOSPHERIC_ENGINE.md).

## Install and run

Use Python 3.11 or newer in an isolated environment. From the repository root:

```bash
python -m pip install -e .
net weather catalog
net weather example thermodynamics --output weather-request.json
net weather run weather-request.json --output-dir weather-run-001
net weather inspect weather-run-001
net weather verify weather-run-001
net weather replay weather-run-001 --output-dir weather-replay-001
net weather export weather-run-001 --output weather-result.json
```

`example PROFILE --output FILE` accepts every profile listed below. Edit the
generated JSON input values, preserving its schema and explicit units, then run
it into a new directory. Request and export files must also be new: these commands
refuse to overwrite them. Use a fresh output directory for every run or replay.
The catalog supplies input examples, output units, scope and limitations; reading
it does not qualify a profile or execute its model.

The request schema is `ciw.weather-request.v1`, with exactly `schema`, `profile`,
`context` and `inputs`. Context contains `source_kind` and a nonempty `source_ref`.
Generated examples are `synthetic`; manually supplied configurations may use
`declared_inputs`. Neither label asserts that inputs are qualified measurements.
Unknown fields, missing inputs, nonfinite values and out-of-scope values are
refused rather than silently repaired. Units are fixed by the profile; this API
does not infer or convert arbitrary input units.

## Course alignment

This table maps implemented tools to selected topics. It is not a syllabus
equivalence, York endorsement, or claim that all material in a course is covered.
The user-supplied 2024–25 calendar links are preserved in the course column.
Their calendar application was unavailable during scope research; the readable
official York descriptions [Y1–Y3](#course-sources) were used instead.

| Course | Implemented profiles and useful activity | Significant course material outside this implementation |
| --- | --- | --- |
| [LE/ESSE3030 — Atmospheric Radiation and Thermodynamics](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/5ecd89489db21d2600460c46) | `thermodynamics`, `radiation`: parcel moisture/state quantities, uniform-temperature hydrostatic thickness, direct-beam attenuation and surface radiative budget | Moist parcel ascent, spectral transfer and multiple scattering |
| [LE/ESSE3040 — Atmospheric Dynamics I](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/59cac64e2ff94501000f360c) | `synoptic`: geostrophic/ageostrophic wind, vorticity, divergence and temperature advection | Thermal wind, Ekman layers, quasi-geostrophic evolution and general equations-of-motion solver |
| [LE/ESSE4050 — Synoptic Meteorology I](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/59cac6722ff94501000f3622) | `synoptic`, `thermodynamics`: inspect declared local wind/pressure/temperature derivatives and layer thickness | Weather-map ingestion, front detection, air-mass classification and storm-track analysis |
| [LE/ESSE4051 — Synoptic Meteorology II](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/59cac5c06fb2530100b445c7) | `forecast_verification`: compare supplied temperature forecasts and a persistence baseline against paired reference values | GEM/other model ingestion, satellite/radar nowcasting and forecast generation |
| [LE/ESSE4120 — Cloud Physics and Radar Meteorology](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/59cac5a61b2ab801004b2847) | `radar_cloud`, `storm_sounding`, `thermodynamics`: liquid-drop moments, empirical rain estimate and supplied-parcel buoyancy | Nucleation, condensational growth, collision/coalescence, mixed-phase microphysics and radar processing |
| [LE/ESSE4140 — Numerical Weather Prediction](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/59cac6675fa0580100650a24) | `nwp_transport`, `forecast_verification`: bounded advection exercise, numerical conservation/diffusion and temperature-error comparison | Full numerical weather prediction, assimilation, atmospheric physics and boundary forcing |
| [LE/ESSE4240 — Storms and Weather Systems](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/59cac67a2ff94501000f3628) | `storm_sounding`, `synoptic`, `radar_cloud`: inspect buoyancy, declared-layer shear and local diagnostics | Cyclone evolution, tornado/hail/lightning predictions, lake-effect modeling and hazard probabilities |
| [SC/GEOG4205 — Climatology of High Latitudes](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/673cfd44a269d097a4de2ae3) | `polar_radiation`, `ice_growth`: polar day/night branches, prescribed energy budget and ideal freshwater-ice growth | Observed climatology, atmospheric/oceanic energy transport and climate-feedback dynamics |
| [SC/GEOG4210 — Hydrometeorology](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/673cfd840547fb3735c57a90) | `evapotranspiration`, `water_balance`: daily reference evaporation demand and conservative liquid-water accounting | Instrument acquisition/calibration, actual landscape evaporation, catchment routing and flood forecasting |
| [SC/GEOG4310 — Dynamics of Snow and Ice](http://calendars-2024-25.studentsv3.uit.yorku.ca/academic-calendar#/courses/view/673cfee75df4e0302c0b0bdf) | `snow_ice`, `ice_growth`: precipitation partition, energy-limited snowmelt and freshwater-ice growth | Snow structure evolution, sea-ice salinity/mechanics, river-ice processes and glacier dynamics |

## Implemented models and limits

The source `PROFILES` and validation functions are authoritative for input bounds.
These bounds define a supported numerical domain, not evidence that every accepted
configuration is a physically accurate model of its intended site.

### Thermodynamics, radiation and liquid-drop radar

`thermodynamics` uses Buck 1996 saturation expressions with an explicit `water`
or `ice` phase. Relative humidity is a fraction in [0, 1] relative to that phase.
Supported temperatures are 233.15–323.15 K over water and 223.15–273.15 K over ice.
Parcel pressure is 20–110 kPa; vapor partial pressure cannot exceed 20% of total
pressure. Mixing ratio, specific humidity, virtual temperature, density and dry
potential temperature use an ideal mixture with fixed constants. Hydrostatic
thickness uses this single parcel's virtual temperature throughout the layer.
There is no supersaturation, enhancement factor, solute/curvature correction,
condensate loading, latent heating, or computed parcel ascent. [S1, S2]

`radiation` uses direct-beam transmission `exp(-optical_depth / solar_cosine)` and
an opaque gray surface. Net longwave is
`emissivity * (downwelling_longwave - sigma * surface_temperature**4)`;
positive net radiation heats the surface. Optical depth, diffuse shortwave and
downward longwave are prescribed independently. The solar cosine is 0.05–1:
this profile excludes night, twilight and spherical/refraction corrections.
It calculates no spectral/multiple-scattering transfer, turbulent exchange,
conduction or temperature evolution. The separate `polar_radiation` profile has
explicit daily polar day/night branches.

`radar_cloud` accepts 1–128 spherical liquid-drop bins. `concentration_m3` is a
bin-integrated number concentration, not a number-density spectrum per millimetre.
Diameters are millimetres. It returns number, liquid-mass and sixth-diameter
reflectivity moments, dBZ and the empirical rain estimate from `Z = a * R**b`.
The declared Rayleigh guard is `pi * diameter / wavelength <= 0.3`, with consistent
length units; it is not a scattering error bound. Total concentration must be
positive because zero-reflectivity dBZ is undefined. Fixed water density is
1000 kg/m³. No drop growth, ice, mixed phase, beam geometry, attenuation, Doppler
velocity or measured radar ingestion is implemented. A selected Z–R relation
does not calibrate a storm or derive rain rate from fall speeds. [S3]

### Local dynamics and numerical transport

`synoptic` uses local east/north/up Cartesian coordinates, constant-height
derivatives, and `f = 2 * Earth_rotation * sin(latitude)`. Geostrophic balance is
steady and frictionless on an f-plane. Vorticity and divergence use the supplied
wind-gradient tensor; they are not derivatives of the calculated geostrophic
wind. Temperature advection is `-(u * dT_dx + v * dT_dy)`. Latitudes with magnitude
below 5° and exact poles are excluded; this does not establish applicability of
geostrophy elsewhere. No curvature, beta effect, vertical motion, front dynamics
or weather evolution is modeled. [S4]

`nwp_transport` solves one-dimensional periodic constant-velocity passive-tracer
advection with first-order upwind steps on a uniform grid. It accepts 3–128 cells
and 0–500 steps, requires nonnegative dimensionless cell averages, and enforces
`abs(velocity) * time_step / cell_width <= 1`. Output includes the final field,
Courant number, extrema, total variation, integrals and the leading modified-
equation numerical-diffusion coefficient. Tracer integrals have units of metres,
not atmospheric mass. Numerical diffusion is not physical diffusivity. Momentum,
moisture, terrain, assimilation, sources/sinks and atmospheric boundary forcing
are absent: the name identifies an NWP teaching primitive, not an NWP model. [S5]

### Evaporation, water, snow and ice

`evapotranspiration` implements daily FAO-56 grass reference ET with prescribed
net radiation and soil heat in MJ/m²/day, pressure/vapor pressure in kPa, daily
minimum/maximum temperature in Celsius and wind at 2 m in m/s. It reports
radiative and aerodynamic components. Negative raw ET remains available as a
condensation diagnostic; reference demand is clipped at zero. Supersaturation
is refused. This is neither actual crop ET, open-water evaporation nor frozen-
surface sublimation. No field calibration or input-uncertainty propagation is
performed. [S6]

`water_balance` is a declared daily single-store bucket for 1–366 days. Each day
applies infiltration/capacity overflow, then available-water-limited ET, then a
prescribed fractional drainage. Inputs and stores are millimetres of liquid
water; outputs retain mass accounting. Subdaily timing, groundwater exchange,
frozen soil, Richards flow and channel routing are absent. This is a reduced
model, not HEC-HMS or a calibrated catchment model.

`snow_ice` tracks 1–366 daily steps of SWE, snowfall, rainfall, melt and liquid
outflow. Rain/snow fraction varies linearly between declared air-temperature
thresholds. Melt uses nonnegative energy available **after** warming a ripe
snowpack to 0°C, at 0.334 MJ/kg latent heat, and cannot consume more SWE than is
available. It reports used and unused melt energy. SWE in millimetres is
liquid-water-equivalent mass per area, not geometric snow depth. The model has
no cold-content state, negative-energy cooling, refreezing, sublimation, liquid
retention, compaction, drifting or avalanche prediction.

`polar_radiation` uses approximate FAO-56 daily solar geometry with explicit
polar day/night branches. It converts daily TOA energy to a daily-mean surface
shortwave flux using prescribed transmissivity and albedo. Its surface residual
subtracts upward sensible heat, upward latent heat and downward ground heat from
net radiation. Incoming longwave and temperature are also prescribed. FAO warns
of reduced winter validity beyond 55° latitude: avoiding singularities at the
poles does not improve astronomical accuracy. There is no refraction, terrain
shading, observed climatology, prognostic temperature or feedback model. The
residual is not automatically available snowmelt energy. [S6]

`ice_growth` evaluates the one-phase quasi-steady freshwater Stefan relation
`h_final**2 = h_initial**2 + 2*k*(0 - T_surface)*duration/(rho*latent_heat)`.
Constants are 2.2 W/(m K), 917 kg/m³ and 334000 J/kg. Water remains at 0°C and
the prescribed ice-surface temperature is constant. It neglects ice heat
capacity, snow insulation, salinity, water heat flux, solar absorption and
mechanical deformation. Surface temperature is not automatically air
temperature. No ice load-bearing or travel-safety conclusion follows. [S7]

### Storm-environment and forecast comparison

`storm_sounding` computes `g * (parcel_Tv - environment_Tv) / environment_Tv`
from supplied virtual temperatures and integrates a piecewise-linear buoyancy
profile with exact within-segment zero crossings. Positive, negative and net
integrals cover the entire supplied layer. They are **not operational CAPE/CIN**:
the tool does not compute parcel ascent or determine LFC/EL. Endpoint wind shear
is over the declared layer, not automatically a 0–6 km or effective storm layer.
Fixed gravity, no entrainment, condensate loading or pressure perturbations, and
no storm occurrence or hazard forecast are assumed.

`forecast_verification` compares equal-weight paired temperatures in Kelvin. It
returns bias, MAE, RMSE, persistence RMSE and the difference
`persistence_MSE - forecast_MSE` in K². This difference is not normalized skill
and is defined even for a perfect baseline. The caller must establish matching
locations/valid times and a persistence forecast that uses no future information.
No missing-value omission, uncertainty intervals, event scores or forecast
generation is provided. In-sample errors alone do not establish predictive skill.

## Evidence, execution and verification

The workflow retains its input declaration as NET source evidence. That evidence
identifies a model-input record, not a new physical measurement. It executes
`weather.compute.v1` and, after a completed calculation, a distinct
`weather.verify.v1` operation. Evidence ID, operation ID, calculation execution
and result IDs, verifier execution ID and verification ID remain separate.
The checker binds the exact retained candidate occurrence, including its source,
result, execution and digest; a detached substitute is refused.

| Action | What happens | What its result establishes |
| --- | --- | --- |
| `catalog` | Reads fixed trusted profile metadata | Availability of declarations only; no qualification run |
| `run` | Records a fresh calculation and verification in a new directory | A local calculation and bounded numerical-check outcome |
| `inspect` | Reopens retained records, checking schema, seals and identity/dependency bindings | Structural integrity and retained outcomes; no model compute or fresh numerical checking |
| `verify` | Applies current numerical checks to the retained candidate and compares the retained report | Fresh numerical checking, with current checker identity; no new calculation occurrence |
| `replay` | Requires matching recorded calculator/checker source and Python/environment identities, then runs into a new directory | New execution/verification occurrences and comparison of the deterministic result digest |
| `export` | Performs fresh retained verification and writes its inspection result to a new JSON file | Export of a passing local result with its identities and limitations |

The command-level `verify` comparison does not add a new retained operation
occurrence. Use a new `run` or `replay` when a new recorded execution is needed.
`inspect` reports `fresh_execution: false` and
`fresh_numerical_verification: false`; it does not present old calculations as
new work. Replay's claim is `same_runtime_deterministic_result_reproduction`,
not empirical replication or cross-platform numerical equivalence.

Numerical checks examine inverse equations, physical bounds, conservation,
moment identities, analytic/linear-transport relationships and score
reconstruction within these representations. They can catch implementation or
record inconsistencies. Their passing does not test the assumptions against
independent field measurements or quantify predictive uncertainty. Catalog or
local `PASS`/`LOCAL` status therefore cannot establish experimental validation.

Retained authority explicitly remains:

```json
{
  "physical_validation": "not_established",
  "operational_forecast": "not_established",
  "state_admission": "not_performed",
  "hardware_actuation": "not_performed"
}
```

JSON digests bind records for consistency; this workflow does not create a
third-party attestation or authenticate the truth of input declarations.

### Recorded local qualification

For this implementation, the selected weather and existing atmosphere/operation/
catalog suite completed with **705 passed, zero failures, errors or skips**.
A built wheel installed outside the source checkout completed **74 CLI calls**
covering all twelve profiles through example, run, inspect, verify, replay and
export. Supplementary operator checks completed with **55 passed and one skipped
external-native integration test**. These are numerical and software-integration
results. Hosted Linux/Windows CI remains pending; physical validation remains
unestablished.

## Integration handoff

The fixed Python providers plug into NET's Session/operation substrate. Saved
requests are data-only and cannot select arbitrary code or load plugins. Keep
new providers behind explicit scope, units, shape, resource and identity checks.

Potential compositions require explicit conversion and scientific assumptions.
For example, daily `reference_et0_mm_day` can be declared as a bucket demand
only when reference ET is appropriate for that exercise. Snow
`liquid_outflow_mm` can provide liquid input to a bucket after matching daily
intervals and units. A surface energy residual must account for snow cold
content and relevant fluxes before it becomes `melt_energy_mj_m2`. These are
handoff conventions, not an implemented automatic coupling engine.

The current extension has no CF/NetCDF, GRIB, METAR/radiosonde, satellite, or
radar-volume ingestion path; map/chart rendering and a dedicated weather GUI
are also outside these commands. A real-data extension needs retained original
artifacts, source/time/location identities, units and coordinate interpretation,
missing-data policy, acquisition/calibration evidence, and reproducible
preprocessing before declaring numerical inputs. Forecast comparisons additionally
need issue/valid-time provenance and leakage-resistant evaluation splits.

Scientific expansion points include uncertainty propagation, field-calibrated
evaporation and hydrology, cold-content/refreezing snow physics, snow-covered or
saline ice, moist parcel ascent, spectral/cloud radiation, gridded synoptic
operators and a qualified external weather model. Implement these as additional
profiles or adapters with their own validation evidence. None is implicitly
provided by the current twelve profiles.

## Course sources

Scope research accessed 2026-10-03. Course descriptions establish topic alignment,
not scientific validation of NET and not the current year's course availability.

- **Y1:** [York Lassonde, Atmospheric Science stream](https://lassonde.yorku.ca/esse/academics/eats-atmospheric-science-stream/): descriptions for ESSE3030, 3040, 4050, 4051, 4120 and 4140.
- **Y2:** [York Lassonde, graduate courses](https://lassonde.yorku.ca/esse/academics/graduate/graduate-courses/): ESS5201 Storms and Weather Systems, explicitly integrated with ESSE4240.
- **Y3:** [York EUC, course descriptions](https://www.yorku.ca/euc/our-courses/): GEOG4205, 4210 and 4310. The readable [individual GEOG4210 page](https://www.yorku.ca/euc/euc-course/eu-geog-4210-hydrometeorology/) confirms the evaporation/instrumentation emphasis.

## Scientific references

These references motivate formulas and interpretation. NET does not claim to
reimplement the complete referenced packages, operational models or methods.
Formula constants and implemented limits are frozen in the versioned source.

- **S1:** [NSF NCAR EOL, Water Vapor Pressure Formulations](https://www.eol.ucar.edu/data-software/conventions-and-standards/water-vapor-pressure-formulations), Buck 1996 water and ice expressions.
- **S2:** [Unidata MetPy, potential temperature](https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.potential_temperature.html), [virtual temperature](https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.virtual_temperature.html), and [hydrostatic thickness](https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.thickness_hydrostatic.html). NET's uniform-layer calculation is narrower than general sounding integration.
- **S3:** [NOAA/NWS, Radar Reflectivity Measurement](https://training.weather.gov/nwstc/NEXRAD/RADAR/3-1.htm) and [wradlib Z–R conversion](https://docs.wradlib.org/en/latest/generated/wradlib.zr.z_to_r.html).
- **S4:** [NOAA GFDL, Relation between flow and mass fields](https://www.gfdl.noaa.gov/wp-content/uploads/files/user_files/stg/ch_5.pdf), geostrophic balance; [MetPy advection](https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.advection.html).
- **S5:** [MITgcm, linear advection schemes](https://mitgcm.readthedocs.io/en/latest/algorithm/adv-schemes.html), first-order upwind; [Clawpack, advection](https://www.clawpack.org/riemann_book/html/Advection.html), analytic transport reference.
- **S6:** [FAO Irrigation and Drainage Paper 56, Chapter 2](https://www.fao.org/4/x0490e/x0490e06.htm), daily reference ET; [Chapter 3](https://www.fao.org/4/x0490e/x0490e07.htm), vapor-pressure, solar-geometry, input units and limits; [Chapter 4](https://www.fao.org/4/x0490e/x0490e08.htm), worked calculations.
- **S7:** Zhaka, Bridges, Riska and Cwirzen, [A review of level ice and brash ice growth models](https://www.cambridge.org/core/journals/journal-of-glaciology/article/review-of-level-ice-and-brash-ice-growth-models/A0972F8600E4C9CD9B8A84BD0DEBEE3F), *Journal of Glaciology* 68(270), 685–704 (2022; online 2021), [doi:10.1017/jog.2021.126](https://doi.org/10.1017/jog.2021.126), section 2.1 on Stefan growth assumptions.
