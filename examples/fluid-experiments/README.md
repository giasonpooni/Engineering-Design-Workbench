# Synthetic observation fixture

These values are declared synthetic observations for exercising ingestion and
comparison. They are not measurements and establish no experimental support.
Run the default reservoir request, then use:

```sh
net fluid experiment ingest --csv examples/fluid-experiments/synthetic-observations.csv --metadata examples/fluid-experiments/synthetic-metadata.json --output-dir observations
net fluid experiment compare --model-dir reservoir-run --measurement-dir observations --output-dir comparison
net fluid experiment verify comparison --output fresh-audit.json
```

The example uncertainty, calibration references, and clock are synthetic operator
declarations. Edit a generated template for an actual held-out dataset; retain
its exact SI units, baseline, split, covariance, content hashes, and provenance.
See [the experiment contract](../../docs/FLUID_EXPERIMENTS.md).
