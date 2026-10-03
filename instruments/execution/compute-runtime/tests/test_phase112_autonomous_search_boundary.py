"""Phase 112: autonomous search / evolution / evaluation boundary audit.

Comparative substrates, both cloned and read (not inferred from
documentation): AI Scientist-v2 (13,213 LOC) and ShinkaEvolve (64,797
LOC).

sec.23 VERDICT: THE PROPOSITION SURVIVES. Autonomous scientific discovery
does not require collapsing search, optimization, execution, evidence and
epistemic truth into one ontology. It requires a computational CONTROL
LAYER over immutable scientific state, invoking evidence-producing
operations whose admission semantics are independent of search success.

Both substrates were attacked for a counterexample. Neither produced one.
What they produced instead is the strongest available confirmation: both
central objects collapse the layers, and the collapse is visible in their
own field lists.

WHAT THE TWO CENTRAL OBJECTS ACTUALLY ARE
------------------------------------------
`ai_scientist/treesearch/journal.py::Node` -- MUTABLE, `id =
uuid.uuid4().hex`, `ctime = time.time()`, `parent`/`children` held as
LIVE OBJECT REFERENCES. One object carries, simultaneously:

    plan, overall_plan          a PROPOSAL
    code, plot_code             an IMPLEMENTATION
    _term_out, exc_type,        EXECUTION residue
      exc_info, exec_time
    metric                      an EVALUATION
    analysis, vlm_feedback      an INTERPRETATION
    is_buggy                    a JUDGEMENT
    plots, plot_paths           PRESENTATION

Seven layers, one mutable record, random identity.

`shinka/database/dbase.py::Program` -- MUTABLE, id not content-addressed,
`timestamp = time.time()`, carrying:

    code, code_diff             an ARTIFACT
    parent_id, generation,      SEARCH state
      island_idx, migration_history
    combined_score,             OPTIMIZATION state
      public_metrics, private_metrics
    correct: bool               a TRUTH-SHAPED FLAG
    children_count              SEARCH state WRITTEN BACK ONTO THE ARTIFACT
    in_archive: bool            MEMBERSHIP, mutated in place
    embedding, embedding_pca_2d/3d,
      embedding_cluster_id      REPRESENTATION stored ON the artifact
    text_feedback               PRESENTATION

THE SINGLE MOST DECISIVE LINE FOUND (sec.8, sec.14, sec.21)
------------------------------------------------------------
    parallel_agent.py:713
    node.is_buggy = response["is_bug"] or node.exc_type is not None

An LLM's opinion and a Python exception are OR-ed into one boolean. A
ZeroDivisionError and "the model thinks this is wrong" become the same
event. And `is_buggy` is later MUTATED in place (lines 1394, 1643, 1652,
1659) -- a judgement overwritten after the fact. This is the failure-
taxonomy collapse and the immutability violation in a single field, in
production code, in the substrate. It is the empirical answer to sec.8's
"do not collapse these merely because the search system labels them
failed": the search system does exactly that, and the reason is that it
has nowhere else to put the distinction.

sec.2 THE EVALUATOR AUDIT -- THE CENTRAL ATTACK
------------------------------------------------
Shinka's evaluator contract, read from `examples/*/evaluate.py`, writes
`{"correct": correct, "error": error}` plus metrics. `combined_score` is
an aggregate over those metrics.

    Is a fitness score evidence about the world?

NO. It is evidence about THE PERFORMANCE OF A PROGRAM UNDER A SPECIFIED
EVALUATOR. Those coincide only if the evaluator is itself a valid
measurement of the world -- which is a scientific claim about the
evaluator, of exactly the kind Phase 107-110 showed cannot be smuggled in
as configuration. `correct: bool` is the sharpest case: it is a
PROGRAM-CORRECTNESS verdict wearing the name of a truth predicate.

sec.3 THE TWO PIPELINES ARE NOT EQUIVALENT
-------------------------------------------
    program -> evaluator -> score
    experiment -> measurement -> observation

They diverge at the second arrow. An evaluator is a FUNCTION THE SEARCH
SYSTEM WROTE AND CAN REWRITE; a measurement is an interaction with
something the system does not control. Same shape, opposite epistemic
direction: one closes a loop inside the process, the other opens it.

sec.4 FITNESS != TRUTH, BY TASK
-------------------------------
    optimization task     score IS the objective. A > B, and nothing
                          further is claimed. VALID.
    numerical benchmark    A > B on this benchmark. Generalisation is a
                          separate claim. CONDITIONAL.
    physical simulation    A > B under this discretisation and these
                          boundary conditions. Agreement with physics is
                          a further claim. CONDITIONAL.
    empirical experiment   score is a summary of measurements; the
                          comparison inherits every Phase 106-108 caveat.
    scientific hypothesis  NOT VALID under any condition. No score
                          ranks hypotheses by truth.

sec.5/17 DOES AUTONOMY CREATE A NEW VULNERABILITY?
---------------------------------------------------
NO -- it industrialises the existing one. Phase 111's attack was
    computation -> fabricated Record.raw_content -> Observation -> Claim.
The autonomous version is the same path with an LLM writing the value and
a controller consuming the result. Neither an evaluator score, nor
archive membership, nor selection, nor evolutionary ancestry supplies ANY
independent external warrant for the value: every one of them is computed
from the same process that produced it. The change is throughput and the
absence of a human at the fabrication step, not kind.

sec.13 AN UNEXECUTED CANDIDATE MEANS ONE THING
-----------------------------------------------
NOT unobserved-as-in-refuted, not false, not rejected, not dominated, not
infeasible. It means EXACTLY: no evidence exists at that coordinate. Our
architecture already says precisely this and nothing more --
`predict` at an unoccupied cell returns `predicted_value=None`,
`sample_count=0`, and consults no neighbour.

sec.19 IDENTITY AXES, CONFIRMED AND EXTENDED
---------------------------------------------
Phase 108 found model identity independent of evidence identity. These
substrates add three more axes that must not merge: PROGRAM identity (an
artifact), SEARCH-STATE identity (which node/generation), and EVALUATION
identity (which evaluator, at which version, produced this score). Shinka
proves the need by violating it: `children_count` and `in_archive` are
search state mutated onto the artifact, so the artifact's identity
silently depends on the search's progress.

sec.21 SUBSTITUTION TABLE

    fitness -> truth                    INVALID
    score -> evidence                   INVALID
    evaluator -> scientific validator   CONDITIONALLY VALID -- only with
                                        an admitted claim that the
                                        evaluator measures the quantity
    archive -> knowledge base           INVALID
    genealogy -> provenance             CONDITIONALLY VALID -- genealogy
                                        is `modified_from`, which is
                                        constitutive like `derived_from`;
                                        but it also carries `inspired_by`
                                        (Shinka's inspiration_ids), which
                                        is NOT constitutive
    mutation -> hypothesis revision     INVALID
    candidate -> claim                  INVALID
    failed execution -> falsification   INVALID
    elite -> authoritative              INVALID (Phase 105)
    search convergence -> scientific
      convergence                       INVALID
    repeated selection -> empirical
      support                           INVALID

sec.20/22 WHAT IS GENUINELY ABSENT
-----------------------------------
Nothing epistemic. Everything absent is CONTROLLER STATE:

    a search frontier / population
    a parent-selection rule over it
    a generation or step counter
    a resource budget and its exhaustion
    an execution-failure taxonomy distinct from scientific failure

None of these is a scientific object; all are exactly what
`SelectionPolicy`, `RankingPolicy` and `OptimizationPolicy` already are
in kind -- Phase 105 established that policies carry no identity and
cannot reach evidence, which is why a controller built from them cannot
contaminate the pool.

The one genuine gap this phase does expose is COMPUTATIONAL, not
epistemic: there is no place to put a search frontier, and no failure
taxonomy separating "the process crashed" from "the hypothesis was
falsified". Our architecture has neither, and needs neither until an
autonomous loop is actually built -- which the standing constraints
forbid.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes in this phase.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from evidence.pool import EvidencePool
from materials.candidates import ActionCandidate
from materials.decision import Criterion
from materials.model_state import Prediction, Sample, make_model_state, predict, resolve_model_state_key
from materials.optimization import OptimizationPolicy
from materials.ranking import CandidateRanking, RankingPolicy
from materials.results import ExperimentalResult
from materials.selection import SelectionPolicy
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench", "scout")


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


# -- 4. proposal and result are structurally separate, not procedurally ----------------------------


def test_proposal_and_result_are_different_types_with_different_fields():
    """"do this experiment" vs "this produced this". AI Scientist's Node
    holds BOTH in one mutable record; here they cannot merge."""
    candidate = {f.name for f in dataclasses.fields(ActionCandidate)}
    result = {f.name for f in dataclasses.fields(ExperimentalResult)}
    assert "existing_evidence_ids" in candidate and "record_id" not in candidate
    assert "record_id" in result and "existing_evidence_ids" not in result
    # A candidate names an intention; a result names a record. No field is
    # shared that would let one become the other.
    assert candidate & result == {"id", "formulation", "property"}
    # `id` is shared as a NAME only: a candidate's hashes its requirement
    # ids (the evidence epoch), a result's hashes its record and content.


def test_a_candidate_carries_no_execution_or_evaluation_residue():
    """The seven things AI Scientist's Node fuses, absent here."""
    fields = {f.name for f in dataclasses.fields(ActionCandidate)}
    for absent in ("code", "exc_type", "term_out", "metric", "analysis",
                   "is_buggy", "plots", "exec_time", "score"):
        assert absent not in fields


