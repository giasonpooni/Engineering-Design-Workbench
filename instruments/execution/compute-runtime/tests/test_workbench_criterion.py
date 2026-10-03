"""Phase 96: criterion evaluation.

The one comparison the materials layer defines: a candidate cell against
a DECLARED Criterion -- (property, operator, target, context) supplied by
the caller, never inferred from another cell. Phase 95 established this
is the only legitimate reference relation the system has.

STATUS VOCABULARY (the real one, discovered rather than assumed):
    PASS  FAIL  CONFLICTING_EVIDENCE  INSUFFICIENT_EVIDENCE  INCOMPARABLE

SUBSTRATE (sec.8, investigated rather than assumed): `evaluate_program`
takes no ModelState anywhere in its signature. It reads ADMITTED
EVIDENCE in the EvidencePool, reached through `analyze_program` and the
RetrievalEngine. There is NO state override, and none was invented.
These verdicts are therefore about admitted evidence, not about the
ModelState predictions `predict`/`state`/`timeline` report.

WHY THE EVALUATION IS RECOMPUTED: `ExperimentSession.observe` carries
`iteration` forward unchanged, so `session.iteration.decision` stays
pinned to the `evidence_version_id` it was built from at bootstrap.
Rendering that after an observation would report a verdict about
evidence the session no longer has. `reevaluate_program` against the
live pool is the same composition applied to current inputs -- it calls
no `put_*`/`admit_*` and never mutates the pool.
"""

import json
from pathlib import Path

import pytest

from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "polymer_tensile_strength.json"

