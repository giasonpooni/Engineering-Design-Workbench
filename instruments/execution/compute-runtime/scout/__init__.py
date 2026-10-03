"""SCOUT: the first external-intelligence primitive.

SCOUT observes an external source, extracts candidate evidence, and
attaches it to the evidence pool (`evidence/`) via that package's own
admission gate -- it never constructs, mutates, or bypasses
`core.canonical` state, and never calls `validate_candidate` (see
`docs/SCOUT_ARCHITECTURE.md` and `tests/test_scout_boundaries.py`).

SCOUT does not decide what is true. It does not fabricate confidence.
It does not merge uncertain entities. It stops at evidence attachment
-- promotion of any evidence toward canonical state is future,
unimplemented work (`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §O, §R
steps 3-5), deliberately out of scope for this primitive.

The LLM/model is one replaceable component (`scout.interface.Extractor`)
plugged into a model-agnostic pipeline (`scout.pipeline`) -- nothing in
`scout/` or `evidence/` imports or references any specific model
provider.
"""
