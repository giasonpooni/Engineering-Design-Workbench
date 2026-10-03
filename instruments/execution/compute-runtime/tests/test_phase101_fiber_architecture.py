"""Phase 101: coordinate / fiber architecture audit.

Phase 100's interpretation SURVIVED contact with the algebra. This
module encodes the falsification results and the multi-property audit.

  COORDINATE   c = (formulation_id, property, target_context), realised
               by `resolve_model_state_key`. Complete: it identifies
               every ModelState cell the materials algebra supports.

  FIBER        over each coordinate, the sequence of ModelStates that
               contain it. The coordinate is the base; the state axis is
               the fiber. `ModelState.samples` is literally a mapping
               from coordinate to the fiber's contents at that state.

  NOT A TENSOR No operation anywhere contracts, aggregates or otherwise
               combines two axes into a product quantity. Verified by
               searching every production module.

MULTI-PROPERTY, the Phase 100 gap, resolved precisely: the materials
layer already supports it end to end. A real 2 formulations x 2
properties x 3 contexts programme runs through
reevaluate_program -> generate_candidates -> evaluate -> select -> plan
-> design -> campaign -> session -> observe -> predict -> diagnostics ->
criterion with ZERO production changes, producing 12 candidates over 12
distinct cells and independent per-property verdicts.

The single-property assumption lives in exactly THREE lines of
`workbench/interaction.py` -- the schema field, the criterion
construction and the query construction. Nothing below the workbench
assumes one property. Claim (G) holds.
"""

import ast
import inspect
from pathlib import Path

import pytest

from evidence.admission import admit_document, admit_record, admit_referent
from evidence.identity import content_hash
from evidence.pool import EvidencePool
from evidence.types import make_document, make_record, make_referent, make_source
from experiment.session import ExperimentSession, make_experiment_session, trajectory_of
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.diagnostics import diagnose_transitions
from materials.ensemble import make_counterfactual_set, project_outcome
from materials.evaluation import evaluate_candidates
from materials.iteration import reevaluate_program
from materials.model_state import (
    _transition, make_model_state, predict, resolve_model_state_key,
)
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from materials.trajectory import compare_predictions
from workbench.interaction import ResearchScenario

REPO = Path(__file__).resolve().parent.parent

FORMULATIONS = ("baseline", "modified")
PROPERTIES = ("tensile_strength", "elongation_at_break")
CONTEXTS = ({"temperature_c": 25}, {"temperature_c": 100},
            {"temperature_c": 25, "pressure_kpa": 200})

_ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)


class _Programme:
    """A real multi-property programme, built through the existing APIs
    only. No production code is touched or bypassed."""

    def __init__(self, properties=PROPERTIES, contexts=CONTEXTS, formulations=FORMULATIONS):
        self._tick = 0
        self.pool = EvidencePool()
        from retrieval.engine import DeterministicRetrievalEngine
        self.engine = DeterministicRetrievalEngine()

        source = make_source(kind="lab_notebook", name="phase 101")
        self.pool.put_source(source)
        self.document = make_document(
            source_id=source.id, raw_content="phase 101",
            retrieval_method="manual_entry", retrieved_at=self.clock())
        admit_document(self.pool, self.document)
        self.pool.put_document(self.document)
        process = make_referent(natural_key="process-std-190c", kind="process")
        admit_referent(self.pool, process)
        self.pool.put_referent(process)
        for key in formulations:
            referent = make_referent(natural_key=key, kind="formulation")
            admit_referent(self.pool, referent)
            self.pool.put_referent(referent)

        self.criteria = tuple(
            make_criterion(p, ">=", 75.0, context=c) for p in properties for c in contexts)
        self.query = make_material_program_query(
            list(formulations), "process-std-190c", tuple(properties))
        self.iteration = reevaluate_program(
            self.pool, self.engine, self.query, self.criteria)
        self.candidates = generate_candidates(self.iteration.specification)
        selection = select_candidates(evaluate_candidates(self.candidates), _ALLOW_ALL)
        self.campaign = assemble_experimental_campaign(
            assemble_experimental_design(assemble_experiment_plan(selection)))
        self.session = make_experiment_session(
            self.pool, self.engine, self.iteration, document_id=self.document.id)

    def clock(self) -> str:
        self._tick += 1
        return f"2026-08-26T15:{self._tick:02d}:00Z"

    def cell(self, formulation, prop, context):
        return next(
            c for c in self.candidates.candidates
            if c.formulation.natural_key == formulation and c.property == prop
            and dict(c.target_context) == dict(context))

    def observe(self, candidate, value, unit):
        record = make_record(document_id=self.document.id,
                             locator=f"p101:{self._tick}", raw_content=f"{value} {unit}")
        admit_record(self.pool, record)
        self.pool.put_record(record)
        content = {"property": candidate.property, "value": value, "unit": unit}
        content.update(candidate.target_context)
        entry = next(e for e in self.campaign.entries if e.candidate_id == candidate.id)
        result = make_experimental_result(
            self.campaign, entry, content=content,
            record_id=record.id, extracted_at=self.clock(), extraction_method="measurement:campaign_execution")
        observation, _ = admit_experimental_result(self.pool, result, confidence=1.0)
        prediction = self.session.predict(candidate)
        assessment, self.session = self.session.observe(
            candidate, prediction, result, observation)
        return assessment


