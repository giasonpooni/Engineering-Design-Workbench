# CIW calibration subprocess, v1

RCI owns conversion, assembly binding, calibration applicability, and
uncertainty. CIW owns sessions, operations, executions, results, persistence,
and verification identities. There is no CIW import in this endpoint and no
scientific code needs to be copied into the workbench.

The existing `rci-assembly-v1` and observation formats, acquisition behavior,
and pinned digests remain unchanged. The new calibration binding supplements
the assembly contract; a legacy assembly alone is insufficient for this
endpoint. All fixtures are explicitly simulated.

## Invocation

With this repository installed, use:

```bash
python -m instrument_chain.ciw_adapter < request.json > response.json
```

From the source checkout, use `PYTHONPATH=src` with the same command. One JSON
request is read from stdin; one JSON response is written to stdout. Expected
domain refusals exit successfully at the process level, with `status: refused`
and no `data`. An unsuccessful process invocation is a separate CIW execution
failure. The endpoint performs no file writes, receiver calls, clock reads,
network calls, or CIW identity allocation.

CIW must pin this repository revision and executable environment before
launching the process. RCI does not accept a caller-provided revision as proof
of the code actually executed. The maximum request is 8 MiB and the maximum
batch is 512 records.

Build a displacement request or two separate reservoir mass requests:

```bash
PYTHONPATH=src python examples/ciw_calibration.py > request.json
PYTHONPATH=src python -m instrument_chain.ciw_adapter < request.json
PYTHONPATH=src python examples/ciw_calibration.py --reservoirs > reservoir-requests.json
```

The second example emits an array of two requests; invoke the endpoint once
per request. Distinct assemblies and calibration profiles are essential: two
samples from one assembly must not be relabeled as two independent sensors.

## Request

```json
{
  "schema": "ciw.adapter-request.v1",
  "operation_id": "rci.calibrate.v1",
  "inputs": {
    "assembly_toml": "<exact complete rci-assembly-v1 declaration>",
    "calibration": {
      "schema": "rci-calibration-binding.v1",
      "calibration_id": "linear-v1",
      "assembly_id": "bench-displacement-01",
      "assembly_version": "1",
      "installation_id": "bench-stand-01",
      "assembly_digest": "<SHA-256 of exact UTF-8 assembly_toml bytes>",
      "valid_from": "2026-01-01T00:00:00Z",
      "valid_until": "2026-02-01T00:00:00Z",
      "parameter_order": ["scale", "zero_raw"],
      "parameter_covariance": [[1e-10, 1e-7], [1e-7, 0.04]],
      "residual_correlation": "independent",
      "raw_parameter_independent": true
    },
    "records": [{
      "raw_record_b64": "<base64 of exact native observation JSON bytes>",
      "observed_at": "2026-01-15T12:00:00Z"
    }],
    "raw_covariance": [[0.25]]
  }
}
```

Raw records are native `Observation.as_dict()` objects or native receiver log
rows with `digest` and optional delivery metadata. A receiver digest is
verified using RCI's existing canonical digest; delivery metadata remains
outside that payload digest. Independently, the new source evidence digest
covers **all exact imported bytes**, including whitespace and delivery
metadata. No source bytes are normalized, rewritten, or replaced.

Legacy device ticks have no UTC origin. Therefore `observed_at` is explicitly
**caller-declared acquisition context**, preserved with that meaning; it is
not inferred from ticks, the execution clock, or log arrival. Its source must
be supplied by the acquisition integration. It must carry an explicit UTC
offset. Calibration applies on the half-open interval
`valid_from <= observed_at < valid_until`. Historical offline replay checks
the acquisition instant, not the current wall clock.

The exact assembly digest binds the board, interface, instrument,
installation, calibration coefficients, ranges, and units, as well as their
declaration text. A changed declaration needs a new binding. This is a
declared applicability gate, not external authentication of a calibration
certificate. `traceability` remains `none_claimed`.

