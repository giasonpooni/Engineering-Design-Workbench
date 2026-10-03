"""VerificationPolicy: the proof-cost dial, as a deterministic controller.

Stage 6 measured the ladder -- native ~ms, Nexus ~15 s, RISC Zero ~65 s,
SP1 ~300 s -- and proved evidence identity is blind to the warrant.
Stage 7 turns that into a decision mechanism ABOVE the substrate:

    ProofBackend        = capability   (unchanged)
    VerificationPolicy  = decision     (this module)
    VerifiedExecution   = earned result (unchanged)
    EvidencePool        = scientific state (untouched)
    OperationTrace      = machine history  (untouched)

THE POLICY SELECTS A WARRANT. It cannot manufacture one (every verified
outcome still comes through `prove_and_verify_result`, i.e. real proof +
sealed verification + host recomputation), cannot weaken one (a failed
lane is recorded as failed, never relabeled), and cannot touch evidence
(warrant records live in campaign metadata; nothing here writes a field
an Observation carries).

DETERMINISM: sampling is content-driven, not random -- whether a
specification draws an independent or heavyweight sample is a pure
function of (policy identity, spec identity, role), so a rerun of the
same campaign under the same policy makes identical decisions. A policy
is itself scientific configuration and is content-addressed
(`scout.campaign.verification-policy.v1`).

ESCALATION (deterministic, smallest useful ruleset): a failed routine
lane escalates to the independent lane; a failed independent escalates
to the heavyweight lane; if every attempted lane fails, the dispatch
FAILS (the seam records it; nothing is admitted). An escalated success
is recorded AS escalated -- the earlier failure stays in the record,
never silently absorbed. An unavailable lane (backend not built here)
is recorded as `unavailable` and skipped: optional expensive verifiers
being absent must not stop the campaign (Stage 7 invariant 9), and
skipping is visibly different from verifying.
"""

from __future__ import annotations

import pathlib
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from campaign.warrant_cache import WarrantCache, statement_key
from execution.commitments import commit_hex
from execution.engine import ExecutionResult, run_specification
from execution.proving import (
    ProvedRunError,
    ProvingUnavailable,
    prove_and_verify_result,
    verify_existing_proof,
)
from execution.specification import ExecutionSpecification

POLICY_TAG = "scout.campaign.verification-policy.v1"
SAMPLE_TAG = "scout.campaign.verification-sample.v1"

_REPO = pathlib.Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class VerificationLane:
    """One backend the policy may route to: a name, a host binary, and
    the registry-resolved reproducible artifact per program."""

    name: str
    host_path: pathlib.Path

    def artifact_for(self, spec: ExecutionSpecification) -> Optional[pathlib.Path]:
        try:
            from execution.guest_registry import GUESTS
        except ImportError:
            return None
        entry = GUESTS.get(spec.program_identity(), {}).get(self.name)
        if entry is None:
            return None
        return _REPO / entry["elf_path"]

    def available_for(self, spec: ExecutionSpecification) -> bool:
        artifact = self.artifact_for(spec)
        return self.host_path.exists() and artifact is not None and artifact.exists()

    def verifier_artifact_for(self, spec: ExecutionSpecification) -> Optional[pathlib.Path]:
        """Stage 10: the persisted verification artifact for this lane's
        registered guest, when one has been exported (convention: the
        `.vkart` sibling of the guest ELF). None simply means hits pay
        the per-verification setup -- correctness is identical either
        way, and a PRESENT-but-invalid artifact fails closed in the
        host, never silently falls back."""
        artifact = self.artifact_for(spec)
        if artifact is None:
            return None
        candidate = artifact.with_name(artifact.name + ".vkart")
        return candidate if candidate.exists() else None


def default_lanes() -> dict:
    from execution.proving import (
        default_host_path,
        default_nexus_host_path,
        default_risc0_host_path,
    )

    return {
        "nexus": VerificationLane("nexus", default_nexus_host_path()),
        "risc0": VerificationLane("risc0", default_risc0_host_path()),
        "sp1": VerificationLane("sp1", default_host_path()),
    }


