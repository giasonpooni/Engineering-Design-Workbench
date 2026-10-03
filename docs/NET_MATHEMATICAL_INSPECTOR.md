# Mathematical inspection and linked visual systems

NET can now turn a retained thermal observation view into a recheckable mathematical
report and a self-contained interactive browser inspector. The existing thermal
provider still owns inference, its model matrices, native innovations and next-step
sensor selection. This increment adds bounded **display algebra**, not another
Kalman filter, optimizer, covariance propagator or physical-state owner.

## Run it

Use a new output directory each time. From this feature branch's checkout:

```sh
python -m pip install -e '.[dev]'
python scripts/run_thermal_observation_demo.py \
  --source examples/thermal-observations/source.json \
  --output-dir results/thermal-visual-source-001
python scripts/run_math_visual_demo.py \
  --evidence-dir results/thermal-visual-source-001 \
  --output-dir results/thermal-math-001
```

Open `results/thermal-math-001/inspector.html` in a browser. No service, external
JavaScript, CDN, GPU engine, or internet connection is required by the document.
The source is explicitly synthetic. The demo uses the existing Python thermal
reference; it is not a new Julia/Bevy/Godot or hardware execution.

For independently selected retained input bytes, use the command interface:

```sh
net math results/thermal-visual-source-001/posterior.json \
  --expected-sha256 'sha256:<expected hash of that exact observation-view file>' \
  --output results/thermal-math-report.json
net inspect results/thermal-math-report.json
net view results/thermal-math-report.json --output results/thermal-inspector.html
```

`net math` reads at most 64 KiB of one explicit thermal observation view and checks
its expected byte hash. The hash names the input *view*, not the original workspace.
That view already carries its workspace binding. `net view` accepts only the supported
mathematical report and validates it before export. Both commands use create-only
outputs. The source files and the original Session remain unchanged.

## Mathematical functionality

For the selected thermal state with mean mu and covariance P, the display kernel
uses the installed NumPy Cholesky and symmetric eigenvalue routines:

- **Full covariance contour:** P = L L^T; x(theta) = mu + k L [cos(theta), sin(theta)]^T.
  The selectable k values are 1, 2 and 3. A contour has squared Mahalanobis radius
  k^2. It is **not** automatically a k-sigma joint probability/coverage statement.
- **Uncertainty structure:** marginal standard deviations, the full normalized
  correlation matrix, principal variances and condition number. Thermal coordinates
  share kelvin units. No mixed-unit principal-axis interpretation is performed.
- **Whitened prior innovation:** S = L_s L_s^T; solve L_s z = r, where r and S are
  copied from the original native result. z^T z must agree with the retained NIS.
  These triangular-basis components can mix sensor coordinates and are not
  independent per-sensor fault scores.
- **Conditional covariance reduction:** sum(log(diag(L_pred))) minus
  sum(log(diag(L_post))) equals one half of log(det(P_pred)/det(P_post)). It describes
  covariance reduction under the declared Gaussian model and current available
  measurements. It is not empirical information, a cross-tick information sum,
  or a new sensor-selection decision.

The kernel supports one or two dimensions. It never symmetrizes a matrix, clips
negative eigenvalues, diagonalizes away correlations, or invents missing values.
An asymmetric, singular, nonpositive, or condition-number-above-1e12 covariance gets
an explicit unavailable display result, not a fabricated contour. The original
matrix is still retained. No covariance repair is added to the existing validator.

Sources for the numerical primitives: [NumPy Cholesky](https://numpy.org/doc/stable/reference/generated/numpy.linalg.cholesky.html),
[linear solve](https://numpy.org/doc/stable/reference/generated/numpy.linalg.solve.html),
and [symmetric eigenvalues](https://numpy.org/doc/stable/reference/generated/numpy.linalg.eigvalsh.html).
Cholesky itself does not check symmetry; this display kernel checks both stored
triangles for exact agreement before calling it. The project dependency pin is
unchanged by this work.

## Linked visual panels

The retained tick slider, previous/next buttons, and plotted NIS/temperature points
select a single tick across the panels. Keyboard interaction uses the native range
input. Prediction/posterior selection and radius selection alter the display only.
They do not rerun the model or alter the retained observations.

1. Temperature samples and marginal +/-k sigma bars in source time. The first sample
   is at dt, preserving the existing predict-then-correct order. Missing thermometer
   samples are labelled, not drawn at zero. Samples remain discrete points.
2. A core/shell state-plane covariance contour with equal kelvin-per-pixel axes.
   A hollow point marks the other conditioning stage; a cross marks a complete
   measurement. Missing measurement coordinates do not create a fake plane point.
3. The complete selected covariance or correlation matrix, principal variances and
   condition number. Rounding is presentation-only; exact values remain in raw data.
4. Whitened innovations, native NIS history annotated by active dimension, and the
   original innovation/covariance/gain arrays. No statistical alarm threshold is
   inferred, especially when measurement dimension changes.
5. All four native next-step sensor-subset information scores, including infeasible
   subsets and the original selected subset. This panel is explicitly the forecast
   after the final retained tick, not a recomputed score at the time cursor.
6. The declared thermal equations, parameters, and original continuous/discrete
   model matrices, plus source/occurrence bindings and exact selected-tick data.

The browser is a mathematical inspector, not a spatial scene engine. The existing
Godot application, Blender/Bevy adapters and GSC spatial presentation paths are
unchanged. This local document does not claim live synchronization with them. Its
numerical report is an additive retained artifact that later viewer adapters can
consume through an explicit supported contract.

## Report, identity and numerical checks

`ciw.thermal-math-inspection.v1` separates **retained** source data from **derived**
numerical display quantities. It carries exact input UTF-8 text and its SHA256,
original execution/result/workspace bindings, fixed policy, display profile and
producer metadata. It introduces no new estimator execution or verification identity.
Display decomposition is a real bounded numerical calculation and is labelled as
such, rather than claiming that no computation occurred.

`net inspect` recomputes only the supported display algebra and uses the existing
native reader to validate its source. Copied native fields must match exactly.
Derived floating-point values are compared at fixed rtol 1e-10 and atol 1e-12 so
inspection does not pretend to require cross-platform bit identity. Structural
integers, schema, authority, dimensions and policy remain exact. Producer version
and source hash are retained declarations, not proof of authentic execution.

This does not establish physical calibration, empirical coverage, statistical
acceptance, source authenticity, new state admission or cross-tick covariance.
Synthetic generator/evaluation/held-out truth is not exported into the observation
view and therefore is not introduced by the mathematical inspector.

## Browser boundary and qualification

HTML export embeds the report as inert base64 data. Packaged script and style hashes
are the only hashes allowed by its Content Security Policy; network connections,
external resources, forms and base-URL rewriting are disabled. User text is rendered
with textContent, never interpolated into HTML or executable JavaScript. The page
has no file-based plugin loader, remote provider API or equipment-control channel.
The report can be saved from the browser and rechecked with the normal Python reader.

Run `python -m pytest -q tests/test_math_inspector.py` for algebraic oracles, native
thermal cases, all four sensor-availability masks, mutation rejection, exact input
binding, read-only lifecycle checks and package/CLI boundaries. The browser harness
is `validation/math_visual_browser.py`; it actually drives Chromium, changes every
selection, checks covariance/missingness and downloaded data, and records screenshots
at desktop, 700px and 390px widths.

The default browser harness opens the HTML with file://. Some managed browser
installations block local-file navigation. `--document-mode content` tests the same
HTML bytes via the browser's document-loading API instead; its report explicitly
records that different transport. It does not count as a successful file:// test.
Screenshots and successful results are retained only for tests actually executed.
