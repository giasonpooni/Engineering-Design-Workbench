# Kernel

This repository owns the schematic IR and eligibility routing.
It does not own A, V, samples, or dispositions.

A fixture A is tagged fixture=true and does not open PLSR.
The adapter in schematics.adapters.jspt wraps jacobian_at against
giasonpooni/Jacobian-Sensitivity-Propagation-Testbed@7399ab03087b27683620b4c57f97b2ac14546c7f.
Missing sensitivity is NOT_CHECKED, not a sample.
RCI digest binding records the supplied digest. The separate record-binding path
validates a supplied measurement record; neither path acquires a physical sample.

## Content-bound Jacobian routing

`call_jacobian_at` adds a `NsJacobianBinding@0.1` binding to its certificate.
The declaration identity covers the function attributes and ordered wired port
declarations, including declared axes, units, chart, frame and model parameters.
The actual call-input snapshot records `model_ref`, finite `x_star`, and the
effective `c` for quadratic drag; catalogue models use their declared revision's
reference defaults. Derived `rank`, `invisible_dim` and later `sigma_x` queries
are excluded from the Jacobian declaration identity. Other attribute or port
order changes conservatively invalidate the old record.

Each call has a separate `sra-execution:` occurrence ID. Its result commitment
binds the finite Jacobian matrix, declaration, actual input snapshot, operation,
declared kernel pin, occurrence and provenance limitations. These are **content
consistency checks, not execution authentication**. Records self-report
`adapter_call_record`; source revision is `declared_pin_not_verified` and no
independent verification is claimed. The live suite checks installed dependency
revision metadata separately. Authors who can rewrite whole records can
recompute hashes, so origin trust remains an external responsibility.

Dependent covariance, local-structure and Lyapunov calls require one unambiguous
current certificate with explicit `fixture=false`, the Jacobian operation and a
matching binding. Legacy authored annotations remain readable but cannot open
these routes. A failed or unavailable rerun invalidates the current record;
multiple current records require explicit resolution. This is numerical routing,
not permission to operate physical equipment. On `run`, stale downstream records
retain numeric values and `historical_result`, but become `NOT_ELIGIBLE` with
`currentness=stale`; their old values must not be used as current results.
Covariance and Monte Carlo records also retain and compare their own `sigma_x`
input; changing or removing it invalidates those records without invalidating
the Jacobian. Refused/unavailable reruns retain the prior sample under
`historical_sample` rather than discarding its numerical evidence.

Malformed or nonfinite covariance declarations produce `REFUSED`; missing
covariance remains `NOT_ELIGIBLE`. PSD validation still belongs to the numerical
kernel. JSON reads reject unknown/conflicting declared schematic schemas; legacy
payloads with no schema remain readable as the existing IR. USDA remains a
display projection, not a lossless execution-record interchange; replay uses JSON.
