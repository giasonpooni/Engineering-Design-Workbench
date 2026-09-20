# JSPT pin

Covariance transport is provided by the pinned JSPT adapter. FSRT retains its fluid
state, observation and declaration types.

Pinned SHA: `c0a01c1a27f10b099ac200c7e83b0f03187ee4d2`

Live call site: `set_lcm.bridge.jspt.map_covariance` → `sensitivity.push_covariance`.
`AffineCoordinates._map_covariance` must use that function (no local `T @ P @ T.T`).
See `tests/test_jspt_chart.py`.

Default CI stays numpy-only so a JSPT axiom change cannot silently rewrite reports.
Install the extra to compare.

```bash
uv run --locked --python 3.12 --dev --extra jspt pytest -q tests/test_jspt_chart.py
```

The optional dependency is recorded in `uv.lock`. After changing the declared
pin, regenerate the lock with `uv lock` and run the bridge tests. CI checks that
the lock matches project metadata before running the NumPy-only default suite.

Keep `GaussianState`, masks, Joseph, and declaration here.
