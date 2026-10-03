# Impact scenario example

This finite scenario grid varies incoming speed and yield force in the
[crush benchmark](../impact-crush/README.md). Each case retains its own Session,
solver execution, independent verification and typed preservation receipts.

```sh
net impact sweep example --output impact-sweep-request.json
net impact sweep run impact-sweep-request.json --output-dir impact-sweep-run
net impact sweep inspect impact-sweep-run
net impact sweep verify impact-sweep-run
```

The example evaluates six cases with mass 1 kg, stiffness 10,000 N/m, incoming
speeds 1, 2 and 3 m/s, and yield forces 80 and 100 N. Requirements are peak force
at most 150 N and permanent compression at most 0.045 m. All six cases qualify
numerically; five satisfy both requirements. The 3 m/s, 80 N case exceeds the
permanent-compression limit. Thus the example deliberately returns exit code 2,
with numerical status `LOCAL` and requirements status `FAIL`.

Requirement comparisons use the retained numerical scalar values. They do not
certify a safety margin after accounting for numerical or physical uncertainty.
`inspect` reopens every retained case and compares the aggregate without
numerical replay. `verify` independently rechecks retained observations without
rerunning the solvers. Both leave the bundle unchanged. Destinations must be
new; requests cannot supply arbitrary case paths or provider code.

Read the [scenario envelope contract](../../docs/IMPACT_SCENARIO_ENVELOPE.md)
for the 24-case bound, supported SI axes and criteria, failure retention, and
the distinction between this finite grid and probabilistic robustness.
