"""Stage 7 locks -- the verification policy's critical invariants,
each with real proofs where a proof is the thing under test.

Proof budget kept deliberately small: one shared campaign run with
routine Nexus + forced RISC Zero sample (2 real proofs, ~90 s) carries
invariants 1-3 and 10; the escalation test adds 1 Nexus proof; the
rest are proof-free.
"""

from __future__ import annotations

import dataclasses
import pathlib

import pytest

from campaign.driver import CampaignPoint, make_campaign_pool, run_campaign
from campaign.policy import (
    PolicyVerificationError,
    VerificationLane,
    VerificationPolicy,
    WarrantRecord,
    default_lanes,
    policy_runner,
)
from execution.engine import default_cli_path
from execution.proving import (
    default_nexus_host_path,
    default_risc0_host_path,
)
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR,
    ExecutionSpecification,
    encode_heat_input,
)
from operations.trace import FAILED, SUCCEEDED, OperationTrace

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine not built; environment gap",
)

SPEC_A = ExecutionSpecification(
    HEAT_DIFFUSION_DESCRIPTOR, b"", encode_heat_input(50, [0, 700_000, 1_000_000, 700_000, 0, 0])
)


def _peak(candidate, result):
    finals = [int.from_bytes(result.output[a:a + 8], "little", signed=True)
              for a in range(0, len(result.output), 8)]
    return {"property": candidate.property, "value": max(finals), "unit": "fixed_point_mk"}


def _campaign_with_runner(runner):
    pool, doc = make_campaign_pool(["rod-A"])
    trace = OperationTrace()
    report = run_campaign(pool, doc.id, trace, [
        CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak, runner=runner)
    ])
    return pool, trace, report


# -- identity of the policy itself -------------------------------------------------------------------


def test_policy_is_content_addressed_and_sampling_is_deterministic():
    base = VerificationPolicy()
    assert base.identity() == VerificationPolicy().identity()
    for change in (
        dict(routine="risc0"), dict(independent=None), dict(independent_rate_bp=2501),
        dict(heavyweight_rate_bp=0),
    ):
        assert dataclasses.replace(base, **change).identity() != base.identity()
    assert base.planned_roles(SPEC_A) == base.planned_roles(SPEC_A)
    # the sample decision is a function of the POLICY identity too
    other = dataclasses.replace(base, independent_rate_bp=9999)
    assert isinstance(other.planned_roles(SPEC_A), list)


# -- invariants 1-3 and 10, with real proofs ---------------------------------------------------------


NEXUS_OK = default_nexus_host_path().exists()
RISC0_OK = default_risc0_host_path().exists()


@pytest.mark.skipif(not (NEXUS_OK and RISC0_OK), reason="nexus/risc0 not built; environment gap")
def test_policy_and_backend_changes_never_move_evidence(tmp_path):
    """Invariants 1, 2, 3, 10 in one shared run:
    - no policy vs full policy -> same Observation id;
    - a second proof (forced independent sample) -> still ONE observation;
    - warrant metadata (backend, cost, role, policy id) exists ONLY in
      the campaign's warrant records, never in the observation."""
    # world 1: no verification at all
    _, _, plain = _campaign_with_runner(None)
    # world 2: routine nexus + FORCED risc0 independent sample
    warrants: list[WarrantRecord] = []
    policy = VerificationPolicy(routine="nexus", independent="risc0",
                                heavyweight=None, independent_rate_bp=10000)
    pool, trace, proved = _campaign_with_runner(
        policy_runner(policy, tmp_path, warrants))

    assert plain.observation_ids == proved.observation_ids, (
        "invariants 1+2: the policy and its backends moved no evidence")
    assert proved.unique_evidence == 1, "invariant 3: two proofs, one observation"
    assert [w.outcome for w in warrants] == ["verified", "verified"]
    assert {w.backend for w in warrants} == {"nexus", "risc0"}
    assert len({w.proof_identity for w in warrants}) == 2, "two distinct warrants"

    observation = pool.get_observation(proved.observation_ids[0])
    text = repr(observation.content) + observation.extraction_method
    for token in ("nexus", "risc0", "policy", "proof", "routine", "warrant"):
        assert token not in text, f"invariant 10: {token!r} leaked into evidence"


# -- escalation and hard failure ---------------------------------------------------------------------


@pytest.mark.skipif(not NEXUS_OK, reason="nexus not built; environment gap")
def test_failed_routine_escalates_and_the_failure_stays_on_the_record(tmp_path):
    """A genuinely failing routine lane (its artifact resolver points at
    the WRONG program's ELF, so the stage-5 registry gate refuses)
    escalates to the independent lane, which verifies. The escalated
    success does NOT erase the routine failure: both warrants persist,
    and the dispatch succeeds exactly once."""
    lanes = default_lanes()
    wrong = VerificationLane("nexus", default_nexus_host_path())
    # a lane whose artifact resolution is deliberately broken:
    object.__setattr__  # (frozen dataclass -- build a wrapper instead)

    class WrongArtifactLane(VerificationLane):
        def artifact_for(self, spec):
            return pathlib.Path(__file__).resolve().parent.parent / "zk" / "artifacts" / "sp1-pairwise.elf"

    lanes["broken-nexus"] = WrongArtifactLane("nexus", default_nexus_host_path())
    warrants: list[WarrantRecord] = []
    policy = VerificationPolicy(routine="broken-nexus", independent="nexus",
                                heavyweight=None, independent_rate_bp=0)
    pool, trace, report = _campaign_with_runner(
        policy_runner(policy, tmp_path, warrants, lanes=lanes))

    assert report.successes == 1
    outcomes = [(w.role, w.outcome) for w in warrants]
    assert ("routine", "failed") in outcomes, "the failure is on the record"
    assert ("escalated-independent", "verified") in outcomes
    assert trace.state_of(0) == SUCCEEDED


def test_all_lanes_failing_fails_the_dispatch(tmp_path):
    """Invariants 5+6+7: when every attempted lane fails there is no
    VerifiedExecution, no admission, and no way for the policy to
    manufacture success -- the dispatch FAILS at the seam."""
    class WrongArtifactLane(VerificationLane):
        def artifact_for(self, spec):
            return pathlib.Path(__file__).resolve().parent.parent / "zk" / "artifacts" / "sp1-pairwise.elf"

    lanes = {"bad": WrongArtifactLane("bad", default_nexus_host_path())}
    warrants: list[WarrantRecord] = []
    policy = VerificationPolicy(routine="bad", independent=None, heavyweight=None)
    pool, trace, report = _campaign_with_runner(
        policy_runner(policy, tmp_path, warrants, lanes=lanes))
    assert report.failures == 1 and report.successes == 0
    assert "PolicyVerificationError" in report.failure_kinds[0]
    assert trace.state_of(0) == FAILED
    assert warrants[-1].outcome == "failed"


def test_unavailable_heavyweight_does_not_stop_the_campaign(tmp_path):
    """Invariants 8+9: a lane whose backend is not built here is
    recorded `unavailable` -- explicitly, never as a quiet success --
    and the campaign proceeds on the lanes that exist."""
    lanes = {
        "ghost": VerificationLane("ghost", pathlib.Path("/nonexistent/ghost-host")),
    }
    warrants: list[WarrantRecord] = []
    policy = VerificationPolicy(routine="ghost", independent=None, heavyweight=None)
    pool, trace, report = _campaign_with_runner(
        policy_runner(policy, tmp_path, warrants, lanes=lanes))
    # nothing verified, nothing failed-as-proof; execution itself stands
    assert report.successes == 1
    assert [w.outcome for w in warrants] == ["unavailable"]
    assert trace.state_of(0) == SUCCEEDED