# -- 2/3. score is about the evaluator, not the world -----------------------------------------------


def test_no_production_object_carries_a_score_or_a_correctness_flag():
    """`combined_score` and `correct: bool` have no counterpart, and the
    one ranking that exists is a recomputed ordinal (Phase 106)."""
    forbidden = {"combined_score", "fitness", "correct", "score",
                 "public_metrics", "private_metrics", "in_archive", "elite"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef):
                    for stmt in node.body:
                        target = None
                        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                            target = stmt.target.id
                        if target in forbidden:
                            hits.append(f"{path.relative_to(REPO)}: {node.name}.{target}")
    assert hits == [], hits


def test_the_only_ranking_is_a_recomputed_ordinal_over_utility():
    fields = {f.name for f in dataclasses.fields(CandidateRanking)}
    assert fields == {"candidate_id", "utility", "rank", "ranking_status"}
    assert {f.name for f in dataclasses.fields(RankingPolicy)} == {
        "direction", "unknown_utility_policy"}
    # `rank` is None under unknown utility -- selection never manufactures
    # an order where the inputs do not support one.


# -- 7/20. controller state is policy-shaped and cannot reach evidence ------------------------------


@pytest.mark.parametrize("policy", [SelectionPolicy, OptimizationPolicy, RankingPolicy])
def test_every_policy_is_identityless_and_therefore_unreachable_from_evidence(policy):
    fields = {f.name for f in dataclasses.fields(policy)}
    assert "id" not in fields
    # Phase 105: no identity means no pool node. A controller assembled
    # from policies cannot contaminate the pool by construction.


