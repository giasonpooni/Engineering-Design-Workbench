# Illustrative atmospheric measurement import

**These values are an illustrative fixture, not acquired measurements.** The
instrument labels, timestamp and uncertainty declarations are examples. No
calibration evidence or physical-validation claim accompanies them.

The CSV exercises the declared-measurement import format with temperature
`288.15 K` and pressure `101325 Pa` at sample zero. The dry request uses the same
origin values and UTC context. Agreement at this configured boundary is a
workflow check; it does not independently test the atmospheric profile.
`independent_of_candidate` is explicitly `false`.

From the repository root, with `net` installed, run:

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
```

Output directories and export files must be absent before creation. Preparation
retains the CSV and declaration, validates their mapping, and seals the reference
and policy. It does not acquire data, authenticate an instrument, assess a
calibration or execute a scientific comparison.

The absolute bounds are already declared expanded uncertainties: `U = 0.2 K`
and `U = 50 Pa`, each with coverage factor `k = 2`. The comparator retains `k`
and does not multiply either bound by it again. Engineering allowances are
separately declared as `0.5 K` and `100 Pa`; relative allowances are zero.
The resulting acceptance bands are `0.7 K` and `150 Pa`. No confidence level
or statistical model is inferred.

Both CSV calibration-reference cells are empty and become JSON null. Replace
this fixture with corrected observations and independently assessed acquisition,
uncertainty and calibration evidence before making a physical-validation claim.
Retain held-out sample heights distinct from values used to set the request's
boundary or fit its parameters.

See [the measurement ingress guide](../../docs/ATMOSPHERIC_MEASUREMENT_INGRESS.md)
and [the comparison contract](../../docs/ATMOSPHERIC_REFERENCE_VALIDATION.md).
