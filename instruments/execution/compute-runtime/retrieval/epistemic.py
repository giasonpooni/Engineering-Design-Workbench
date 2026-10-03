"""Epistemic-status classification, reusing the taxonomy
`docs/COMPUTATIONAL_COMMONS.md` §K already established (`observed` /
`extracted` / `inferred` / `hypothesized` / `simulated` / `predicted` /
`validated`) -- NOT a new taxonomy, per this phase's explicit
instruction.

That document's taxonomy was research-only; no code anywhere classified
an `Observation` against it before this module. The classification here
is deliberately conservative: it only maps the `extraction_method`
values that actually occur in this codebase's data
(`docs/SCOUT_ARCHITECTURE.md` §6-9 -- `"regex:..."` from the one
deterministic extractor, `"model:..."` per §K's rule, and
`"human_transcription"`/`"simulation:..."` as documented-but-not-yet-
produced conventions from `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md`
§B/§K). `hypothesized`, `predicted`, and `validated` have no producer
anywhere in this repository yet (no agent proposes hypotheses; no
review/promotion step exists) -- `classify_epistemic_status` never
returns them, rather than guessing at a mapping with no real data behind
it.
"""

from __future__ import annotations

from evidence.types import Observation

OBSERVED = "observed"
EXTRACTED = "extracted"
INFERRED = "inferred"
SIMULATED = "simulated"

# The full taxonomy from docs/COMPUTATIONAL_COMMONS.md §K, for reference
# and for anything downstream that wants to validate against the whole
# set -- HYPOTHESIZED/PREDICTED/VALIDATED are deliberately unreachable
# from classify_epistemic_status (see module docstring).
HYPOTHESIZED = "hypothesized"
PREDICTED = "predicted"
VALIDATED = "validated"

ALL_STATUSES = (OBSERVED, EXTRACTED, INFERRED, SIMULATED, HYPOTHESIZED, PREDICTED, VALIDATED)


def classify_epistemic_status(observation: Observation) -> str:
    method = observation.extraction_method
    if method.startswith("model:"):
        return INFERRED
    if method.startswith("simulation:"):
        return SIMULATED
    if method == "human_transcription":
        return OBSERVED
    # Deterministic, non-model, non-simulation extraction (e.g.
    # "regex:kv_v1", the only extractor implemented in scout/) --
    # pulled from a Document/Record by a mechanical process, not a
    # direct observation and not an inference.
    return EXTRACTED
