# Polymer heating-cycle temperature qualification

Status: pilot protocol and conditional software calculation. No physical
qualification data, calibrated instrument, installed-chain validation, trained
PINN/gPINN, or temperature SP1 proof is supplied by this increment. The planning
record in [pilot-setup.json](../examples/temperature/pilot-setup.json) deliberately
leaves hardware, ranges, uncertainty requirements and acceptance thresholds open.
It is not an executable processing request.

## What the software result means

The temperature processor accepts `ciw.temperature-processing-request.v1`
requests for `metrology.temperature.process.v1`. Its conventional calculation is
an affine conversion, `T_sensor_K = gain * raw + offset_K`, for one sensor/readout
and 1 to 64 retained samples, with declared joint covariance across the raw
samples, gain and offset. An optional installed
correction can produce a separately labelled local-polymer estimate. Providing
that correction and uncertainty is an input declaration, not experimental
evidence that the correction is adequate. Physical qualification remains
`not_established`.

The acceptance rule evaluates the submitted sample instants only. It does not
establish bounds between samples, a continuous-cycle peak temperature, or dwell
time within a band. Qualification of those derived quantities requires their
own temporal model, timing/response evidence and uncertainty calculation.

Acceptance endpoints are rounded outward from the exact arithmetic of the
reported binary64 value, standard uncertainty and multiplier. Thus positive
sub-resolution uncertainty cannot disappear at a tolerance boundary. This is
not a rigorous error enclosure of the preceding calibration, covariance or
square-root calculations; their numerical adequacy remains a qualification item.

Uncertainty propagation is first order. Multiplication of uncertain gain and
raw input can require a higher-order assessment; applicability of the
approximation must be checked for the physical pilot. Additional covariance
contributions and installed corrections require explicit independence from the
other source groups and disjoint dependency identities. Unknown cross-source
dependence is refused; the contract does not represent an arbitrary joint model
of installed corrections and calibration. Missing budget categories or invalid,
missing, saturated, stale or out-of-domain observations cannot produce an
unqualified operational acceptance. These are conditional checks on declarations.

Keep the raw structured observation, calibrated sensing-element temperature,
and any local-polymer or core/field estimate distinguishable. In a heating cycle,
calibration of a probe does not establish equality between sensing-element and
polymer temperature. The installed thermal coupling needs its own evidence.

The report commitments cover canonical UTF-8 JSON declarations. They do not
commit to the original acquisition file bytes, establish authenticated origin,
or prove that the observations describe a physical experiment. Retain original
acquisition files separately; a later signed acquisition contract must specify
byte encoding, signer identity and verification. A calibration-document hash is
an identity aid, not a traceability chain.

Distinguish four decisions:

| Decision | Question answered | Required evidence |
| --- | --- | --- |
| Processing validity | Can this declared calculation be evaluated within its software contract? | Valid structure, arithmetic domain, covariance and applicable declared bounds |
| Operational acceptance | Does the calculated result satisfy the supplied rule? | A frozen rule applied to the result and declared uncertainty |
| Evidence completeness | Are the required experimental records and reviews present? | The evidence matrix below, with reviewer and unresolved gaps |
| Physical qualification | Does the installed chain meet its intended measurement requirement? | Reviewed comparison experiments and an adequate uncertainty model over the claimed envelope |

An operational acceptance result cannot promote either of the last two states.
Filled evidence references establish an inventory; references still require
technical review. Synthetic processing examples establish no physical result.

## Freeze the pilot before confirmatory experiments

Define the target as polymer temperature at a named location and time, with a
specified spatial and temporal averaging convention. State whether this means
the temperature in the instrumented specimen or the estimated undisturbed
polymer temperature. A core temperature or full field is a separate measurand.
Specify polymer grade, lot, conditioning, geometry, material state, probe
placement and its tolerance, installation method, heating/cooling programme,
ambient range, sample timing and required uncertainty. Record any excluded
material transitions or operating regimes. The customer decision determines the
required uncertainty and acceptance thresholds; this document supplies no
numerical performance claim.