def test_selection_never_sees_a_pool():
    from materials.selection import select_candidates
    assert set(inspect.signature(select_candidates).parameters) == {"evaluations", "policy"}
    source = inspect.getsource(select_candidates)
    assert "pool" not in source and "put_" not in source


def test_no_search_or_population_state_exists_in_production():
    forbidden = {"SearchTree", "Population", "Archive", "Island", "Generation",
                 "Frontier", "EvolutionNode", "Hypothesis", "Agent"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef) and node.name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


# -- 13. an unexecuted candidate means exactly one thing --------------------------------------------


def test_an_unexecuted_candidate_means_only_that_no_evidence_exists_there():
    """Not false, not rejected, not dominated, not infeasible."""
    occupied = resolve_model_state_key("f", "tensile_strength", {"temperature_c": 25})
    state = make_model_state({occupied: (Sample(value=90.0, observation_id="o1"),)})

    class _Probe:
        def __init__(self, context):
            self.formulation = type("R", (), {"id": "f"})()
            self.property = "tensile_strength"
            self.target_context = dict(context)
            self.id = "probe"

    unexecuted = predict(state, _Probe({"temperature_c": 60}))
    assert unexecuted.predicted_value is None
    assert unexecuted.sample_count == 0
    assert unexecuted.uncertainty is None
    # No neighbour consulted, no default, no penalty, no zero.


