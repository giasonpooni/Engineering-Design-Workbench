"""rank_candidates(utility_set, policy) -> CandidateRankingSet: the
first phase in this pipeline where ranking is intentionally allowed --
still not selection. Every candidate in the input is preserved in the
output; none is dropped, and none is called "bad" or "ineligible"
unless the caller's own policy explicitly puts it last.

`CandidateUtility` (Phase 47) carries exactly one numeric quantity worth
ranking by -- `utility: Optional[float]` -- so `RankingPolicy` does not
need a "which field" selector; there is only one field, and adding a
generic field-name string here would be machinery this architecture has
no second use for yet. What genuinely needs to be an explicit, caller-
stated choice is: which direction is preferred, and what happens to a
candidate whose utility is `None` (Phase 47's own `NOT_DETERMINABLE`,
reused directly here, not redefined).

Two policy fields, both required, no defaults -- the same "an explicit
policy states every rule; nothing is silently assumed" discipline
`materials.selection.SelectionPolicy` (Phase 39) already established:

  direction               -- ASCENDING or DESCENDING.
  unknown_utility_policy  -- UNRANKED (a candidate with `utility=None`
                              gets `rank=None`, listed but never given a
                              rank NUMBER) or RANKED_LAST (it still gets
                              a rank number, always after every
                              determinate-utility candidate, regardless
                              of `direction`).

Tie-break is NOT a policy field: two candidates with equal `utility`
are always ordered by `ActionCandidate.id` (ascending, regardless of
`direction`) -- a structural determinism guarantee this module provides
unconditionally, the same way `materials.candidates`/`materials.evaluation`
/`materials.selection` already order their own output by candidate id
rather than exposing tie-breaking as something a caller configures.

`ranking_status` (RANKED / NOT_DETERMINABLE) is deliberately independent
of whether a `rank` integer was assigned: under RANKED_LAST, a
`None`-utility candidate still receives a rank number (so every
candidate has a defined position to iterate over), but its
`ranking_status` stays NOT_DETERMINABLE -- that number reflects "placed
last by policy," never "determined to be worse than rank N-1" through
any actual utility comparison. Conflating the two would silently imply
a judgment the missing utility never supported.

Each `CandidateRanking` embeds the complete, unmodified `CandidateUtility`
-- the full candidate -> requirement -> gap -> audit -> decision ->
evidence/provenance chain Phase 37-47 already built stays reachable
without duplicating any of it. No new identity system: `candidate_id` is
exactly `ActionCandidate.id` (via `CandidateUtility.candidate_id`),
untouched since Phase 37.

No Bayesian prior, expected-information-gain calculation, probability,
business ontology, optimizer configuration, scheduling, or execution
logic exists anywhere in this module -- it orders what Phase 47 already
computed, nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from materials.utility import NOT_DETERMINABLE, CandidateUtility, CandidateUtilitySet

ASCENDING = "ASCENDING"
DESCENDING = "DESCENDING"
ALL_DIRECTIONS = (ASCENDING, DESCENDING)

UNRANKED = "UNRANKED"
RANKED_LAST = "RANKED_LAST"
ALL_UNKNOWN_UTILITY_POLICIES = (UNRANKED, RANKED_LAST)

RANKED = "RANKED"


@dataclass(frozen=True)
class RankingPolicy:
    """Both fields required, no defaults -- a caller must state the
    ranking rule explicitly."""

    direction: str
    unknown_utility_policy: str

    def __post_init__(self) -> None:
        if self.direction not in ALL_DIRECTIONS:
            raise ValueError(f"RankingPolicy.direction must be one of {ALL_DIRECTIONS}, got {self.direction!r}")
        if self.unknown_utility_policy not in ALL_UNKNOWN_UTILITY_POLICIES:
            raise ValueError(
                f"RankingPolicy.unknown_utility_policy must be one of {ALL_UNKNOWN_UTILITY_POLICIES}, "
                f"got {self.unknown_utility_policy!r}"
            )


@dataclass(frozen=True)
class CandidateRanking:
    """One candidate's ranking result. `utility` is the complete,
    unmodified Phase 47 `CandidateUtility` -- full provenance without
    duplicating any of it. `rank` is 1-based when assigned, `None` only
    under `unknown_utility_policy=UNRANKED` for a `utility=None`
    candidate."""

    candidate_id: str
    utility: CandidateUtility
    rank: Optional[int]
    ranking_status: str


@dataclass(frozen=True)
class CandidateRankingSet:
    process_natural_key: str
    utility_set: CandidateUtilitySet
    policy: RankingPolicy
    rankings: Tuple[CandidateRanking, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rankings", tuple(self.rankings))


def _sign(direction: str) -> int:
    return -1 if direction == DESCENDING else 1


def rank_candidates(utility_set: CandidateUtilitySet, policy: RankingPolicy) -> CandidateRankingSet:
    """Deterministic, side-effect-free, read-only -- takes only a
    CandidateUtilitySet and an explicit RankingPolicy; never mutates
    either argument. Every candidate in `utility_set.utilities` appears
    exactly once in the output, regardless of policy.

    Ordering: candidates with a determinate `utility` are sorted by
    (`utility` per `direction`, `candidate_id` ascending as the
    tie-break) first; candidates with `utility=None` are appended after
    them (in `candidate_id` order among themselves) whether
    `unknown_utility_policy` is UNRANKED (rank=None) or RANKED_LAST
    (rank continues numbering) -- independent of insertion order,
    dict/set iteration, or PYTHONHASHSEED."""
    base_order = tuple(sorted(utility_set.utilities, key=lambda u: u.candidate_id))
    determinate = [u for u in base_order if u.utility is not None]
    indeterminate = [u for u in base_order if u.utility is None]

    sign = _sign(policy.direction)

    def _sort_key(u: CandidateUtility) -> Tuple[float, str]:
        assert u.utility is not None  # guaranteed by the `determinate` filter above
        return (sign * u.utility, u.candidate_id)

    determinate.sort(key=_sort_key)

    rankings = [
        CandidateRanking(candidate_id=u.candidate_id, utility=u, rank=i, ranking_status=RANKED)
        for i, u in enumerate(determinate, start=1)
    ]

    if policy.unknown_utility_policy == RANKED_LAST:
        rankings.extend(
            CandidateRanking(candidate_id=u.candidate_id, utility=u, rank=i, ranking_status=NOT_DETERMINABLE)
            for i, u in enumerate(indeterminate, start=len(determinate) + 1)
        )
    else:  # UNRANKED
        rankings.extend(
            CandidateRanking(candidate_id=u.candidate_id, utility=u, rank=None, ranking_status=NOT_DETERMINABLE)
            for u in indeterminate
        )

    return CandidateRankingSet(
        process_natural_key=utility_set.process_natural_key, utility_set=utility_set,
        policy=policy, rankings=tuple(rankings),
    )
