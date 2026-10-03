# Polymer processing workload

This workload extends NET's existing Session, operation, retained-evidence, and
verification substrate for polymer processing. It is a development instrument
for Notation Systems Inc., with applications in Notations Manufacturing and
Notations Laboratories. It supports `injection_molding` and
`extrusion_blow_molding` as explicit, distinct process identities.

The current implementation accepts retained quantitative sensor features,
assesses declared tolerances, runs a bounded engineering reference calculation,
prepares a deterministic copilot context, and exercises a toy control plant.
It does not decode camera images, load a learned engineering model, call an LLM,
access a PLC, or establish physical validation. These interfaces provide a place
to attach qualified sensors, models, and machine adapters later without creating
a second evidence store or merging their authority with numerical verification.

## Operator readiness

Install the project, then run the finite readiness gate:

```bash
python -m pip install '.[dev]'
net polymer doctor
net polymer qualify --output-dir qualification
```

`doctor` reads the fixed local tool contracts without executing or granting them.
`qualify` executes both process profiles, the complete typed agent graphs,
idempotent retries, fresh replays and numerical audits. It saves
`qualification/qualification.json` and each cycle's report. Its scope is the
installed reference instrument; a passing gate does not establish factory
accuracy, trained-model performance or physical commissioning.

For a single usable example with saved outputs:

```bash
net polymer demo --process injection_molding --output-dir injection-demo
net polymer summary injection-demo
net polymer verify injection-demo --output fresh-audit.json
net polymer export injection-demo --output-dir exported-report
```

Open `injection-demo/report/report.html` for a readable retained report.
`measurements.csv` contains every original sample, timestamp, SI unit, declared
standard uncertainty and source/calibration/clock reference. `summary.json`
labels workflow completion, numerical audit, part conformity, model, copilot
and simulated-control outcomes separately. CSV is a marginal projection; it
does not encode joint covariance. The retained native ingress, when supplied,
is also exported intact. These views do not rerun models or modify the source.
Exports and saved receipts use create-only destinations.

The synthetic example deliberately has a nonconforming dimension. A successful
workflow and numerical audit preserve that decision. Copilot context contains
cited documentation leads; it has no LLM inference or established cause.

