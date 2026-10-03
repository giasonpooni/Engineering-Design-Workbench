"""campaign: ORCHESTRATION -- above execution, beside workbench.

Stage 6's own boundary lock caught the first draft of this package
living inside `execution/` while importing evidence machinery. The
execution layer must not touch the pool (that is its contract, tested);
a campaign driver legitimately composes BOTH sides -- pool setup,
experiment steps, execution runners -- which makes it an orchestration
layer, the same altitude as `scout.pipeline` and `workbench`. So it
lives here, and the execution package's boundary stays intact.
"""

from campaign.driver import CampaignPoint, CampaignReport, make_campaign_pool, run_campaign

__all__ = ["CampaignPoint", "CampaignReport", "make_campaign_pool", "run_campaign"]
