# Check retained scientific evidence

`net check` applies a small, explicit policy to retained observations, covariance
or comparisons. It reuses the existing `verify` and `overall` numerical checks.
It does not run a provider, become another experiment scheduler, evaluate Python
expressions, or allocate execution/verification occurrence identities.

## Run the example

Install this candidate NET revision and use new output directories:

```sh
python -m pip install -e '.[dev]'
python scripts/run_thermal_observation_demo.py \
  --source examples/thermal-observations/source.json \
  --output-dir results/thermal-observations-002
python scripts/run_thermal_check_demo.py \
  --evidence-dir results/thermal-observations-002 \
  --output-dir results/thermal-checks-002
net inspect results/thermal-checks-002/accepted-report.json
```

The first command script runs the existing Python thermal reference and fresh
replay on synthetic inputs. The second checks its retained outputs, including:

- **PASS:** all posterior temperatures lie inside declared 250..350 K bounds,
  every posterior covariance marginal clears the declared numerical PD margin,
  and the retained fresh-replay comparison passes.
- **INDETERMINATE:** the supplied measurement series contains a missing component.
- **FAIL:** prediction and posterior are not equal at zero tolerance. This is an
  expected consequence of conditioning, not an estimator fault.

The bounds and covariance margin in this example are demonstration policies, not
physical acceptance requirements. A source hash calculated from the same file is
a content-binding check, not independent evidence of provenance or authenticity.

Each scenario retains a plan and report. All three outcomes are expected; the
demo script fails if its expected outcomes are not obtained. None means a machine
command has been authorized, ESM has admitted state, or a physical model is valid.

## Write and run a plan

A `ciw.check-plan.v1` has `suite_id`, `inputs` and `checks`. Each input alias declares
an exact UTF-8 file SHA256 and supported schema. A check declares `name`, `kind`,
`input` and `policy`. Names must be unique; inputs must be declared and used.
No imports, expressions, executable paths, optional-check flag or fallback code
are accepted. Paths are supplied separately by the operator, not by the plan.

This complete example binds an existing posterior view:

```python
from pathlib import Path
from ciw.check_suite import plan
from ciw.control_contracts import bytes_ref, save_new

source = Path('results/thermal-observations-002/posterior.json')
policy = plan('declared-temperature-window', inputs={
    'posterior': {
        'schema': 'ciw.thermal-observation-view.v1',
        'sha256': bytes_ref(source.read_bytes()),
    }
}, checks=[{
    'name': 'Every retained temperature lies inside declared bounds',
    'kind': 'bounded', 'input': 'posterior',
    'policy': {'minimum': 250.0, 'maximum': 350.0, 'unit': 'K'},
}])
save_new(Path('results/temperature-check-plan.json'), policy)
```

```sh
net check --plan results/temperature-check-plan.json \
  --input posterior=results/thermal-observations-002/posterior.json \
  --output results/temperature-check-report.json
net inspect results/temperature-check-report.json --json
```

`python -m ciw.net check` and `python -m ciw.check_suite` are equivalent interfaces.
An existing report is never overwritten. Source input files are never modified.
The plan and each supplied input are read once, bounded, and detached before use.

## Policies and evidence

| Kind | Accepted evidence | Policy |
| --- | --- | --- |
| `bounded` | Original observation stream or retained thermal observation view | `minimum`, `maximum`, `unit` |
| `less_than` | Same | `limit`, `unit` |
| `conserved` | Same; at least two samples | `tolerance`, `unit` |
| `close_to` | Existing `ciw.comparison.v1` | Empty object; the comparison retains its own tolerances |
| `covariance_positive_definite` | Covariance artifact, typed state, stream or thermal view | Ordered `quantity_ids`, `units`, `frame`, positive `margin` |

For covariance on a series, **every sample is checked**, including a missing
covariance as INDETERMINATE. Complete native matrices remain intact; no diagonal
substitution, clipping or invented correlations. Positive-definiteness follows
the existing normalized-eigenvalue policy, not a claim of calibrated uncertainty
or statistical coverage. A singular artifact accepted by the general PSD reader
may fail this stricter requested PD condition.

Other checks cover the complete selected series. There is no hidden truncation,
subsampling, interpolation, unit conversion or cross-clock alignment. Use the
existing explicitly scoped comparison operation to construct comparison evidence.
A report cannot be used as another report's input: recursive check execution is
outside this bounded interface.

Omitting an input binding explicitly records `null` and keeps all its requested
checks INDETERMINATE. A supplied unreadable file, wrong hash, wrong schema,
inconsistent native record, or malformed policy is a refusal, not missing data.
FAIL dominates INDETERMINATE in aggregation, but missing inputs and all individual
results remain visible. No empty plan or empty check set is accepted.

Exit codes: 0 PASS; 2 FAIL; 3 INDETERMINATE; 1 malformed/refused. A FAIL or
INDETERMINATE report is retained; a malformed report is not published.

## Offline report verification

`ciw.check-report.v1` retains the complete declared plan, its content identity,
each supplied input's exact UTF-8 bytes/hash, every original assertion record,
per-sample covariance indices and aggregate outcome. `net inspect` reconstructs
the checks from that evidence without launching a provider or needing the original
files. Rehashing a report with deleted checks, changed policy, altered evidence,
forged PASS, or expanded authority does not satisfy that reconstruction.

This detects internal contradictions, not replacement of an entire history by
an adversary who can rewrite all declarations. Check `plan_id` and input hashes
against independently selected trusted records when that threat matters. The
report has no producer signature and does not authorize admission or release.

Limits: 1..8 inputs, at most 64 KiB per input or plan, 1..32 checks, at most 256
expanded assertions, and the existing 8 MiB output limit. Larger workloads must
be explicitly partitioned; nothing is silently skipped to fit a budget.

## Validation and qualification

`tests/test_check_suite.py` covers complete/missing/corrupt evidence, per-sample
covariance, exact-byte binding, three-valued results, reporting integrity, CLI
exit codes, output non-overwrite and a genuine existing Python thermal/replay
path. Fixtures and thermal data are synthetic; no new native-engine or physical
qualification is implied by them.

The focused scientific workflow retains all earlier tests and the 11-case genuine
CSR campaign, and adds these checks plus an installed-wheel check demo. The
oversized-source rejection test now has a compact explicit test ID; its original
2 MiB input and assertions are unchanged. This fixes a reproducible multi-megabyte
node-name/reporting problem; previous CI cancellations are not attributed to that
problem without runner evidence. No numerical tolerances or required cases were
weakened or skipped.
