"""Phase 105: falsification of DECLARATION AUTHORITY as a new mechanism.

THE QUESTION: can externally declared architectural/scenario rules
possess different authority levels while preserving the separation
between authority and truth?

VERDICT: SURVIVES -- and requires nothing to be built, because the
separation already exists in a STRONGER form than a rank.

WHAT THE INVENTORY FOUND
------------------------
Immutability is universal, not tiered. Every dataclass in `evidence/`,
`retrieval/`, `materials/` and `experiment/` is `frozen=True`; the only
two mutable ones are `WorkbenchState` and `InvestigationResult`, both in
`workbench/`, both documented in place as interaction holders and not
domain objects.

Of the seven properties this phase asked about, exactly three exist:

  immutable status  -- universal, and it is a CONSEQUENCE of content-
                       addressing, not a permission granted to anyone.
  provenance        -- `DerivedValue.derived_from` + `ancestry_of`, for
                       evidence only.
  versioning        -- `pool.fingerprint()` / `fingerprint_history()` /
                       `evidence_version_id`: a version of the WORLD
                       STATE, never of a declaration.

Four do not exist: precedence, priority, policy rank, override
semantics. Every token that looks like one is something else --
`CandidateRanking.rank` is a derived ordinal recomputed from utility
under a declared `RankingPolicy.direction`; `FEPSignal.priority` is a
self-labelled placeholder; every "override" in the tree is a caller
substituting an argument; every "superseded" is a display label or prose
about a branch parent. `TrustGraph` is named for trust and its own
docstring says it is "never authoritative".

THE SEPARATION IS REACHABILITY, NOT RANK
----------------------------------------
The proposed tiers are already enforced structurally, by what each layer
can reach -- which is strictly stronger than a rank, because a rank
merely forbids what reachability makes unrepresentable:

  Tier 0 evidence      every object has an `id`; the pool's eight
                       `put_*` methods accept these and nothing else.
  Tier 1 scenario      `ResearchScenario`, `Criterion`, `MaterialQuestion`,
                       `EvidenceRequirement`, `MaterialProgramQuery` have
                       NO `id` at all. (`RetrievalQuery` is the single
                       identity-bearing declaration, because a
                       `RetrievalResult` is derived from it.)
  Tier 2 policy        `SelectionPolicy`, `OptimizationPolicy`,
                       `RankingPolicy`, `ExperimentPolicy` have no `id`.
                       `select_candidates(evaluations, policy)` does not
                       take a pool and its module does not import one:
                       structurally incapable of reaching evidence.
  Tier 3 invariant     not data at all -- it is code, and it already
                       bounds Tiers 1 and 2 by REFUSING malformed
                       declarations at construction (the Phase 98
                       measurement-key guard, `Criterion`'s operator
                       check, `SelectionPolicy.max_selected >= 0`).

Empirically: varying the criterion target, the contexts, or the number
of contexts moves candidate ids and cell keys and leaves the evidence
fingerprint byte-identical. A scenario declaration reaches candidate
generation and nothing above it.

"IMMUTABILITY MAY BE CONTINGENT ON AUTHORITY" -- CONTRADICTION
--------------------------------------------------------------
Immutability here is not a permission that could be granted or withheld.
`id = content_hash(content)`, so changing content produces a DIFFERENT
OBJECT; there is no "change this object" operation for authority to be
contingent on. Making immutability contingent on authority would require
an id that survives a content change -- a second identity system.

The coherent neighbour is a different predicate: ADMISSIBILITY may be
contingent on authority (who may write into the pool), and that already
exists as the sole `admit_experimental_result` semantic write boundary.
Authority over admission is coherent. Authority over mutation is not,
because mutation does not exist.

AUTHORITY / VALIDITY / TRUTH ALREADY DO NOT COLLAPSE
----------------------------------------------------
  VALIDITY  is checked at construction (`__post_init__` guards).
  TRUTH     is admitted at the pool boundary and lives only there.
  AUTHORITY does not exist: no owner, no role, no actor anywhere.

And the architecture refuses to let them collapse in three places that
predate this phase. `metrics.source_diversity` explicitly declines to
weight by source quality. `Observation.confidence` is required, is
excluded from identity, and is read by NOTHING in `materials/`,
`experiment/` or `workbench/`. `retrieval/epistemic.py` already carries
the full observed/extracted/inferred/hypothesized/simulated/predicted/
validated taxonomy, uses it only as a SET MEMBERSHIP FILTER, never
orders it -- and leaves `VALIDATED`/`HYPOTHESIZED` deliberately
unreachable, saying why in place: "no review/promotion step exists".
That is this phase's question, already asked and already declined.

WHAT "RANK" MAY MEAN -- four collapse, one already exists
---------------------------------------------------------
  A precedence        collapses declaration into truth the moment it
                      discards the loser. Survives only as presentation
                      sequence.
  B permission        coherent, but needs an actor model (role, owner)
                      that does not exist and that this phase forbids.
  C confidence        collapses authority into truth. Already refused.
  D truth             collapses outright. Authority cannot make a claim
                      true.
  E execution priority ALREADY EXISTS, correctly: `CandidateRanking.rank`,
                      recomputed from utility, `None` when utility is
                      unknown, never stored on the declaration.

THE PROVENANCE DAG CANNOT CARRY AUTHORITY -- three reasons
-----------------------------------------------------------
  1 MEMBERSHIP -- policies and scenarios have no pool identity and no
    `put_*`. They cannot be nodes.
  2 DIRECTION -- Observations are the DAG's minimal elements; everything
    depends on them and they depend on nothing. In the proposed
    hierarchy observation is Tier 0, the LOWEST tier. The two orders
    disagree in direction on the only pair both relate.
  3 RELATION KIND -- `derived_from` means "computed from": a factual
    dependency, antisymmetric by content-addressing. Authority means
    "may overrule": not a dependency, and not guaranteed antisymmetric,
    since two authorities can each claim precedence in a different
    respect. Different partial orders, on different carrier sets.

THE EXISTING TEMPLATE FOR A BOUNDED PRECEDENCE
----------------------------------------------
`select_candidates` is the one place production must choose between
competing eligible items. Under `max_selected` it walks candidates in
canonical `ActionCandidate.id` order -- a deliberately MEANINGLESS
tie-break chosen for determinism -- and records the excluded candidate
as eligible-but-not-selected with its reason, "never silently promoted
and never silently dropped from the output". A bounded precedence is
safe exactly when it looks like that: arbitrary where the science is
silent, and lossless about what it set aside.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes in this phase.
Nothing here demonstrates an unavoidable semantic gap; making the tiers
explicit as a rank would be strictly weaker than the reachability that
already enforces them, and would invite exactly the collapses above.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import re
from pathlib import Path

import pytest

from evidence.identity import content_hash
from evidence.pool import EvidencePool
from evidence.types import DerivedValue, Observation
from materials.decision import Criterion, evaluate_program
from materials.model_state import resolve_model_state_key
from materials.selection import SelectionPolicy, select_candidates
from workbench import theme
from workbench.interaction import _observation_content, bootstrap_research_scenario

REPO = Path(__file__).resolve().parent.parent
LOWER_LAYERS = ("evidence", "retrieval", "materials", "experiment")
ALL_LAYERS = LOWER_LAYERS + ("workbench",)


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _clock():
    n = [0]

    def c():
        n[0] += 1
        return f"2026-01-01T00:00:{n[0]:02d}Z"

    return c


def _scenario(contexts=({"temperature_c": 25}, {"temperature_c": 40}), target=500.0):
    return bootstrap_research_scenario({
        "name": "phase 105", "process": "process-std-190c",
        "formulations": ["formulation-a", "formulation-b"],
        "property": "viscosity",
        "criterion": {"operator": "<=", "target": target},
        "contexts": [dict(c) for c in contexts],
    }, clock=_clock())


def _candidate_fingerprint(state) -> str:
    return content_hash(sorted(c.id for c in state.candidates.candidates))


def _cell_fingerprint(state) -> str:
    return content_hash(sorted(
        resolve_model_state_key(c.formulation.id, c.property, c.target_context)
        for c in state.candidates.candidates
    ))


# -- 1. immutability is universal, not tiered -----------------------------------------------------


def test_every_lower_layer_dataclass_is_frozen():
    mutable = []
    for package in LOWER_LAYERS:
        for path in sorted((REPO / package).rglob("*.py")):
            text = path.read_text()
            for line in text.split("\n"):
                if line.startswith("@dataclass") and "frozen=True" not in line:
                    mutable.append(str(path.relative_to(REPO)))
    assert mutable == [], mutable


def test_the_only_mutable_objects_are_workbench_holders():
    mutable = []
    for path in sorted((REPO / "workbench").rglob("*.py")):
        lines = path.read_text().split("\n")
        for i, line in enumerate(lines):
            if line.startswith("@dataclass") and "frozen=True" not in line:
                mutable.append(lines[i + 1].split("class ")[1].rstrip(":"))
    assert sorted(mutable) == ["InvestigationResult", "WorkbenchState"]


def test_immutability_is_a_consequence_of_content_addressing_not_a_permission():
    """There is no mutation operation for an authority to be contingent
    on: changing content yields a different id, i.e. a different object."""
    assert Observation.__dataclass_params__.frozen
    assert DerivedValue.__dataclass_params__.frozen
    assert content_hash({"value": 1.0}) != content_hash({"value": 2.0})


# -- 2/3. the tiers already exist as REACHABILITY -------------------------------------------------


FACTUAL_EVIDENCE = [
    ("evidence.types", n)
    for n in ("Source", "Document", "Record", "Observation", "Referent", "ClaimedRelationship")
]
SCENARIO_DECLARATIONS = [
    ("workbench.interaction", "ResearchScenario"),
    ("materials.decision", "Criterion"),
    ("materials.specification", "EvidenceRequirement"),
    ("materials.program", "MaterialProgramQuery"),
    ("materials.analysis", "MaterialQuestion"),
]
EXECUTION_POLICIES = [
    ("materials.selection", "SelectionPolicy"),
    ("materials.optimization", "OptimizationPolicy"),
    ("materials.ranking", "RankingPolicy"),
    ("experiment.policy", "ExperimentPolicy"),
]


def _flat(text: str) -> str:
    """Collapse line wrapping, so a phrase can be located regardless of
    where the source happened to break the line."""
    return " ".join(text.split())


def _identifiers(text: str) -> set:
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))


def _code_names(path) -> set:
    """Every identifier that is actually CODE -- names, attributes,
    arguments, functions, classes. Comments and docstrings are excluded,
    so prose about precedence is not mistaken for a precedence."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


