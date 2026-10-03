# Using FSRT

FSRT (Fluid State Reconciliation Testbed) is a Python library and a collection of
reproducible experiments. The importable package is `set_lcm`. This is measurement
reconciliation against a declared balance, not visual reconstruction of a fluid volume.

Start with the small example, then choose whether you need to check raw fluid measurements, reconcile an existing
estimate or replay a sequence of measurements through an estimator.

Clone size, test tiers, and naming: [`USAGE_NOTES.md`](USAGE_NOTES.md).

## Install and run the example

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), clone the repository,
and run the following from its root:

```bash
uv run --frozen --python 3.13 python examples/quickstart.py
```

`uv` creates an isolated environment using the committed lockfile. Python 3.12 is also
supported. Running the example itself does not fetch data and does not read `data/`.
A full clone is about 50 MB because `data/` holds NOAA/USGS replay fixtures and
`results/` holds generated reports.

The example prints:

```text
Small disagreement
  Score: 1.78; reference threshold: 10.83
  Action: ok
  Original estimate: [52.0, 46.0] kg
  Output estimate: [52.889, 46.889] kg
  Residual before: -2.000 kg
  Residual after: -0.222 kg

Large disagreement
  Score: 44.44; reference threshold: 10.83
  Action: model_inconsistent
  Original estimate: [60.0, 50.0] kg
  Output estimate: [60.0, 50.0] kg
  Residual before: 10.000 kg
  Correction held: investigate the measurements and model.
```

The remaining residual in the first case is intentional: the total itself has uncertainty.
`ok` means that the requested reconciliation was applied; it does not certify the model or
the measurements. The second case illustrates a policy that holds reconciliation when the
unprojected estimate exceeds the reference threshold.

## Tests

```bash
uv run --frozen --python 3.13 --dev pytest -q -o addopts= -m "not slow and not extended"
uv run --frozen --python 3.13 --dev pytest -q
uv run --frozen --python 3.13 --dev pytest -q -m slow
```

## Full API guide

The camera, recording, reconcile, replay, declaration, and report-regeneration
sections last lived in full at commit `390b12d`:

https://github.com/giasonpooni/Fluid-State-Reconstruction-Testbed/blob/390b12d13fcc81f5c0dd20d3a4dc1d47b8e8c714/docs/USAGE.md

Restore them onto `main` with:

```bash
git checkout 390b12d -- docs/USAGE.md
```

then keep the naming / clone-size / three-tier paragraphs from this file.
