# Retained observations and whole-study replay

This increment connects the existing thermal observer to NET's observation,
comparison and inspection contracts. It also exposes the existing CSR whole-study
replay through `net science replay-study`. There is no new filter, simulation,
state owner, graph scheduler, mandatory dependency or private-provider download.

## Run the executable thermal example

From this branch's checkout, install the candidate package, then run:

```sh
python -m pip install -e '.[dev]'
python scripts/run_thermal_observation_demo.py \
  --source examples/thermal-observations/source.json \
  --output-dir results/thermal-observations-001

net inspect results/thermal-observations-001/posterior.json
net compare results/thermal-observations-001/posterior.json \
  results/thermal-observations-001/replayed-posterior.json --atol 0
net compare results/thermal-observations-001/posterior.json \
  results/thermal-observations-001/measurement.json --atol 1
```

The source is a **declared synthetic two-capacity thermal case** with one missing
shell-thermometer sample. The existing Python thermal reference performs inference;
this is not a new Julia execution, physical measurement or material validation.
The script retains original/replayed workspaces, predicted/posterior/measurement
views, three comparison records and `demo-report.json` in a new directory.

The replay comparison must PASS at zero tolerance for the demonstrated same-runtime
case, with fresh native execution/result IDs. The measurement comparison is
INDETERMINATE because one component is missing. Posterior versus prediction at
zero tolerance is FAIL for this example because conditioning changes the estimate;
that is an expected difference, not a claim that the estimator failed. CLI exit
codes remain 0 PASS, 2 FAIL, 3 INDETERMINATE and 1 malformed/refused.

## Export one exact native observation view

```sh
net science observations \
  --workspace results/thermal-observations-001/original/workspace.json \
  --workspace-sha256 '<sha256:... recorded for that exact workspace>' \
  --bundle '<exact thermal-observer bundle_id>' \
  --stage posterior \
  --entity 'assembly-A/core-shell' \
  --output results/posterior-view.json
```

Use the matching checksum and bundle identity printed by the demo or recorded by
your existing workflow. The exporter compares the expected SHA256 against the
same bounded bytes it reads before reopening them with the existing Session reader.
The source workspace is never overwritten. The output is create-only. A checksum
selected from the file itself demonstrates content binding, not independently
trusted provenance or a producer signature.

Supported stages are `predicted`, `posterior`, and `measurement`. Exact bundle
selection is mandatory; there is no newest-result fallback. This first producer
adapter accepts only the existing `thermal-observer` workflow. It does not claim
to handle generic Julia workers, FSRT, arbitrary sensors or engine scenes.

## What the view retains

`ciw.thermal-observation-view.v1` contains the original native step, its input and
result identities, source/workspace/bundle bindings, coordinate order, stage,
per-row missingness context, and a standard `ciw.observation-stream.v1`.
Every observation carries an existing model identity, caller-declared entity,
source-scoped clock, kelvin unit, ordered two-component value and provenance.

Coordinates are `[core_temperature, shell_temperature]`; covariance axes are
`[temperature[0], temperature[1]]`. The frame labels that ordered thermal state
space, not a spatial world/body coordinate frame. Time comes from the original
predict-then-correct cadence: sample `i` is at `(i+1)*sample_interval_s`. The first
observation is at dt, not zero. Clock identity is bound to the exact source evidence,
so different datasets are not silently aligned simply because both use seconds.

Predicted and posterior means retain the original estimator execution identity
and `estimated` semantics. Measurement values come from the original input request,
not the estimator's output: they have `simulated` semantics and a null execution
identity rather than falsely attributing acquisition to the estimator occurrence.
Their containing view still references the selected native result as context.

Complete samples wrap the **unchanged full native covariance matrix** in the
existing covariance artifact, including its off-diagonal entries and original
reference values. This wrapper receives a new content identity for its representation;
it is not a new numerical propagation or measurement. Native matrices remain in
the retained step for exact comparison. No cross-tick covariance or empirical
calibration/coverage is inferred.

For a partially or wholly missing measurement row, values stay null. The full
declared observation-noise matrix remains in the native request, but is not attached
to an invented complete reference vector. Row context explicitly marks that
covariance as unattached due to missing values. Nothing is zero-filled or imputed.

The new view excludes the source's `evaluation`, generator states and held-out
reference truth. These remain in the original synthetic workspace; the exporter
does not give them to the estimator or mix them into observations. The original
native inference request/result validator remains responsible for numerical checks.

## Inspect, compare, and recheck against the original workspace

`net inspect VIEW` checks the original native input/result bindings and reconstructs
the exact projection. It performs the existing bounded numerical validation but
launches no provider lifecycle, creates no execution/verification occurrence, and
makes no physical-acceptance or admission decision. Rehashing an altered value,
covariance, unit, time, axis order or diagnostic context does not make a contradictory
projection valid.

The view's hashes cannot authenticate a maliciously replaced entire source history.
Use the original independently selected workspace to check its retained bindings:

```python
from pathlib import Path
from ciw.control_contracts import load
from ciw.scientific_observations import match_workspace

view = load(Path('results/thermal-observations-001/posterior.json'))
match_workspace(view, Path('results/thermal-observations-001/original/workspace.json'))
```

`net compare` accepts either original observation streams or these validated native
views. It retains the selected observations with their covariance and provenance
references in the existing comparison record. Keep the native view/workspace
alongside it when full request context is needed. No observation-stream or
comparison schema is silently reinterpreted. Differences in unit/frame/model/entity,
clock, timestamp, completeness or shape remain INDETERMINATE where applicable.
Deterministic error comparisons do not infer independence or uncertainty of a
difference from marginal covariance alone.

The Python `select_observations(session, ...)` function is also available. Its
`workspace_sha256` is explicitly a caller-supplied declaration. Use
`export_observations(path, expected_sha256=..., ...)` for exact-byte file binding.
Neither path imports code named by saved data.

## Replay a complete existing CSR heading study

```sh
net science replay-study \
  --workspace results/heading-study-001/workspace.json \
  --study results/heading-study-001/study.json \
  --binding csg=/absolute/path/to/approved-CSR-checkout \
  --output-dir results/heading-study-replayed-001 --json

net science inspect \
  --workspace results/heading-study-replayed-001/workspace.json \
  --study results/heading-study-replayed-001/study.json --json
```

The command validates the original retained study before binding, then delegates
unchanged to `curved_path_study.replay_study`. It replays the baseline and every
candidate through their existing native paths. The new study retains `replay_of`
and fresh native bundle/execution/result/verification occurrences with the original
source, runtime pins and numerical comparisons. The original study/workspace remain
unchanged. This is fresh reproduction, not checkpoint continuation or physical
validation. Failure retains completed original native history and does not publish
a completed study. Existing arclength, validity and conditional-covariance scope
remain unchanged.

## Qualification scope

The new observation tests use the actual existing Python thermal workflow on
synthetic inputs, not a mocked estimator. They include complete/single-missing/
both-missing observations, original matrices, source checksum mismatch, rehashed
contradictions, excluded reference truth, fresh replay, offline inspection and
create-only output. The focused workflow adds an installed-package run of the
committed example and expands its genuine CSR campaign to whole-study replay.
No previous qualification case is removed or changed to pass via a fallback.

A diagnostic watchdog records Python stacks and exits nonzero when the combined
contract suite stalls; it is not a successful timeout or a skipped gate. The
previous Windows job was cancelled with no retrievable log. Its cause is not
inferred from cancellation alone. Current observed CI outcomes are recorded in
PR #51 separately from local test results.
