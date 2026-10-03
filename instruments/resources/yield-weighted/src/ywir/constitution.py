"""Frozen numeric law for admission.

These are not user parameters. The caller supplies a loop name, a
department, a token request, and declared observations. They do not
set the yield threshold or the similarity cap. Embeddings, wording,
and plant physics do not live here.
"""

PACKAGE_VERSION = "0.2.0"
INSTRUMENT = "ywir"

DEPARTMENTS = ("ledger", "evidence", "exploration", "gauge")
SHIP_DEPARTMENTS = ("ledger", "evidence")
EXPLORATION_DEPARTMENTS = ("exploration",)
GAUGE_DEPARTMENTS = ("gauge",)

YIELD_THRESHOLD = 0.0
GAUGE_SIMILARITY_CAP = 0.85
MAX_DEPARTMENTS = 4
MIN_TOKENS = 1
MAX_BURST_TOKENS = 4096

# Scalar filter on observed yield. Not a second model.
ETA_BLEND = 0.4

DOES_NOT_CLAIM = (
    "building_safe",
    "lyapunov_certified",
    "jacobian_accuracy",
    "answer_true",
    "publisher_identity",
    "observations_truthful",
    "model_quality",
)
