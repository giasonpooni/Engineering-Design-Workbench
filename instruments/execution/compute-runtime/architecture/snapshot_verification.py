"""Hosted-binding verification boundary: pin_accepted + behavioral_canary.

No hosted model binding is instantiated in this repository (inspected:
no API client, key, or call site). This module is therefore the
BOUNDARY those bindings must pass through when instantiated -- real
machinery, exercised today against the repository's deterministic
extractor as the reference binding, never a fabricated probe:

  pin_accepted        the binding's startup probe ran and accepted the
                      pinned identifier. Detects deprecation,
                      revocation, typo, misconfiguration. CANNOT detect
                      served-weight substitution behind a stable id --
                      stated, not papered over.

  behavioral_canary   fixed in-repo fixtures with fixed labels, scored
                      on task-relevant STRUCTURED FIELDS (never raw
                      output hashes -- hosted inference is not
                      bit-deterministic). The noise floor is MEASURED
                      by repeated runs against the same binding; the
                      threshold derives from it and both are committed
                      with provenance. A score drop beyond threshold
                      HALTS ingest, surfaces the diff, and requires a
                      human re-pin.

Residual (recorded, load-bearing): behavioral drift behind a stable
identifier is detectable but not provable, and drift smaller than the
noise floor is undetectable by construction. The canary makes drift
loud; it does not make hosted execution reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence, Tuple


class SnapshotVerificationError(RuntimeError):
    """Fail closed: the binding must not serve ingest."""


@dataclass(frozen=True)
class CanaryFixture:
    """One fixture: the input and the labeled structured fields the
    binding's output is scored against."""

    fixture_id: str
    payload: str
    expected_fields: Mapping[str, object]


@dataclass(frozen=True)
class CanaryCalibration:
    """The committed calibration: measured noise floor and the derived
    threshold, with the run count that measured it."""

    binding_id: str
    fixture_version: str
    runs: int
    noise_floor: float   # max observed score deviation across repeats
    threshold: float     # accepted deviation; must be >= noise_floor

    def __post_init__(self):
        if self.threshold < self.noise_floor:
            raise SnapshotVerificationError(
                "a threshold below the measured noise floor guarantees "
                "false positives; recalibrate"
            )


def pin_accepted(binding_id: str, probe: Callable[[str], bool]) -> None:
    """Startup probe against the pinned identifier; fail closed."""
    if not probe(binding_id):
        raise SnapshotVerificationError(
            f"binding {binding_id!r} did not accept its pinned identifier "
            f"(deprecated, revoked, or misconfigured); ingest must not start"
        )


def score_fixture(expected: Mapping[str, object], actual: Mapping[str, object]) -> float:
    """Field-level agreement on the labeled structured fields: the
    fraction of expected fields the output reproduced exactly.
    Structured comparison -- never a raw output hash."""
    if not expected:
        raise SnapshotVerificationError("a fixture with no labeled fields scores nothing")
    agreed = sum(1 for key, value in expected.items() if actual.get(key) == value)
    return agreed / len(expected)


def measure_noise_floor(
    fixtures: Sequence[CanaryFixture],
    run: Callable[[CanaryFixture], Mapping[str, object]],
    runs: int,
) -> Tuple[float, Tuple[float, ...]]:
    """Repeated runs against the SAME binding: the noise floor is the
    largest score deviation observed between repeats. For a
    deterministic binding this measures exactly 0.0."""
    if runs < 2:
        raise SnapshotVerificationError("a noise floor needs at least 2 runs")
    per_run = []
    for _ in range(runs):
        scores = [score_fixture(f.expected_fields, run(f)) for f in fixtures]
        per_run.append(sum(scores) / len(scores))
    floor = max(per_run) - min(per_run)
    return floor, tuple(per_run)


def behavioral_canary(
    fixtures: Sequence[CanaryFixture],
    run: Callable[[CanaryFixture], Mapping[str, object]],
    calibration: CanaryCalibration,
) -> float:
    """The deployment-time canary: score the binding on the committed
    fixtures; a drop beyond (1 - threshold) from perfect agreement,
    relative to the calibrated expectation, halts ingest with the diff
    surfaced. Returns the score on success."""
    scores = {f.fixture_id: score_fixture(f.expected_fields, run(f)) for f in fixtures}
    mean = sum(scores.values()) / len(scores)
    if mean < 1.0 - calibration.threshold:
        failing = {fid: s for fid, s in scores.items() if s < 1.0}
        raise SnapshotVerificationError(
            f"behavioral canary breach for {calibration.binding_id!r}: mean "
            f"agreement {mean:.3f} < {1.0 - calibration.threshold:.3f} "
            f"(threshold {calibration.threshold}, noise floor "
            f"{calibration.noise_floor}); HALT INGEST; per-fixture diffs: "
            f"{failing}; human re-pin required"
        )
    return mean
