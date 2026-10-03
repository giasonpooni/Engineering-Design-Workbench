# Observation-design token admission

`ywir.observation-design-token-admission.v1` is a deterministic, advisory
adapter for CIW. It binds token advice to one retained EDSPT selection and
candidate. EDSPT owns observation cost and expected uncertainty reduction;
YWIR owns inference-token admission against caller-declared budgets.

```python
from ywir import evaluate_token_admission, replay_token_admission

request = {
    "schema": "ywir.observation-design-token-request.v1",
    "selection_content_id": "edspt:selection:" + "a" * 64,
    "selected_candidate_id": "tank-2-pressure",
    "budget_unit": "inference_token",
    "department": "exploration",
    "token_budget": 100,
    "requested_tokens": 16,
    "yield_claim": {
        "expected_rank_delta": 0,
        "expected_new_morphism": False,
    },
    "eta_hat": 0.0,
    "similarity_to_store": 0.0,
}
advice = evaluate_token_admission(request)
assert advice["admitted"]
assert replay_token_admission(request, advice) == advice
```

The selection ID in this example is illustrative. CIW must verify it against
the retained EDSPT content and verify the selected candidate is the one EDSPT
returned. A missing selection stops the composition before YWIR. YWIR neither
imports EDSPT nor checks its ranking or scientific model.

Every request field shown above is required; unknown fields are refused.
`inference_token` is the only budget unit. Budget and token counts are strict
nonnegative integers; spending proposals remain subject to the existing
1–4096 burst bound. Yield/similarity inputs must be finite, similarity must lie
in `[0, 1]`, and rank/morphism claims keep the existing core types and meaning.
An expected reduction of measurement uncertainty is not a YWIR rank increase.
The example uses the existing exploration policy with no positive yield claim.

The adapter calls the existing `open_host` and `decide` in a fresh, disposable
context. It cannot access a caller's host, accepted-morphism store or outstanding
reservations. Budgets therefore describe a hypothetical admission context;
repeating advice does not consume or reserve tokens. No close/reindex command,
composition-store import, settlement or physical observation is performed.
Live admission continues to require the existing caller-owned host and the
`reserve` → external work → `settle`/`cancel` lifecycle.

## Identity and replay

| Identity | Meaning |
| --- | --- |
| `selection_content_id` | Caller-verified EDSPT selection content |
| `operation_id` | This versioned YWIR adapter operation |
| `request_content_id` | All explicit request declarations |
| `proposal_content_id` | Existing core proposal bound to the request through its loop |
| `result_content_id` | Full deterministic advisory result |
| Execution and verification occurrence | Fresh CIW envelope identities, outside this result |

The result schema is `ywir.observation-design-token-result.v1` and
`authority_scope` is always `advisory_only`. It includes the status, support
code, selected candidate, declared budget, requested tokens and advisory cap.
No host, decision, reservation or settlement occurrence is exported. This avoids
presenting discarded in-memory host identities as retained execution evidence.
Core runtime occurrence handling and one-use capability checks are unchanged.

IDs use SHA-256 over a namespace, a NUL byte and canonical UTF-8 JSON (sorted
keys, compact separators, finite numbers). Requests retain their explicit JSON
numeric representation; no silent conversion between integer and float occurs.
`replay_token_admission(request, retained)` recomputes the complete result and
compares canonical bytes. A rehashed result with changed admission or budget
still fails. Fresh CIW execution and verification identities surround replay;
the deterministic content IDs remain stable.

This adapter does not verify caller observations, reserve compute, measure
provider tokens, authorize equipment, certify model quality or claim observed
experimental uncertainty reduction. Existing `does_not_claim` values remain
unchanged.
