# Calibration covariance basis, v2

`rci.calibrate.v2` adds explicit covariance provenance and acquisition-time
applicability to the existing offline subprocess. It uses the unchanged v1
numerical calculation after validating and projecting its binding. The v1
operation, response schema, numerical behavior, and native digests remain
available unchanged; a regression test pins the complete v1 stdout bytes.

```bash
PYTHONPATH=src python examples/ciw_calibration_v2.py > reservoir-requests-v2.json
PYTHONPATH=src python examples/ciw_calibration_v2.py --common-reference > common-reference-requests-v2.json
```

These commands produce two-request arrays for synthetic examples. Invoke each
request separately with `python -m instrument_chain.ciw_adapter`, as described
in [v1](ciw-adapter-v1.md). Neither example establishes a physical calibration
or traceability. The generator explicitly declares new synthetic uncertainty
assumptions; it is not a general migration from old calibration profiles.

## Versioned contract

The transport envelope remains `ciw.adapter-request.v1` /
`ciw.adapter-response.v1`. The operation is `rci.calibrate.v2`. A successful
response contains `measurement-record-batch.v2` and `measurement-record.v2`
records. The input is the v1 input with these binding additions:

```json
{
  "schema": "rci-calibration-binding.v2",
  "covariance_basis": {
    "schema": "rci-covariance-basis.v1",
    "parameter_components": [
      {
        "component_id": "fit",
        "kind": "fitting",
        "status": "included",
        "covariance": [[0.0, 0.0], [0.0, 0.02]],
        "represented_by": null,
        "reason": "Synthetic fit-only zero-parameter contribution",
        "evidence_ids": ["synthetic-fixture:assembly-A:covariance-basis-v2"],
        "dependency_ids": ["synthetic-fit:assembly-A"],
        "shared_source_ids": []
      },
      {
        "component_id": "reference",
        "kind": "reference_standard",
        "status": "included",
        "covariance": [[1e-10, 1e-7], [1e-7, 0.02]],
        "represented_by": null,
        "reason": "Synthetic reference contribution expressed in native parameter coordinates",
        "evidence_ids": ["synthetic-fixture:assembly-A:covariance-basis-v2"],
        "dependency_ids": ["synthetic-reference:standard-A"],
        "shared_source_ids": ["synthetic-reference:standard-A"]
      },
      {
        "component_id": "other-systematics",
        "kind": "shared_systematic",
        "status": "excluded",
        "covariance": null,
        "represented_by": null,
        "reason": "Additional environmental effects are outside this synthetic fixture's scope",
        "evidence_ids": ["synthetic-fixture:assembly-A:covariance-basis-v2"],
        "dependency_ids": [],
        "shared_source_ids": []
      }
    ],
    "raw": {
      "reason": "Synthetic acquisition-noise covariance, in record order",
      "evidence_ids": ["synthetic-fixture:assembly-A:covariance-basis-v2"],
      "dependency_ids": ["synthetic-acquisition:assembly-A"],
      "shared_source_ids": []
    },
    "residual": {
      "scope": "additional_independent_output_residual",
      "reason": "Synthetic residual excluding all separately included parameter, reference and raw terms",
      "evidence_ids": ["synthetic-fixture:assembly-A:covariance-basis-v2"],
      "dependency_ids": ["synthetic-residual:assembly-A"],
      "shared_source_ids": []
    },
    "independence": {
      "parameter_components": true,
      "raw_parameter": true,
      "residual_other": true,
      "reason": "Independent latent variables are declared by the synthetic generative construction",
      "evidence_ids": ["synthetic-fixture:assembly-A:covariance-basis-v2"]
    }
  }
}
```

The excerpt omits the unchanged required binding fields: calibration and
assembly IDs/version/digest, installation, validity interval, parameter order
and total covariance, `residual_correlation`, and
`raw_parameter_independent`. The generated fixture provides a complete request.

Every component must have an explicit status, reason, nonempty evidence-ID
array, and explicit dependency/shared-source arrays. The three component
kinds must each be covered; multiple components of the same kind are allowed.
Included components require at least one dependency or shared-source ID.

Identifiers are caller-supplied domain provenance references. Their existence,
authenticity, and independence evidence are not verified by this endpoint.
They are not automatically SHA-256 content commitments, certificates, or
proofs. Digests of the enclosing binding and basis commit to the declarations.
`traceability` stays `none_claimed`, and covariance coverage never claims a
verified complete uncertainty budget.

## Inclusion, representation, and exclusion