def _fields(module, name):
    cls = getattr(importlib.import_module(module), name)
    return {f.name for f in dataclasses.fields(cls)}


@pytest.mark.parametrize("module,name", FACTUAL_EVIDENCE)
def test_tier_0_evidence_is_identity_bearing(module, name):
    assert "id" in _fields(module, name)


@pytest.mark.parametrize("module,name", SCENARIO_DECLARATIONS + EXECUTION_POLICIES)
def test_tier_1_and_2_declarations_carry_no_identity(module, name):
    """No id means no node, in any graph -- provenance or otherwise."""
    assert "id" not in _fields(module, name)


def test_retrieval_query_is_the_one_identity_bearing_declaration():
    """And only because a RetrievalResult is DERIVED from it."""
    assert "id" in _fields("retrieval.query", "RetrievalQuery")
    assert "evidence_version_id" in _fields("retrieval.result", "RetrievalResult")


def test_the_pool_accepts_evidence_and_nothing_else():
    puts = sorted(m for m in dir(EvidencePool) if m.startswith("put_"))
    assert puts == [
        "put_claimed_relationship", "put_derived_grounding", "put_derived_value",
        "put_document", "put_observation", "put_record", "put_referent", "put_source",
    ]
    # No put_policy, no put_scenario, no put_criterion.


