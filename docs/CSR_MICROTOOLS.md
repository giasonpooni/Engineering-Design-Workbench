# Surface Path micro-tools in NET

Three small callable operations, not another instrument launcher or registry.
The provider implements NumPy/sequence APIs and a bounded JSON worker in CSR;
NET binds that worker through its existing `PinnedSubprocessAdapter`, advertises
it through the existing `CapabilityRegistry`, and retains operations in the
existing `ciw.Session`. No solver, second controller or new evidence store is added.

| Tool | Operation | Useful bounded question |
| --- | --- | --- |
| Surface pose error | `csr.pose-propagate.v1` | How does a declared starting offset and heading error propagate? |
| Surface tolerance box | `csr.error-box.v1` | Do deterministic component bounds exceed supplied sampled limits? |
| Surface covariance | `csr.covariance-propagate.v1` | How does the full correlated starting covariance propagate? |

All three advertise `geometry.surface_path`. That capability label is not a
fourth executable operation. The operations are specialized consumers of the
existing general transfer-map kernel. They are useful from scientific notebooks,
industrial alignment/tolerance studies, idealized simulation paths and curved-world
game-development experiments. They do not imply mesh navigation, CAD collision
checking or installed Blender/Godot/Bevy scene adapters.

## Run from the terminal

Install this NET feature branch. In a separate clean CSR checkout, select
`0b00e837c2df3206a3d38b497799f85b72de80f7` (CSR draft PR #7). Its `src` directory and
NumPy must be available to the chosen Python interpreter. Source checkout,
interpreter and dependency identities are captured and checked before/after
execution; a saved workspace cannot select executable bindings.

```sh
net tools catalog
net tools example --operation csr.error-box.v1 > request.json
net tools run --workspace investigation/workspace.json --request request.json --operation csr.error-box.v1 --csr-root /absolute/Curved-Surface-Runtime --csr-revision 0b00e837c2df3206a3d38b497799f85b72de80f7 --output-dir results/surface-001
net tools inspect results/surface-001/workspace.json
net tools replay --workspace results/surface-001/workspace.json --result RESULT_ID_FROM_RUN --csr-root /absolute/Curved-Surface-Runtime --csr-revision 0b00e837c2df3206a3d38b497799f85b72de80f7 --output-dir results/surface-002
```

Replace `investigation/workspace.json` with a real existing NET/CIW workspace.
For a self-contained synthetic context only:

```python
from pathlib import Path
from ciw.instruments import make_demo_run
from ciw.session import Session
Session(make_demo_run(), Path("investigation")).save_workspace(
    Path("investigation/workspace.json"))
```

The recording is explicitly labelled **investigation context only**, not a
computational input or measured calibration for the path. The mathematical input
is the exact retained request. Arclength is never relabelled as elapsed time.
The example produces lateral bounds of 0.002, 0.003 and 0.004 m against a 0.003 m
limit. The last sample fails the tolerance check while the numerical execution
completes successfully.

Outputs must use a fresh directory. Original recording/results/executions remain
unchanged. Provider refusals are saved as refused executions with no numerical
result. Invalid requests are rejected before dispatch. Inspection registers only
trusted structural readers, runs without CSR installed, and never launches the
provider. Reproduction requires an explicitly supplied binding identical to the
original runtime; it creates fresh execution/result IDs and retains both histories.
Its exact-data equality flag is a scoped diagnostic, not a universal determinism
claim or an independent verification certificate.

## Plug into the existing controller

```python
from pathlib import Path
from ciw.csr_microtools import bind_csr, CONTEXT
from ciw.control_plane import experiment, run_graph
from ciw.session import Session

registry = bind_csr(Path("/absolute/Curved-Surface-Runtime"),
                    "0b00e837c2df3206a3d38b497799f85b72de80f7")
session = Session.from_workspace(Path("investigation/workspace.json"),
                                 Path("results/surface-graph"))
session.operations = registry.operations
# request is the decoded JSON request generated above.
plan = experiment("surface-check", model_id="constant-curvature-transverse-jacobi.v1",
    nodes=[{"node_id": "tolerance", "operation_id": "csr.error-box.v1",
            "parameters": {"request": request, "recording_role": CONTEXT},
            "inputs": {}, "depends_on": []}])
report = run_graph(session, plan, registry)
session.save_workspace(Path("results/surface-graph/workspace.json"))
```

`register_csr(existing_registry, explicitly_bound_adapter)` adds these capabilities
to a registry that already contains other providers. No automatic plugin loading,
server/network dependency or change to the existing approved `csg` provider pin is
required. The typed output port is `response: csr.microtool-result.v1` at `data` in
the existing operation result. Downstream typed consumers must be explicitly
implemented; unrelated instruments are not advertised as connected.

## Scientific boundary

This first profile is first-order, constant-curvature transverse Jacobi response
at 1..512 supplied arclength samples. Inputs carry length unit and frame; lateral
and heading-radian coordinates keep their order. Curvature uses inverse squared
length units. Numerical profile bounds and strict finite JSON prevent silent
coercion, underflow-to-zero and unbounded requests.

The box is deterministic rather than root-sum-square uncertainty. Covariance
cross terms are retained using the original CSR covariance guards. No covariance
repair, noise model, confidence level, independent-sample assumption or physical
validity is invented. A PASS does not establish nonlinear finite-displacement
accuracy, continuous-path clearance, machine authority or verified admission.
The saved result remains `verification_id: null`, `not_verified`.

## Qualification and next extraction

`tests/test_csr_microtools.py` checks registry, Session, typed DAG, saved-reader,
identity, refusal, tamper, bounds and replay contracts with explicitly labelled
fixed response fixtures. Those fixtures are not native numerical evidence.
`scripts/check_csr_microtools_native.py` separately executes all three operations
and all three reproductions through the real pinned subprocess; it must fail,
not substitute or skip, when the native provider is unavailable.

The focused Linux/Windows workflow runs contract tests, preserved controller /
scientific regressions, an installed-wheel check and the actual native campaign.
Existing wider repository workflows remain separate gates. Inspect their actual
results; adding a workflow does not establish a passing qualification.

The extraction pattern is now concrete: keep the original kernel, expose a small
array API plus bounded operation, add a typed existing-registry binding, and test
real retained execution. Apply it next to calibration, timestamp reconciliation,
residual diagnostics and sensor-placement candidates rather than creating another
SDK or promoting all research scaffolds to finished tools at once.
