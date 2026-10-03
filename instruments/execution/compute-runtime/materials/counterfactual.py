"""project_update(state, candidate, hypothetical_value) -> ModelState:
Phase 58's smallest pure COUNTERFACTUAL state-transition operation --
"what would the model state become if this candidate's experiment
produced value y?", without ever performing, observing, or admitting
that experiment.

Before writing this module, `materials/model_state.py`, `materials/
trajectory.py`, `materials/diagnostics.py`, `materials/assessment.py`,
`materials/information.py`, `materials/surrogate.py`, and `materials/
results.py` were re-read. Finding: `materials.model_state.update`
already contains exactly the transition rule this phase needs -- append
one sample to the one cell a candidate names, leave every other cell
untouched, return a new `ModelState`. It was NOT duplicated here.
`update`'s body was factored (Phase 58, in `materials/model_state.py`)
into a private, shared `_transition(state, key, value, sample_id) ->
ModelState` -- the ONE underlying transition rule -- and this module
calls that exact function, never a re-implementation of it. `update`
itself is otherwise unchanged: it remains the only path that ever
reads a real `Observation`/`ExperimentalResult`.

--------------------------------------------------------------------
ACTUAL vs COUNTERFACTUAL -- the same F, a different epistemic origin
for y (Phase 58 sec.2/10):

    S_(t+1) = F(S_t, y)      -- the ONE transition rule
    y_hat    = G(S_t, x)     -- the ONE prediction rule (`predict`, unchanged)

    ACTUAL:          y = a real, already-admitted Observation's value
                     (`materials.model_state.update`)
    COUNTERFACTUAL:  y = a caller-supplied HYPOTHETICAL value that was
                     never observed, never admitted, and never will be
                     by this function (`project_update`, here)

`F` (`materials.model_state._transition`) does not know or care which
case it is in -- it only ever sees `(state, key, value, sample_id)`.
The DIFFERENCE between the two cases is entirely in what `update`/
`project_update` supply as `sample_id`, documented next.

--------------------------------------------------------------------
WHY A HYPOTHETICAL SAMPLE CANNOT SHARE A REAL OBSERVATION'S IDENTITY,
AND WHAT THAT MEANS FOR PHASE 58 SEC.4's INVARIANT:

A real `Observation.id` is a content hash over that Observation's own
extraction fields (source records, extraction method, content) --
`project_update` has none of those (it never constructs an `Observation`
at all, per sec.6) and must not fabricate a plausible-looking one. The
placeholder this module uses instead (`_hypothetical_sample_id`) is
deterministic in exactly the way Phase 58 sec.5 requires -- the SAME
`(model_state_key, hypothetical_value)` pair always produces the SAME
placeholder, so repeated identical projection is deterministic and
distinct hypothetical values produce distinct states -- but it is
PREFIXED (`"hypothetical:..."`) so it can never collide with, or be
mistaken for, a genuine (unprefixed, bare-hex) `content_hash` observation
id.

Phase 58 sec.4 asks for `update(...).id == project_update(...).id` when
the actual observed value equals the hypothetical one. Investigated
directly and NOT implemented as literal `ModelState.id` equality: doing
so would require the counterfactual sample to carry a REAL, unprefixed
observation id, which would make a projected `ModelState` indistinguishable
by content from one built from genuine admitted evidence -- directly
contradicting sec.6 ("counterfactual states are NOT evidence... must not
be treated as a historical state transition") and sec.13 ("without any
of those projected states being mistaken for history"). Those two
requirements cannot both be satisfied literally at once, and this module
resolves the conflict in favor of sec.6/13 -- a real observation and a
hypothetical one must remain distinguishable, always.

What sec.4's invariant DOES hold, exactly, and is what this module's
own tests verify: `predict(update(...), candidate)` and
`predict(project_update(...), candidate)` produce IDENTICAL
`predicted_value`/`uncertainty`/`sample_count` when the hypothetical
value equals the real observed value. This follows directly from
`predict`'s own math (`materials/model_state.py`): mean/variance are
computed ONLY from `Sample.value`, never from `Sample.observation_id` --
so two `ModelState`s whose sample VALUES agree at a cell, but whose
sample IDENTITIES (real vs hypothetical) differ, are mathematically
indistinguishable to `predict`, while remaining honestly, permanently
distinguishable as OBJECTS (different `.id`, and the hypothetical one's
samples carry the tell-tale `"hypothetical:"` prefix). "One underlying
transition rule" (sec.4's second sentence) is satisfied in the
strongest possible sense -- `update`/`project_update` call the literal
same `_transition` function, not merely an equivalent algorithm.

--------------------------------------------------------------------
NO RESULT WRAPPER (Phase 58 sec.3): `project_update` returns a bare
`ModelState`, exactly mirroring `update`'s own `-> ModelState` signature.
A wrapper exposing `source_state_id`/`candidate_id`/`model_state_key`/
`hypothetical_value` alongside `projected_state` was considered and
declined: every one of those fields is either already in the caller's
hand (they supplied `state`, `candidate`, `hypothetical_value`
themselves) or trivially recomputed (`state.id`,
`resolve_model_state_key(...)`, the returned state's own `.id`) --
a wrapper would duplicate information the caller already possesses,
exactly the unjustified machinery Phase 58's own stop condition warns
against. This is not a "generic counterfactual engine": there is
exactly one function, and it does exactly one thing.

--------------------------------------------------------------------
EXPLORING A LOCAL NEIGHBORHOOD (Phase 58 sec.13): nothing new is needed
for `S_t` to branch into several projected successors --

    S_t --y=80--> S'_1
    S_t --y=85--> S'_2
    S_t --y=90--> S'_3

is simply three ordinary `project_update(S_t, candidate, y)` calls; each
returns an independent, immutable `ModelState` that never mutates `S_t`
or any of its siblings (`ModelState`/`_transition` were already
immutable, unchanged since Phase 52). See this module's own tests for a
direct demonstration, including comparing predictions/information
values across the resulting states via the EXISTING `predict`/
`compare_predictions`/`ModelStateInformationValueModel`/
`estimate_information_value` machinery -- no new comparison or
information-theoretic machinery is added here (Phase 58 sec.7/8): this
module produces states, nothing else consumes or interprets them.

--------------------------------------------------------------------
CANDIDATE/CONTEXT SEMANTICS (Phase 58 sec.9): `project_update` resolves
its cell exactly the way `predict`/`update` already do --
`resolve_model_state_key(candidate.formulation.id, candidate.property,
candidate.target_context)` -- the Phase 53 resolution, unchanged. No
raw `Observation.content`, no `materials.analysis._comparison_context`,
no incidental metadata (`unit`, etc.) is read anywhere in this module,
because none is available: `project_update` never receives an
`Observation` or `ExperimentalResult` at all.

--------------------------------------------------------------------
BOUNDARY (Phase 58 sec.6), enforced by this module's own signature, not
merely by convention: `project_update` takes only `(state, candidate,
hypothetical_value)` -- there is no `EvidencePool` parameter anywhere in
this module, so it is structurally impossible for it to read or write
one. No `Observation`/`ExperimentalResult`/`ClaimedRelationship` is ever
constructed here. No admission gate (`evidence.admission.*`) is
imported. A projected `ModelState` exists only as an in-memory value --
nothing in this module ever calls `pool.fingerprint()`, appends to a
fingerprint history, or makes a projected state reachable through
`retrieval.engine`. `materials.results` remains the sole write boundary;
this module could not touch it even by mistake.

PHASE 61 -- THE ONE DIRECTION THAT MUST NEVER HAPPEN, GUARDED ELSEWHERE:
nothing here stops a caller from taking a `ModelState` this module
returns and passing it back into `project_update` again (a deeper
counterfactual lookahead tree, fully legitimate -- Phase 58 sec.13's own
"local neighborhood" framing already anticipates it) -- but taking it
into `materials.model_state.update` instead, as if it were real history,
must never silently succeed. `update` itself now refuses any `state`
containing a hypothetical sample (Phase 61's guard, in that module, not
this one); this module's placeholder id (`_hypothetical_sample_id` below)
is what makes that guard possible to enforce at all.
"""