For agent tooling, use the explicit
[polymer MCP profile](NET_AGENT_PROTOCOL.md#polymer-cycle-profile). The trusted
launch selector and per-operation grants are independent of profile data.

## Run and inspect

After installing the project, run either process fixture through the same NET
workflow:

```bash
net polymer example --process injection_molding --output request.json
net polymer run request.json --output-dir run
net polymer inspect run
net polymer verify run
net polymer replay run --output-dir replay
```

For the extrusion blow molding fixture:

```bash
net polymer example --process extrusion_blow_molding --output blow-request.json
net polymer run blow-request.json --output-dir blow-run
net polymer inspect blow-run
net polymer verify blow-run
net polymer replay blow-run --output-dir blow-replay
```

The example requests contain synthetic measurements, calibration and clock
references, material/tool identities, and documentation fixtures. They are not
facility records or production recipes. Use a different output directory for a
replay so that the original retained run remains available for comparison.

`run` retains `request.json` and the original Session's `workspace.json` in a new
directory. `inspect` validates and reads retained results without new model
execution. `verify` makes a fresh numerical audit with its own verification
identity without rewriting saved results. `replay` executes the retained request
in a new directory, producing new execution/result/verification occurrences.
The request/evidence identity can remain the same while those occurrences differ.

An inspection `PASS` means the declared operation attempts completed and the
retained numerical verification passed. It does not mean the part conforms, the
copilot found a cause, or the model is physically qualified. The example's
dimensional measurement deliberately lies outside its specified interval; that
nonconformance can be correctly calculated and numerically verified.

Add `--summary` to `run`, `inspect` or `replay` for concise decisions while
retaining the full JSON interface. `verify --output audit.json` saves a fresh
verification receipt without rewriting the retained workspace.

## Explicit operations and identities

| Operation | Function | Authority boundary |
| --- | --- | --- |
| `polymer.assess-cycle.v1` | Associate quantitative evidence with a cycle; assess metrology, engineering reference, and a bounded proposal. | Declared inputs and reference calculations do not establish a qualified physical state. |
| `polymer.copilot-context.v1` | Bind the retained assessment to its request and compile scoped documentation and observations. | Prepares data only; performs no LLM inference, diagnosis, parameter change, or grant creation. |
| `polymer.control-simulate.v1` | Evaluate bounded control behavior in a toy plant. | Simulation output is not a machine command or commissioning result. |
| `polymer.verify-cycle.v1` | Independently check numerical interval, cooling, and control-bound consistency. | Numerical consistency is separate from physical validation and execution authority. |

Evidence/request identity, operation identity, execution occurrence, and
verification identity retain their existing NET meanings. A content digest binds
bytes; it does not prove instrument calibration, source authenticity, document
authority, or physical truth. Run and verification records must retain that
distinction even when a numerical check succeeds. Evidence admission and machine
actuation are not performed by this workload.

Copilot and verification operations require the **actual retained assessment
occurrence**. The live Session/runner preflight checks the supplied dependency
against retained results before provider dispatch or result publication; a
fabricated or altered assessment is refused even if it has a valid-looking
content seal. Fixed payload schemas bind its source, process, authority,
result/execution identities, and digest. Workspace restoration also checks these
dependencies. These integrity checks establish record consistency, not physical
truth or source authenticity.

## Quantitative ingress and metrology

The request schema is `ciw.polymer-cycle-request.v1`. Every request binds a
facility, machine, tool, material lot, cycle, and part. Its source kind is either
`synthetic` or `retained_observation`; sensor origins must agree with that
declaration. The retained-observation label is not itself evidence of authenticity
or traceable calibration.

The bounded ingress requires:

- A declared shared frame, aligned clock identity, cycle time interval, maximum
  skew, and freshness allowance for each sensor.
- Exact supported SI units; unit conversion and frame/clock reconciliation occur
  before ingress rather than silently inside this workload.
- Sensor source, calibration, and clock content references, with strictly ordered
  acquisition times, finite readings, and nonnegative declared standard uncertainty.
- A measurement condition of `ejection` or `conditioned`, and explicitly declared
  tolerance bounds, condition, uncertainty multiplier, and specification reference.

Requests are limited to 2 MiB, 32 channels, 4,096 samples per channel, and 16
distinct tolerance quantities. Supported quantities include cavity pressure,
mold/cooling-water/part temperature, part dimension, wall thickness, surface
defect score, vibration RMS, moisture, screw position, and tie-bar strain.
Supported modality labels describe the retained features' declared origin;
`vision_3d` does not activate a camera or perform reconstruction.

Metrology uses the final acquired sample of each channel. Missing and stale
channels remain visible. For multiple fresh channels measuring the same
tolerance quantity, acquisition times must satisfy the declared skew. Cycle
association alone does not imply simultaneous multimodal sampling.

For a reading `y`, declared standard uncertainty `u`, and declared multiplier
`k`, the channel interval is `[y - k*u, y + k*u]`. Multiple channels for one
quantity are combined by taking the smallest lower bound and largest upper
bound. This conservative enclosing interval retains disagreement; it does not
assume independent noise or reduce uncertainty through repeated measurements.

| Result | Decision rule |
| --- | --- |
| `CONFORMING` | The entire combined interval lies inside the declared tolerance. |
| `NONCONFORMING` | The entire interval lies outside the tolerance on one side. |
| `INDETERMINATE` | The interval intersects a tolerance boundary, or required evidence is missing, stale, unaligned, or measured under a different condition. |

These are computations relative to caller-declared uncertainties and
specifications. The implementation does not establish a coverage probability,
calibration traceability, final-part release authority, or structural strength.
A hot dimension at ejection does not satisfy a specification for a conditioned
part merely because its numeric interval would fit the same bounds.

## Retained native ingress

`ciw.polymer_ingress` connects retained `ciw.calibrated-window-session.v1` and
`ciw.acquired-calibrated-window-session.v1` bundles to this workload. It reuses
the existing native bundle readers and performs no acquisition, provider
execution, calibration calculation, or native numerical replay during import.
The acquired path also retains the complete PPDA acquisition graph and selected
snapshot records through its unchanged native child.

An envelope contains the full native bundles, a valid polymer request template,
explicit bindings, the exactly derived request, and a deterministic mapping
receipt. Each binding contains only `sensor_id`, `bundle_ref`, `quantity`,
`modality`, and `max_age_s`. Its `bundle_ref` is the digest of the **full** native
bundle, including any retained verification. Native sensor identity, quantity
semantics, SI output unit, frame and reference clock must match exactly; all
bundles must share the exact epoch. No aliases, unit conversion, epoch rebasing,
value/time/uncertainty overrides, or sample selection are performed. Every native
sample is copied, and the template's sensor rows are wholly replaced.

```python
from ciw.polymer_ingress import make_envelope, derive, validate
from ciw.telemetry import digest

envelope = make_envelope(template, [native_bundle], [{
    "sensor_id": "sensor:dimension",     # exact native calibration identity
    "bundle_ref": digest(native_bundle),
    "quantity": "part_dimension",       # exact native quantity semantics
    "modality": "vision_3d",            # caller-declared quantitative modality
    "max_age_s": 2.0,
}])
request = derive(validate(envelope))
```

Save the envelope as JSON and run it with:

```bash
net polymer run-ingress envelope.json --output-dir imported-run --summary
```

The run retains the envelope as `ingress.json` and
inside the existing source metadata, so offline inspection, verification and
replay can check exact upstream-to-request lineage. `make_envelope`, `validate`
and `derive` return detached data. Their content receipts certify mapping
consistency, without adding execution occurrences or physical authority.

The projection copies each native MCUR corrected value and standard uncertainty
with its TBRT nominal mapped timestamp. Native raw source bytes, calibration and
clock declarations, joint raw covariance, full mapped time/value covariance,
STFE feature, GSIE state, native runtime identities, and retained verification
remain inspectable in the envelope. Pointwise metrology uses the marginal value
uncertainty and the existing conservative interval enclosure; it performs no
averaging or precision gain. Features and posterior estimates are not imported
as instantaneous acquired observations.

The existing reader checks the native source's exact covariance declaration.
The importer checks mapped matrix shape, symmetry and marginal consistency. It
does not rederive or repair native rounded covariance, or certify that the full
mapped matrix is positive semidefinite. The full matrix remains retained; it is
not substituted by a diagonal approximation for a downstream joint calculation.

Native statistical time covariance does not become a deterministic `max_skew_s`
certificate. The template's skew, freshness, cycle/part association and modality
remain caller declarations conditional on nominal coordinates. No validated
cycle membership, acquisition authenticity or traceable calibration follows
from import. If a configured imported pressure channel has nonzero mapped time
uncertainty, the arrival calculation receives an explicitly unbound reserved
identity and abstains. Its full timing covariance remains retained.

The current independent-input cooling model receives explicitly unbound reserved
temperature and boundary identities and reports `ABSTAINED` for native ingress.
The mapping receipt records this withheld binding, and the original template
remains unchanged. This preserves native correlations without quietly projecting
them into a model that assumes independence. A numerical audit may correctly pass
that abstention while physical validation remains unestablished.

The shipped `examples/polymer/native-dimension.bundle.json` is retained output
from actual pinned TBRT, MCUR, STFE, GSIE and SET executions of a **synthetic bench
declaration**. Its two positive dimension readings intentionally do not represent
a real molded part. It supports repeatable offline import checks; regenerating
its native numbers requires those exact provider checkouts. Its uncertainty and
time/value covariance are retained unchanged.

Native envelopes use a bounded, duplicate-key/nonfinite-rejecting JSON reader
and atomic create-only writer. Their 4 MiB file budget includes original native
byte encodings; these retained strings are not truncated to fit the smaller
generic control-document text limit.

Fresh PPDA acquisition was not qualified in this pass because an authenticated
checkout of its exact private pin was unavailable. Acquired import's tests
cover offline graph validation and routing; actual native execution evidence
here covers TBRT, MCUR, STFE, GSIE and SET. The
[readiness record](../validation/polymer/README.md) states this distinction.

Prepare and run that shipped fixture from the repository root:

```bash
net polymer prepare-ingress examples/polymer/native-dimension.template.json \
  --bundle examples/polymer/native-dimension.bundle.json \
  --sensor-id sensor:level --quantity part_dimension --modality vision_3d \
  --max-age-s 2 --output native-envelope.json
net polymer run-ingress native-envelope.json --output-dir native-run --summary
net polymer qualify --ingress native-envelope.json --output-dir qualification
```

`sensor:level` is the retained bench sensor identity; its quantity semantics in
this fixture are explicitly `part_dimension`. Import does not rename or infer
the quantity from that identity.

## Engineering reference and simulated control

The model kind is `lumped_cooling_reference`. It computes a homogeneous lumped
energy balance with characteristic length `L = V/A`, time constant
`tau = rho*cp*V/(h*A)`, and Biot number `Bi = h*V/(A*k)`. For initial part
temperature `T0`, constant cooling boundary temperature `Tb`, and elapsed time
`t`, its prediction is:

```text
T(t) = Tb + (T0 - Tb) * exp(-t/tau)
```

The boundary sensor must declare `cooling_water_temperature`; the input is not
factory ambient temperature. Both the boundary and part-temperature sensors must
be present, fresh under the model's age/skew allowance, and bound to the declared
frame and clock. Temperature and elapsed time must lie in the declared validity
domain. The model also checks `Bi + m*uBi <= maximum_biot <= 0.1`, where `uBi` is
the propagated standard uncertainty and `m` is the declared
`biot_uncertainty_multiplier` (2 in the example). This is a declared numerical
guard, not a confidence guarantee or experimental check of uniform temperature.
Ill-conditioned or unreachable target-temperature times are reported rather than
manufactured into finite recommendations.

This reference assumes uniform part temperature, homogeneous effective material
properties, a constant boundary and heat-transfer coefficient, and negligible
latent heat, radiation, viscous heating, and spatial gradients. It excludes mold
geometry, flow, crystallization, and detailed polymer constitutive behavior.
The required `uncertainty_profile` is `independent_first_order_declared`: analytic
first-order sensitivities propagate the supplied standard uncertainties assuming
independent inputs. This is a model assumption, not an independence finding about
the sensor system. Clock skew is reported separately as a bound, and model
discrepancy is excluded. Validity-domain checks and a numerical verification pass
do not establish those physical assumptions.

For injection molding, `cavity_arrival` reports a **nominal sampled pressure
threshold crossing** at an instrumented location. It returns the bracketing
acquisition times and endpoint pressure uncertainties, not an interpolated
sub-sample arrival time, confidence guarantee, or melt-front identity. A channel
already above the threshold at its first sample is left-censored and abstained.
There is no spatial extrapolation. Extrusion blow molding does not use these
injection-cavity pressure-arrival locations.

The control plan is always `simulation_only`. It supports `cooling_time_s` and,
depending on process identity, `holding_pressure_pa` or `blow_pressure_pa`.
A proposal requires a single fresh, compatible response measurement, determinate
response-specific metrology bound to a matching specification and measurement
condition, a declared nonzero local gain, uncertainty budget, parameter bounds,
maximum step, and gain-validity domain. An unrelated nonconforming quantity cannot
qualify a response whose uncertainty overlaps its tolerance or whose ejection
measurement is incompatible with a conditioned-part specification. Its relaxed
linear correction is bounded by the maximum step and parameter interval. The
gain is declared, not learned from the current cycle or inferred by an LLM.

The required `control.cycle_guard` declares `current_cycle_index`,
`measurement_cycle_index`, `last_adjustment_cycle_index` (or `null`),
`minimum_dwell_cycles`, and `maximum_measurement_delay_cycles`. A future
measurement-cycle declaration is rejected. A proposal abstains if the measurement
is too old, the minimum dwell since the prior adjustment has not elapsed, or the
measurement is not from a cycle after that adjustment. It declares its proposed
trial for `current_cycle_index + 1`. The example uses current and measured cycle
10, prior adjustment cycle 0, a three-cycle dwell, and at most three cycles of
measurement delay. These cycle indices are supplied declarations; a future
machine adapter must independently establish part/cycle attribution and actual
measurement availability.

The toy simulation uses an instantaneous scalar linear plant with a separately
declared actual gain. A simulated interlock dropout permanently halts that run;
an out-of-domain simulated response also halts. These are software behaviors,
not a model of a safety PLC. Toy cycle indices start at the declared current
cycle. After a parameter change, `DWELLING` rows retain the parameter until the
minimum cycle spacing has elapsed; the example retains 20 toy cycles. Each toy
cycle supplies an immediate noiseless observation. Consequently, the simulation
does not represent physical inspection latency, nonlinear flow, machine
dynamics, disturbances, or acquisition uncertainty. It is a standalone declared
plant trial and does not execute the metrology-derived proposal against hardware.

## Copilot context

The copilot performs deterministic, scoped lexical retrieval over retained text.
Documents must declare process applicability and either exact tool/material-lot
scope or general applicability. Inapplicable documents are excluded. Each
document's content reference must match its exact UTF-8 text bytes. The corpus is
bounded to 32 documents, 16 KiB per document, and 128 KiB in total.

The assessment must bind the request's content identity and its declared process,
source kind, and part/cycle identities. Missing, stale, unaligned, indeterminate,
or unbound evidence causes abstention. Matching documents remain untrusted data:
their hashes prove byte integrity, not correct guidance or source authenticity.

When context is available, ranked hypotheses are document-relevance investigation
leads. They are not inferred root causes. Parameter changes remain empty. The
prepared context lists existing NET inspection, observation, comparison, and
candidate methods, subject to separately configured AgentHost grants; listing a
method does not grant its use. Embedded document instructions do not acquire
authority over the host. No provider call or machine actuation occurs.

## Scientific limits

The intended applications need different validation evidence:

| Application | What this workload supplies | Evidence still required |
| --- | --- | --- |
| Inline quality station | Typed quantitative feature ingress and uncertainty-aware interval decisions. | Calibrated acquisition, image/point-cloud processing, measurement-system analysis, latency measurements, and comparison with traceable references. |
| Internal cavity observer | Explicit process and sensor identities, retained curves, and a place for reference calculations. | Sensor placement, tool geometry, qualified forward/inverse models, observability analysis, and independent melt-front or thermal-state measurements. |
| Blow-molding thickness observer | An explicit thickness quantity and an extrusion blow molding process identity. | Direct thickness sensing or a validated process-specific inverse model, including material/rheology and geometry dependence. |
| Process controller | A bounded proposal/simulation/verification seam. | Identified action-response behavior, qualified parameter envelopes, machine adapters, interlocks, commissioning, and measured intervention results. |
| Manufacturing copilot | Evidence-bound context and scoped retained guidance. | A separately configured inference provider, source governance, expert evaluation, and abstention/latency tests on facility tasks. |

Sparse strain, pressure, and temperature signals do not automatically identify a
complete spatial melt-front or wall-thickness field. Any such reconstruction must
be labeled as a model-conditioned estimate and accompanied by uncertainty and
observability limits. Surface classification does not determine weld-line
strength or structural acceptance.

Ambient temperature is not melt temperature. A correlation between ambient
conditions and defects does not establish that lowering injection speed or hold
pressure will correct a particular tool/material combination. Observed process
changes, documented hypotheses, numerical predictions, and qualified causal
interventions remain separate records.

No millisecond inspection budget or solver speedup is claimed for this
implementation. Timing must be measured end to end on the actual acquisition,
hardware, resolution, and output task. LLM orchestration belongs outside a
hard-deadline machine loop; deterministic qualified control and independent
machine interlocks must retain their own execution boundaries.

## Commissioning path

1. **Qualify retained replay.** Confirm units, sample acquisition time, clock
   reconciliation, cycle/cavity/part association, content integrity, missing-data
   behavior, and reproducibility. Preserve separate observed and synthetic labels.
2. **Qualify metrology.** Compare with traceable references; quantify repeatability,
   bias, drift, uncertainty, and thermal conditioning. Validate the selected
   conformity rule and release specification for the actual part.
3. **Qualify engineering models.** Define geometry, resin/rheology, boundary
   conditions, quantities predicted, and operating domain. Split validation by
   campaign, tool, machine, and resin lot. Check uncertainty coverage, sensor
   dropout, and out-of-domain abstention against independent measurements.
4. **Qualify interventions.** Use controlled experiments to identify local action
   effects and settling behavior. Define machine-specific bounds, maximum step,
   cycle boundary, interlocks, fallback, rollback, and independently observed
   outcome. A toy-plant improvement is not evidence of a production improvement.
5. **Qualify assistance.** Evaluate evidence citation, scope binding, instruction
   isolation, abstention, and task correctness with process technicians. Admit
   inference and execution providers separately under existing host policies.

Software tests and replay checks establish implementation behavior. They do not
replace these physical commissioning steps.

The [supplied research register](POLYMER_RESEARCH_REGISTER.md) records a concrete
industrial example in *Polymers* 2022, 14, 3551: molding cycles of 76–95 s and
inspection tasks of 44 s for dimensions, 9 s for camera images, and 8 s for mass.
Its controller spaces actions by multiple cycles, with a longer interval for
mold-temperature changes. These timings are specific to that experiment, but
demonstrate why acquisition, inspection, intervention, and settling delays belong
in an identified production model. Its surface classifier uses holding-pressure
levels mapped to a quality index; it does not validate structural weld strength.
Conflicting dimensional precision statements in that paper must be resolved
before adopting a metrology specification.

The register also flags an augmented-cycle random split in the supplied injection
quality preprint. Group all derivatives of an original physical cycle into the
same data partition and reserve chronological, batch, tool, and machine holdouts
before claiming prospective predictive performance. Wearable sensing reviews
and Lie-group observer theory supply architectural ideas; they do not qualify
polymer hardware or make an unobservable cavity state identifiable.

## Primary references and claim boundaries

The following sources were inspected on 2026-10-03. They motivate the interfaces;
they are not validation evidence for NET.

- [IM-Chat: a multi-agent LLM framework for injection molding knowledge transfer,
  arXiv:2507.15268](https://arxiv.org/pdf/2507.15268). The study reports about 24.4 s
  query latency for GPT-4o, about 40 s for 64 diffusion-generated candidates on an
  RTX 3090, and 13 nondefective products in 15 physical trials. Larger candidate
  tests used a learned surrogate. This supports decision-support research, not a
  millisecond control guarantee.
- [SIMCON: scientific research on its AI
  solver](https://www.simcon.ai/en/solutions/cadmould-ai-solver-scientific-research)
  and [the AI solver
  manifesto](https://www.simcon.ai/en/solutions/cadmould-ai-solver-manifesto).
  Vendor-reported early speedups of 500–1,000 times concern filling scenarios.
  The technical comparison uses two EPYC CPUs for numerical simulation and an
  A100 for AI inference; localized errors can reach double-digit percentages.
  These research-preview results do not establish NET speed or accuracy.
- [Chen, Chen and Gao: capacitive transducer for in-mold monitoring,
  2004](https://researchportal.hkust.edu.hk/en/publications/capacitive-transducer-for-in-mold-monitoring-of-injection-molding/).
  Purpose-built sensing demonstrated melt-front position, flow rate, gate-freeze,
  and overpacking monitoring. This is a concrete instrumentation route rather
  than evidence that arbitrary external signals determine the full cavity state.
- [SPE Blow Molding Division: improved wall-thickness
  measurement](https://www.blowmoldingdivision.org/white). The technical
  presentation describes direct THz measurements on parisons before clamping and
  on molded articles; it does not establish measurement through arbitrary metal
  tooling.
- [RJG: injection molding sensor technology](https://rjginc.com/sensors/) and
  [key process
  parameters](https://rjginc.com/the-8-key-parameters-in-injection-molding-process-optimization-to-avoid-defects/).
  These sources distinguish cavity pressure, temperature, and mold deflection and
  describe multiple interacting process parameters. They do not qualify a
  universal ambient-temperature correction rule.
- [Explainable AI for root-cause analysis in injection molding,
  arXiv:2505.01445](https://arxiv.org/html/2505.01445v1). The experimental study
  documents interacting settings and disagreement among attribution methods.
  Feature attribution alone is not a general proof of physical causation.
- [Kariminejad et al.: Bayesian adaptive experiments for industrial injection
  molding, 2024](https://www.nature.com/articles/s41598-024-80405-2). The study
  validates an in-mold thermal proxy using post-production dimensional metrology,
  illustrating the need to connect immediate process observations with later
  finished-part measurements.
- [Survey of multi-sensor fusion for embodied AI,
  arXiv:2506.19769](https://arxiv.org/html/2506.19769v1). This is general fusion
  background; it is not a polymer-specific dimensional inspection benchmark.
