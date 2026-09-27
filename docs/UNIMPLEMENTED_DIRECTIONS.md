# Unimplemented directions

These notes were removed from the root README so the product page only
describes implemented inspect, calculate and retain paths.

Nothing in this file is a command, a provider, an inspect client, or an
Evidence and State Management admission route. Naming a direction here
does not implement it.

The root README no longer treats these as product features:

| Direction | Status on the product page |
| --- | --- |
| Oscillator demo | Implemented built-in example; not a curriculum |
| OpenUSD scene interchange | Not implemented |
| Julia / C++ / Rust as a required chain | Not required; adapters are optional |
| GPU energy measurement | Optional host bench only |
| Category-theoretic design manifolds | Not an implemented runtime |
| Full mathematics curriculum | Not implemented; one RMS lesson exists |

Related research context: [RESEARCH_CONTEXT.md](RESEARCH_CONTEXT.md),
[JULIA_SP1.md](JULIA_SP1.md), [NATIVE_INTEROP.md](NATIVE_INTEROP.md),
[ENERGY_ACCURACY.md](ENERGY_ACCURACY.md), [LEARNING.md](LEARNING.md).

<a id="unified-mathematical-reasoning-and-learning-layer"></a>
<a id="one-substrate-two-complementary-uses"></a>
<a id="proposed-terminal-surfaces"></a>
### Learning and reasoning direction

**Planned extension after the currently assigned pilot work is completed and
verified.** The existing equation cards and previews are a starting point, not
an implemented universal tutor or theorem prover.

The aim is to teach the same mathematics that users execute in the workbench,
with a concept retaining its identity across explanations, worked examples,
calculations and checks. The proposed surfaces are:

| Surface | Purpose |
| --- | --- |
| `history` | Explain the problems, stories and contributions behind mathematical ideas. |
| `learn` | Develop a concept through examples, mechanism, notation, calculation and verification. |
| `explore` | Inspect, derive, connect and generalize concepts. |
| `work` | Use supported calculations through the existing operation system. |
| `verify` | Inspect the specific checks, bounds or proofs supporting a claim. |

These are **interface proposals**, not commands added by this README. Existing
`ciw` commands remain the operating interface.

<a id="historical-prologue-and-capability-map"></a>
The built-in curriculum is intended to start with a substantial historical
prologue covering the development and roles of mathematical fields, followed by
the shared pedagogy. That programme is **not implemented**; the only executable
lesson is the retained RMS statistics walkthrough.

```text
Historical problem -> example -> mechanism -> mathematical structure
                   -> notation -> computation -> verification -> generalization
```

Users should be able to move between concrete, geometric, symbolic, structural,
formal, computational and research explanations without changing systems.
Learning remains optional for users who simply need to work. A first executable
lesson must reuse the same concept and operation records as its calculation and
checks; it must not introduce a second session, evidence store or execution engine.

<a id="applied-reasoning-and-natural-philosophy-boundary"></a>
This also supports the broader inquiry discussed as **natural philosophy**:
observation, questions, theories, predictions, experiments and revision. The
workbench assists formalization, computation and comparison; it does not replace
human judgment about questions, experiments or what the evidence establishes.
Mathematical proof and empirical validation remain different activities.

## Physical integration direction

**General instrument and equipment integration remains delivery work.** The
longer-term laboratory combines computational studies with supported sensors,
data-acquisition equipment and local controllers. The bounded GPU measurement
path above is not evidence of a general hardware gateway.

A physical workflow must separate:

```text
proposed action -> authorization -> device request -> controller outcome
                                                    -> measured result
```

Each supported device path must bind identity, configuration, units, coordinate
frames, clocks, operating limits and authorization. Local controllers retain
time-critical execution and equipment protections. A recommendation, command
acknowledgement or display update is not proof of a physical outcome.

An optional assistant or future MCP interface may propose work through the same
boundaries; neither receives independent equipment-control or approval authority.
Current CIW scientific operations remain read-only with respect to external
actuators. The target authority modes are Explore, Observe, Prepare and Operate,
not a claim that all four are implemented.

<a id="a-testbed-for-parametric-design-and-representation"></a>
## Research and integration directions

The research question is whether a shared description makes investigations
easier to connect and compare **without losing required meaning, results or
evidence**. Compare a conventional formulation with the shared representation
on the same inputs, independent references and declared tolerances. Include
invalid and held-out cases, and measure representation size, integration effort,
error and execution/checking costs separately.

This is a research programme, not a demonstrated universal compiler or a measured
compression advantage. Broader physics, chemistry/materials, biology, agriculture,
AEC, logistics, manufacturing, robotics and social-modelling coverage requires
separately supported models, providers and validation. The learning benefit also
needs to be tested rather than inferred from the architecture.

<a id="kernel-architecture"></a>
<a id="computational-kernel-families"></a>
<a id="language-boundaries"></a>
<a id="sensor-fusion"></a>
<a id="qualification-and-next-executable-slice"></a>
### Extending calculations and sensor fusion

A **computational kernel** performs one bounded mathematical operation. The
existing and proposed work is organized into six families: numerical algebra and
local response; dynamics and geometry; inference and sensor fusion; constraint
reconciliation; design and experiment selection; and claim/certificate checking.
These are responsibilities, not six new services or a completed universal library.

