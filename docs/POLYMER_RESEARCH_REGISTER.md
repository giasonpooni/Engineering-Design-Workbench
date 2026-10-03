# Polymer processing research register

This register connects the user-supplied research corpus to the NET polymer
instrument. It records what each source supports, the limits of that evidence,
and implementable consequences. Research support, a passing software check, and
a qualified physical installation remain separate claims.

The source PDFs stay outside this repository. Page references are one-based PDF
pages; the journal PDFs also print matching article page numbers. All summaries
below are paraphrases. No paper-specific dataset, trained weights, performance,
calibration, or live machine connection is supplied by this register.

## Source identity and dates

| ID | Uploaded filename | Title and source type | Date presented in source |
|---|---|---|---|
| R1 | `2511.08108v1.pdf` | Rottenwalter, Tilly and Owolabi, *Improving Industrial Injection Molding Processes with Explainable AI for Quality Classification*. Experimental arXiv preprint. | arXiv v1: 11 November 2025 |
| R2 | `polymers-14-03551 (1).pdf` | Aminabadi et al., *Industry 4.0 In-Line AI Quality Control of Plastic Injection Molded Parts*. Experimental journal article, DOI `10.3390/polym14173551`. | Published 29 August 2022 |
| R2-DUP | `polymers-14-03551 (1)(1).pdf` | Byte-identical duplicate of R2; one evidence source. | Same as R2 |
| R3 | `sensors-26-02034.pdf` | Brunyé, Petrimoulx and Cantelon, *From Sensing to Sense-Making: A Framework for On-Person Intelligence with Wearable Biosensors and Edge LLMs*. Perspective, DOI `10.3390/s26072034`. | Published 25 March 2026 |
| R4 | `sensors-26-04350.pdf` | Aghaee and Shaker, *Large Language Models in Sensor-Driven Control Systems: Architectures, Challenges, and Opportunities*. Review, DOI `10.3390/s26144350`. | Published 9 July 2026 |
| R5 | `0810.0748v1.pdf` | Lageman, Trumpf and Mahony, *Observer design for invariant systems with homogeneous observations*. Mathematical observer-design paper. | arXiv v1 label: 4 October 2008; title-page date: 1 November 2018 |

R5 contains different version-related dates. The supplied bytes, rather than a
filename-derived publication assumption, identify the analyzed document. Its PDF
metadata creation date is 25 June 2021; that is not a research publication date.
No claim of a more recent paper revision is made.

| ID | SHA-256 of supplied PDF bytes |
|---|---|
| R1 | `83fae0111cdb39a635dd243eae4ceaf40b2475ca030e6b3bfa1768f308649ad0` |
| R2 / R2-DUP | `37f487cfe2e1230f1ab1d385d80cbe4724120294125100f9a0f97f3de6c9e4cb` |
| R3 | `363c8622fbe46982a11d42dbf60ebecefe16530161860284e2f5e321257ed7f6` |
| R4 | `d290c0b62e08aba4d27e8306d3c5721befa7ad02bac464ecefec2ac72a00d01f` |
| R5 | `ed82d393ff17edd249382adb3012f15c5b7843951b7454717c2c028c8aaf3e71` |

## R1: XAI feature selection for injection molding

**Experimental boundary.** Section IV.A, p. 3 reports 1,171 labeled molding
cycles using polypropylene and an approximately 10 × 10 × 15 cm box. An
experienced operator labeled quality. Each cycle contains roughly 1,800 time
steps sampled at 10 ms intervals. These are process-time-series labels, not
independent calibrated dimensional measurements or structural test results.

**Reported result.** Table III, p. 5 reports ten-run mean validation
accuracy/F1 of 86.79%/89.08% with 19 features, 91.33%/92.52% with nine features,
and 84.70%/86.29% with six features. The respective accuracy standard deviations
are 11.08, 5.79, and 9.24 percentage points. Section V.C, p. 5 reports relative
inference improvements of 7% and 13% for the nine- and six-feature models.
These are measurements on the authors' setup; they are not NET runtime or
cross-machine guarantees.