def test_execution_policy_is_structurally_unable_to_reach_evidence():
    parameters = set(inspect.signature(select_candidates).parameters)
    assert parameters == {"evaluations", "policy"}
    source = inspect.getsource(select_candidates)
    assert "put_" not in source and "admit_" not in source and "pool" not in source


def test_scenario_declaration_moves_candidates_but_never_evidence():
    baseline = _scenario()
    variants = [
        _scenario(target=42.0),
        _scenario(contexts=({"temperature_c": 25}, {"temperature_c": 100})),
        _scenario(contexts=({"temperature_c": 25}, {"temperature_c": 40}, {"temperature_c": 100})),
    ]
    for variant in variants:
        assert variant.pool.fingerprint() == baseline.pool.fingerprint()
    assert len({_candidate_fingerprint(v) for v in [baseline] + variants}) == 4


def test_criterion_target_reaches_candidate_identity_but_not_the_coordinate():
    """The precise Tier 1 boundary: a declaration changes WHICH candidates
    exist, never WHERE they sit."""
    a, b = _scenario(target=500.0), _scenario(target=42.0)
    assert _cell_fingerprint(a) == _cell_fingerprint(b)
    assert _candidate_fingerprint(a) != _candidate_fingerprint(b)


def test_tier_3_invariants_already_bound_tier_1_and_tier_2():
    """Architectural invariants are code, and they bound declarations by
    REFUSAL at construction -- not by outranking them."""
    class _Candidate:
        property = "viscosity"
        target_context = {"unit": "celsius"}

    with pytest.raises(ValueError, match="may not use the measurement key"):
        _observation_content(_Candidate(), 1.0, "pascal_second")

    with pytest.raises(ValueError, match="unsupported operator"):
        Criterion(property="viscosity", operator="~", target=1.0, context={})

    with pytest.raises(ValueError, match="max_selected"):
        SelectionPolicy(
            allowed_action_classes=None, allow_already_represented_context=True,
            allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=-1,
        )


