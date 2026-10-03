# FSRT usage notes

Public name: **FSRT** (Fluid State Reconciliation Testbed). Import: `set_lcm`.
This is measurement reconciliation against a declared balance, not visual
reconstruction of a fluid volume.

The full API and example walkthrough remains in [`USAGE.md`](USAGE.md).

## Clone size

A full clone is about 50 MB because `data/` holds NOAA/USGS replay fixtures and
`results/` holds generated reports. `examples/quickstart.py` does not read
`data/` and makes no network requests.

## Tests

```bash
# Unit / contract gate — no experiment regeneration
uv run --frozen --python 3.13 --dev pytest -q -o addopts= -m "not slow and not extended"

# Default suite — includes report/contract tests; excludes only -m slow
uv run --frozen --python 3.13 --dev pytest -q

# Slow — full simulation grid, calibration and sweeps
uv run --frozen --python 3.13 --dev pytest -q -m slow
```
