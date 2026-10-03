# Agriculture and irrigation

`net irrigation` turns declared soil observations, daily weather and zone
parameters into a retained, numerically checked irrigation investigation. It
computes reference evapotranspiration, combines compatible observations of root
zone moisture, balances water and allocates a finite pump budget across zones.
Its output is a simulated proposal for review. It does not operate a valve or
pump, establish agronomic suitability, or train a forecasting model.

## Run an investigation

Install the Terminal from this checkout with `python -m pip install .`, then run
the commands from a writable investigation directory:

```sh
net irrigation example --output irrigation-request.json
net irrigation run --request irrigation-request.json --output-dir irrigation-run
net irrigation inspect irrigation-run
net irrigation verify irrigation-run --output irrigation-fresh-audit.json
net irrigation replay irrigation-run --output-dir irrigation-replay
net irrigation export-csv irrigation-run --output irrigation.csv
net irrigation report irrigation-run --output irrigation.html
```

The example contains synthetic declarations. Copy it to a new request file and
replace its observation, calibration, zone and weather declarations before
evaluating a real investigation. Each run, replay and exported artifact is
create-only; choose a new path to retain a previous investigation.

`as_of` is an explicit UTC midnight timestamp ending in `Z`. The weather dates
must be contiguous daily rows starting on that date. Observation and calibration
times also use explicit UTC timestamps. Freshness is evaluated against `as_of`,
so a historical replay does not quietly use the current wall clock. The example
repeats synthetic weather on October 3–5; these rows are not measured October
weather or a validated forecast.

Inspection checks retained structure, identities, seals and dependency links.
It does not rerun the numerical verifier. `verify` creates a fresh verification
occurrence. `replay` executes the declared calculation again with new execution
and result identities. CSV export and the offline HTML report also request
fresh verification while preserving the original bundle. Opening the HTML file
does not contact a service or control equipment.

## Model and units