# -- (A) one coordinate identifies one cell -------------------------------------------------------------


def test_the_coordinate_is_complete_over_the_declared_programme():
    programme = _Programme()
    assert len(programme.candidates.candidates) == 12          # 2 x 2 x 3
    keys = {resolve_model_state_key(c.formulation.id, c.property, c.target_context)
            for c in programme.candidates.candidates}
    assert len(keys) == 12                                      # different coordinate -> different cell

    # same coordinate -> same cell, recomputed independently
    for candidate in programme.candidates.candidates:
        again = resolve_model_state_key(
            candidate.formulation.id, candidate.property, dict(candidate.target_context))
        assert again == resolve_model_state_key(
            candidate.formulation.id, candidate.property, candidate.target_context)


def test_the_coordinate_survives_repeated_observation_and_state_change():
    """(B) state evolution occurs over FIXED coordinates."""
    programme = _Programme()
    candidate = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    key = resolve_model_state_key(
        candidate.formulation.id, candidate.property, candidate.target_context)

    ids = [programme.session.state.id]
    for value in (90.0, 100.0, 80.0):
        programme.observe(candidate, value, "MPa")
        ids.append(programme.session.state.id)

    assert len(set(ids)) == 4                                   # four distinct states
    assert list(programme.session.state.samples) == [key]       # ONE unchanged coordinate
    assert len(programme.session.state.samples[key]) == 3       # the fiber grew


def test_a_counterfactual_lands_on_the_same_coordinate():
    """(E) counterfactuals are projections, not an axis."""
    programme = _Programme()
    candidate = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    programme.observe(candidate, 90.0, "MPa")
    outcome = project_outcome(programme.session.state, candidate, 70.0)
    key = resolve_model_state_key(
        candidate.formulation.id, candidate.property, candidate.target_context)
    assert outcome.model_state_key == key
    assert outcome.projected_state_id not in {s.id for s in programme.session.state_history}


def test_regenerating_candidates_moves_the_action_not_the_coordinate():
    """(C) candidates are actions, not coordinates."""
    programme = _Programme()
    candidate = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    key = resolve_model_state_key(
        candidate.formulation.id, candidate.property, candidate.target_context)
    programme.observe(candidate, 90.0, "MPa")

    iteration = reevaluate_program(
        programme.pool, programme.engine, programme.query, programme.criteria)
    regenerated = generate_candidates(iteration.specification)
    same_cell = next(
        c for c in regenerated.candidates
        if resolve_model_state_key(c.formulation.id, c.property, c.target_context) == key)
    assert same_cell.id != candidate.id     # the action proposal moved
    assert resolve_model_state_key(         # the coordinate did not
        same_cell.formulation.id, same_cell.property, same_cell.target_context) == key


# -- (D) predictions are derived --------------------------------------------------------------------------


def test_a_prediction_carries_the_coordinate_but_is_not_one():
    programme = _Programme()
    candidate = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    programme.observe(candidate, 90.0, "MPa")
    prediction = programme.session.predict(candidate)
    key = resolve_model_state_key(
        candidate.formulation.id, candidate.property, candidate.target_context)
    assert prediction.model_state_key == key      # it REPORTS the coordinate
    assert prediction.state_id == programme.session.state.id
    # and it is reproducible purely from (state, candidate) -- carrying no id of its own
    assert not hasattr(prediction, "id")
    assert predict(programme.session.state, candidate) == prediction


# -- multi-property audit ----------------------------------------------------------------------------------


def test_two_properties_occupy_independent_cells_end_to_end():
    programme = _Programme()
    tensile = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    elongation = programme.cell("baseline", "elongation_at_break", {"temperature_c": 25})
    assert tensile.formulation.id == elongation.formulation.id
    assert dict(tensile.target_context) == dict(elongation.target_context)

    programme.observe(tensile, 90.0, "MPa")
    programme.observe(elongation, 12.0, "percent")

    assert programme.session.predict(tensile).predicted_value == 90.0
    assert programme.session.predict(elongation).predicted_value == 12.0
    assert len(programme.session.state.samples) == 2
    # diagnostics remain per-candidate
    for candidate in (tensile, elongation):
        diagnostics = diagnose_transitions(
            trajectory_of(programme.session), candidate, ())
        assert diagnostics.candidate_id == candidate.id


def test_criterion_evaluation_is_independent_per_property():
    programme = _Programme()
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")
    programme.observe(
        programme.cell("baseline", "elongation_at_break", {"temperature_c": 25}), 12.0, "percent")

    decision = reevaluate_program(
        programme.pool, programme.engine, programme.query, programme.criteria).decision
    verdicts = {
        (p.criterion.property, tuple(sorted(p.criterion.context.items()))): p.observed_status
        for f in decision.formulations if f.formulation.natural_key == "baseline"
        for p in f.properties
    }
    at_25 = (("temperature_c", 25),)
    assert verdicts[("tensile_strength", at_25)] == "PASS"       # 90 >= 75
    assert verdicts[("elongation_at_break", at_25)] == "FAIL"    # 12 < 75
    # each property's verdict is decided only by its own evidence
    assert verdicts[("tensile_strength", (("temperature_c", 100),))] == "INCOMPARABLE"


def test_the_single_property_assumption_is_confined_to_the_workbench_schema():
    """(G) multi-property is a scenario/schema limitation, nothing more."""
    with pytest.raises(ValueError, match="must be a non-empty string"):
        ResearchScenario.from_config({
            "name": "two", "process": "process-std-190c", "formulations": ["baseline"],
            "property": ["tensile_strength", "elongation_at_break"],
            "criterion": {"operator": ">=", "target": 75.0},
            "contexts": [{"temperature_c": 25}],
        })

    # and no module BELOW the workbench hard-codes a single property
    for package in ("materials", "experiment", "evidence", "retrieval"):
        for path in (REPO / package).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "properties[0]" not in source, path
            assert "single_property" not in source, path


# -- (H) no cross-property relation exists ------------------------------------------------------------------


def test_two_properties_in_one_state_are_not_comparable():
    programme = _Programme()
    tensile = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    elongation = programme.cell("baseline", "elongation_at_break", {"temperature_c": 25})
    programme.observe(tensile, 90.0, "MPa")
    programme.observe(elongation, 12.0, "percent")

    with pytest.raises(AssertionError, match="same ActionCandidate"):
        compare_predictions(programme.session.predict(tensile),
                            programme.session.predict(elongation))
    with pytest.raises(ValueError):
        make_counterfactual_set((
            project_outcome(programme.session.state, tensile, 95.0),
            project_outcome(programme.session.state, elongation, 15.0),
        ))


# -- (F) the registry is an admissible subset, not a necessary product --------------------------------------


def test_a_sparse_programme_is_simply_a_smaller_set_of_cells():
    """Nothing requires Cartesian completeness. Declaring fewer contexts
    for one property is expressible, and the cells that exist are exactly
    the ones declared."""
    full = _Programme()
    sparse = _Programme(properties=("tensile_strength",), contexts=(CONTEXTS[0],))
    assert len(full.candidates.candidates) == 12
    assert len(sparse.candidates.candidates) == 2      # 2 formulations x 1 x 1
    sparse_keys = {resolve_model_state_key(c.formulation.id, c.property, c.target_context)
                   for c in sparse.candidates.candidates}
    full_keys = {resolve_model_state_key(c.formulation.id, c.property, c.target_context)
                 for c in full.candidates.candidates}
    assert sparse_keys < full_keys                     # a proper subset of the same space


def test_an_empty_context_is_a_coordinate_like_any_other():
    programme = _Programme(properties=("tensile_strength",), contexts=({},))
    assert len(programme.candidates.candidates) == 2
    for candidate in programme.candidates.candidates:
        assert dict(candidate.target_context) == {}
        assert len(resolve_model_state_key(
            candidate.formulation.id, candidate.property, candidate.target_context)) == 64