## Scientific computation and covariance

This release preserves both existing `linear` and `affine` behavior:

\[
y_i=s(r_i-z),\qquad J_{i,:}=[r_i-z,-s].
\]

The existing affine method is not reinterpreted as `s*r + offset`.
The parameter order is always `[scale, zero_raw]`, with units
`[output_unit/raw_unit, raw_unit]`. A full symmetric positive-semidefinite
2-by-2 covariance is mandatory. Raw covariance is an N-by-N matrix in record
order, in raw-unit squared; it may contain correlations. Boolean/nonfinite
values, asymmetric matrices, and indefinite covariances are refused.

The first-order propagation is:

\[
\Sigma_y=J\Sigma_\theta J^T+s^2\Sigma_r+\sigma_\mathrm{residual}^2 I.
\]

The result retains every matrix and contribution. Shared parameter
uncertainty creates off-diagonal covariance **across all records sharing the
profile**. The declared residual sigma and its original explanation are
retained separately. The endpoint requires explicit independence between raw
noise and parameter uncertainty, and independent residual noise. It refuses
other models rather than silently omitting their cross terms. Independence
between residual noise and the other two sources is part of the declared
independent residual model.

This is a first-order approximation for uncertain scale and zero, not an
exact distribution of their product. A profile's scalar sigma must represent
the additional independent residual component, excluding the separately
declared parameter/raw contributions; otherwise this decomposition would
double count uncertainty. The fixture's sigma is an explained synthetic
assumption. Existing placeholder uncertainty does not become a traceable
measurement through this adapter.

## Response, identities, and refusal

Success:

```json
{"schema":"ciw.adapter-response.v1","status":"ok","data":{
  "schema":"measurement-record-batch.v1",
  "records":["<measurement-record.v1 objects>"],
  "uncertainty":"<full covariance decomposition>",
  "uncertainty_digest":"<content digest>",
  "calibration":"<complete binding>",
  "calibration_digest":"<content digest>",
  "assembly_digest":"<exact declaration byte digest>",
  "assembly_toml":"<exact declaration>"
}}
```

Each record contains `raw_record_b64`, `source_evidence_digest`,
`derived_evidence_digest`, `observed_at`, `raw: {value,unit}`,
`calibrated: {value,unit}`, source quality, assembly identity,
`calibration_state: applicable`, and its covariance row index. Its derived
digest includes calibration and batch uncertainty digests. Changing a
calibration or covariance therefore changes derived evidence while leaving
source evidence unchanged. The source and derived identities cannot collapse.

The complete request is replay material. Identical replay returns identical
domain content; CIW must allocate a **new execution identity and result
identity** for each replay. RCI does not allocate either, certify physical
truth, or produce a disposition.

Refusal:

```json
{"schema":"ciw.adapter-response.v1","status":"refused","refusal":{
  "code":"calibration_unavailable",
  "reason_code":"calibration_expired",
  "message":"Calibration had expired at observation time"
}}
```

Missing, expired, not-yet-valid, mismatched, out-of-range, or unsupported
calibration/uncertainty states refuse the whole batch. Raw unavailable,
non-applicable source calibration, and mismatched native source digests also
refuse. Malformed requests use `invalid_request`. A refusal has no `data` and
must not create a CIW result row; CIW may persist its execution and refusal
record together with the original evidence.

## Reservoir slice

`--reservoirs` declares separate simulated mass instruments. Raw counts 7000
and 3000 calibrate to 70 kg and 30 kg. Their output variances are 0.005315
kg² and 0.001323 kg² respectively. A caller may construct a simultaneous
two-reservoir snapshot with diagonal joint covariance **only when it
explicitly declares the two calibration/source uncertainties independent**.
FSRT owns interpretation through a declared reservoir model; the adapter does
not turn generic displacement into fluid mass or invent a geometry/density
conversion. Longer time series must carry shared calibration covariance into
a compatible estimator; dropping it to fit an independent-sample model is
not supported.
