# Scientific Computation Runtime Stage 7 -- Proof-Cost-Aware Verification Policy

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
Stage 6 measured the ladder; Stage 7 makes it a dial. The policy is a
controller ABOVE the substrate:

    ProofBackend       = capability     (unchanged)
    VerificationPolicy = decision       (campaign/policy.py, new)
    VerifiedExecution  = earned result  (unchanged)
    EvidencePool       = scientific state (untouched)
    OperationTrace     = machine history  (untouched)

## The mechanism (smallest that expresses the four modes)

`VerificationPolicy(routine, independent, heavyweight, rates)` --
content-addressed (`scout.campaign.verification-policy.v1`); sampling is
CONTENT-DRIVEN, not random: whether a spec draws an independent or
heavyweight sample is a pure function of (policy identity, spec
identity, role), so reruns decide identically. `policy_runner` plugs
into the existing `CampaignPoint.runner` slot -- the driver, the seam,
and every identity are untouched.

**One computation, many warrants**: `prove_and_verify` was split so the
scientific execution runs ONCE and each selected lane proves/verifies
against that single result (`prove_and_verify_result`). Warrants are
`WarrantRecord`s -- campaign metadata (backend, role, outcome, proof
identity, measured seconds, policy identity) that never enters any
evidence identity; a lock test greps the admitted observation for every
such token.

**Deterministic escalation**: failed routine -> independent -> heavyweight;
an escalated success keeps the earlier failure ON THE RECORD; all lanes
failing fails the dispatch (FAILED at the seam, nothing admitted).
An unavailable lane is recorded `unavailable` -- explicit, never a quiet
success -- and the campaign proceeds (optional expensive verifiers may
be absent).

## The experiment (real run, larger than stage 6's verified surface)

```text
policy                  : routine=nexus, independent=risc0 @25%,
                          heavyweight=sp1 @8%   (id b9dc819b...)
executions              : 17   successes 15   failures 2
                          (execution failure + downstream rejection;
                           SUCCEEDED=15 FAILED=1 REJECTED=1)
observations / unique   : 15 / 11
warrants                : nexus 15 verified (301.8 s total)
                          risc0 1 independent sample (65.0 s)
                          broken-routine 1 failed -> escalated, verified
                          sp1 0 drawn (content-driven sampling; the
                          lane is live and policy-selectable)
verification coverage   : 11/11 warranted specs; 2 with second-system
                          coverage
total proving time      : 366.8 s
baseline (all-SP1)      : 15 x 299 s = 4485 s
PROOF-COST REDUCTION    : 91.8%
```

## Invariants, verified empirically (tests/test_execution_stage7_policy.py)

1+2. No-policy vs full-policy runs admit the IDENTICAL observation id.
3. A forced second proof (independent sample) creates no second
   observation -- two warrants, one evidence id.
4. Repeats keep minting occurrences (stage-6 locks still standing).
5-7. All-lanes-failed = dispatch FAILED; no VerifiedExecution, no
   admission, no way for the policy to manufacture an outcome.
8-9. Unavailable lanes are explicit records; the campaign runs without
   the expensive verifier.
10. No warrant vocabulary reaches evidence content.

## Next bottleneck (measured, not guessed)

With SP1 policy-contained, routine Nexus proving IS the cost: 301.8 s of
366.8 s total -- and 5 of those 15 proofs were of the SAME specification
(repeats + retry), re-proving an identical statement each time. The
next lever is **warrant reuse**: a proof is a portable artifact, so a
cache keyed by (specification identity, backend, artifact identity) can
answer a repeated statement with re-VERIFICATION of the stored proof
(seconds) instead of re-PROVING (tens of seconds), with zero trust
change -- verification, not trust in the cache, remains the gate.
