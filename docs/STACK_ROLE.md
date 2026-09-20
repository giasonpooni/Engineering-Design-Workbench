# Stack role: streaming telemetry feature extraction

## Stable responsibility

Streaming Telemetry Feature Extraction is the signal-domain instrument that
turns bounded, ordered telemetry windows into declared spectral or temporal
features and stream-quality diagnostics. Its stable responsibility is:

\[
(\text{samples},\ \text{time semantics},\ \text{source references},\
\text{operation configuration})
\longrightarrow
(\text{derived features},\ \text{quality diagnostics}).
\]

This boundary is upstream of state estimation and downstream of acquisition.
It is independently usable and may feed more than one estimator or analysis
workflow.

## Authority matrix

| Concern | Authority |
| --- | --- |
| Source capture and retained raw observations | Provenance-Preserving Data Acquisition / owning evidence subsystem |
| Windowing, filtering and feature computation | Streaming Telemetry Feature Extraction |
| Clock mapping or calibration validity | The referenced clock/calibration artifact and its owning subsystem |
| Geometry and coordinate transforms | Geometric Telemetry Engine or another declared geometry instrument |
| Latent-state estimation and sensor fusion | State-Inferential-Cortex or another declared estimator |
| Constraint correction | Constraint-Based State Reconciliation |
| Stress, fault and estimator evaluation | State Estimation Evaluation Testbed |
| Operation orchestration and replay inspection | Computational Instrumentation Workbench |
| Evidence admission and governed state | Evidence and State Management |

The feature extractor has no authority to rewrite raw evidence, admit canonical
state, declare a physical fault verified, select an operational action or
silently repair another instrument's output.

## Composition boundary

The intended composition is:

\[
\text{raw stream}
\rightarrow
\text{qualified measurements/features}
\rightarrow
\text{state estimate}
\rightarrow
\text{constraint reconciliation}
\rightarrow
\text{evaluation}.
\]

The stream instrument may provide denoised measurements, spectral features,
vibration indicators, signal-quality scores, time-local residual features and
candidate event markers. Downstream consumers must still retain the references
needed to recover the exact source window and operation configuration.

State-Inferential-Cortex remains a separate component because feature
extraction and latent-state inference make different claims. A deterministic
FFT result can be numerically correct even when the measurement is physically
invalid; an estimator can be mathematically coherent while receiving a poorly
conditioned stream. Keeping identities and diagnostics separate makes those
failure modes observable.

## Workbench integration state

The component is registered in the public CIW stack map as a planned provider.
There is currently no executable provider, source pin, adapter, session workflow
or replay path. Documentation registration is not an implemented integration.

An eventual CIW adapter must bind:

- repository revision and operation identifier;
- input artifact references and byte/content digests where applicable;
- window and stream policy;
- causal/offline mode;
- execution environment and implementation version;
- output artifact identities; and
- verification references without collapsing them into the execution record.

The adapter may invoke and inspect the instrument. It may not translate a
feature result into canonical evidence or state without a separately declared
mapping and the owning subsystem's admission process.

## Existing exchange compatibility

The State Estimation Evaluation Testbed validates these existing exchange
schemas:

- `notation.instrument.observation-batch.v1`;
- `notation.instrument.result-artifact.v1`; and
- `notation.instrument.verification-artifact.v1`.

Telemetry windows should reference retained observation batches. Scalar feature
vectors can be projected into a result artifact when component ordering, units,
frame semantics, uncertainty status and input references are explicit.
Frequency arrays, filter state and window policy require a domain extension or
companion artifact. Such an extension is not automatically interchangeable
with the generic schemas and must have an explicit, tested mapping.

## Integration admission gates

The stack should not describe this component as executable or integrated until
all of the following are true:

1. operation semantics and refusal conditions are versioned;
2. the C++ and NumPy references agree within declared tolerances;
3. causal replay proves the absence of future-data leakage;
4. missing, late and out-of-order samples exercise explicit policies;
5. output records retain complete source and execution identity;
6. the SET validator accepts any claimed generic exchange projection;
7. the CIW provider is pinned to a reviewed revision; and
8. the operating guide states implemented limits and failure behavior.

## Public/private boundary

The public repository may contain reusable stream operators, generic contracts,
synthetic fixtures and conformance tests. Customer telemetry, deployment
configuration, proprietary calibration profiles, private detector thresholds,
operational policies and agent prompts remain outside this public interface.
