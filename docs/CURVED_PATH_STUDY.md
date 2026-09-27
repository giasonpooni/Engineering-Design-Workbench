# Curved-path candidate study

Compare a small set of proposed initial headings on one declared constant-curvature
path. Each candidate executes the existing `ciw.curved-path-transfer.v1` operation
in its pinned native provider. The study links those retained occurrences and
explains the response using the shared matrix contribution arithmetic.

This is a heading-only comparison, with zero initial lateral displacement. It
holds curvature, arclength grid, units, frame, assumed covariance and native
validity settings fixed. The operator supplies candidates and separate lateral
and heading limits; the tool does not rank candidates or choose a design.

## Run, reopen and replay

Install CIW and provision the exact CSG checkout as described in
[Geodesic references](GEODESIC_REFERENCES.md#exact-providers). Run from this checkout:

```sh
python scripts/check_curved_path_study.py run --csg-repo /trusted/references/csg --source examples/curved-path-study/baseline.json --spec examples/curved-path-study/spec.json --output results/curved-study
python scripts/check_curved_path_study.py inspect --workspace results/curved-study/workspace.json --study results/curved-study/study.json
python scripts/check_curved_path_study.py replay --csg-repo /trusted/references/csg --workspace results/curved-study/workspace.json --study results/curved-study/study.json --output results/curved-replay
```

Output directories must be new. `workspace.json` contains the exact source bytes,
native results and histories using existing workspace version 3. `study.json`
contains the bounded comparison, references and its content digest. Keep both.
Inspection and reopening need no provider. Replay needs an explicitly bound clean
checkout and matching computational identity; it creates fresh execution, result,
verification and bundle occurrences. Content identity is not authentication.

A multi-candidate run is not atomic. A later refusal leaves earlier completed
occurrences inspectable. The script writes `partial-workspace.json` on that path,
without emitting a completed study. Use a new output directory after correction.

To reuse an existing retained baseline programmatically:

```python
from ciw import curved_path_study as study
request = study.make_request(
    baseline_bundle_id,
    [{"candidate_id": "small", "initial_heading_radian": 0.001}],
    sample_index=16,
    limits={"max_abs_lateral": 0.004, "max_abs_heading": 0.003,
            "units": {"length": "m", "angle": "radian"}},
    study_id="heading-comparison",
)
record = study.run_study(session.workbench, request)
study.save_study("study.json", session.workbench, record)
```

## What the comparison means

At the selected arclength sample, the retained transfer matrix is

\[
\Phi(s)=\begin{pmatrix}a(s)&b(s)\\a'(s)&b'(s)\end{pmatrix},\qquad
\Delta z(s)=\Phi(s)\begin{pmatrix}0\\\Delta\theta_0\end{pmatrix}.
\]

The prime means differentiation with respect to arclength, not time. State order
is lateral displacement then heading, in the declared length unit and radians.
The transverse frame is parallel-transported along the nominal geodesic. Curvature
is inverse length squared in the declared unit; this profile performs no unit,
frame or geographic-coordinate conversion.

The response records each matrix contribution, their sum, the predicted candidate
state, the separately executed candidate state and their residual. Both executions
use the same linearized model. A small residual checks that comparison's internal
consistency; it does not independently validate nonlinear or physical accuracy.
The scalar/affine optimization profiles have different dimensionless contracts
and are not used to optimize this mixed-unit state.

Each row also reports maximum absolute sampled lateral and heading values,
componentwise `within`/`exceeds` comparisons, endpoint covariance, native validity,
resolution and calibration declarations, and maximum absolute determinant drift
from one. Drift is reported as supplied; it is not corrected or turned into a
certificate. Native step-refinement convergence remains unestablished.

The sample comparisons concern predicted means only, with no uncertainty or
integration-error margin and no continuous-path guarantee. They are not acceptance
or authorization decisions. The assumed covariance supplies conditional marginals
at each arclength. There is no joint cross-arclength or cross-candidate covariance,
route-wide coverage probability or covariance for differences. The native
heading validity limit bounds the submitted deterministic perturbation; it does
not certify the support of that assumed covariance, including lateral variation.
Physical calibration remains unbound.

The request allows one to eight named candidates and one selected sample. Every
heading, including the baseline, must satisfy both the operation's numerical bound
and the retained native heading-only validity bound before any candidate executes.
Missing references, changed units/grid/covariance, invalid source declarations or
unavailable providers refuse rather than substituting an equivalent later result.

## Retention and the next integrations

The comparison introduces no new scientific operation or workspace format. It
retains exact source, evidence, bundle, operation, execution, result, numerical
result, verification and runtime references. Offline inspection validates those
references and accounting against retained values; it neither calls the provider
nor independently rechecks its mathematics. `replay_of` is a declared parent-study
content link. Without the parent study file, inspection cannot authenticate that
grouping; native replay receipts separately bind each actual replay occurrence.

BIM is the next proposed transfer test, preserving the distinction between design
changes and observation updates. Its current [quantity adapter](INTEGRATED_MODULES.md)
is implemented; surveyed-frame geometry and clearance are separate gates. ESM
currently accepts telemetry and calibrated-observable candidates through separate
bindings. Curved studies do not yet have an ESM mapping or admission route.
Geographic visualization still requires a genuinely geographic declaration and a
cross-repository browser gate. A local curved-path record supplies neither.

The existing installed-reference CI gate now runs the study tests and terminal
walkthrough, then applies ICRH's existing constant-curvature/covariance oracle and
fresh-pair checks to every original/replay candidate. It does not certify the
operator's comparison policy. No new ICRH scientific profile is introduced.

See [study validation](CURVED_PATH_STUDY_VALIDATION.md) for executed tests and pins.
