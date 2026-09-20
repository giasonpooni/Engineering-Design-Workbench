# Retrofitted Computational Instrumentation

Preserve the useful physical instrument. Modernize acquisition. Make the
whole measurement chain serviceable and reconstructible.

This repository is the first host increment of that contract. It is not a
universal device platform and it is not a flashing image.

The first assembly happens to be a bench displacement stand. The contract
is for manufacturing, infrastructure, agri-food, and logistics instruments:
one declared chain from raw counts to a qualified record. BIM is a consumer
of those records, not the owner of the sample.

## First increment

One declared assembly:

- board: LILYGO T-Display-S3 (profile only; GPIO15 is power enable)
- interface: simulated bridge counts (electrical compatibility is not inferred)
- instrument: displacement indication on a hand-operated stand
- installation: bench fixture
- calibration: `y = 0.01 * (raw - 0)` mm, declared, cited as prototype

The laptop produces a replayable JSONL log. Inference is `not_run`.
A retry does not create a second observation. A disconnect does not become zero.

An additive [CIW subprocess adapter](docs/ciw-adapter-v1.md) now transports
immutable raw evidence, explicitly bound calibration, and full first-order
covariance to the workbench. RCI retains domain ownership; CIW retains
execution and result identities. Missing, expired-at-acquisition, or
mismatched calibration yields a refusal with no result.

The additive [v2 covariance-basis contract](docs/ciw-adapter-v2.md) declares
fitting, reference-standard, and shared-systematic inclusion, prevents
unsupported independent addition, and commits immutable acquisition-time
applicability. Existing v1 requests and output bytes remain supported.

```
Physical sensor or mechanism
        |
        v
Acquired raw signal
        |
        v
Declared conversion y = g(r; theta)
        |
        v
Qualified measurement (four status dimensions)
        |
        v
Laptop log / later observer
```

## Run

Use Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). From a fresh checkout:

```bash
git clone https://github.com/giasonpooni/Retrofitted-Computational-Instrumentation.git
cd Retrofitted-Computational-Instrumentation
uv run --python 3.12 --dev python -m pytest
uv run --python 3.12 python examples/displacement_bench.py
```

Alternatively, in an activated Python 3.12-or-newer virtual environment, run
`python -m pip install -e . pytest`, then `python -m pytest` and
`python examples/displacement_bench.py`. The example writes
`results/displacement_bench.jsonl` and `results/displacement_commitments.jsonl`.
All observations in these files are simulated.

Pinned host-stand-in digests live in
[`validation/rci-displacement-digests-v1.json`](validation/rci-displacement-digests-v1.json).
They test the record format. They are not field millimetres.

## Bind a record in the CSE harness

This repo never proves. CSE never treats a millimetre as `YieldStrengthMPa`,
a lot code, or a cold-store temperature. After you have an
`rci-evidence-commitment-v1` JSON object, run the following **from an installed
CSE checkout** (the `gat` CLI and disposition fixture belong to that repository):

```bash
python -m gat.demo.experiment_harness \
  --disposition validation/beam-b1-disposition-v1.json \
  --commit path/to/rci-evidence-commitment.json \
  -o out/harness-bundle.json
```

The harness stores the digest on a project space. Quality flags stay on
the observation. JSPT is not imported here. Firmware remains C (ESP-IDF)
when it exists.

## What this release does not claim

- That the simulated counts are an LVDT or load cell.
- That a camera reading of a dial is process pressure.
- That the conversion is traceable.
- That firmware on the S3 is implemented. See `firmware/CONTRACT.md`.
- That a bound digest is a beam observation or a food-safety record.

Language ownership is in `docs/KERNEL.md`. Python owns this contract.
C owns the future acquisition runtime. Julia does not sit above either.
JSPT owns A2-A5 and is not imported here.

## Portfolio

Notation Systems. Companion mathematical tools stay in their own repos
and consume records from this contract; they do not own the sample.

- [CSE domain map](https://github.com/giasonpooni/Construction-State-Estimator-for-BIM/blob/main/docs/domain-v1.md)
- [CSE experiment harness](https://github.com/giasonpooni/Construction-State-Estimator-for-BIM/blob/main/docs/experiment-harness-v1.md)
- [JSPT](https://github.com/giasonpooni/Jacobian-Sensitivity-Propagation-Testbed) owns the chart law, not the bench.
