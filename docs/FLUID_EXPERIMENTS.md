# Held-out fluid observation comparisons

`net fluid experiment` compares explicitly declared observations against a
freshly qualified `LOCAL` reservoir model. It reports
`EMPIRICALLY_COMPATIBLE`, `INCOMPATIBLE`, or `INCONCLUSIVE` for the declared
observables, times, baseline, and uncertainty. None of these outcomes establishes
universal physical validation, authenticates a sensor or calibration certificate,
admits measured state, or actuates hardware.

The first observation operator supports the lumped two-reservoir piston model.
Wave, SPH, molecular, and partitioned FSI sensor operators require their own
qualified spatial and temporal mappings; they currently return `EXPAND`.

## Use

```sh
net fluid experiment template --profile reservoir --output template.json
net fluid experiment ingest --csv observations.csv --metadata metadata.json --output-dir measured
net fluid experiment compare --model-dir reservoir-run --measurement-dir measured --output-dir comparison
net fluid experiment inspect comparison
net fluid experiment verify comparison --output fresh-audit.json
```

The template contains `metadata` and `csv_header`. Save the edited `metadata`
object as `metadata.json`, rather than passing the entire template to ingestion.
Set `csv_sha256` to `sha256:` followed by the SHA256 of the exact UTF-8 CSV bytes,
and `target_request_digest` to the canonical retained model request digest.
The default template targets the default reservoir request. Input and output
paths are create-only; no existing bundle or receipt is overwritten.

CSV headers are exactly `sample_id,time_s,role` followed by the declared SI
channels. Every row has a unique sample ID, strictly increasing nonnegative
acquisition time, and `holdout` or `calibration` role. Only holdout rows contribute
to the comparison. Calibration rows require explicit calibration sample IDs.
No gains, baseline adjustments, unit conversions, or parameter fits are inferred.

| Declaration | Meaning |
| --- | --- |
| `source_kind: synthetic_fixture` | Pipeline exercise with no measured support, including when compatible |
| `source_kind: declared_measured` | Operator declaration; compatible support remains conditional on authenticity, calibration, split, uncertainty, and model assumptions |
| `coordinate_frame` | Exact reservoir vertical-head and outward-piston convention |
| `baseline` | Hydrostatic pressure deviations from the fixed preloaded equilibrium |
| `clock` | Unit-scale acquisition-to-model offset, Gaussian standard uncertainty, and explicit common-offset propagation |
| `split` | Separate calibration and parameter-fit dataset/sample/content references; fixed parameters and uncertainty declared before holdout |
| `uncertainty.axes` | Held-out row-major sample/channel order, such as `s0/head1_m` |

The supported direct fields are `head1_m`, `head2_m`,
`pressure1_deviation_pa`, `pressure2_deviation_pa`, `flow_m3_per_s`,
`connector_velocity_m_per_s`, `piston_displacement_m`, and
`piston_velocity_m_per_s`. These are lumped model quantities, not arbitrary local
sensor fields. At most 16 CSV rows and 2 channels give 32 stacked residual axes.
Each input file is bounded to 65,536 bytes; retained comparison workspaces are
bounded to 64 MiB. Readers reject symlinks, devices, pipes, duplicate JSON keys,
nonfinite values, incorrect hashes, and unsupported units or operators.

## Statistical meaning

The residual is observation minus the linearly interpolated finest retained
model state. Interpolation occurs only inside the model time grid. The declared
three-standard-uncertainty clock envelope must also lie inside that grid. A
Gaussian distribution has unbounded support, so this envelope is a declared
containment policy rather than a probability-one bound.

Four full stacked covariance matrices are required: measurement,
parameter-prediction, model-discrepancy, and numerical/interpolation uncertainty.
Each needs a rationale and content references. A `null` matrix declares unknown
uncertainty and yields `INCONCLUSIVE`; explicit zero matrices remain operator
claims and must have a rationale. The terms and clock error must be declared
mutually independent, jointly zero-mean Gaussian. Matrices preserve correlations
across channels and times, and entries have the products of their axis units.
Positive semidefiniteness is checked in dimensionless coordinates without
symmetrizing, clipping, or repairing covariance.

One clock-offset error is shared by the complete history. If `g` is the stacked
prediction slope and `sigma_t` its declared standard uncertainty, its linearized
contribution is `sigma_t**2 * outer(g,g)`. Off-diagonal entries are retained;
the clock error is not treated as independent jitter per sample.

For positive definite, sufficiently conditioned total covariance `C`, the
fixed-parameter statistic is `r.T @ inv(C) @ r`, evaluated without explicitly
forming an inverse. Its degrees of freedom equal the full residual dimension;
no parameters are estimated on holdout. The upper-tail probability is compared
to the declared significance level. Non-rejection is conditional compatibility,
not a probability that the model is true. Singular covariance, unknown terms,
or a decision within the numerical boundary tolerance yield `INCONCLUSIVE`.
The backend uses Cholesky whitening and NumPy interpolation; an independent
verifier uses bracket interpolation and eigen whitening and freshly rechecks the
retained model's `LOCAL` qualification.

This method follows the [NIST chi-square distribution definition](https://www.itl.nist.gov/div898/handbook/eda/section3/eda3666.htm)
after Gaussian whitening, and the covariance-aware
[NIST law of propagation of uncertainty](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-law-propagation-uncertainty).
The separation between numerical verification, uncertainty, and experimental
validation follows [NIST IR 8298](https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8298.pdf).
The Gaussian, fixed-parameter, covariance-known assumptions are explicit limits
of this implementation, not conclusions inferred from those references.

## Retention and authority

CSV and metadata bytes, hashes, acquisition clock, observations, and declarations
are retained in the existing `run.v1` evidence store. A computed model trajectory
is carried as an explicit foreign operation-result dependency, with its source,
execution/result identities, and fresh verification witness. The comparison is
`fluid.experiment.compare.v1`; independent verification is
`fluid.experiment.verify.v1`. Each has a distinct Session execution and result;
verification allocates a new verification occurrence identity.

These providers require an explicitly activated trusted registry. The default
registry refuses them, and loading an archive activates no providers. Static
`inspect` validates source bytes, seals, bindings, dependency identities, and
stored schema only. It does not rerun models, interpolation, covariance
factorization, or hypothesis tests. `verify` performs a new independent operation
and returns a retained audit witness while leaving the original bundle unchanged.
Seals establish content consistency; fresh numerical verification is still
required to detect coherent resealed numerical tampering.

The included example is explicitly synthetic. No measured dataset was supplied
or acquired as part of this feature, and it establishes no experimental support.