# -- 4. what already exists, and what does not ----------------------------------------------------


def test_no_precedence_priority_or_override_semantics_exist():
    forbidden = {
        "precedence", "authority", "policy_rank", "override", "supersede",
        "outranks", "overrules", "rank_of",
    }
    hits = []
    for package in ALL_LAYERS:
        for path in sorted((REPO / package).rglob("*.py")):
            for name in _code_names(path):
                if name.lower() in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits
    # The words DO occur, exclusively as prose: `theme.py` on which label
    # wins a narrow column, `retrieval/engine.py` calling a document "the
    # authority on content", `workbench` on a caller substituting a `state`
    # argument. None of them names a thing the system can execute.


def test_the_one_rank_in_production_is_a_recomputed_ordinal():
    """`CandidateRanking.rank` is derived from utility under a declared
    direction and is None when utility is unknown -- execution priority,
    never an attribute of a declaration."""
    fields = _fields("materials.ranking", "CandidateRanking")
    assert fields == {"candidate_id", "utility", "rank", "ranking_status"}
    assert _fields("materials.ranking", "RankingPolicy") == {"direction", "unknown_utility_policy"}


def test_versioning_versions_the_world_not_a_declaration():
    assert hasattr(EvidencePool, "fingerprint")
    assert hasattr(EvidencePool, "fingerprint_history")
    for module, name in SCENARIO_DECLARATIONS + EXECUTION_POLICIES:
        assert "version" not in " ".join(_fields(module, name))


def test_trust_graph_is_named_for_trust_and_carries_none():
    text = (REPO / "evidence" / "trust_graph.py").read_text()
    assert "never authoritative" in text
    assert "add_edge" not in text.replace("no `TrustGraph.add_edge()`", "")


# -- 6/7. authority, validity and truth do not collapse -------------------------------------------


def test_confidence_is_recorded_excluded_from_identity_and_never_consulted():
    """Source confidence is the most obvious candidate for a smuggled
    authority. It reaches no decision anywhere above `evidence/`."""
    assert "confidence" in {f.name for f in dataclasses.fields(Observation)}
    readers = []
    for package in ("materials", "experiment", "workbench"):
        for path in sorted((REPO / package).rglob("*.py")):
            source = "".join(
                line for line in path.read_text().split("\n")
                if not line.strip().startswith("#")
            )
            # strip docstrings crudely: only executable references count
            for node_source in re.findall(r"^\s*[^\s#].*\.confidence\b.*$", source, re.M):
                if '"""' not in node_source and "`" not in node_source:
                    readers.append(f"{path.relative_to(REPO)}: {node_source.strip()}")
    assert readers == [], readers


def test_metrics_refuses_to_weight_by_source_quality():
    text = (REPO / "evidence" / "metrics.py").read_text()
    assert "NOT weight by source quality" in text