# -- 8/14. the failure taxonomy is not collapsible here ---------------------------------------------


def test_no_production_object_has_a_universal_failed_flag():
    """AI Scientist's `is_buggy = response["is_bug"] or exc_type is not
    None` OR-s an LLM opinion with a Python exception. Nothing here has
    a field that could hold both."""
    forbidden = {"is_buggy", "failed", "is_bug", "success", "ok", "valid"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef):
                    for stmt in node.body:
                        if (isinstance(stmt, ast.AnnAssign)
                                and isinstance(stmt.target, ast.Name)
                                and stmt.target.id in forbidden):
                            hits.append(f"{path.relative_to(REPO)}: {node.name}.{stmt.target.id}")
    assert hits == [], hits


def test_the_five_criterion_statuses_are_the_whole_verdict_vocabulary():
    """None of them means "the process crashed" -- which is the gap this
    phase exposes, and it is computational, not epistemic."""
    from materials.decision import ALL_STATUSES
    assert set(ALL_STATUSES) == {
        "PASS", "FAIL", "CONFLICTING_EVIDENCE", "INSUFFICIENT_EVIDENCE", "INCOMPARABLE"}


# -- 6/19. identity axes must not merge -------------------------------------------------------------


def test_no_production_identity_is_random_or_wall_clock():
    """Both substrates use uuid4 and time.time(). Neither appears here."""
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in ("uuid4", "uuid1", "time"):
                    hits.append(f"{path.relative_to(REPO)}:{node.lineno}: {node.attr}")
    assert hits == [], hits


def test_search_state_is_never_written_onto_a_scientific_object():
    """Shinka mutates `children_count` and `in_archive` onto `Program`.
    Every scientific object here is frozen, so the equivalent is
    impossible rather than merely discouraged."""
    from materials.candidates import CandidateSet
    from materials.model_state import ModelState
    for cls in (ActionCandidate, CandidateSet, ModelState, Prediction, Criterion):
        assert cls.__dataclass_params__.frozen


# -- 5/17. the autonomous attack is the Phase 111 attack -------------------------------------------


def test_no_evaluator_score_can_reach_the_pool():
    """Neither score, archive membership, selection nor ancestry supplies
    an external warrant -- and none of them has a `put_*` path at all."""
    writes = set()
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
                    writes.add(node.attr)
    assert writes == {
        "put_record", "put_source", "put_document", "put_referent",
        "put_observation", "put_claimed_relationship",
    }


def test_the_autonomous_attack_adds_no_new_gate_to_break():
    """It reuses Phase 111's path exactly: a computed value written into
    a Record. The vulnerability is throughput, not kind."""
    pool = EvidencePool()
    # The gates an autonomous controller would meet are the same six.
    assert not hasattr(pool, "put_score")
    assert not hasattr(pool, "put_program")
    assert not hasattr(pool, "put_hypothesis")


# -- 23. nothing was added ---------------------------------------------------------------------------


def test_phase_112_added_no_search_machinery():
    forbidden = (
        "AgentManager", "TreeSearch", "ProgramDatabase", "ParentSelector",
        "combined_score", "island_idx", "in_archive", "is_buggy",
    )
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits


def test_production_still_references_no_external_substrate():
    names = {"ai_scientist", "shinka", "treesearch", "ShinkaEvolve", "AI-Scientist"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            for name in names:
                if name in text:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits
