# Information geometry in the retained mathematical inspector

Inspect **which uncertainty directions a measurement reduces**, not just the
covariance trace or a scalar information score. This is an opt-in extension of
NET's existing mathematical report and browser inspector. The thermal provider
still owns prediction, conditioning, candidate covariances and sensor selection.
No additional estimator, optimizer, runtime owner, network service or mandatory
dependency is introduced.

## Run the existing model and inspect its retained alternatives

```sh
python -m pip install -e '.[dev]'
python scripts/run_thermal_observation_demo.py \
  --source examples/thermal-observations/source.json \
  --output-dir results/information-source-001
python scripts/run_information_visual_demo.py \
  --evidence-dir results/information-source-001 \
  --output-dir results/information-001
```

Open `results/information-001/inspector.html`. The source is the existing synthetic
core/shell thermal example. The second command does not rerun its model. It creates
`information-report.json`, `inspector.html` and `demo-summary.json` in a new output
directory. Existing files are not overwritten.

For a separately selected retained thermal observation view:

```sh
net math posterior.json --expected-sha256 'sha256:<exact input hash>' \
  --information-geometry --output information-report.json
net inspect information-report.json
net view information-report.json --output inspector.html
```

Without `--information-geometry`, `net math` continues producing the original
`ciw.thermal-math-inspection.v1`. With the flag, it produces the **v2 superset**:
all v1 evidence, native values, policy, original derived quantities and authority
are retained, with a separate `information` field. Both versions are readable.
The additional display kernel has its own profile and source digest declaration.
A digest is content lineage, not producer authentication or complete build closure.

## Mathematical meaning

Let **P** be a retained before-covariance and **Q** the corresponding retained
after-covariance in the same ordered state coordinates. With P = LLᵀ, compute

```
B = solve(L, cholesky(Q))
W = B Bᵀ = L⁻¹ Q L⁻ᵀ
lambda = squared singular values of B, ascending
```

P becomes the identity in the prior-whitened basis. The generalized variance
ratios lambda describe the variance remaining in the extremal linear directions.
For example, `[0.25, 1]` means one direction has one quarter of its original
variance while another retains all of it. Standard deviations scale with the
square roots, not these variance ratios themselves.

A two-dimensional Mahalanobis-radius contour is `k B [cos(theta), sin(theta)]`.
The prior is the circle of radius k. Both are centered at zero for **covariance
comparison**: this is not a hypothetical posterior mean or a physical phase plot.
Contour radii are not automatically joint confidence probabilities.

The 72 precomputed directional probes are in five-degree increments. For a unit
vector n in this prior Cholesky basis:

```
variance ratio       = nᵀ W n
standard deviation   = sqrt(nᵀ W n)
ellipse support point = W n / sqrt(nᵀ W n)
projection endpoint   = sqrt(nᵀ W n) n
```

The support point touches the covariance contour in the direction n. Its
projection onto n has the indicated standard deviation. **This projection length
is not the ellipse's radial intercept.** No matrices are decomposed in the browser;
it displays these retained, recheckable numerical samples.

The area ratio and log-volume reduction are

```
area(Q) / area(P) = sqrt(det(Q) / det(P))
gain              = 0.5 log(det(P) / det(Q)) = -0.5 sum(log(lambda))
```

The gain equals the difference of Gaussian differential entropies under the
declared model. It is not empirical information, a realized-error score, a KL
divergence between different means, or a sum of independent information across
ticks. Every available candidate gain is compared with the **original native
sensor information score**; a numerical contradiction refuses the report.

The generalized ratios and area ratio are invariant under an invertible common
coordinate transformation within this bounded numerical domain. The Cholesky
basis and its drawn angles are not invariant and are **not named sensor axes**.
No unique generalized direction vectors are claimed for repeated eigenvalues.

## Linked views and original decisions

The top panel has two explicit contexts:

- **Selected tick update:** the original prediction-to-posterior covariance pair.
  The shared tick cursor updates this panel. The State selector elsewhere changes
  the state display, not which pair this comparison means.
- **Next-step sensor design:** the provider's final forecast prior and each of its
  four retained candidate covariances. Candidate buttons and the native score bars
  link to the geometry. This is a fixed final forecast, not a new forecast at each
  historical tick. Infeasible candidates are visible and explicitly labelled;
  selecting one for inspection never changes the original provider decision.

The same contour-radius control applies. The direction slider changes only the
selected numerical probe. Existing time, covariance, innovation, model, provenance
and report-download panels remain present. Keyboard controls, responsive layouts,
text-only handling of supplied labels and hash-based CSP remain in place. The
page has no provider API, external asset or network request.

In the shipped three-tick example, tick two has one available thermometer. Its
normalized variance ratios are approximately `[0.517630, 1]`: one direction is
reduced and another is unchanged. In the final forecast, no sensors gives `[1,1]`;
the shell-only candidate gives approximately `[0.576433,1]`; both sensors give
approximately `[0.559990,0.676517]` but exceed the original budget. The provider
retains shell-only as its selected candidate. These are synthetic, model-conditional
results, not physical validation or a recommendation to configure real sensors.

## Numerical refusal and compatibility

The new algebra calls the existing strict covariance-display validation for both
inputs. It never symmetrizes, clips, diagonalizes away cross terms, adds jitter,
or imputes a missing matrix. Nonsymmetric, singular, nonpositive, malformed and
ill-conditioned inputs do not produce fictitious geometry. It also checks the
**relative** condition number; two individually acceptable matrices can form an
unreliable relative problem. The existing condition limit remains 1e12.

Expansion and mixed directional changes are retained rather than clipped to a
contraction. Relation labels use an explicit 1e-10 numerical display tolerance;
this is not a scientific acceptance threshold. Generalized eigenvalue computations
use singular values of the factor instead of forming an inverse. Each available
result is cross-checked against the log-volume difference.

`net inspect` checks the outer seal, validates all original v1 fields and native
source bindings through the original reader, and rederives the added quantities
under the existing fixed display tolerance. No provider lifecycle runs and no
new execution, verification occurrence, admission, or hardware action is created.
The exact native matrices and values remain retained even if their geometry is
unavailable. Saved files cannot bind code. This remains a thermal-specific adapter,
not a generalized covariance propagation service or new OIT/JSPT implementation.

## Tests and numerical references

`tests/test_information_display.py` covers analytical diagonal/correlated examples,
the generalized determinant polynomial, support-point versus radial geometry,
coordinate congruence, unchanged/contracting/expanding/mixed pairs, input and relative
condition refusal, all four real synthetic observation masks, native score matching,
v1/v2 compatibility, resealed contradictions and provider-free inspection.

`validation/information_visual_browser.py` exercises actual Chromium controls,
all four sensor alternatives, unchanged provider decision, shared tick selection,
fixed-forecast context, direction selection, 700/390-pixel layouts, offline saved
report revalidation, and absence of network/CSP errors. Existing v1 browser checks
are retained. Local content-loading and CI file navigation are reported separately;
a content-loaded browser test is not a claim of local `file://` acceptance.

Numerical building blocks and the entropy identity:

- NumPy Cholesky decomposition: https://numpy.org/doc/stable/reference/generated/numpy.linalg.cholesky.html
- NumPy symmetric eigensystems: https://numpy.org/doc/stable/reference/generated/numpy.linalg.eigh.html
- Gaussian differential entropy derivation: https://statproofbook.github.io/P/mvn-dent.html

These references explain mathematics; the repository retains its pinned dependency
versions. Current revision-specific execution evidence belongs in PR #51. No
repository-wide, native-engine, physical, or browser-platform qualification is
implied beyond the combinations actually run.
