# Stack role and authority

MCUR owns the bounded transformation from a referenced indicated measurement, declared calibration profile, and complete joint covariance to a calibration candidate and uncertainty budget.

It extends the existing acquisition, measurement, inference, and verification instruments without taking their authority:

| Instrument or boundary | Retained authority | MCUR relationship |
| --- | --- | --- |
| PPDA | Source bytes, observation identity, extraction lineage, missingness | Accepts an observation reference; never overwrites source evidence. |
| RCI | Measurement adapter behavior and acquisition-facing semantics | Reusable profile and affine mathematics may be consumed through an explicit adapter; the existing measurement boundary remains intact. |
| Jacobian Sensitivity Propagation Testbed (JSPT) | Generalized sensitivity and uncertainty propagation | Shares mathematical concepts, but MCUR remains calibration-specific with sensor identity and applicability checks. |
| GSIE | State estimation, estimator covariance and diagnostics | May consume the corrected measurement and uncertainty candidate; MCUR makes no plant-state or estimator-adequacy assertion. |
| SET / SEET | Exchange contract and evaluation procedures | The optional exporter validates the already defined result-artifact contract at a pinned SET revision. |
| CIW | Evidence/result/execution/verification binding and inspection | The result retains evidence pointers and operation identity; no native workbench binding is claimed. |
| ESM | Admission and governed state transitions | No admission, current-use authorization, or actuation is performed here. |

The public package contains the reference mathematical operation, its typed contract, synthetic demonstrations, and reproducible validation. Actual sensor-specific calibration evidence, proprietary calibration profiles, deployment policy, and operational state are supplied by the consuming system and are not fixtures in this repository.

Numerical eligibility, physical traceability, operational admission, and execution authorization remain separate claims. A valid matrix is a valid matrix under the stated numerical policy; it does not prove that the matrix accurately describes a real measurement process.