**Useful input candidates.** Table II, p. 4 ranks injection pressure, actual
clamping force, screw position, end-of-ejection position, screw torque, mold
position, screw speed, contact force, and screw velocity. These are candidate
tags for a facility-specific sensor/feature manifest. Their ranking does not
justify permanently removing other sensors or treating feature importance as
causal process authority.

**Validation limitation.** Section IV.A, p. 3 describes quadrupling the dataset
into 4,684 sequences and randomly splitting the resulting datasets into 67%
training and 33% validation. Unless the original-cycle grouping is preserved,
correlated augmentations can enter both partitions. This is an audit inference
from the described method, not a claim that leakage was independently proven.
NET should split original cycles before augmentation, retain original-cycle IDs,
and separately hold out chronological runs, resin lots, tools, and machines when
claiming the corresponding deployment scope. The reported validation scores
cannot serve directly as NET admission thresholds.

**Implementable consequence.** Store explicit feature lineage and training
partition identity. Begin with deterministic, phase-specific telemetry features
and a replayable baseline. Add an LSTM/XAI provider only after acquiring labeled
facility data and measuring held-out utility, calibration, latency, and missing
channel behavior. A pressure or screw-position feature remains an observation;
neither a feature rank nor a class probability proves a defect cause.

## R2: cycle-based in-line measurements and predictive control

**Physical installation.** Sections 3.1–3.2, p. 12 describe ABS Novodur HH-112
with 4% black masterbatch, an EcoPower 110 injection molding machine with a
35 mm screw, a reflective partially cylindrical part, mold temperature-control
units, and robotic handling. Generalization to another resin, geometry,
machine, or blow-molding process requires its own qualification.

**Measurement and transport requirements.**

| Source location | Reported capability or timing | NET consequence |
|---|---|---|
| §2.3.1, pp. 6–7 | Scale specified at 0.001 g; fixture and air-motion stability checks | Record measurement method, calibration, stabilization criteria, part identity, and uncertainty; do not assign the paper's scale performance to a generic weight channel. |
| §2.3.2, p. 7 | Three linear and three rotary profiles, measured while parts are as molded | Associate each dimension with its profile, coordinate frame, and time/temperature state; sampled profiles are not complete surface coverage. |
| §2.3.3, p. 8 | Monochrome camera with controlled LED illumination; 250–300 images during rotations | Images require controlled acquisition and geometric/photometric qualification before quantitative metrology. |
| Table 1, p. 9 | 44 s dimensional measurement, 9 s camera scan, 8 s weight measurement; 76–95 s part-production cycle with parallel handling | Measure latency by stage and respect pipeline delay. This study does not demonstrate whole-part inspection within milliseconds of ejection. |
| §3.3.1, p. 13 | OPC UA machine/peripheral collection at 60 Hz | Protocol transport rate is separate from physical bandwidth and estimation validity. |
| §3.3.2–3.3.3, pp. 13–14 | Important machine analog signals and four mold sensors sampled at 600 Hz; three combined pressure/temperature sensors and one pressure sensor | Preserve source clock, sample rate, channel location, and calibration. Do not merge 60 Hz and 600 Hz channels without explicit temporal alignment. |
| §3.3.4, p. 14 | Ambient temperature/humidity in three locations sampled every 30 s and uploaded every ten minutes | Ambient context has different freshness/transport requirements from pressure-waveform features. |

**Dimensional-specification inconsistency.** Section 2.3.2, p. 7 states
±0.005 mm precision for the measurement system. Section 4.1, p. 16 instead
states ±0.010 μm from an earlier study. These differ substantially. The supplied
paper alone does not resolve that discrepancy. Neither value is adopted as
NET's calibrated uncertainty or acceptance band.

**Surface-quality boundary.** Section 2.3.3, p. 8 labels ResNet-18 training
images by holding-pressure level, then maps predicted classes to a normalized
quality index. This is a process-linked surface proxy. It does not demonstrate
structural weld-line strength, fracture resistance, or calibrated severity for
every visible defect. The presence or appearance of a weld line cannot by
itself qualify structural integrity.