JCGM GUM-6 structures this work around a defined measurand, a measurement model,
influence effects and experimental assessment of adequacy. Its cautions about
extrapolation apply to hybrid models as well as empirical ones. This protocol is
an application of that guidance, not a prescribed JCGM test method.
[JCGM GUM-6:2020, sections 6, 10, 12 and 13.2](https://doi.org/10.59161/JCGMGUM-6-2020).

Assign a protocol version, owner and reviewer. Freeze the operating envelope,
comparison metrics, decision rule, uncertainty coverage convention, split
manifest and sample-size rationale before the confirmatory set is opened.
Record amendments and whether they require new held-out observations.

## Evidence matrix

| Area | Experiment or record | Qualification gate |
| --- | --- | --- |
| Measurand and range | Completed pilot setup, installation drawing, operating envelope and customer requirement | Target, units, time/location semantics and numerical limits are agreed |
| Traceability | Reference identity; calibration results, uncertainty, validity and chain to the stated reference; readout-channel calibration | Each calibration link and its contribution is reviewed for the intended use |
| Static comparison | Compare the complete probe/readout channel against a suitable reference across the temperature range; ascending and descending sequences; checks before and after the campaign | Comparison supports the fitted conversion and uncertainty throughout the claimed range |
| Installed dynamic comparison | Representative polymer heating cycles with a characterized reference near the target location; known timestamp alignment; recorded location separation | Lag, gradients, contact, conduction and insertion disturbance are corrected or bounded adequately |
| Repeatability and reproducibility | Independent cycles across days, reinstallations, operators and devices as applicable | Estimated variation and its estimation uncertainty meet the agreed requirement |
| Environmental and fault response | Ambient variation, heating-rate changes, drift, hysteresis, sensor/readout saturation and missing observations | Corrected effects remain within scope; unsupported conditions yield explicit invalid/unsupported outcomes |
| Uncertainty | Source ledger, model, joint covariance, coverage calculation and comparison residual analysis | No material omitted or counted twice; required uncertainty is met across the envelope |
| Independent validation | Untouched cycles and conditions; independent instrument or laboratory where feasible | Frozen comparison criteria pass without post-test tuning |
| Maintenance | Check-standard schedule, control limits, version/installation changes, withdrawal and reprocessing procedure | Responsibility, triggers and affected-result handling are operational |

Use a reference appropriate to both the temperature range and dynamic behaviour.
Its own lag, placement, acquisition timing and uncertainty must be included.
Where practical, interchange probe positions or vary insertion geometry to
separate probe bias from spatial gradients. A reference probe may itself alter
the polymer temperature; document this interaction. Static bath comparison does
not replace installed dynamic comparison.

Traceability concerns a documented calibration chain with uncertainty at its
links. It does not itself establish that uncertainty is sufficiently small for
the customer application.
[NIST metrological traceability guidance](https://www.nist.gov/metrology/metrological-traceability).

## Replication, reference comparisons and sample size

Use independent specimens and complete heating cycles as experimental units.
Repeated timestamps within one cycle are correlated observations, not
independent replicates. Where reheating changes a specimen, record that history
and use new specimens when needed to preserve the intended condition.

Balance or randomize feasible factors. Cross operators and devices with
conditions where possible; avoid confounding an operator with one day or one
heating profile. Estimate within-cycle noise, between-cycle, between-day and
installation contributions using a design that can separate them. Device-family
claims need evidence across devices; one device supports only its specified
configuration. NIST describes nested designs for separating time-related
variation; adapt those levels to this chain rather than copying a sample count.
[NIST measurement-process designs](https://itl.nist.gov/div898/handbook/mpc/section4/mpc433.htm).

Use a preliminary campaign to estimate variability, then choose confirmatory
cycle counts for the desired precision of bias/reproducibility estimates and
power of the declared baseline/model comparison. Document independent-unit
counts, factor levels, confidence criteria and exclusions. If resources cannot
support a planned claim, narrow the claim and record the limitation.

Compare against the reference at aligned times and defined locations. Retain
signed differences, uncertainty of those differences, errors by heating phase,
and the prespecified cycle-level metrics. Evaluate reference uncertainty and
shared calibration effects, rather than treating the reference as exact. For a
comparison difference, `u2(delta) = u2(test) + u2(reference) - 2*cov(test,reference)`.
Large uncertainties can conceal bias, so require both adequate comparison
agreement and the separately agreed maximum uncertainty.

## Uncertainty decomposition and numerical checks

For the affine sensor calculation, retain the full joint covariance over
`[raw:<sample_id>..., gain, offset_K]`. Each output row has sensitivity `gain`
to its raw observation, `raw` to gain and `1` to offset. This carries shared
calibration and sample-to-calibration dependence into the output covariance.
The proposed experiment must justify these input declarations.

Maintain a ledger with source identity, affected quantities, estimation method,
distribution/covariance, supporting record and an `included_in` explanation.
Distinguish certificate uncertainty, calibration fit, readout resolution/noise,
drift, placement, thermal coupling, dynamic lag, timing, specimen variation and
model discrepancy. If fit covariance already includes reference uncertainty,
do not add the same reference uncertainty again. If reproducibility residuals
already contain an effect, partition it or explain its aggregate treatment
before adding a second component. Type A/Type B classify evaluation methods;
they do not mean random/systematic or independent/dependent.
[JCGM 100:2008, sections 3.3 and 5.2](https://doi.org/10.59161/JCGM100-2008E).

For installed corrections, record their dependence on the original observations
and calibration parameters. Do not silently add covariance as though independent
when an estimated correction shares those inputs. Unsupported joint dependence
requires a richer contract or a restricted claim, not an independence default.
Time uncertainty is especially relevant during rapid heating; placement
uncertainty is relevant in a gradient. A first-order assessment uses local time
and spatial sensitivities, with covariance where shared effects exist.

The uncertainty of an instantaneous result differs from uncertainty of a cycle
mean, peak or threshold-crossing time. Do not reduce shared systematic effects
by the number of timestamps. Do not compute a peak or event uncertainty from
only pointwise standard uncertainties when temporal dependence matters.

Document any linearization, rounding, discretization and solver approximations.
For nonlinear extensions, compare uncertainty propagation with a suitable
distribution-propagation calculation where needed; Monte Carlo is a numerical
uncertainty method, not experimental validation of a physical model.
[JCGM 101:2008](https://doi.org/10.59161/JCGM101-2008).
The controlled standards register should include the currently applicable
nonlinearity amendment listed by BIPM.
[JCGM publication index](https://www.bipm.org/en/committees/jc/jcgm/publications).

## Conventional, PINN and gPINN comparison

The conventional baseline is the calibrated sensor calculation, with an installed
correction only if justified. Core/field reconstruction requires a conventional
model for the same target; a local probe result alone is not a like-for-like core
temperature baseline. PINN and gPINN execution are future experiment work, not
implemented by the affine processing operation.

Create development, tuning and untouched confirmatory manifests grouped by
specimen and cycle. Hold out whole days, lots, installations or profiles where
the desired generalization claim requires it. Keep final reference readings
unavailable for training, model selection, normalization fitting and tuning.
Use comparable observations and tuning opportunities for all candidate methods.

Freeze architecture, weights, preprocessing, material parameters, boundary and
initial conditions, training data identities and seeds. Compare signed bias,
the agreed cycle-level error metrics, uncertainty-interval behaviour, operating
cost and latency. Distinguish pointwise interval coverage from simultaneous
coverage of an entire trajectory. Assess coverage against uncertain reference
data; simple containment of reference point estimates is insufficient.

Estimate model discrepancy from independent comparisons after accounting for
known observation/reference effects. Report condition-dependent residuals and
model-choice uncertainty. Repeated training seeds alone cannot represent all
model discrepancy; small PDE or gradient residuals do not establish global
temperature accuracy.

Separate held-out conditions inside the intended envelope from deliberate OOD
stress tests: new heating rates or boundary conditions, changed thickness,
material/lot, contact, missing channels or sensor drift. Define an applicability
policy and test it. Unsupported conditions must be flagged or refused unless
the extended domain is separately qualified. Do not replace missing raw
observations with model values under the observation label. A final-test failure
followed by model tuning requires a new untouched confirmatory set.

## Decisions, maintenance and pilot delivery

Agree the tolerance, required uncertainty, bias/error limit, coverage convention,
comparison margin and acceptance/rejection/indeterminate treatment before
qualification. Near a tolerance boundary, the operational rule must explicitly
state how uncertainty affects the decision. A selected multiplier is not itself
evidence of its coverage probability. Consider false acceptance and false
rejection when selecting the rule.
[JCGM 106:2012](https://doi.org/10.59161/JCGM106-2012).

Maintain check standards at suitable operating points before/after campaigns and
on a justified schedule. Use observed drift and consequences of failure to set
recalibration intervals. Reassess after probe/readout replacement, repair,
reinstallation, firmware, calibration, preprocessing or model changes. Record
as-found and as-left checks. On failure, identify results since the last
demonstrably acceptable state, assess their validity, withdraw or qualify
affected reports, and retain the relationship to any corrected/reprocessed
replacement. Preserve originals and the reason for each change.

Deliver the installed-chain evidence dossier, raw record inventory, calibration
and uncertainty model, frozen split manifest, baseline/model comparison,
qualification decision with exclusions, and maintenance procedure. Price the
pilot against these agreed deliverables; use measured cost and customer value
to decide whether the optional proof feature belongs in a subscription.

## Optional SP1 extension: proposed contract, not implemented

The existing bounded integer heat guest is a computational example; it does not
qualify polymer temperature or this affine processing procedure. A temperature
extension needs its own guest, numerical profile and qualification.

The initial proposed claim is: this report was computed from the committed
records, calibration and rules by the specified bounded processing program.
Start with the conventional transformation and uncertainty calculation. A future
PINN extension should first target bounded inference or a precisely defined
checker; proving residual checks does not prove training or global accuracy.

Freeze the following before building the guest:

| Contract item | Required definition |
| --- | --- |
| Input bytes | Versioned bounded encoding; exact field order/lengths; units; sample/time identities; missing/saturation semantics; duplicate-field and nonfinite rejection; original-byte versus normalized-declaration commitments explicitly distinguished |
| Applicability | Declared numerical and measurement bounds; required fields and calibration validity; checks concern declarations and cannot establish their physical truth |
| Calculation | Exact affine conversion; covariance ordering and propagation; installed corrections only when their joint uncertainty is supported; acceptance rule and its boundary behaviour |
| Arithmetic | One pinned representation, such as checked scaled integers; scales, signed ranges, intermediate width, division/rounding, square-root bounds and overflow rejection; no host-default arithmetic semantics |
| Numerical equivalence | Independent reference calculations; explicit error bounds against the metrology calculation; outward rounding for reported interval bounds; treatment of numerical uncertainty without double counting |
| Commitments | Domain-separated commitments to observations, calibration, covariance, procedure, rules and report; all mathematically relevant settings included |
| Public outputs | Procedure/numerical-contract identifiers, input commitments, report commitment, result disposition and any disclosed report fields needed by the verifier |
| Verifier | Expected guest/program identity and verification key, approved toolchain/backend, public-output schema and input/report bindings; fail closed on mismatch, missing evidence or stale policy |

Software release gates are independent of physical qualification: deterministic
known-answer and boundary vectors; malformed/overflow/covariance refusal tests;
independent arithmetic comparison; genuine build/prove/fresh-verify; negative
tests with changed inputs, reports, public outputs or guest identity; and measured
cycles, proving/verification time, memory and cost. Benchmark representative and
maximum allowed workloads before widening bounds. SP1 distinguishes execution
from proving and recommends executing larger workloads during development.
[SP1 quickstart](https://docs.succinct.xyz/docs/sp1/getting-started/quickstart).

A valid computation proof does not authenticate acquisition, establish correct
installation, verify a calibration chain, or demonstrate model adequacy. Those
claims retain the separate evidence requirements above. Until a genuine
temperature guest and verifier pass their gates, report the proof feature as
unavailable, never verified by replay or by the existing heat guest.