Extensions reuse existing providers and the CIW/SCR interfaces. Python remains
responsible for the shared session and records; Julia and C/C++ supply selected
scientific calculations; Rust supplies supported native execution and checks.
JuMP and JuliaControl remain candidate extensions. SP1 applies only to selected
registered computations, not automatically to Julia output or physical truth.
See [Julia/SP1 contracts](docs/JULIA_SP1.md) and [integration coverage](docs/INTEGRATION_COVERAGE.md).

The next numerical extension starts with an actual bounded linear-response or
oscillator request, an independent reference comparison and retained results.
A subsequent two-sensor case must preserve clock/frame mappings, shared errors,
full required covariance, pre-update predictions and innovations. Duplicate
observations must not add information twice; missing and late data need explicit
handling. The [covariance guide](docs/COVARIANCE.md) records current limits.

<a id="kernel-contracts"></a>
<details>
<summary>Implementation requirements for numerical extensions</summary>

- Declare input/output order, units, frames, clocks, sample support, model identity,
  allowed changes and validity domain. Linearization must name its base point;
  vector subtraction is not assumed valid for every state space.
- Record arithmetic, tolerances, algorithm/runtime versions, resource limits,
  and any random-stream and replay policy. Distinguish exact, approximate and
  stochastic claims; matching software versions do not guarantee bitwise equality.
- Preserve dependencies and the uncertainty representation a model requires.
  Unknown uncertainty is not zero; covariance is not appropriate for every model.
  Keep original observations and pre-correction residuals when computing corrections.
- Keep numerical routines separate from storage, policy and device I/O. Use bounded
  process messages where isolation is needed; in-process bindings require tested
  ownership, buffer layout, endianness, version and error-handling rules.
- Retain transport bytes and any canonical semantic representation separately.
  Saved data must not select arbitrary imports, code or executable paths; worker
  failure must not become an empty successful result.
- Challenge duplicate, dropout, late-data, shared-error and stale-binding cases.
  Unsupported cross-covariance or rank-deficient inference must be explicit.
  A satisfied balance constraint alone does not identify a faulty sensor.
- Exercise real providers, bounded failure recovery, provider-free reopening and
  fresh replay. Proof-enabled paths require genuine proof production, independent
  verification and rejection of corrupted or mismatched claims. Skipped checks
  are not passes.

</details>

<a id="testbed-framework-and-design-spaces"></a>
### Advanced descriptions of design spaces

A smooth family of designs may use local coordinates and a manifold description;
other designs may be discrete or mix both. **Parametric design manifolds** name
that specialized research case, not every investigation. It is not an
implemented runtime. Equivalence-based model
descriptions, topology and category-theoretic composition are tools to use where
a workload requires them, not prerequisites for running Notations.

Changing coordinates, reducing a model, losing information in an encoding and
coupling two physical models are different operations. A change of domain is not
automatically a new chart on the same manifold. Required calculation inputs must
survive a representation change; preserving one invariant alone is insufficient.
The existing [research context](docs/RESEARCH_CONTEXT.md) and
[state transformation contract](docs/STATE_TRANSFORMATIONS.md) describe this work.

## OpenUSD scene interchange

**Selected direction; implementation pending.** OpenUSD is intended to export
supported geometry and trajectories for inspection alongside the existing
scientific records. It does not replace the investigation, model or evidence
formats. Godot, geographic inspection and terminal-only use remain independent
of an OpenUSD installation.

Start with a read-only `.usda` export of one retained oscillator trajectory.
Reopen it with a pinned OpenUSD runtime and compare geometry, units, time mapping
and links to the original result. Challenge missing or altered dependencies
before claiming that export supported. Binary `.usdc`, packaged `.usdz` and
scene import are later, separately tested extensions.

<details>
<summary>Scene-export requirements</summary>

Use the upstream C++ API or Python bindings behind a registered adapter, rather
than inventing another scene format. Prims and transforms describe supported
assets and spatial outputs; layers and references compose scene assets; variant
sets expose selected configurations; time samples display trajectories; metadata
links them to separately retained model and result identities.

Preserve explicit `metersPerUnit`, `upAxis`, coordinate/frame mappings and
`timeCodesPerSecond` where relevant. Keep source clocks, epochs, offsets, sample
support and interpolation policy separate; interpolated display values are not
new observations. Mixed-unit assets require explicit corrective transforms.

Keep Notations investigation and result identifiers separate from scene paths. Bind contributing asset/layer
digests, layer order, selected variants and exporter/runtime identity; hashing
only the root file does not bind an externally referenced scene. Declare any
supported schema subset, tessellation, decimation or precision loss.

Missing references or unsupported geometry must not be silently approximated.
Only configured, bounded assets and host-controlled plugins/resolvers may be
used. Loading a scene cannot authorize network access, arbitrary execution,
scientific operations or equipment control. Future scene edits/imports enter as
new candidate evidence and require domain checks, never silent source replacement.
Retain original domain files, including IFC, chemistry mechanisms and numerical
arrays. Appearance materials are not validated physical properties.

Scene composition and scientific-operation composition remain separate. Keep
provider-free scientific reopening separate from optional scene inspection.
Upstream references: [OpenUSD introduction](https://openusd.org/release/intro.html),
[units](https://openusd.org/release/api/group___usd_geom_linear_units__group.html),
[stage/time APIs](https://openusd.org/release/api/class_usd_stage.html) and
[Python tutorials](https://openusd.org/release/tut_usd_tutorials.html).

</details>