**Training and control.** Section 3.4, pp. 14–15 describes 56 experiments,
roughly 2,500 samples, and separately blocked thermal conditions. Section 4.1,
p. 16 reports regression R² of 98.63% for one profile and 99.26% for weight,
with surface quality about 70%, using ten-fold validation. This supports
separate quality heads and validation metrics; a high weight R² cannot justify
surface-defect performance or dimensional compliance.

Algorithms 1–2, pp. 11–12 use bounded machine-parameter enumeration, measured
quality feedback, a minimum number of shots between adjustments, and warnings
for strong prediction/measurement disagreement. Sections 4.2.1–4.2.3,
pp. 17–18 report three-cycle action spacing, up to three-cycle measurement
pipeline delay, and ten-cycle spacing when mold temperature is included. The
controller underestimated the necessary action at one tested thermal condition
(§4.2.1, p. 18). Section 5, p. 21 identifies multi-objective control as future
work. This is evidence for a bounded cycle-based controller, not arbitrary
autonomous reinforcement learning or universal multi-objective convergence.

**Implementable consequence.** A proposal should bind the observed cycle,
part/lot/tool identity, snapshot, parameter domain, and prediction source. The
controller must account for the effective cycle of an action and configurable
settling/dwell requirements for each actuator. Prediction/measurement mismatch
should trigger investigation or abstention. Bound and evaluate deterministic
candidate settings in a simulator before any separately commissioned machine
adapter is enabled. Actual dwell constants come from the installation; three
and ten cycles are study examples, not universal molding constants.

## R3: quality-aware inference and attention policy

R3 is a wearable-biosensor **Perspective**, not a polymer-machine experiment.
Its transferable value is architectural.

- Section 2.1–2.2, p. 5 requires acquisition-quality metadata and treats fusion
  as estimation rather than channel concatenation. For molding, the analogous
  metadata includes calibration status, clipping, missingness, source clock,
  alignment, and availability.
- Section 2.2–2.3, p. 6 preserves uncertainty, drift, and abstention in a compact
  state handoff. The LLM synthesizes trusted state and guidance; it does not
  establish measurements from prose.
- Table 1 and the formal interface, p. 9 separates acquisition, probabilistic
  estimation, grounded reasoning, and an attention policy deciding whether to
  alert, defer, log, or abstain. Recommended outputs contain rationale,
  uncertainty, and provenance.
- The evaluation discussion, pp. 11–12 requires field validity, shift/drift
  behavior, uncertainty calibration, and downstream human outcomes.

**Implementable consequence.** Retain evidence quality and uncertainty in
copilot context. Suppress repetitive low-urgency alerts using an explicit
operator-configurable policy. Assess false alarms, missed defects, burden, and
time to useful investigation separately from classifier accuracy. No wearable
physiology inference or new employee sensing is implied by this adaptation.

## R4: LLM role and verification boundaries

R4 is a cross-domain **Review**, not a new benchmark or commissioned controller.
Its strongest transferable finding is the division of responsibilities.

| Source location | Architectural finding | NET consequence |
|---|---|---|
| §4.2, pp. 19–20 | LLMs fit controlled supervisory interfaces; plant automation retains real-time control and protection | Read-only evidence and bounded proposals are separate from any machine execution authority. |
| §4.3, pp. 20–21 | Sensor-to-semantics transformation precedes reasoning | Feed cycle summaries, qualified estimates, and evidence references rather than unbounded raw streams. |
| §4.6–4.7, pp. 23–24 | External execution/simulator feedback and validation wrappers constrain generated outputs | Schema validation, snapshot checks, rules, simulation, and independent verification precede action. Self-critique alone is insufficient. |
| §6.2 and Table 11, pp. 32–33 | Grounding fidelity, traceability, robustness, latency, unsafe recommendation rate, consistency, and trust calibration matter | Replay tests must include degraded channels, stale snapshots, contradictory evidence, unsupported causes, and disallowed actions. |
| §6.3–6.4, pp. 34–35 | LLM output has no intrinsic stability guarantee; delays and weak grounding matter | Keep deterministic control and protection separate; inspect all recommendations against bounded numerical and temporal constraints. |
| §6.5, pp. 36–37 | Synthetic/narrow benchmarks omit sensing realism | Report simulation verification separately from held-out plant validation and machine qualification. |