def test_a_never_declared_coordinate_is_representable_and_unoccupied():
    formulation = content_hash({"f": "ghost"})
    key = resolve_model_state_key(formulation, "thermal_conductivity", {"humidity_pct": 40})
    assert len(key) == 64
    assert key not in make_model_state({}).samples


# -- (I) tensor falsification ------------------------------------------------------------------------------


def test_no_production_operation_combines_two_coordinate_axes():
    """A tensor interpretation needs a multilinear operation. There is
    none: no contraction, no cross-axis aggregation, no covariance, no
    embedding over the coordinate product."""
    forbidden = ("contract", "tensor", "einsum", "outer_product", "kron",
                 "covariance", "embedding", "aggregate_axes", "marginalise",
                 "marginalize")
    for package in ("materials", "experiment", "evidence", "retrieval", "workbench"):
        directory = REPO / package
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    lowered = node.name.lower()
                    for name in forbidden:
                        assert name not in lowered, f"{path}: {node.name}"


def test_model_state_is_a_mapping_from_coordinate_to_fiber_contents():
    """The fibered structure is literal, not metaphorical: `samples` maps
    a coordinate to the samples held there at this state."""
    formulation = content_hash({"f": "baseline"})
    key = resolve_model_state_key(formulation, "tensile_strength", {"temperature_c": 25})
    other = resolve_model_state_key(formulation, "tensile_strength", {"temperature_c": 100})
    state = _transition(_transition(make_model_state({}), key, 90.0, "a"), other, 60.0, "b")
    assert set(state.samples) == {key, other}
    assert len(state.samples[key]) == 1 and len(state.samples[other]) == 1
    # the two fibers do not interact
    grown = _transition(state, key, 100.0, "c")
    assert len(grown.samples[key]) == 2
    assert grown.samples[other] == state.samples[other]


# -- transition classification (sec.4) ----------------------------------------------------------------------


def test_the_only_state_producing_operation_is_observe():
    """STATE x INPUT -> STATE exists exactly once. Everything else is
    STATE -> ARTIFACT or STATE x INPUT -> ARTIFACT, which is why no
    generic morphism abstraction is warranted."""
    programme = _Programme()
    candidate = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    before = programme.session

    # STATE -> ARTIFACT: reading never advances
    programme.session.predict(candidate)
    programme.session.inspect_counterfactual(candidate, 70.0)
    trajectory_of(programme.session)
    assert programme.session is before
    assert programme.session.state.id == before.state.id

    # STATE x INPUT -> STATE: returns a NEW session, never mutates
    programme.observe(candidate, 90.0, "MPa")
    assert programme.session is not before
    assert before.state.id != programme.session.state.id
    assert len(before.state_history) == 1


def test_session_transitions_return_new_objects_rather_than_mutating():
    signature = inspect.signature(ExperimentSession.observe)
    assert "return" in str(signature) or signature.return_annotation is not inspect.Signature.empty
    programme = _Programme()
    candidate = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    held = programme.session
    held_id = held.state.id
    programme.observe(candidate, 90.0, "MPa")
    programme.observe(candidate, 100.0, "MPa")
    assert held.state.id == held_id                    # historical fiber point unchanged
    assert len(held.state_history) == 1


# -- historical fibers (sec.5) -------------------------------------------------------------------------------


def test_history_is_a_sequence_over_the_same_coordinate_space():
    programme = _Programme()
    tensile = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    elongation = programme.cell("baseline", "elongation_at_break", {"temperature_c": 25})
    key = resolve_model_state_key(
        tensile.formulation.id, tensile.property, tensile.target_context)

    programme.observe(tensile, 90.0, "MPa")
    after_first = programme.session.state
    programme.observe(elongation, 12.0, "percent")
    programme.observe(tensile, 100.0, "MPa")

    history = programme.session.state_history
    assert len(history) == 4
    # the coordinate exists at every state after it was first occupied,
    # and its historical contents never change
    assert key in after_first.samples
    assert len(after_first.samples[key]) == 1
    assert len(history[-1].samples[key]) == 2
    assert history[1].samples[key] == after_first.samples[key]
    # no second coordinate system was needed to express any of this
    assert all(isinstance(k, str) and len(k) == 64 for s in history for k in s.samples)
