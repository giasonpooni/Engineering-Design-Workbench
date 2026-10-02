# Bounded impact scenario envelope

`net impact sweep` evaluates an explicit Cartesian grid of scalar contact
scenarios on the original impact Session workflow. It supports the elastic
spring profile and the unilateral elastic-perfectly-plastic crush profile.
Each case retains its own source evidence, solver execution, independent
verification occurrence, and preservation contract. The existing numerical
providers remain responsible for their respective physical models.

```sh
net impact sweep example --output impact-scenarios.json
net impact sweep run impact-scenarios.json --output-dir impact-scenarios
net impact sweep inspect impact-scenarios
net impact sweep verify impact-scenarios
```

The default manifest evaluates six combinations: initial speeds 1, 2 and 3 m/s
with effective yield forces 80 and 100 N, at mass 1 kg and spring stiffness
10,000 N/m. Its requirements are peak force at most 150 N and residual plastic
compression at most 0.045 m. The 3 m/s, 80 N case exceeds the residual compression
requirement while retaining numerical qualification: five cases pass and one
fails. It demonstrates a
declared design-condition failure within a qualified synthetic model.

## Manifest contract

The strict `ciw.impact-sweep-request.v1` manifest has exactly `schema`,
`base_request`, `axes`, and `requirements`. The base request uses one of the
existing supported contact request schemas. Every generated request passes
that profile's full validator before any output directory is created. An
invalid combination rejects the entire manifest; parameters are never clamped.

| Field | Accepted values |
| --- | --- |
| Axis names | `mass_kg`, `stiffness_n_per_m`, `initial_speed_m_per_s`; `yield_force_n` for crush only |
| Dimensions | 1–3 |
| Values per dimension | 1–6 unique finite numbers |
| Grid size | At most 24 cases |
| Requirements | 1–4 rows with exactly `quantity`, `unit`, `operator`, `limit` |
| Operators | Literal `<=` or `>=` |

| Requirement quantity | Exact unit | Contact profiles |
| --- | --- | --- |
| `peak_force_n` | `N` | Elastic and crush |
| `restitution` | `1` | Elastic and crush |
| `residual_compression_m` | `m` | Crush |
| `plastic_work_j` | `J` | Crush |

Axes use the existing `ParameterSpace`, `Choice`, and bounded `grid` machinery.
Dimension names are sorted, and values retain their explicitly declared order.
The resulting case sequence is deterministic across JSON object key ordering.
These are discrete scenarios without probability weights or statistical
coverage; results apply to the enumerated conditions and declared model only.

## Two independent verdicts

The summary's `status` retains the numerical scope action: `LOCAL`, `EXPAND`, or
`REFUSE`. Its `requirements_status` is `PASS`, `FAIL`, or `UNRESOLVED`.
Requirement measurements use the independently audited primary-trace metrics.
Comparisons use numerical point estimates and literal declared thresholds;
they do not supply certified error bounds or a certified design safety margin.
Only a `LOCAL` case receives a resolved design comparison. `EXPAND` and `REFUSE`
cases retain null requirement values with `UNRESOLVED` verdicts, including
refused solver or verifier attempts. A known requirement violation makes the
aggregate requirements verdict `FAIL`; otherwise any unresolved case makes it
`UNRESOLVED`. Passing requires every case and requirement to pass.

A requirement verdict does not establish physical failure, experimental
validation, a confidence bound, or failure probability. Effective spring
stiffness and yield force are scalar model parameters. Geometry, polymer
identification, rate response, thermal response, fracture, hardness, molecular
mechanisms, and continuum plate response require additional qualified models
or evidence through the existing scope gate.

The CLI returns 0 for a qualified all-pass envelope, 2 for numerical scope
expansion/refusal or failed/unresolved requirements, and 1 for rejected input
or invalid retained artifacts.

## Retention and verification

Output contains create-only `manifest.json`, sealed `summary.json`, and fixed
`case-000` through `case-NNN` directories. The aggregate binds the canonical
manifest, exact manifest bytes, each generated request, and exact retained
request/workspace/verification/preservation file bytes. Provider refusals retain
their available request and workspace files with refused execution records.
No case is retried or reused, and existing destinations are never overwritten.

`inspect` reopens every fixed case through `impact_workflow.inspect`, checks its
request against its generated coordinate, and rebuilds the whole comparison.
It executes no solver or numerical verifier. Missing cases, changed file bytes,
relabelled verdicts, altered coordinates, and resealed aggregate modifications
are rejected. Case paths are derived from trusted integer indices rather than
saved path strings.
Retained case workspaces have a separate 64 MiB file budget to accommodate the
declared integration limits; other documents retain the 8 MiB budget. File
sizes and symlinks are checked before opening the retained Session.

`verify` additionally invokes the existing independent retained-sample verifier
for every case. It compares the recomputed aggregate with the retained summary
without executing a solver, creating new operation occurrences, or modifying
the retained bundle. Seals identify content; they do not authenticate who
produced it. Evidence, operation, execution, verification, and admission
identities remain separate, and no state admission or actuation is performed.
