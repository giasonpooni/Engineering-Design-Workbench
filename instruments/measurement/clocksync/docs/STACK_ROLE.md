# Stack role and integration boundary

TBRT extends the existing instrumentation stack with one derived time coordinate. It owns a supplied clock model's bounded numerical application and first-order uncertainty propagation. Raw acquisition evidence survives unchanged.

| Neighbor | Boundary |
|---|---|
| PPDA | Supplies the original timestamp, explicit clock identity, and source-evidence reference. Source bytes and extraction lineage stay with PPDA. |
| STFE | Can consume reconciled event time for time-dependent stream operations. TBRT does not filter or resample measurements. |
| GSIE | Can consume aligned observation times and time uncertainty. Estimation policy decides how timing uncertainty enters its state and observation models. |
| GTE | Can use aligned epochs where its geometric workload needs them. Clock identity does not replace spatial frame identity. |
| Calibration runtime | Can use aligned event time for an explicitly time-dependent calibration domain. Calibration applicability is not decided by TBRT. |
| SET | Can evaluate a declared timing/estimation workload against its own fixtures and criteria. Successful reconciliation is not an accuracy benchmark. |
| CIW / SCR | Can pin and execute the bounded operation with distinct input, operation, execution, and result references. |
| ESM | Retains evidence admission and canonical-state authority. A derived timestamp does not admit itself. |

The core has no dependencies on those repositories. Optional `tbrt.exchange` exports the existing SET `result-artifact.v1` schema, validated by a source-pinned SET dependency. Its example maps an actual numerical result, retains full input and output payloads, and uses explicitly synthetic execution/revision declarations. This conformance check does not establish live CIW execution integration, independent verification, or evidence admission.

TBRT has no clock-setting, acquisition, dispatch, control, or actuation authority. It does not promote a statistical estimate into observed truth. The original device event time, derived reference event time, receipt time, and knowledge time remain distinct coordinates or metadata.