The paper's discussion of approval and safety architectures is evidence for
design choices, not an additional user-authorization requirement for building or
testing NET's simulated workload. Machine deployment remains a separately
specified integration and qualification task.

## R5: geometry, observer innovation, and observability limits

Theorem 5, pp. 8–9, projects invariant Lie-group dynamics with **complementary
observations** onto homogeneous output dynamics. Corollary 6, p. 10
characterizes indistinguishable states by a stabilizer subgroup. Its practical
lesson is that an observer estimates only what its output map can distinguish.

The required opposite invariance of system dynamics and observations is
explicit on p. 5; the main results do not apply to matched observations.
Section 5.1, p. 18 requires an invariant Riemannian metric on a reductive
homogeneous output space. Theorem 18 and Corollary 19, p. 19 additionally
require invariant cost structure and, for almost-global convergence, a
Morse–Bott cost with one global minimum and no other local minima. Corollary
21, p. 22 gives convergence of full-group error to the stabilizer, rather than
unconditional identification of every original state coordinate.

**Implementable consequence.** A future pose/geometry sensor-fusion provider
can declare its manifold, action, output map, observable quotient, innovation,
and verified assumptions. These results do not automatically qualify a generic
Kalman filter, thermal/cavity observer, or learned flow model. A single pressure
threshold arrival event does not uniquely reconstruct a full melt front;
external camera images and process telemetry do not uniquely recover an
unmeasured internal thickness field. Retain explicit unobservable quantities,
model assumptions, and validation requirements instead of filling them with
LLM-generated certainty.

## Prioritized extensions and acceptance evidence

These are research-grounded next steps, not claims that all are implemented.
They extend the current evidence, estimation, metrology, copilot, and operation
boundaries without creating a second authority store.

| Priority | Extension | Minimal implementation | Evidence needed before stronger claim |
|---|---|---|---|
| 1 | Cycle attribution and actuator settling | Bind part/cycle/snapshot identities; configurable minimum cycle distance and action-effective cycle | Replay with delayed measurements; verify no early correction or incorrect action attribution |
| 1 | Leakage-resistant data partition audit | Original-cycle/group IDs, split-before-augmentation manifest, chronological and lot/tool/machine holdouts | Verify disjoint provenance groups; report performance by held-out domain |
| 1 | Quality-aware, abstaining state handoff | Structured quality, missingness, freshness, drift, uncertainty, source/model identities | Corrupted/missing/degraded-channel replays; verify no confident answer from insufficient evidence |
| 2 | Explainable baseline quality model | Deterministic phase features and a versioned small-model provider contract | Independently labeled parts and metrology; calibration and latency on target hardware |
| 2 | Multi-rate acquisition manifest | Distinguish source bandwidth, sampling/transport rate, alignment, and validity horizon | Clock-offset and packet-delay tests plus traceable physical calibration |
| 2 | Cycle-bounded candidate search | Finite admissible grid, simulator prediction, explicit objective, dwell and numerical checks | Model-error tests, sensitivity/robustness analysis, plant commissioning for any live adapter |
| 3 | Quantitative image/3D metrology | External qualified image/geometry provider with frame and uncertainty output | Traceable artifacts, measurement-system analysis, reflective/translucent surface cases |
| 3 | Blow-molding internal observer | Declared parison/stretch/wall-thickness model and observation map | Independent thickness measurements and identification/observability evidence across resins/geometries |

None of these supplied sources demonstrates a general 1,000× polymer solver,
millisecond complete-part dimensional verification, universal structural
weld-line assessment, or directly observed in-tool blow-molding thickness.
Those remain separately testable capability targets. Low-cost deterministic
replay and explicit contracts can be built now; credible physical claims require
the corresponding measurements and domain-qualified models.