The daily reference calculation follows [FAO-56, chapter 2, equation 6](https://www.fao.org/4/x0490e/x0490e06.htm):

```math
ET_0=\frac{0.408\Delta(R_n-G)+\gamma\frac{900}{T+273}u_2(e_s-e_a)}
{\Delta+\gamma(1+0.34u_2)}.
```

`ET0` is grass-reference evapotranspiration, not an observation of crop water
use. Wind refers to 2 m height; radiation and soil heat flux are daily energy
totals in MJ/m²/day, temperatures are °C and vapour pressures are kPa. Declared
weather must already match these units and reference conditions.

The fixed root zone uses `TAW = 1000 (theta_fc - theta_wp) root_depth_m` and
`RAW = depletion_fraction × TAW`, in mm. The stress-adjusted single-coefficient
crop estimate is `ETc = Ks Kc ET0`; this approximation is most appropriate when
soil evaporation is a small part of total ET. These relationships and the root
zone balance are described in [FAO-56, chapter 8](https://www.fao.org/4/x0490e/x0490e0e.htm).

This instrument is a daily bucket with fixed, declared crop and soil
parameters. It does not resolve wetting fronts, spatial flow, infiltration
kinetics or Richards' equation. Upward capillary water flow is physically
possible. The declared capillary-rise term represents an external input to the
bucket; the model does not calculate it from a water table or pressure field.

## Observation handling

Only observations declared to represent the same zone-wide, root-depth mean
volumetric water content can be combined. Moisture is expressed in m³/m³.
A point probe at one depth, EC, temperature, canopy imagery and satellite
indices do not automatically measure this same quantity. A separate qualified
observation operator is needed to map them into the declared root-zone mean.

The request retains its source reference. Each observation retains its ID,
calibrated value, observation time, calibration reference and expiry, and clock
reference. The observation group declares the common root-zone measurand, units
and covariance. The covariance describes both individual uncertainty and
correlation between the included measurements. Supplying many
correlated probes cannot establish precision by treating them as independent.
This release checks these declarations and calculates conditional numerical
uncertainty; it does not certify calibration records or empirical uncertainty
coverage.

Uncertainty propagation covers the initial soil observations while weather,
crop, soil and pump parameters remain fixed. The screening interval propagates
the initial `k=2` endpoints with the same nominal allocated irrigation; it is
not a forecast confidence interval and has no declared coverage probability.
Calibration drift growth and weather or parameter uncertainty are not modelled.

An observation dated after `as_of` or older than `max_age_hours` causes that zone
to abstain. A calibration ending at or before `as_of` also causes abstention.
Calibration expiry is exclusive: one ending exactly at `as_of` has expired.

## Proposal and qualification

`status` reports numerical qualification of the declared model. The separate
`planning_status` reports whether the simulated proposal is ready, needs
review, has unmet demand, or abstains because its observations cannot support
the decision. A numerically qualified calculation can still abstain or leave
demand unmet. The command response retains these distinctions.

The CLI exits `0` for a numerically qualified READY proposal, `2` for a
numerically qualified REVIEW, ABSTAIN or UNMET proposal, and `1` for malformed
inputs or failed numerical qualification. Exit `2` can accompany a successfully
created retained bundle or report; read both `status` and `planning_status`.

Pump capacity, the daily water budget, declared efficiency and per-zone limits
bound the allocation. Zone list order determines allocation priority. An
unmet request remains visible rather than exceeding the budget. Scheduled
volumes are gross delivered m³; net irrigation depths are water entering the
root-zone bucket. `1 mm` over `1 m²` is `0.001 m³`. Efficiency converts gross
water into net irrigation; these quantities must not be added together.

Flow and pressure residuals are diagnostic hints relative to declared expected
telemetry. They can support further investigation of a leak, restriction or
valve problem; they do not uniquely identify its physical cause. A valid
telemetry discrepancy places the corresponding zone on REVIEW and holds its
allocation. Supplied stale, future or expired telemetry makes that zone ABSTAIN.
These holds persist across the declared horizon; clearing them requires a new
investigation with suitable evidence.

The CSV contains one row per zone per declared day in allocation order:

| CSV quantity | Unit and meaning |
| --- | --- |
| `depletion_start_mm`, `depletion_end_mm` | mm below field capacity; larger depletion means a drier root zone |
| `et0_mm` | Daily grass-reference ET depth, separate from the declared crop estimate |
| `actual_crop_et_mm` | Stress- and available-water-limited model ET depth, not measured crop ET |
| `allocated_gross_m3` | Proposed pump-delivered volume before application efficiency |
| `allocated_net_mm` | Proposed irrigation depth entering the root zone after efficiency |
| `unmet_net_mm` | Requested irrigation depth that the limits prevent allocating |
| `unmet_crop_et_mm` | Potential crop ET depth not supplied by the bucket's stressed/finite water availability |
| `rainfall_mm`, `runoff_mm`, `capillary_rise_mm`, `deep_percolation_mm` | Explicit terms in the root-zone conservation balance |
| `screening_lower_end_mm`, `screening_upper_end_mm` | Conditional initial-soil uncertainty endpoints in mm |
| `pump_window_relative_start_h`, `pump_duration_h`, `pump_window_relative_end_h` | Sequential hours relative to the declared daily pump window; no absolute valve command |
| `balance_residual_mm` | Computed water-conservation residual; fresh verification checks it |
| `planning_status`, `reasons`, `projection_is_descriptive_only` | Holds, shortfalls and descriptive projections remain explicit |

The retained source declaration, operation, execution, result and verification
have distinct identities. Numerical qualification compares the candidate with
a separately implemented reference and checks water conservation, finite
values and allocation bounds. The authority fields continue to report
`physical_validation: not_established` and `hardware_actuation: not_performed`.

LSTM/PINN training, satellite assimilation, live MQTT/LoRa/ISOBUS ingress,
fertigation, frost protection and autonomous actuation need separate data,
models, interfaces and qualification. A physics constraint alone does not
establish a learned model's accuracy.

## Qualify an installed package

The reusable gate runs the actual installed commands from a new directory
outside the checkout, with isolated Python imports. It retains command receipts
and `qualification.json`:

```sh
python scripts/check_irrigation_installed.py \
  --python /absolute/path/to/installed/python \
  --net /absolute/path/to/installed/net \
  --output-dir /new/irrigation-qualification
```

Add `--expected-wheel /absolute/path/to/package.whl` to compare the installed
package bytes with the qualified wheel. This gate checks numerical reference
values, allocation and balance, fresh verification and replay identities,
immutable retained bundles, exports, and negative input cases. A passing gate
qualifies the bounded synthetic investigation; field validation requires
independent measured weather, calibrated observations, delivered volumes and
held-out crop and soil investigations.
