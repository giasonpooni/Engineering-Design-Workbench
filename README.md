# Fluid State Reconstruction Testbed (FSRT)

**Check whether measurements in a fluid network agree with a declared physical balance.**

This is **not** visual reconstruction of a fluid volume. It is not a 3DGS / NeRF / PDE fluid solver. “State reconstruction” here means estimating a physical system from measurements and keeping the evidence needed to challenge that estimate.

| Surface | Name |
|---|---|
| Public name | FSRT (Fluid State Reconciliation Testbed) |
| GitHub repository | `giasonpooni/Fluid-State-Reconstruction-Testbed` |
| Installable project | `fluid-state-reconstruction-testbed` |
| Import | `set_lcm` (historical: state estimate + linear constraint matching) |

FSRT is a Python research toolkit for water levels, flow gauges and storage measurements. It estimates the state of a system, checks the estimate against a declared balance, and keeps a record of the disagreement and any correction.

The aim is to help investigate degrading measurements: **when did the readings stop agreeing, what could explain the difference, and what can this sensor arrangement actually detect?**

## A practical example

A reservoir has measurements of stored water, incoming flow and outgoing flow. Over the same time interval, conservation relates them:

```text
change in stored water = water in − water out
```

If the measurements do not support that balance, FSRT can flag the disagreement and show its size under your stated uncertainties. The cause could be a drifting instrument, an outdated rating curve, an unmeasured inflow, or an unsuitable model. **An alarm starts an investigation; it does not, by itself, identify a broken sensor.**

## Try it

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and a checkout of this repository. Python 3.12 and 3.13; runtime dependency NumPy.

The checkout is about 50 MB. Most of that is committed NOAA/USGS replay fixtures under `data/` and generated reports under `results/`. The quickstart does not read `data/` and makes no network requests.

```bash
git clone https://github.com/giasonpooni/Fluid-State-Reconstruction-Testbed.git
cd Fluid-State-Reconstruction-Testbed
uv run --frozen --python 3.13 python examples/quickstart.py
```

The example uses two tanks and a declared total of 100 kg. It shows two cases:

- A small disagreement: reconcile the estimate while retaining the original values.
- A large disagreement: flag it and hold the correction so the balance cannot hide the problem.

The example uses synthetic values and makes no network requests. See the [usage guide](docs/USAGE.md).

For a workbench integration, FSRT also exposes a [pinned JSON subprocess operation](docs/CIW_ADAPTER.md)
for one simultaneous two-reservoir snapshot. It retains full channel covariance,
the original observations, model disagreement, and explicit numerical refusals.

## Explore the examples

| Example | What it demonstrates | Report |
|---|---|---|
| Camera and gauge | Synthetic grayscale measurements, fixed-marker motion compensation, timing problems and disagreement under shared calibration uncertainty. | [Camera baseline results](results/camera_baseline.md) |
| Invariant filtering | Ordinary KF equivalence under unit, coordinate and measurement-order changes, including missing and biased readings. | [Invariant layer results](results/invariant_layer.md) |
| Fluid fault benchmark | Offset, drift and gain across 128 evaluation seeds per case, including confounded faults and physical changes. | [Baseline results](results/fluid_baseline.md) |
| Ridgway measurement baseline | Matching daily intervals and full residual covariance, under declared timing/model and uncertainty assumptions. | [Measurement replay](results/real_fluid_baseline.md) |
| Two-reservoir simulation | Noise, missing readings, biased sensors and stale balances, scored against hidden simulated truth. | [Simulation results](results/summary.md) |
| NOAA tide gauge | Measurement replay, water-level filters and checks that do not require known truth. | [Water-level results](results/real_noaa.md) |
| NOAA tide gauge, one month | What record length changes: which tidal constituents 31 days separate and 15 do not, a q fitted on the first half and scored on the second, and the stated per-reading uncertainty against a model-free bound. | [Month results](results/real_noaa_month.md) |
| Ridgway filter study | Historical estimator comparison, retaining its documented daily-mean/reference approximation. | [Water-balance results](results/real_water_balance.md) |
| Real-record diagnosis | The first isolation result on real evidence: two candidates a practitioner separates are exactly collinear on a closure residual, and the engine reports ambiguity rather than naming one. | [Diagnosis](results/real_diagnosis.md) |
| Taylor Park, a second reservoir | What a second site cost, and what it found: three inflow gauges instead of two, two of them seasonal, and a balance that does not close — 9.80% of gauged inflow even on the days every gauge reports. | [Second-site results](results/real_taylor_park.md) |
| Two-reach river | The first topology here that can name an instrument: six declared faults recovered in 100% of records with routing, none of the storage ones without it. | [Muskingum results](results/muskingum_reach.md) |
| Second-balance design study | Which proposed topology could actually isolate a fault, computed before either is built: conservation alone reaches 1 of 7, the constitutive relation reaches 5 of 7. | [Design study](results/second_balance.md) |
| Cooling-manifold procurement study | How many metered circuits are worth buying, computed before any are: conservation alone isolates nothing because a fouling circuit conserves energy, the duty row reaches 18 of 19, and the answer is still the hardest pair rather than the count — going from one metered circuit to six moves it by a factor of 1.14, while the declared heat load moves it by 88. | [Circuit study](results/cooling_circuits.md) |
| Uncertain relations | What treating a measured coefficient as exact costs, against a null that is true by construction: 26 to 30 times the nominal false-alarm rate. | [Calibration](results/errors_in_variables.md) |
| Uncertain relations, reconciled | The same cost to the estimate rather than the test: a nominal 95% region that actually covers 1.5%, and an over-confidence measured to be quadratic in the operating point to within 0.10%. | [Projection](results/eiv_projection.md) |

To run tests:

```bash
# Unit / contract gate (no experiment regeneration)
uv run --frozen --python 3.13 --dev pytest -q -o addopts= -m "not slow and not extended"

# Default suite (excludes only the multi-minute slow marker)
uv run --frozen --python 3.13 --dev pytest -q
```

## Read further

- [Usage guide](docs/USAGE.md)
- [Methods and interpretation](docs/METHODS.md)
- [Development roadmap](docs/ROADMAP.md)
- [Detailed research history](docs/RESULTS.md)
- [Data provenance](data/daf/PROVENANCE.md)

“State reconstruction” means estimating a physical system from measurements. FSRT retains the evidence needed to challenge its estimates. Whether a fault can be detected depends on the measurements, model and declared uncertainty.

## License

FSRT is available under the [MIT License](LICENSE).
