# Retained FSRT results for GSC

`python -m ciw.fsrt_view` exports one explicitly selected retained FSRT snapshot
execution, including a refusal. It uses the existing `Session.from_workspace`
reader in scratch space. No provider is registered, imported or launched, no
source workspace is modified and no execution/verification identity is created.

```sh
python -m ciw.fsrt_view path/to/workspace.json \
  --execution execution-<32 hexadecimal characters> \
  --expect-workspace-sha256 sha256:<64 hexadecimal characters> \
  --output tank.view.json
```

The expected workspace digest comes from the operator's retained-artifact
selection. The command reports `view_sha256` for the GSC reader. Record this
separately from the view. A hash is content integrity, not publisher identity.
Existing output files are refused; the source is read once within an 8 MiB
budget and the exact frozen bytes are validated. The view is at most 256 KiB.

The new additive `ciw.fsrt-view-envelope.v1` carries an exact UTF-8 `payload`
string and SHA-256. Its `ciw.fsrt-view.v1` payload retains the complete original
execution and result records, source/evidence identities, source ordering,
acquisition timestamps, original clock description, and source description.
A refusal has `result: null` and its original refusal record, not empty estimates.
The reader must hash the string bytes, not reserialize Python JSON in JavaScript.

Both existing `fsrt.tank-reconstruct.v1` and `.v2` are supported. V1 is not
promoted to six-artifact v2. V2 retains all six covariance stages, full matrices,
source order and uncertainty assumptions. A held correction retains the original
posterior and the separately named reconciled-stage record; it does not claim
that a correction was applied. Missing data must not be replaced with estimates.
The registered RCI snapshot builder currently supplies independent complete
channels. This export does not broaden it to missing, correlated-source or
multi-timestamp input assembly, even though standalone FSRT supports some of
those observations. Output covariance cross terms remain intact.

This projection is local inspection material, not an ESM admission, public
release, shared selection bus, live stream, new numerical validation, fault
identification, confidence interval or equipment command. Runtime metadata and
source descriptions are retained and may be sensitive. Export does not authorize
publication. The full workspace remains the audit artifact, including source
calibration records not independently authenticated by this view.

## Qualification

`tests/test_fsrt_view.py` executes the existing approved RCI/FSRT pins on public
synthetic examples: ordinary v2, held correction, a refused model and legacy v1.
It then checks provider-free export, exact record identity, all covariance stages,
rehashed incompatible records, input budgets, duplicate JSON, digest/selection
mismatch and CLI non-overwrite. Provider paths are required; no missing-provider
skip qualifies this gate. The dedicated read-only workflow retains the resulting
workspaces, exported views, digest index, JUnit and wheel.

For provider-free reruns against a checksum-verified downloaded evidence bundle,
set `CIW_FSRT_VIEW_FIXTURES` to its index directory. Such a rerun is not fresh
provider qualification. Existing numerical thresholds, runtime pins and wider
pilot gates are unchanged. The GSC companion extends its existing `/numerics`
viewer; it never calls the FSRT worker. Nothing here deploys a service.