@dataclass(frozen=True)
class VerificationPolicy:
    """The decision table. Content-addressed: two campaigns claiming
    'the same policy' either share this identity or are not running the
    same policy. Rates are in basis points of 10000 for exact integer
    determinism (2500 = 25%)."""

    routine: Optional[str] = "nexus"
    independent: Optional[str] = "risc0"
    heavyweight: Optional[str] = "sp1"
    independent_rate_bp: int = 2500
    heavyweight_rate_bp: int = 800

    def identity(self) -> str:
        canonical = "\n".join([
            "ste-verification-policy v1",
            f"routine {self.routine}",
            f"independent {self.independent} {self.independent_rate_bp}",
            f"heavyweight {self.heavyweight} {self.heavyweight_rate_bp}",
        ]).encode()
        return commit_hex(POLICY_TAG, [canonical])

    def _sampled(self, spec: ExecutionSpecification, role: str, rate_bp: int) -> bool:
        digest = commit_hex(
            SAMPLE_TAG,
            [self.identity().encode(), spec.identity().encode(), role.encode()],
        )
        return int(digest[:8], 16) % 10000 < rate_bp

    def planned_roles(self, spec: ExecutionSpecification) -> List[tuple]:
        """(role, lane-name) pairs this policy selects for `spec` --
        before availability and escalation are considered."""
        plan = []
        if self.routine:
            plan.append(("routine", self.routine))
        if self.independent and self._sampled(spec, "independent", self.independent_rate_bp):
            plan.append(("independent", self.independent))
        if self.heavyweight and self._sampled(spec, "heavyweight", self.heavyweight_rate_bp):
            plan.append(("heavyweight", self.heavyweight))
        return plan


@dataclass(frozen=True)
class WarrantRecord:
    """What one lane did about one execution. CAMPAIGN METADATA -- never
    admitted, never part of any evidence identity, and the tests pin
    that none of these fields reaches an Observation."""

    spec_identity: str
    policy_identity: str
    role: str          # routine | independent | heavyweight | escalated-<role>
    backend: str
    outcome: str       # verified | failed | unavailable
    seconds: float
    proof_identity: Optional[str] = None
    proof_path: Optional[str] = None
    error: Optional[str] = None
    #: Stage 8: how the warrant was obtained. None = no cache in play;
    #: "miss+stored" = freshly proven and stored; "hit" = reused after
    #: mandatory re-verification; "hit-invalid" = the cached artifact
    #: FAILED verification (never silently regenerated); "invalidated"
    #: = the policy's explicit decision to discard a failed warrant
    #: before regenerating. Campaign metadata, never evidence.
    cache: Optional[str] = None


class PolicyVerificationError(RuntimeError):
    """Every attempted lane failed; the dispatch fails with the full
    lane-by-lane record in the message."""


def policy_runner(
    policy: VerificationPolicy,
    proof_dir: pathlib.Path,
    warrant_sink: List[WarrantRecord],
    lanes: Optional[dict] = None,
    cache: Optional[WarrantCache] = None,
    regenerate_invalid: bool = False,
) -> Callable[[ExecutionSpecification], ExecutionResult]:
    """A `SpecificationDispatcher` runner that executes the science ONCE
    and then applies the policy's verification plan to that one result.

    Returns the native `ExecutionResult` unchanged -- the seam, the
    admission path, and every identity downstream are exactly what they
    would be with no policy at all. The warrants land in `warrant_sink`.

    Stage 8: with a `cache`, each lane first looks up the statement key.
    A HIT retrieves the stored proof and MUST still pass the backend
    verifier (`verify_existing_proof`) -- reuse skips PROVING, never
    verification. A hit whose verification fails is recorded
    `hit-invalid` and treated as a failed lane (escalation applies);
    only with `regenerate_invalid=True` does the policy explicitly
    invalidate the entry and prove afresh -- a recorded decision, never
    an automatic repair that would hide corruption."""
    lanes = lanes if lanes is not None else default_lanes()

    def _record(spec, role, lane_name, outcome, started, cache_state=None,
                proof_identity=None, proof_path=None, error=None):
        warrant_sink.append(WarrantRecord(
            spec_identity=spec.identity(), policy_identity=policy.identity(),
            role=role, backend=lane_name, outcome=outcome,
            seconds=time.monotonic() - started, cache=cache_state,
            proof_identity=proof_identity, proof_path=proof_path,
            error=None if error is None else str(error)[:300],
        ))

    def _prove_fresh(role, lane, lane_name, spec, native, started, cache_state):
        proof_out = proof_dir / f"proof-{spec.identity()[:16]}-{lane_name}.bin"
        try:
            proved = prove_and_verify_result(
                native, spec, proof_out, lane.host_path, lane.artifact_for(spec)
            )
        except (ProvedRunError, ProvingUnavailable) as error:
            _record(spec, role, lane_name, "failed", started,
                    cache_state=cache_state, error=error)
            return "failed"
        if cache is not None:
            key = statement_key(lane.name, lane.artifact_for(spec), spec)
            cache.store(key, pathlib.Path(proved.proof_path).read_bytes(),
                        lane.name, spec.identity())
            cache_state = (cache_state or "miss") + "+stored"
        _record(spec, role, lane_name, "verified", started,
                cache_state=cache_state,
                proof_identity=proved.proof_identity, proof_path=proved.proof_path)
        return "verified"

    def _attempt(role, lane_name, spec, native):
        lane = lanes.get(lane_name)
        started = time.monotonic()
        if lane is None or not lane.available_for(spec):
            _record(spec, role, lane_name, "unavailable", started)
            return "unavailable"

        if cache is not None:
            key = statement_key(lane.name, lane.artifact_for(spec), spec)
            hit = cache.lookup(key)
            if hit is not None:
                fields = verify_existing_proof(
                    native, spec, hit.proof_path, lane.host_path,
                    lane.artifact_for(spec),
                    verifier_artifact=lane.verifier_artifact_for(spec),
                )
                if fields.get("outcome") == "verified":
                    _record(spec, role, lane_name, "verified", started,
                            cache_state="hit",
                            proof_identity=fields.get("proof_identity"),
                            proof_path=str(hit.proof_path))
                    return "verified"
                # HIT BUT INVALID: never silently regenerated.
                _record(spec, role, lane_name, "failed", started,
                        cache_state="hit-invalid",
                        error=f"cached warrant failed verification: "
                              f"{fields.get('failure')}; intact={hit.artifact_intact}")
                if regenerate_invalid:
                    cache.invalidate(key)
                    _record(spec, role, lane_name, "invalidated", started,
                            cache_state="invalidated")
                    return _prove_fresh(role, lane, lane_name, spec, native,
                                        time.monotonic(), "regenerated")
                return "failed"
        return _prove_fresh(role, lane, lane_name, spec, native, started,
                            "miss" if cache is not None else None)

    def run(spec: ExecutionSpecification) -> ExecutionResult:
        # ONE scientific execution, checked as always.
        native = run_specification(spec)
        if native.status != "completed":
            raise ProvedRunError(
                f"execution halted (exit {native.exit_code}); nothing to verify"
            )

        plan = policy.planned_roles(spec)
        escalation_order = [r for r in ("routine", "independent", "heavyweight")
                            if getattr(policy, r if r != "routine" else "routine")]
        outcomes = {}
        for role, lane_name in plan:
            outcomes[(role, lane_name)] = _attempt(role, lane_name, spec, native)

        # Deterministic escalation: a FAILED lane escalates to the next
        # rung not already attempted; unavailability does not escalate
        # (absence of a verifier is not evidence of a bad computation).
        attempted = {lane for (_, lane) in plan}
        if any(v == "failed" for v in outcomes.values()):
            for rung in escalation_order:
                lane_name = getattr(policy, rung)
                if lane_name and lane_name not in attempted:
                    attempted.add(lane_name)
                    outcomes[(f"escalated-{rung}", lane_name)] = _attempt(
                        f"escalated-{rung}", lane_name, spec, native
                    )
                    if outcomes[(f"escalated-{rung}", lane_name)] == "verified":
                        break

        results = list(outcomes.values())
        if "failed" in results and "verified" not in results:
            raise PolicyVerificationError(
                f"every attempted verification lane failed for {spec.identity()[:16]}: "
                f"{[(k[0], k[1], v) for k, v in outcomes.items()]}"
            )
        return native

    return run
