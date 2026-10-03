# Atmospheric measurement preparation

`net atmosphere compare prepare` maps an explicit SI CSV and an authoring
declaration into the existing sealed reference and acceptance-policy contracts.
Preparation validates authoring and mapping. It does not acquire or authenticate
observations, validate calibration, execute a scientific operation or create
operation, execution or verification occurrence identities.

The runnable files in
[`examples/atmosphere-measurements`](../examples/atmosphere-measurements/README.md)
are **illustrative, with no acquired data**. Their configured origin values exercise the lifecycle, with no independent
evidence for the model's profile or physical accuracy.

## Executable lifecycle

With `net` installed, run these commands from the repository root. Every created
directory and export file must be absent:

```sh
net atmosphere compare prepare examples/atmosphere-measurements/measurements.csv \
  --declaration examples/atmosphere-measurements/declaration.json \
  --output-dir measurement-prepared
net atmosphere compare preparation-inspect measurement-prepared
net atmosphere compare preparation-verify measurement-prepared
net atmosphere run examples/atmosphere-measurements/request.json \
  --output-dir measurement-atmosphere
net atmosphere compare run measurement-atmosphere \
  --reference measurement-prepared/reference.json \
  --policy measurement-prepared/policy.json \
  --output-dir measurement-comparison
net atmosphere compare verify measurement-comparison
net atmosphere compare export measurement-comparison \
  --format csv --output measurement-comparison.csv
net atmosphere compare export measurement-comparison \
  --format json --output measurement-comparison.json
```

Inspection validates retained preparation data. Preparation verification freshly
reconstructs the CSV/declaration mapping and checks the resulting reference and
policy. The later comparison executes the existing comparison operations and
retains their separate identities. Its independent numerical verification checks
the comparison arithmetic; it can PASS for a correctly calculated disagreement.

Preparation retains five files: `measurements.csv`, `declaration.json`,
`reference.json`, `policy.json` and `preparation.json`. The preparation record
binds the CSV content, declaration, sealed outputs and reference evidence identity.
The commands report `prepared`, `retained` and `checked`, respectively;
`fresh_mapping_check` is true only for preparation verification. These statuses
describe data preparation rather than measurement authenticity or physical
validation.

## Exact import format

The header has these eleven columns, in this exact order:

```csv
sample_index,height_m,quantity,value,unit,uncertainty_kind,absolute_bound,coverage_factor,uncertainty_ref,instrument_ref,calibration_ref
```

Each row declares one scalar quantity at one retained sample:

| Column | Meaning |
| --- | --- |
| `sample_index` | Integer index of the candidate's retained height sample |
| `height_m` | Height above the declared origin, in metres |
| `quantity` | Exact comparison field name |
| `value` | Corrected scalar value in the declared SI unit |
| `unit` | Exact unit required by that field |
| `uncertainty_kind` | `declared_expanded` or `declared_absolute_bound` |
| `absolute_bound` | Nonzero declared bound in the same unit as the value |
| `coverage_factor` | Positive `k` for `declared_expanded`; empty for an absolute bound |
| `uncertainty_ref` | Reference to the retained uncertainty declaration or budget |
| `instrument_ref` | Nonempty reference to the instrument declaration |
| `calibration_ref` | Calibration-evidence reference, or empty to retain JSON null |

Repeated quantities at one sample and inconsistent heights are invalid. Input
rows may appear in any order; preparation deterministically groups observations
by sample index and orders quantity keys. The reference permits 1–129 observations
and at most six quantities per observation. There is no interpolation,
extrapolation or inferred conversion.

| Quantity | Exact unit | Candidate profile |
| --- | --- | --- |
| `temperature_k` | `K` | Dry or moist |
| `pressure_pa` | `Pa` | Dry or moist |
| `density_kg_per_m3` | `kg/m^3` | Dry or moist |
| `water_vapour_pressure_pa` | `Pa` | Moist |
| `relative_humidity` | `1` | Moist, with compatible declared convention |
| `liquid_water_saturation_pressure_pa` | `Pa` | Moist |

Relative humidity is a fraction: `0.50` means 50%. Convert Celsius, pressure
units, RH percentages and assessed instrument corrections before import, and
retain their derivation with the source evidence. The importer does not infer
these transformations.

The unsealed declaration has exact top-level groups `schema`, `provenance`,
`context` and `thresholds`; its schema is
`ciw.atmosphere-measurement-import.v1`. The example's
[`declaration.json`](../examples/atmosphere-measurements/declaration.json)
shows the complete structure. Provenance declares `kind: declared_measurements`,
a source reference, a nullable source URL and an explicit independence boolean.
URLs are retained metadata and are not fetched or authenticated. Thresholds
declare `absolute_tolerance` and `relative_tolerance` for exactly the imported
fields. Preparation generates seals; hand-edited input declarations need no
`record_digest`.

## Context and uncertainty

The reference's frame, height origin, sample indices, exact sampled heights and
nonnull UTC time must match the atmospheric candidate. A declared-measurement
comparison requires the candidate's `reference.context.source_kind` to be
`declared_environment` with the same UTC time. The example uses
`2026-10-03T12:00:00Z` as an illustrative context label; historical declarations
remain inspectable.

For temperature and pressure alone, use humidity convention `not_applicable`.
An RH comparison must explicitly declare its definition. The current moist
provider uses `pure_liquid_magnus_17_62_243_12.v1`. A reference declared as
`pressure_enhanced_relative_humidity` requires an expanded provider and yields
EXPAND for RH; no silent conversion aligns these different definitions.

For expanded uncertainty, supply the already expanded value `U`, with its
coverage factor `k`. The importer and comparator do not multiply `U` by `k`
again or infer a confidence level. The example supplies `U = 0.2 K` and
`U = 50 Pa`, each with `k = 2`. Nonzero uncertainty, an instrument reference
and a nonnull context time are required for declared measurements. An empty
calibration cell records missing calibration evidence rather than assuming a
valid calibration.

The acceptance rule remains
`absolute_tolerance + relative_tolerance * abs(reference_value) + absolute_bound`.
Engineering tolerances and reference bounds are separate declarations. The
example's allowances of `0.5 K` and `100 Pa`, with zero relative tolerances,
produce bands of `0.7 K` and `150 Pa`. This additive rule is not statistical
uncertainty propagation, covariance estimation or a failure probability.
See [the reference contract and primary uncertainty references](ATMOSPHERIC_REFERENCE_VALIDATION.md).

## First physical comparison

Use a stable environment within the selected dry or unsaturated moist model's
declared domain. Retain the acquisition record, instrument and calibration
evidence, corrected SI observations, height/frame/time definitions and assessed
uncertainty budget. Declare engineering tolerances before interpreting agreement.

Choose sampled heights that the request explicitly retains. Keep validation
observations separate from data used to set origin conditions or fit the lapse
rate. The supplied origin-only fixture checks configured boundary values; a
held-out profile comparison is needed to investigate predictive agreement.

Inspect preparation, freshly verify the atmospheric candidate and comparison,
and review pointwise residuals, unsupported fields and alignment diagnostics.
Retain disagreement as evidence. Physical validation additionally requires
independently assessed authenticity, traceability, representativeness and model
discrepancy; a prepared seal or numerical PASS cannot supply those judgments.