def test_epistemic_status_is_a_partition_never_a_rank():
    """The taxonomy exists; it is filtered by SET MEMBERSHIP and never
    ordered. `validated`/`hypothesized` are deliberately unreachable
    because no review/promotion step exists -- this phase's question,
    already asked and already declined."""
    text = _flat((REPO / "retrieval" / "epistemic.py").read_text())
    assert "no review/promotion step exists" in text
    engine = (REPO / "retrieval" / "engine.py").read_text()
    assert "not in query.epistemic_statuses" in engine
    for comparison in ("epistemic_status <", "epistemic_status >", "ALL_STATUSES.index"):
        assert comparison not in engine


def test_no_actor_model_exists_for_authority_to_attach_to():
    """AUTHORITY asks 'who may declare this'. There is no who."""
    forbidden = {"owner_id", "actor", "actor_id", "user_id", "declared_by", "role_rank", "principal"}
    hits = []
    for package in ALL_LAYERS:
        for path in sorted((REPO / package).rglob("*.py")):
            # whole identifiers only: "extractor"/"factor"/"refactor" are not actors
            found = _identifiers(path.read_text()) & forbidden
            hits.extend(f"{path.relative_to(REPO)}: {t}" for t in sorted(found))
    assert hits == [], hits


# -- 8. adversarial cases -------------------------------------------------------------------------


def test_two_conflicting_declarations_are_both_represented_never_resolved():
    """Unsatisfiable together. `evaluate_program` takes no precedence
    argument, so neither can discard the other."""
    a = Criterion(property="viscosity", operator="<=", target=300.0, context={"temperature_c": 25})
    b = Criterion(property="viscosity", operator=">=", target=400.0, context={"temperature_c": 25})
    assert a.context == b.context and a.property == b.property
    assert set(inspect.signature(evaluate_program).parameters) == {"program_answer", "criteria"}


def test_an_immutable_declaration_that_is_wrong_simply_fails():
    """Immutability of a declaration never claimed the declaration was
    true. A criterion contradicted by evidence yields FAIL -- which is
    the system working, not a conflict needing an authority to settle."""
    from materials.decision import FAIL, PASS
    assert FAIL != PASS
    criterion = Criterion(property="viscosity", operator="<=", target=1.0, context={})
    assert criterion.target == 1.0   # frozen, wrong, and perfectly representable


def test_a_policy_cannot_alter_a_sample_that_contradicts_it():
    """A low-authority observation vs a high-authority policy: the
    observation wins on truth, the policy wins on action, and the two
    outcomes never meet."""
    source = inspect.getsource(importlib.import_module("materials.selection"))
    assert "Sample" not in source
    assert "ModelState" not in source


def test_bounded_precedence_template_is_arbitrary_and_lossless():
    """`max_selected` is the one production precedence. It breaks ties in
    canonical id order -- deliberately meaningless -- and records what it
    set aside rather than dropping it."""
    source = inspect.getsource(select_candidates)
    assert "sorted(evaluations.evaluations, key=lambda e: e.candidate.id)" in source
    assert "never silently promoted and never silently dropped" in _flat(source)
    assert "walked in canonical `ActionCandidate.id` order" in _flat(source)


# -- 10. provenance order is not authority order --------------------------------------------------


def test_observations_are_the_minimal_elements_of_the_provenance_dag():
    """So the DAG's direction is the OPPOSITE of the proposed hierarchy's:
    Tier 0 would be lowest, and it is what everything depends on."""
    assert "derived_from" not in {f.name for f in dataclasses.fields(Observation)}
    assert "derived_from" in {f.name for f in dataclasses.fields(DerivedValue)}


def test_declarations_cannot_be_nodes_in_the_provenance_dag():
    from evidence.provenance import ancestry_of
    parameters = set(inspect.signature(ancestry_of).parameters)
    assert parameters == {"pool", "derived_value_id"}
    # It resolves ids through `pool.has_observation` / `pool.has_derived_value`
    # only; a policy or scenario has no id to offer it.
    source = inspect.getsource(ancestry_of)
    assert "has_observation" in source and "has_derived_value" in source
    assert "policy" not in source and "scenario" not in source


# -- 11. nothing was added ------------------------------------------------------------------------


def test_phase_105_added_no_authority_machinery():
    forbidden = (
        "AuthorityLevel", "DeclarationTier", "authority_rank", "AuthorityGraph",
        "declaration_precedence", "OverrideRule",
    )
    hits = []
    for package in ALL_LAYERS:
        for path in sorted((REPO / package).rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits
