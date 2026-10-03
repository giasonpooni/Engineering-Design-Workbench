"""ExperimentPolicy: the policy-selection concern
`docs/EXPERIMENT_ARCHITECTURE.md` §3.2 specifies -- a bundle of
references to already-existing `materials/` policy types, never a new
decision algorithm of its own.

Three fields, all required (no defaults -- the same "an explicit policy
states every rule; nothing is silently assumed" discipline
`materials.selection.SelectionPolicy`/`materials.ranking.RankingPolicy`/
`materials.optimization.OptimizationPolicy` already each established for
themselves):

  selection_policy    -- `materials.selection.SelectionPolicy`, used to
                          build the `ExperimentalCampaign` a chosen
                          candidate's result is admitted against (Phase
                          39's eligibility mechanism -- a DIFFERENT
                          concern from `optimization_policy` below,
                          unchanged since Phase 49: "which candidates
                          could this session design an experiment for
                          at all" versus "which one does it actually run
                          now").

  optimization_policy -- `materials.optimization.OptimizationPolicy`,
                          used with `max_candidates=1` to make the
                          actual decision (Phase 60's own finding:
                          `optimize_candidates` already IS the decision
                          primitive; this package does not add a second
                          one). A caller who supplies a policy with
                          `max_candidates` other than 1 gets exactly
                          `materials.optimization`'s own documented
                          SELECTED-subset semantics -- `experiment.step.
                          run_experiment_step` requires exactly one
                          SELECTED candidate to proceed (see that
                          module for why) and raises otherwise, but does
                          not police `max_candidates`'s value itself.

  utility_input_source -- a plain caller-supplied function,
                          `InformationValueEstimate -> ExperimentUtilityInput`,
                          never a `Protocol` (there is exactly one shape
                          this needs and no second implementation
                          demanding a different one -- the same
                          "structurally ready, not yet necessary, defer"
                          discipline this project has applied
                          repeatedly since Phase 24-26/30). This is
                          exactly Phase 60's own proven composition
                          (`benefit=estimate.estimate, cost=<caller's own
                          number>`), given a place to live -- never a
                          hardcoded `utility = information_value - cost`
                          formula, which this module does not assume on
                          the caller's behalf.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from materials.information import InformationValueEstimate
from materials.optimization import OptimizationPolicy
from materials.selection import SelectionPolicy
from materials.utility import ExperimentUtilityInput


@dataclass(frozen=True)
class ExperimentPolicy:
    selection_policy: SelectionPolicy
    optimization_policy: OptimizationPolicy
    utility_input_source: Callable[[InformationValueEstimate], ExperimentUtilityInput]
