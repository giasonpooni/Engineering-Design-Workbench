# Calibration contract

## Inputs

`Observation` identifies the observation, source artifact, sensor, quantity, input unit, and timezone-aware acquisition instant. It contains an indicated value, an optional numeric raw value, and optional environmental readings. Validity comparisons use UTC instants, including across daylight-saving folds; the original timestamp is retained. Raw bytes and extraction lineage belong to the source acquisition system; `raw_value` is a preserved numeric view, not a substitute for the referenced source artifact.

`CalibrationProfile` identifies a profile and its calibration artifact, sensor, quantity, input/output unit tokens, gain, offset, coefficient covariance in `[g,b]` order, a half-open validity interval `[valid_from, valid_until)`, and optional reference IDs. An optional inclusive input range and named environmental intervals constrain applicability. Unit tokens are exact identifiers; no unit registry, dimensional proof, or implicit conversion is provided. Gain has units `output/input`, offset has output units, and covariance entry `(i,j)` has the product of its two variable units.

`JointCovariance` contains the full covariance in exactly `[x,g,b]` order, where `x` is the indicated value. The `[g,b]` block must exactly match the profile coefficient covariance. Zero cross-covariance is an explicit caller assumption and is never inferred from missing data. There is no default covariance.

`ServingStatus`, when supplied, includes its own record ID, profile ID, report time, and `active`, `superseded`, or `withdrawn` state. The profile ID must match. This is reported evidence, not an independently retrieved registry status. It does not alter acquisition-time validity: a later withdrawal remains visible while historical replay may still calculate a result. An active serving record cannot make an out-of-validity acquisition acceptable. Decisions about retroactive invalidation or present operational use remain external.

All records are frozen. Covariance arrays and iterable record collections are detached into immutable tuples at construction.

## Outputs

`CalibrationResult` returns:

- Observation, source artifact, profile, calibration artifact, and supplied reference identities.
- The original raw and indicated values, corrected value, acquisition time, and explicit input/output units.
- `correction_from_indication = y-x` only when input and output unit tokens match; otherwise `None` because direct subtraction would be ill-typed.
- `additive_correction = b` in output units, independently of whether units match.
- Jacobian, complete supplied joint covariance, propagated variance, standard uncertainty, and six named uncertainty budget terms.
- Optional serving status, approximation/applicability diagnostics, and versioned operation ID.

The result does not identify itself as an admitted state, verified measurement, or certified traceability chain.

## Rejection rules

MCUR rejects mismatched sensor/quantity/unit identities, missing required environmental readings, mismatched environmental units, out-of-range indications or conditions, out-of-validity acquisition events, naive datetimes, invalid record identities, nonfinite values, covariance order or dimension errors, asymmetric or indefinite covariance, coefficient covariance substitution, and unrepresentable numerical outputs. Numerical errors are explicit; there is no fallback covariance, clipping, or result admission.

## Existing exchange boundary

`mcur.exchange.export_result` takes explicitly mapped input payload, complete numerical result, output components and covariance, input/model/calibration references, acquisition applicability statement, caller-supplied source revision, execution reference, and creation time. It calls the pinned SET `validate_result_artifact` validator on `notation.instrument.result-artifact.v1`.

The example exports a corrected scalar component, a one-by-one propagated covariance, original raw/indicated values, complete calibration profile and joint covariance, and calibration/reference identities at both outer and covariance levels. The mathematical input digest is content-based; result identity also binds the execution reference. `verification_refs` starts empty. Export does not fabricate an independent verification artifact.

The exporter snapshots caller-owned mappings and rejects nonfinite JSON values. The source revision is labeled `caller_supplied_unattested`; its syntax check does not prove execution of that commit. SET conformance does not establish metrological traceability, model adequacy, evidence authenticity, or a CIW admission decision.
