# Retained correction and dependency review

This increment extends the existing Session and Workbench. It retains proposed
source replacements, explicit local review decisions and Estimated/Predicted
claim declarations. Accepted reviews mark affected dependencies **stale for
current use**. Original sources, observations, results, executions and provider
verification artifacts retain their exact content and identities.

`current` means that no accepted correction in this journal withdraws a node's
dependencies. It is not a scientific-validity verdict. `stale` records the
correction identities responsible for reevaluation; it does not declare a
historical observation false or erase its acquisition applicability.

## Run the bounded demonstration

From an installed development checkout:

```bash
python scripts/check_correction_loop.py --output-dir results/correction-demo
ciw dependencies results/correction-demo/workspace.json
ciw serve --workspace results/correction-demo/workspace.json --output-dir results/correction-session
ciw send dependency.inspect
```

Use a new demonstration output directory. The fixture is an encoder, gearbox
and leadscrew with a declared homing offset. The existing
`ciw.encoder-position.v1` operation predicts **1.001 m** at 300 decoded counts.
A retained withheld **synthetic** reference is **0.998 m**. Its **0.5 mm**
diagnostic bound flags the **3 mm** residual. A candidate offset change from
1.000 m to 0.997 m is deterministically challenged, retained as a new source,
proposed, and accepted by an explicit demo review request. The new invocation
returns **0.998 m** with fresh execution/result identities.

The script checks inert proposals, transitive claim staleness, exact preservation
of the original artifacts, and complete offline restore. A subsequent historical
execution of the original source stays stale. It retains `workspace.json`,
`correction-journal.json`, the original/corrected/reference fixture files and
`report.json` with identities, digests, numerical comparisons and scope.

The withheld scalar is imported through `source.add` with kind
`reference-evidence`; its actual source identity is a premise of the residual
claim. This data-only source has no executable operation. Its schema declares
origin, quantity, value, unit, frame, timestamp, uncertainty and context. An
`operator_record` origin remains a provenance declaration, not authenticated
physical acquisition. Correcting a reference can mark claims that use it stale
without withdrawing a model output that did not consume that reference.

The initial oscillator recording is the existing Session shell. Encoder sources
and outputs remain native Workbench artifacts; they are not converted into
oscillator samples. No device, live sensor, ESM admission or actuator is involved.
The demo reviewer is a caller declaration, not an authenticated human identity.

## Session requests

All requests use the existing protocol version 1 envelope and can be sent with
`ciw send TYPE --payload-file request.json`. Saved/client data cannot choose an
executable or register a runtime.

| Request | Payload | Effect |
| --- | --- | --- |
| `dependency.inspect` | `{}` | Read the artifact nodes, edges, unresolved native input references, claim declarations, correction reviews and derived current/stale status. |
| `claim.add` | `{claim_type, predicate, scope, basis, dependencies}` | Retain a fresh claim identity linked to existing artifacts or earlier claims. `claim_type` is `estimated` or `predicted`. Predicate/scope/basis are declarations, not executable assertions. |
| `correction.propose` | `{old_source_id, new_source_id, kind, reason}` | Retain a candidate link between existing sources of the same workflow kind with distinct source evidence. No invalidation occurs. `kind` is descriptive text such as `calibration` or `model`. |
| `correction.review` | `{correction_id, decision, expected_revision, reviewer, reason}` | Append one final `accept` or `reject` decision after checking the exact journal revision. Acceptance withdraws the old source from current dependency use. Rejection preserves current status. |

Every claim/proposal/review fixes verification to `not_verified`, admission to
`unadmitted`, and execution authorization to false. Neither a successful model
check nor an accepted local review can alter those fields. Acceptance refuses
an already-stale source or replacement, and a replacement that depends on the
withdrawn source. Revising a review requires a new investigation; v1 does not
silently undo final decisions.

Sources with different labels but the same kind and evidence bytes share the
withdrawal, including aliases added after the decision. Later results deriving
from an old source inherit staleness. Historical computations remain available
for comparison; the journal is not an equipment dispatch policy.

## Dependency scope and persistence

The projection preserves existing evidence, source, bundle, execution and result
identities. Edges include native source links, bundle outputs/upstreams,
residual-monitor window selection, native force/energy trajectory dependencies,
known native input references and legacy JSPT `source_result_id` links. Declared
claims can extend those edges transitively. Unknown native input identities are
exposed as `unresolved_input_refs`; the projection does not infer undocumented
mathematical or physical dependencies. Candidate ESM receipts and external
certificate premises are not part of this v1 computational graph.

Each journal action atomically checkpoints the full **workspace version 4**,
including the candidate event and all retained dependency sources/results,
before publishing the event in memory. `workspace.json` is the recovery object;
the demo's separate journal file is an inspection export. Versions 1–3
remain readable. Restore checks seals, exact fields, source bindings, identity
collisions, chronology, references, acyclic dependencies and review semantics
before writing outputs. Restoring does not execute providers. SHA-256 seals
detect inconsistent content; they do not authenticate the reviewer or prevent
an actor from replacing an entire self-consistent history.

The journal permits 1,024 events, 2 MiB serialized content and 64 dependencies
per claim; the graph permits 32,768 nodes and 262,144 edges. Existing source,
bundle, transport and operation limits continue to apply. `result.get` keeps
the exact retained artifact in its payload and adds `dependency_status` outside
that artifact when a journal exists. `session.get` includes the projection;
clients can fetch it after `dependencies.changed` notifications.

`ciw dependencies WORKSPACE` validates/reopens into disposable output and prints
the projection without writing alongside the retained input. It is a read-only
inspection path, not a replay operation. Explicit workspace saving remains
required after further non-journal work; provider operations and operating
system power-loss recovery retain their existing persistence limitations.

## Open acceptance gates

Physical calibration needs acquired observations, calibrated independent
references, uncertainty and held-out evaluation across the intended domain.
General automated calibration fitting, ESM/canonical admission, authenticated
review, hardware authorization, regulator qualification and hybrid CPS proofs
remain separate work. MCP remains an optional future adapter to these same
operations. The [coverage matrix](INTEGRATION_COVERAGE.md) and
[concerns audit](CONCERNS_AUDIT_2026-10-03.md) name the delivered boundaries.