Included component matrices are 2-by-2 positive-semidefinite covariances in
the native `[scale, zero_raw]` parameter coordinates. Their sum must equal
`parameter_covariance` within floating-point tolerance in the parameter
scales. A covariance in gain/intercept coordinates needs its actual coordinate
transformation before it is supplied here; relabeling the axes is invalid.

If a fitted covariance **already includes reference-standard uncertainty**,
put its total matrix in the included fitting component. Mark the reference
component `status: excluded`, `covariance: null`, `represented_by: "fit"`.
Its dependency/shared-source IDs must be present in that included component.
This means excluded from separate addition, not omitted from the budget.
References may point only to directly included parameter components; chains,
cycles, unknown components, and unsupported residual-reference models refuse.

An excluded component with `represented_by: null` is an explicitly recorded
scope limitation. Its reason does not establish that the effect is physically
absent or zero. Such components appear in
`uncertainty.covariance_coverage.excluded_component_ids`. Consumers must retain
that limitation: the reported covariance is conditional on the included
declared effects, not a demonstrated complete physical uncertainty budget.
An excluded source already named by an included component must identify its
representation rather than make a contradictory exclusion claim.

Independent addition is supported only when the explicit independence
declaration is true and justified by its reason/evidence. Overlapping
dependency/shared-source IDs across included parameter components, raw noise,
or residual noise refuse because the required joint dependence model is not
implemented. Different IDs do **not** establish independence. Evidence IDs
may refer to the same document without implying that its distinct latent
sources are identical.

The residual `scope` must be `additional_independent_output_residual`.
Using a total uncertainty sigma there would double count the parameter/raw
terms. The inherited `residual_correlation: independent` also requires
independence across records; systematic uncertainty is not converted into
independent per-record residual noise.

## Preserved science and full covariance

The native model and derivatives are unchanged:

\[
y_i=s(r_i-z),\qquad J_{i,:}=[r_i-z,-s],\qquad
\Sigma_y=J\Sigma_\theta J^T+s^2\Sigma_r+\sigma_\epsilon^2I.
\]

Both legacy `linear` and `affine` methods retain this same existing behavior.
The response explicitly records `parameterization: {name: scale_zero_raw,
order: [scale, zero_raw], values: [...], units: [...]}`. The complete raw,
parameter, contribution, residual, and output covariance matrices remain in
the response; no off-diagonal is discarded.

For repeated equal readings and only shared zero uncertainty, the variance
of the mean is

\[
\operatorname{Var}(\bar y)=s^2\operatorname{Var}(z)
+\frac{s^2\sigma_r^2+\sigma_\epsilon^2}{n}.
\]

The shared term does not shrink with sample count. A difference cancels that
common zero term, while gain uncertainty remains proportional to
`(r_j-r_i)^2 Var(s)`. Tests check these identities, operating-point changes,
cross-record covariance, and the independent noise that remains after
cancellation. Sharing a latent parameter does not imply that the complete
observation correlation is one.

Across assemblies, `uncertainty.dependency_ids` and `shared_source_ids` expose
the identities needed to detect a common reference even when assembly and
calibration IDs differ. This endpoint handles one assembly per request and
does not invent cross-assembly covariance. A consumer must use an explicit
joint model or refuse unsupported dependence. The `--common-reference`
fixture exercises that boundary.

## Commitments and time semantics

v2 commits the full covariance basis into the calibration digest, uncertainty
digest, and each derived evidence digest. Changing only a reason, evidence
reference, or covariance allocation changes derived evidence. Raw bytes and
their SHA-256 source commitments remain untouched. CIW continues to own
execution/result identities; replay emits deterministic domain content.

Each successful record stores:

```json
"acquisition_applicability": {
  "observed_at": "2026-01-15T12:00:00Z",
  "applicable": true,
  "valid_from": "2026-01-01T00:00:00Z",
  "valid_until": "2026-02-01T00:00:00Z",
  "basis": "caller_declared_acquisition_time"
}
```

This immutable statement uses the inherited half-open acquisition validity
interval. No execution clock or current serving status enters it. CIW may
separately evaluate current profile expiry and availability; doing so must
not alter historical evidence or applicability. v1 results do not acquire a
retroactively fabricated v2 acquisition statement.

All refusal responses omit `data`. Missing/ambiguous basis, mismatched
component sums, double counting, and unsupported dependence fail closed;
no partial batch result is returned. Malformed shapes remain
`invalid_request`. Basis-specific domain refusals use
`calibration_unavailable` with a detailed `reason_code`.