# A criterion naming no experimental context matches any comparison group
# by subset containment, so this scenario exercises real PASS/FAIL.
CONTEXT_FREE = {
    "name": "context-free criterion study",
    "process": "process-std-190c",
    "formulations": ["baseline", "modified"],
    "property": "tensile_strength",
    "criterion": {"operator": ">=", "target": 80.0},
    "contexts": [{}],
}


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-25T07:{n['i']:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _scenario(config) -> WorkbenchState:
    return bootstrap_research_scenario(config, clock=_clock())


def _start() -> WorkbenchState:
    with open(EXAMPLE, encoding="utf-8") as f:
        return _scenario(json.load(f))


@pytest.fixture()
def state() -> WorkbenchState:
    return _start()


@pytest.fixture()
def plain_state() -> WorkbenchState:
    return _scenario(dict(CONTEXT_FREE))


def _verdicts(state: WorkbenchState, formulation: str):
    decision, _ = state.evaluate_criteria()
    for formulation_decision in decision.formulations:
        if formulation_decision.formulation.natural_key == formulation:
            return [(p.observed_status, p.predicted_status)
                    for p in formulation_decision.properties]
    return []


# -- the declared reference --------------------------------------------------------------------------


def test_the_criterion_is_a_declared_target_not_another_candidate(state: WorkbenchState):
    text = dispatch(state, "criterion", [])
    assert "DECLARED" in text
    assert "engineering data, not another candidate" in text
    assert "PROPERTY" in text and "OPERATOR" in text and "TARGET" in text
    for criterion in state.declared_criteria():
        assert not hasattr(criterion, "reference_formulation")
        assert not hasattr(criterion, "formulation")


def test_the_criterion_fields_are_the_scenarios_own(state: WorkbenchState):
    declared = state.declared_criteria()
    assert declared
    for criterion in declared:
        assert criterion.property == "tensile_strength"
        assert criterion.operator == ">="
        assert criterion.target == 80.0
    # one criterion per declared context, no invented ones
    assert {tuple(sorted(c.context.items())) for c in declared} == {
        (("temperature_c", 25),), (("temperature_c", 80),), (("temperature_c", 120),)}


# -- real verdicts -----------------------------------------------------------------------------------


def test_a_satisfied_observed_result(plain_state: WorkbenchState):
    dispatch(plain_state, "select", ["baseline"])
    dispatch(plain_state, "observe", ["95", "MPa"])
    assert _verdicts(plain_state, "baseline")[0][0] == "PASS"
    text = dispatch(plain_state, "criterion", ["baseline"])
    assert "PASS" in text
    assert "the matched evidence satisfies the target" in text


def test_an_unsatisfied_observed_result(plain_state: WorkbenchState):
    dispatch(plain_state, "select", ["modified"])
    dispatch(plain_state, "observe", ["60", "MPa"])
    assert _verdicts(plain_state, "modified")[0][0] == "FAIL"
    text = dispatch(plain_state, "criterion", ["modified"])
    assert "FAIL" in text
    assert "does not satisfy the target" in text


def test_a_zero_sample_candidate_is_insufficient_not_failing(plain_state: WorkbenchState):
    """Absence of evidence is never rendered as a failed criterion."""
    assert _verdicts(plain_state, "baseline")[0] == (
        "INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE")
    text = dispatch(plain_state, "criterion", ["baseline"])
    assert "INSUFFICIENT_EVIDENCE" in text
    assert "FAIL" not in text


def test_a_context_bearing_criterion_reaches_a_real_verdict(state: WorkbenchState):
    """PHASE 98 -- admitted evidence now carries the candidate's declared
    context, so a context-bearing criterion matches its own comparison
    group and the declared target decides the outcome."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["95", "MPa"])          # >= 80 -> PASS
    assert _verdicts(state, "baseline")[0][0] == "PASS"

    text = dispatch(state, "criterion", ["baseline", "25"])
    assert "PASS" in text
    assert "the matched evidence satisfies the target" in text
    # and the matched group names the condition it was measured under
    assert "25" in text


def test_incomparable_remains_reachable_and_is_explained_correctly(state: WorkbenchState):
    """INCOMPARABLE is still a legitimate verdict -- now for a genuine
    matching failure rather than an omission -- and the view no longer
    claims the old cause."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["95", "MPa"])
    dispatch(state, "select", ["baseline", "120"])
    dispatch(state, "observe", ["70", "MPa"])
    # a criterion for 80 C: nothing was measured there
    text = dispatch(state, "criterion", ["baseline", "80"])
    assert "INCOMPARABLE" in text
    assert "no comparison group selected uniquely" in text
    assert "admitted results record property, value and unit" not in text


def test_conflicting_evidence_is_reported_not_resolved(plain_state: WorkbenchState):
    """Two admitted observations straddling the target: the materials
    layer reports the conflict; the workbench must not adjudicate it."""
    dispatch(plain_state, "select", ["baseline"])
    dispatch(plain_state, "observe", ["95", "MPa"])
    dispatch(plain_state, "observe", ["60", "MPa"])
    observed = _verdicts(plain_state, "baseline")[0][0]
    assert observed == "CONFLICTING_EVIDENCE"
    text = dispatch(plain_state, "criterion", ["baseline"])
    assert "CONFLICTING_EVIDENCE" in text
    assert "disagrees with itself" in text
    # no resolution is offered
    for phrase in ("resolve", "correct value", "true value", "discard", "outlier"):
        assert phrase not in text.lower()


# -- observed and predicted stay separate (sec.6) -----------------------------------------------------


def test_observed_and_predicted_are_rendered_as_two_verdicts(plain_state: WorkbenchState):
    dispatch(plain_state, "select", ["baseline"])
    dispatch(plain_state, "observe", ["95", "MPa"])
    observed, predicted = _verdicts(plain_state, "baseline")[0]
    assert observed == "PASS"
    assert predicted == "INSUFFICIENT_EVIDENCE"
    assert observed != predicted

    text = dispatch(plain_state, "criterion", ["baseline"])
    assert "OBSERVED" in text and "PREDICTED" in text
    assert "answered independently and are never combined" in text
    # and neither side's verdict appears on the other's row
    stripped = (line.strip().strip("│").strip() for line in text.splitlines())
    rows = {row.split()[0]: row for row in stripped
            if row.startswith(("OBSERVED", "PREDICTED"))}
    assert "PASS" in rows["OBSERVED"]
    assert "PASS" not in rows["PREDICTED"]


def test_no_combined_verdict_is_ever_produced(plain_state: WorkbenchState):
    dispatch(plain_state, "select", ["baseline"])
    dispatch(plain_state, "observe", ["95", "MPa"])
    for args in ([], ["baseline"]):
        text = dispatch(plain_state, "criterion", args)
        labels = [
            ln.strip().strip("│").strip().split()[0]
            for ln in text.splitlines()
            if ln.strip().strip("│").strip()
        ]
        # no ROW is labelled with a merged verdict. (The view says the word
        # "combined" only in its own disclaimer that the two never are.)
        for merged in ("OVERALL", "COMBINED", "NET", "RESULT", "SATISFIED"):
            assert merged not in labels, f"{merged}: a combined verdict row appeared"
        assert "never combined" in text  # both views state the separation


def test_a_model_prediction_never_becomes_admitted_evidence(state: WorkbenchState):
    """`predict` reads the ModelState; the criterion reads the pool. A
    ModelState prediction must never appear as a criterion verdict."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["95", "MPa"])
    assert state.session.predict(state.selected_candidate).predicted_value == 95.0
    # the predicted SIDE of the criterion has no pool evidence at all
    assert _verdicts(state, "baseline")[0][1] == "INSUFFICIENT_EVIDENCE"
    text = dispatch(state, "criterion", [])
    assert "ADMITTED EVIDENCE, not the model state" in text


# -- evaluation is not comparison (sec.7) -------------------------------------------------------------


def test_the_view_never_ranks_or_compares_candidates(plain_state: WorkbenchState):
    dispatch(plain_state, "select", ["baseline"])
    dispatch(plain_state, "observe", ["95", "MPa"])
    dispatch(plain_state, "select", ["modified"])
    dispatch(plain_state, "observe", ["60", "MPa"])

    text = dispatch(plain_state, "criterion", [])
    lowered = text.lower()
    for phrase in ("best", "worst", "better", "worse", "rank", "winner", "leader",
                   "superior", "inferior", "difference", "delta", "outperform",
                   "only candidate that", "the one that"):
        assert phrase not in lowered, f"criterion view compares candidates: {phrase!r}"
    assert "No row is compared with any other." in text


def test_passing_candidates_are_not_collected_into_a_shortlist(plain_state: WorkbenchState):
    """Two candidates, one PASS and one FAIL. The view must not group,
    count or otherwise turn that into a selection."""
    dispatch(plain_state, "select", ["baseline"])
    dispatch(plain_state, "observe", ["95", "MPa"])
    dispatch(plain_state, "select", ["modified"])
    dispatch(plain_state, "observe", ["60", "MPa"])

    text = dispatch(plain_state, "criterion", [])
    assert "PASS" in text and "FAIL" in text
    for phrase in ("PASSING", "SHORTLIST", "CANDIDATES THAT PASS", "1 OF 2", "SATISFIED:"):
        assert phrase not in text.upper()


def test_registry_order_is_preserved(plain_state: WorkbenchState):
    dispatch(plain_state, "select", ["modified"])
    dispatch(plain_state, "observe", ["999", "MPa"])   # a large PASSing value
    text = dispatch(plain_state, "criterion", [])
    indices = [int(ln.strip().strip("│").strip().split()[0])
               for ln in text.splitlines()
               if ln.strip().strip("│").strip()[:2].isdigit()
               and "·" in ln]
    assert indices == sorted(indices)
    assert indices == list(range(1, len(plain_state.list_candidates()) + 1))


# -- candidates are evaluated independently ------------------------------------------------------------


def test_each_candidate_is_evaluated_independently(plain_state: WorkbenchState):
    dispatch(plain_state, "select", ["baseline"])
    dispatch(plain_state, "observe", ["95", "MPa"])
    assert _verdicts(plain_state, "baseline")[0][0] == "PASS"
    assert _verdicts(plain_state, "modified")[0][0] == "INSUFFICIENT_EVIDENCE"
    # one candidate's evidence never becomes another's
    dispatch(plain_state, "select", ["modified"])
    dispatch(plain_state, "observe", ["60", "MPa"])
    assert _verdicts(plain_state, "baseline")[0][0] == "PASS"
    assert _verdicts(plain_state, "modified")[0][0] == "FAIL"


# -- selection grammar -------------------------------------------------------------------------------


def test_criterion_reuses_the_existing_semantic_selector(state: WorkbenchState):
    candidate = next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == "baseline"
        and dict(c.target_context) == {"temperature_c": 25})
    index = next(i for i, c in enumerate(state.list_candidates(), start=1) if c.id == candidate.id)
    assert dispatch(state, "criterion", ["baseline", "25"]) == dispatch(
        state, "criterion", [str(index)])


def test_an_unknown_selector_names_what_was_expected(state: WorkbenchState):
    assert "EXPECTED" in dispatch(state, "criterion", ["nonexistent"])


# -- provenance --------------------------------------------------------------------------------------


def test_the_evaluation_names_the_evidence_it_used(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["95", "MPa"])
    _, evidence_version = state.evaluate_criteria()
    assert evidence_version == state.pool.fingerprint()
    assert theme.ident(evidence_version, size=24) in dispatch(state, "criterion", [])


def test_the_evaluation_tracks_the_live_pool_not_the_bootstrap_snapshot(state: WorkbenchState):
    """`session.iteration` is pinned at bootstrap; the view must not
    report a verdict about evidence the session no longer has."""
    pinned = state.session.iteration.evidence_version_id
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["95", "MPa"])
    assert state.session.iteration.evidence_version_id == pinned   # still pinned
    assert state.pool.fingerprint() != pinned                       # pool moved
    _, evidence_version = state.evaluate_criteria()
    assert evidence_version == state.pool.fingerprint()             # view follows the pool


def test_no_identity_is_minted(state: WorkbenchState):
    import re
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["95", "MPa"])
    known = {theme.ident(s.id) for s in state.session.state_history}
    known |= {theme.ident(c.id) for c in state.list_candidates()}
    known |= {theme.ident(state.pool.fingerprint())}
    known |= {theme.ident(a.observation.id) for a in state.assessments}
    known |= {theme.ident(a.result.id) for a in state.assessments}
    for args in ([], ["baseline", "25"]):
        text = dispatch(state, "criterion", args)
        for token in re.findall(r"·[0-9a-f]{12}", text):
            assert token in known, f"criterion view minted an identity: {token}"


# -- isolation ---------------------------------------------------------------------------------------


def test_criterion_evaluation_mutates_nothing(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["70"])
    dispatch(state, "observe", ["95", "MPa"])
    dispatch(state, "decide", [])

    session = state.session
    state_id = state.session.state.id
    history = [s.id for s in state.session.state_history]
    fingerprint = state.pool.fingerprint()
    observations = len(state.pool.all_observations())
    assessments = len(state.assessments)
    branches = list(state.branches)
    decisions = list(state.decision_log)
    last_decision = state.last_decision
    previous_decision = state.previous_decision
    selected = state.selected_candidate
    iteration = state.session.iteration

    for args in ([], ["baseline", "25"], ["1"], ["nonexistent"]):
        dispatch(state, "criterion", args)

    assert state.session is session
    assert state.session.state.id == state_id
    assert [s.id for s in state.session.state_history] == history
    assert state.pool.fingerprint() == fingerprint
    assert len(state.pool.all_observations()) == observations
    assert len(state.assessments) == assessments
    assert state.branches == branches
    assert state.decision_log == decisions
    assert state.last_decision is last_decision
    assert state.previous_decision is previous_decision
    assert state.selected_candidate is selected
    assert state.session.iteration is iteration


def test_other_views_are_unaffected_before_and_after(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["70"])
    dispatch(state, "observe", ["95", "MPa"])

    others = {name: dispatch(state, name, args) for name, args in (
        ("predict", []), ("branches", []), ("timeline", []),
        ("thread", []), ("state", []), ("status", []))}
    dispatch(state, "criterion", [])
    dispatch(state, "criterion", ["baseline", "25"])
    for name, args in (("predict", []), ("branches", []), ("timeline", []),
                       ("thread", []), ("state", []), ("status", [])):
        assert dispatch(state, name, args) == others[name], name


# -- determinism -------------------------------------------------------------------------------------


def test_repeated_evaluation_is_identical(plain_state: WorkbenchState):
    dispatch(plain_state, "select", ["baseline"])
    dispatch(plain_state, "observe", ["95", "MPa"])
    assert dispatch(plain_state, "criterion", []) == dispatch(plain_state, "criterion", [])
    assert dispatch(plain_state, "criterion", ["baseline"]) == dispatch(
        plain_state, "criterion", ["baseline"])


def test_the_same_session_twice_evaluates_identically():
    def run() -> tuple:
        st = _scenario(dict(CONTEXT_FREE))
        dispatch(st, "select", ["baseline"])
        dispatch(st, "observe", ["95", "MPa"])
        dispatch(st, "select", ["modified"])
        dispatch(st, "observe", ["60", "MPa"])
        return (dispatch(st, "criterion", []),
                dispatch(st, "criterion", ["baseline"]),
                dispatch(st, "criterion", ["modified"]))

    assert run() == run()


# -- honesty -----------------------------------------------------------------------------------------


def test_the_view_is_real_and_single_ruled(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "explore", ["70"])
    for args in ([], ["baseline", "25"]):
        text = dispatch(state, "criterion", args)
        assert "╔" not in text and "║" not in text
        assert theme.ident(state.branches[0].projected_state_id) not in text


def test_a_verdict_is_never_clipped(state: WorkbenchState):
    """A status is the ANSWER, not a descriptive label, so the established
    clipping policy must never shorten one."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["95", "MPa"])
    for args in ([], ["baseline", "25"]):
        text = dispatch(state, "criterion", args)
        for line in text.splitlines():
            plain = theme._ANSI.sub("", line)
            for status in ("PASS", "FAIL", "CONFLICTING_EVIDENCE",
                           "INSUFFICIENT_EVIDENCE", "INCOMPARABLE"):
                if status[:8] in plain:
                    assert "…" not in plain.split(status[:8])[-1][:len(status)], plain


def test_no_causal_or_material_claim_is_made(plain_state: WorkbenchState):
    dispatch(plain_state, "select", ["baseline"])
    dispatch(plain_state, "observe", ["95", "MPa"])
    for args in ([], ["baseline"]):
        lowered = dispatch(plain_state, "criterion", args).lower()
        for phrase in ("proves", "proved", "caused", "because the material",
                       "demonstrates that", "confirms", "validates", "suitable",
                       "recommended", "acceptable material"):
            assert phrase not in lowered, f"criterion view claims too much: {phrase!r}"


def test_undetermined_is_never_a_section_heading(state: WorkbenchState):
    for args in ([], ["baseline", "25"]):
        for line in dispatch(state, "criterion", args).splitlines():
            if line.lstrip("│║ ").startswith("─ "):
                assert theme.UNDETERMINED not in line