from __future__ import annotations

from evidence.identity import content_hash
from materials.candidates import ActionCandidate
from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX, ModelState, _transition, resolve_model_state_key


def _hypothetical_sample_id(model_state_key: str, value: float) -> str:
    """A deterministic placeholder standing in for `Sample.observation_id`
    -- NEVER a real `Observation.id`. Deterministic in `(model_state_key,
    value)` alone (never in which base `ModelState` it gets appended to
    -- exactly mirroring a real `Observation.id`'s own content-hash
    discipline, which likewise never depends on which downstream
    `ModelState` later consumes it). Prefixed with `"hypothetical:"` so
    it can never collide with, or be mistaken for, a genuine bare-hex
    `content_hash` observation id -- any consumer inspecting a
    `ModelState`'s samples can tell a hypothetical one apart at a
    glance."""
    return HYPOTHETICAL_SAMPLE_PREFIX + content_hash({"model_state_key": model_state_key, "hypothetical_value": value})


def project_update(state: ModelState, candidate: ActionCandidate, hypothetical_value: float) -> ModelState:
    """S'_(t+1) = F(S_t, y) where `y = hypothetical_value` is NEVER an
    admitted `Observation` -- a pure, side-effect-free projection.
    Never mutates `state`; the returned `ModelState` is exactly as
    immutable, and exactly as content-addressed, as any other
    `ModelState` -- it simply was never derived from real evidence, a
    fact permanently legible in its samples' `"hypothetical:"`-prefixed
    ids (see module docstring). Calling this repeatedly with the same
    `(state, candidate, hypothetical_value)` always returns a `ModelState`
    with the same `.id`; a different `hypothetical_value` for the same
    cell always returns a different one."""
    key = resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context)
    sample_id = _hypothetical_sample_id(key, float(hypothetical_value))
    return _transition(state, key, float(hypothetical_value), sample_id)
