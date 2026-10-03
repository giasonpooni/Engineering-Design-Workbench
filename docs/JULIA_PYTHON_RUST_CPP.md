# Julia, Python, Rust and C++ across the instrumentation system

This increment connects domain-owned linear responses to the **existing**
`ciw.native-interop.v1` operation. It does not create a second workbench, copy
SCR crates, change provider pins, or require every calculation to visit every
language.

```text
CSE World / Curved-Surface TransferRecord
                    |
       domain-owned plain-data case
          notation.linear-map.v1
                    |
       Python: validate, normalize, bind identity
                    |
       existing CIW native operation
                    |
       SCR / Rust: pinned host and bounded dispatch
                  /   \
       C++ affine       Julia affine
                  \   /
       retained result + independent Python reference check
                    |
       Python: inspect and export a detached numerical view
                    |
       GSC / TypeScript: exact-byte integrity check and read-only quantities
```

## Ownership and executable scope

| Component | Responsibility in this increment |
| --- | --- |
| Python / CIW | Validate the case, retain its identity, call the existing workflow, inspect saved results and explicitly replay. |
| Rust / SCR | Existing process supervision, runtime binding and bounded native dispatch. No Rust source is duplicated here. |
| C++ | Existing `affine-binary64.v1` numerical implementation. |
| Julia | Existing `affine-binary64.v1` alternative, through the same Rust host. |
| State-Estimator-for-BIM | Export selected rows/columns of the actual current World Jacobian and its baseline means. The World, belief and ledger are unchanged. |
| Curved-Surface-Runtime | Export a bounded heading-column displacement from an existing transfer record. Geodesic integration remains in its owner. |
| GSC | Consume detached numerical results. It neither launches providers nor admits evidence/state. |

The existing Julia ODE, control and optimization profiles and C++ force/energy
profile remain available under their own contracts. This change does not port
the BIM inference engine or curved-surface integrator to another language.

## Shared case and normalization

The strict case contains a schema, model owner/kind/full snapshot digest, named
frame, input/output axes (`id`, `unit`, positive `scale`), baseline output,
row-major Jacobian, input delta and explicit claim limits. It supports 1–8
inputs and 1–8 outputs. Shape mismatch, duplicate axes, coerced/nonfinite
numbers, unknown fields and incomplete model digests are refused.

For `y = y0 + J dx`, let `Sx` and `Sy` contain the declared positive scales:

```text
A_native = inverse(Sy) J Sx
b_native = inverse(Sy) y0
x0_native = 0
dx_native = inverse(Sx) dx
y = Sy y_native
```

This is explicit normalization, **not automatic unit conversion**. Units and
frames remain in the case. The entire case digest becomes the native experiment
identity; equal coefficients cannot silently acquire different units, frames or
model provenance. Binary64 arithmetic and the existing native tolerance/budget
are unchanged. Overflow, erased nonzero values and out-of-profile normalized
values are refused rather than clipped or sent to a fallback provider.

A domain adapter computes its own model digest. Retain the original World or
transfer record beside the investigation; a digest is not a replacement for
that artifact and does not authenticate its producer.

## Run and inspect

Install this increment in the existing `ciw` environment. Provision a qualified
SCR host and, for Julia, the complete approved Julia environment according to
[NATIVE_INTEROP.md](NATIVE_INTEROP.md). No case may supply an executable path,
package import or arbitrary code. Runtime paths are separate operator bindings.

```sh
python -m ciw.polyglot_linear_map run case.json --provider cpp --binding runtime.json --output cpp-run.json
python -m ciw.polyglot_linear_map run case.json --provider julia --binding runtime.json --output julia-run.json
python -m ciw.polyglot_linear_map view cpp-run.json --output cpp-view.json
```

Outputs must be new files. A run retains the case and the native bundle, including
the existing fresh reproduction. Inspection validates the existing retained
native bundle and the complete case binding without starting a provider.

The same compiled source can enter an already-open Workbench session without a
new operation registration:

```python
import base64
from ciw.polyglot_linear_map import compile_case
from ciw.telemetry import canonical

session.workbench.bind_workflow("native-interop", {"runtime": binding_file})
source = compile_case(case, "julia")
record = session.workbench.add_source({
    "kind": "native-interop", "label": "Domain linear response",
    "bytes_b64": base64.b64encode(canonical(source)).decode(),
})
result = session.workbench.execute({
    "operation_id": "ciw.native-interop.v1", "source_id": record["source_id"],
})
session.save_workspace(workspace_file)
```

Keep the complete case alongside that workspace: the native source binds its
digest but does not embed its domain metadata. The `run` CLI retains both.

## Visualization boundary

`export_view(run)` emits `notation.linear-map-view-envelope.v1` with an exact
UTF-8 JSON payload string and its full SHA-256 digest. GSC checks those bytes
against a **separately selected** expected digest, rather than reserializing
Python floating-point values in JavaScript. GSC retains the model, frame, units,
provider, execution/result/numerical/verification/runtime identities and signed
quantity changes. These are quantity coordinates, not invented map positions.

A matching digest checks integrity, not sensor authenticity, source-to-binary
attestation, scientific validity, proof or admission. The reader is an import
function; connecting it to a served artifact route or a browser panel is a
separate application integration. No public dataset or service is deployed.

## Qualification and limits

```sh
python -m unittest discover -s tests -p test_polyglot_linear_map.py -v
python scripts/check_polyglot_native.py --binding runtime.json --output-dir new-native-evidence
```

The first command tests contracts, normalization, references and explicitly
labelled projection doubles. **It is not native qualification.** The second
requires real C++ and Julia executions through SCR, fresh reproduction, explicit
replay, provider-free inspect, a case-swap refusal and cross-provider numerical
agreement. Missing bindings, runtimes or dependencies are failures, not skips.
It qualifies only its declared synthetic affine example, not all domain cases.

This increment always records `first-order-mean-response-only`,
`covariance: not_propagated`, `may_authorize: false`, and no physical-validation,
state-admission or SP1-verification claim. Existing covariance functionality
stays in its owners; it is not replaced with zero or silently inferred from
this mean-only result. Nonlinear solves, uncertainty propagation through this
new seam, live equipment and new proof integrations are not implemented here.
