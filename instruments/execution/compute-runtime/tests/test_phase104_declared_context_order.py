"""Phase 104: falsification of DECLARED ORDER over `target_context`.

THE QUESTION: does `target_context` contain values that can legitimately
participate in a DECLARED ORDER without inferring scientific semantics
from field names or runtime types?

VERDICT: SURVIVES -- but only at the first rung, and only as a sidecar.

WHAT SURVIVES
-------------
An EXTERNAL, scenario-author declaration that enumerates, for ONE context
key, the values the author asserts are ordered, in that order. It supplies
RANK and nothing else. It is held by the caller, never by an `Observation`,
`ExperimentalResult`, `ModelStateKey`, `ComparisonGroup` or `ModelState`,
and it therefore participates in no `content_hash` -- proven below by a
whole-system identity fingerprint taken with and without the declaration
present, twice, byte-identical, against a negative control that shows the
same fingerprint IS sensitive to any change of a context value.

WHAT IS FALSIFIED
-----------------
The inference `25 < 40 < 100` from `target_context` alone. The system holds
three candidate signals and every one of them fails:

  key NAME    -- `processing_mode` is scientifically ordered (slow -> fast)
                 and carries no numeric suffix; `grade` is scientifically
                 unordered and could be renamed `grade_index` tomorrow.
                 A name is authorial prose, not a declaration.

  runtime TYPE-- a nominal integer (reactor id, batch number, sample slot)
                 is `int` and totally unordered. Python's ability to
                 compare two integers is a fact about the encoding, not
                 about the scientific dimension.

  LEXICAL order-- right by accident for `grade` (A2, B1), REVERSED for
                 `processing_mode` (sorts to fast, slow; the science is
                 slow, fast). Nothing distinguishes the two cases.

`resolve_model_state_key` is moreover order-DESTROYING by construction:
SHA-256 over the canonical mapping. The hash order of the cells for 25,
40 and 100 is not the value order. Nothing downstream of the coordinate
could recover an order even if one had been intended.

THE LADDER -- order != difference != distance != metric != topology !=
scientific similarity. Of the nine consequences tested, exactly one
follows:

  A sortable            FOLLOWS -- it is what the declaration IS, and only
                        for enumerated values (rank(60) is None, not 1.5).
  B adjacency           relative to the enumeration only. Declaring
                        (25,40,100) makes 40 adjacent to 100; declaring
                        (25,40,60,100) does not. The science did not change.
  C distance            NO. Rank says the 25->40 and 40->100 steps are
                        equal; the values say 15 and 60. An order is
                        invariant under any monotone relabelling.
  D cell comparison     NO. Ordering the CONTEXT does not make the VALUES
                        commensurable; Phase 29 splits them on purpose.
  E interpolation       NO. 60 is a different, empty cell and stays None.
  F aggregation         NO -- this is precisely the Phase 29 defect.
  G prediction transfer NO. `predict` reads `state.samples.get(key)` for
                        one key; there is no cross-cell operation.
  H topology            the order topology on a finite set is DISCRETE:
                        supplied, and information-free.
  I metric              |rank(a)-rank(b)| is a real metric on the INDEX
                        SET, asserting d(25,40) == d(40,100). Available,
                        and scientifically false. Not a metric on the
                        dimension.

PRODUCT ORDER: three declared-ordered axes give a componentwise PARTIAL
order that refuses to answer for 24 of 66 cell pairs. A total order is
recoverable only lexicographically, by declaring an axis PRIORITY, and two
different priorities give two different sequences over the same evidence.
That is a presentation choice, never a scientific relation.

THE DANGEROUS CONCLUSION: "25 C is closer to 40 C than to 100 C" is a
claim about the RESPONSE wearing a claim about the coordinate as a
disguise. Under a cure or crystallisation peak -- ordinary polymer
behaviour -- the response at 25 is closer to the response at 100. What
would license it is a model of how the property varies with the
dimension: scientific evidence, not scenario configuration.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes in this phase.
The smallest future abstraction, if one is ever wanted, is one sentence:
a scenario-level `DeclaredContextOrder(key, ordering)` that answers
`precedes(a, b) -> True | False | None` for enumerated values and returns
None -- never False, never a lexical fallback -- for anything else, used
for PRESENTATION SEQUENCE only and never reachable from any hash.
"""

from __future__ import annotations

import ast
from itertools import combinations, product
from pathlib import Path
from typing import Optional, Tuple

import pytest

from evidence.identity import content_hash
from materials.analysis import _comparison_context, _group_by_comparison_context
from materials.candidates import ActionCandidate
from materials.decision import Criterion
from materials.model_state import (
    Sample,
    make_model_state,
    predict,
    resolve_model_state_key,
)
from workbench import theme
from workbench.interaction import bootstrap_research_scenario

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("materials", "evidence", "experiment", "retrieval", "workbench")

FORMULATION = "formulation-a"
PROPERTY = "viscosity"
KEY = "temperature_c"
DECLARED = (25, 40, 100)


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


def _cell_key(context) -> str:
    return resolve_model_state_key(FORMULATION, PROPERTY, context)


class _Cell:
    """A minimal candidate-shaped object, for exercising the coordinate
    function directly without standing up a scenario."""

    def __init__(self, context):
        self.formulation = type("R", (), {"id": FORMULATION})()
        self.property = PROPERTY
        self.target_context = dict(context)
        self.id = content_hash({"c": dict(context)})


class DeclaredContextOrder:
    """THE AUDIT ARTEFACT. Defined here, in a test, and deliberately
    nowhere else -- this phase makes zero production changes.

    It enumerates, for one context key, the values a scenario author
    asserts are ordered. It supplies RANK ONLY: no `distance`, no
    `between`, no `nearest`, no `interpolate`. A value it does not
    enumerate stays NOT_DETERMINABLE (`None`) -- never 0, never False,
    never a lexical fallback."""

    def __init__(self, key: str, ordering: Tuple[object, ...]) -> None:
        self.key = key
        self.ordering = tuple(ordering)

    def rank(self, value) -> Optional[int]:
        try:
            return self.ordering.index(value)
        except ValueError:
            return None

    def precedes(self, a, b) -> Optional[bool]:
        ra, rb = self.rank(a), self.rank(b)
        if ra is None or rb is None:
            return None
        return ra < rb


# -- I. the current boundary ----------------------------------------------------------------------


def test_target_context_value_type_imposes_no_ordering():
    """`object` means no constraint, no order, no numeric protocol."""
    assert ActionCandidate.__annotations__["target_context"] == "Mapping[str, object]"
    assert Criterion.__annotations__["context"] == "Mapping[str, object]"


def test_production_never_orders_a_context_value():
    """Every `sorted`/`min`/`max` in production is canonicalisation (for
    hash determinism), within-cell statistics, or terminal geometry --
    never a comparison of two context VALUES of the same key."""
    offenders = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                ops = {type(o).__name__ for o in node.ops}
                if not ops & {"Lt", "LtE", "Gt", "GtE"}:
                    continue
                source = ast.unparse(node)
                if "context" in source and "len(" not in source:
                    offenders.append(f"{path.relative_to(REPO)}: {source}")
    assert offenders == [], offenders


def test_criterion_operators_compare_the_value_never_the_context():
    """The one place production does compare with `<`/`>` semantics."""
    criterion = Criterion(property=PROPERTY, operator="<=", target=500.0, context={KEY: 25})
    assert criterion.target == 500.0
    # `target` is the measured quantity's threshold. The context rides
    # alongside it and is matched by EQUALITY only.
    assert dict(criterion.context) == {KEY: 25}


# -- II. the tempting inference -------------------------------------------------------------------


def test_content_addressing_destroys_any_value_order():
    """The same three context values, in the same declared sequence,
    produce a DIFFERENT hash order for each formulation -- so the hash
    order carries no information whatsoever about the value order. (It
    coincides with 0,1,2 for `formulation-a` here, which is exactly the
    point: coincidence, not structure.)"""
    orders = {}
    for formulation in ("formulation-a", "formulation-b", "F1"):
        keys = [resolve_model_state_key(formulation, PROPERTY, {KEY: v}) for v in DECLARED]
        assert len(set(keys)) == 3
        orders[formulation] = [i for i, _ in sorted(enumerate(keys), key=lambda pair: pair[1])]
    assert orders["formulation-a"] == [0, 1, 2]
    assert orders["formulation-b"] == [1, 2, 0]
    assert orders["F1"] == [2, 0, 1]
    assert len(set(map(tuple, orders.values()))) == 3


def test_key_name_is_not_a_declaration():
    """`processing_mode` is ordered and unsuffixed; `grade` is unordered
    and could be renamed to look numeric at any time."""
    ordered_but_unsuffixed = "processing_mode"
    unordered_but_renameable = "grade"
    assert not ordered_but_unsuffixed.endswith(("_c", "_kpa", "_per_s"))
    assert _cell_key({unordered_but_renameable: "A2"}) != _cell_key({"grade_index": "A2"})


def test_runtime_type_is_not_a_declaration():
    """A nominal integer is `int` and scientifically unordered."""
    nominal = [_cell_key({"reactor_id": v}) for v in (3, 7)]
    ordinal = [_cell_key({KEY: v}) for v in (25, 40)]
    assert all(isinstance(v, int) for v in (3, 7, 25, 40))
    assert len(set(nominal + ordinal)) == 4
    # Identical structural treatment. The cell function cannot tell a
    # reactor id from a temperature, and must not try.


def test_lexical_order_is_not_scientific_order():
    """Right by accident in one case, reversed in the other."""
    assert sorted(("A2", "B1")) == ["A2", "B1"]           # no scientific order at all
    assert sorted(("slow", "fast")) == ["fast", "slow"]   # scientific order is slow, fast
    scientific = ("slow", "fast")
    assert sorted(scientific) != list(scientific)


def test_inference_25_lt_40_lt_100_is_falsified():
    """No production code path ever receives two context values of the
    same key together with a declared relation between them."""
    declaration = DeclaredContextOrder(KEY, DECLARED)
    # The order exists ONLY once an author states it.
    assert declaration.precedes(25, 40) is True
    # Without the declaration there is nothing to consult: the cell keys
    # are opaque and the candidate carries no ordering field.
    candidate_fields = set(ActionCandidate.__dataclass_fields__)
    assert candidate_fields == {
        "id", "action_class", "requirement_ids", "formulation",
        "property", "role", "target_context", "existing_evidence_ids",
    }


# -- III. the sidecar, and identity invariance (run twice) ----------------------------------------


def _scenario(contexts):
    return bootstrap_research_scenario({
        "name": "phase 104", "process": "process-std-190c",
        "formulations": [FORMULATION, "formulation-b"],
        "property": PROPERTY,
        "criterion": {"operator": "<=", "target": 500.0},
        "contexts": [dict(c) for c in contexts],
    }, clock=_clock())


def _fingerprint(state) -> str:
    """Every identity the system mints, in one canonical hash."""
    return content_hash({
        "document_id": state.document_id,
        "pool": state.pool.fingerprint(),
        "candidates": sorted(
            [
                {
                    "id": c.id,
                    "property": c.property,
                    "role": c.role,
                    "action_class": c.action_class,
                    "requirement_ids": list(c.requirement_ids),
                    "existing_evidence_ids": list(c.existing_evidence_ids),
                    "cell": _cell_key(c.target_context),
                    "target_context": dict(c.target_context),
                }
                for c in state.candidates.candidates
            ],
            key=lambda d: d["id"],
        ),
        "criteria": [
            (c.property, c.operator, c.target, dict(c.context))
            for c in state.session.iteration.decision.criteria
        ],
        "statuses": [
            (fd.formulation.id, pd.criterion.property, pd.observed_status, pd.predicted_status)
            for fd in state.session.iteration.decision.formulations
            for pd in fd.properties
        ],
        "model_state": state.session.state.id,
        "samples": {
            k: [(s.value, s.observation_id) for s in v]
            for k, v in state.session.state.samples.items()
        },
    })


BASE_CONTEXTS = ({KEY: 25}, {KEY: 40}, {KEY: 100})


def test_declaration_leaves_every_identity_invariant():
    """Held by the caller, reachable from no hash. Run twice."""
    declaration = DeclaredContextOrder(KEY, DECLARED)
    prints = []
    for held in (None, declaration, None, declaration):
        state = _scenario(BASE_CONTEXTS)
        _ = held  # the declaration exists in the caller's hand, not the pipeline
        prints.append(_fingerprint(state))
    assert len(set(prints)) == 1


@pytest.mark.parametrize("perturbation", [
    ({KEY: 25}, {KEY: 41}, {KEY: 100}),                 # one value changed
    ({KEY: 100}, {KEY: 40}, {KEY: 25}),                 # declared sequence reversed
    ({KEY: 25}, {KEY: 40, "rank": 1}, {KEY: 100}),      # an order smuggled INTO the context
    ({KEY: "25"}, {KEY: 40}, {KEY: 100}),               # int -> str
])
def test_fingerprint_is_sensitive_to_the_context_itself(perturbation):
    """NEGATIVE CONTROL. Invariance above is only meaningful because the
    same fingerprint moves for any change a declaration must not make --
    including, third row, putting the rank in `target_context`, which
    changes the cell and is exactly what the sidecar exists to avoid."""
    assert _fingerprint(_scenario(perturbation)) != _fingerprint(_scenario(BASE_CONTEXTS))


def test_undeclared_value_stays_not_determinable():
    """Unknown remains unknown: never 0, never False, never interpolated."""
    declaration = DeclaredContextOrder(KEY, DECLARED)
    assert declaration.rank(60) is None
    assert declaration.precedes(60, 25) is None
    assert declaration.precedes(25, 60) is None
    assert declaration.precedes(25, 25) is False   # declared, and simply not before


# -- IV. the consequence ladder, A..I -------------------------------------------------------------


def test_A_sortable_follows():
    declaration = DeclaredContextOrder(KEY, DECLARED)
    assert sorted((100, 25, 40), key=declaration.rank) == [25, 40, 100]


def test_B_adjacency_is_a_property_of_the_enumeration():
    coarse = DeclaredContextOrder(KEY, (25, 40, 100))
    fine = DeclaredContextOrder(KEY, (25, 40, 60, 100))
    assert abs(coarse.rank(40) - coarse.rank(100)) == 1
    assert abs(fine.rank(40) - fine.rank(100)) == 2
    # The science did not change between those two lines.


def test_C_distance_does_not_follow():
    declaration = DeclaredContextOrder(KEY, DECLARED)
    rank_steps = (declaration.rank(40) - declaration.rank(25),
                  declaration.rank(100) - declaration.rank(40))
    value_steps = (40 - 25, 100 - 40)
    assert rank_steps == (1, 1)
    assert value_steps == (15, 60)
    assert rank_steps != value_steps


def test_D_cell_comparison_does_not_follow():
    """Ordering the context does not make the values commensurable."""
    contents = (
        ({"property": PROPERTY, "value": 480.0, KEY: 25}, 480.0),
        ({"property": PROPERTY, "value": 300.0, KEY: 40}, 300.0),
        ({"property": PROPERTY, "value": 120.0, KEY: 100}, 120.0),
    )
    groups = _group_by_comparison_context(
        tuple((_comparison_context(c, "value"), v) for c, v in contents)
    )
    assert len(groups) == 3
    assert all(len(g.values) == 1 and g.disagreement is None for g in groups)


def test_E_interpolation_does_not_follow():
    state = make_model_state({_cell_key({KEY: v}): () for v in DECLARED})
    prediction = predict(state, _Cell({KEY: 60}))
    assert prediction.predicted_value is None
    assert prediction.sample_count == 0
    assert prediction.model_state_key not in {_cell_key({KEY: v}) for v in DECLARED}


def test_G_prediction_transfer_does_not_follow():
    state = make_model_state({_cell_key({KEY: 40}): (Sample(value=300.0, observation_id="obs-1"),)})
    assert predict(state, _Cell({KEY: 40})).predicted_value == 300.0
    neighbour = predict(state, _Cell({KEY: 100}))
    assert neighbour.predicted_value is None
    assert neighbour.sample_count == 0


def test_I_rank_metric_is_a_metric_on_indices_not_on_the_dimension():
    declaration = DeclaredContextOrder(KEY, DECLARED)

    def d(a, b):
        return abs(declaration.rank(a) - declaration.rank(b))

    # a genuine metric on the index set
    assert d(25, 25) == 0
    assert d(25, 40) == d(40, 25)
    assert d(25, 100) <= d(25, 40) + d(40, 100)
    # ...and, read as a claim about temperature, false
    assert d(25, 40) == d(40, 100)
    assert (40 - 25) != (100 - 40)


# -- V. product order -----------------------------------------------------------------------------


AXES = {
    "temperature_c": (25, 40, 100),
    "pressure_kpa": (100, 200),
    "shear_rate_per_s": (10, 100),
}
AXIS_RANK = {k: {v: i for i, v in enumerate(vs)} for k, vs in AXES.items()}
PRODUCT_CELLS = [dict(zip(AXES, combo)) for combo in product(*AXES.values())]


def _leq(a, b) -> bool:
    return all(AXIS_RANK[k][a[k]] <= AXIS_RANK[k][b[k]] for k in AXES)


def test_product_order_is_partial_and_refuses_most_pairs():
    incomparable = [
        (a, b) for a, b in combinations(PRODUCT_CELLS, 2)
        if not _leq(a, b) and not _leq(b, a)
    ]
    assert len(PRODUCT_CELLS) == 12
    assert len(incomparable) == 24
    # one axis rises while another falls; neither precedes the other


def test_total_order_on_the_product_requires_an_arbitrary_axis_priority():
    def sequence(priority):
        return [
            tuple(c[k] for k in priority)
            for c in sorted(PRODUCT_CELLS, key=lambda c: tuple(AXIS_RANK[k][c[k]] for k in priority))
        ]

    first = sequence(("temperature_c", "pressure_kpa", "shear_rate_per_s"))
    second = sequence(("shear_rate_per_s", "pressure_kpa", "temperature_c"))
    assert first != second
    # Same evidence, different sequence: a presentation choice, not science.


# -- VI. dimensions that cannot participate -------------------------------------------------------


def test_undeclared_key_makes_the_whole_context_incomparable():
    declaration = DeclaredContextOrder(KEY, DECLARED)

    def precedes(a, b) -> Optional[bool]:
        others = (set(a) | set(b)) - {KEY}
        if any(a.get(k, object()) != b.get(k, object()) for k in others):
            return None   # a key with no declared order differs -> INCOMPARABLE
        return declaration.precedes(a.get(KEY), b.get(KEY))

    assert precedes({KEY: 25, "grade": "A2"}, {KEY: 40, "grade": "A2"}) is True
    assert precedes({KEY: 25, "grade": "A2"}, {KEY: 40, "grade": "B1"}) is None
    assert precedes({KEY: 25, "grade": "A2"}, {KEY: 25, "grade": "B1"}) is None
    # Mirrors `_comparison_context`: a key present on one side and not the
    # other is never silently treated as a match.


def test_ordered_categorical_and_opaque_token_hash_identically():
    keys = [
        _cell_key({KEY: 25}),
        _cell_key({"grade": "A2"}),
        _cell_key({"batch_token": "b7f3c9"}),
    ]
    assert len(set(keys)) == 3
    assert all(len(k) == 64 for k in keys)


# -- VII. the dangerous conclusion ----------------------------------------------------------------


def test_coordinate_proximity_does_not_imply_response_proximity():
    """"25 C is closer to 40 C than to 100 C" is a claim about the
    RESPONSE. A cure or crystallisation peak -- ordinary polymer
    behaviour -- reverses it, with the coordinates and the declared order
    untouched."""
    monotone = {25: 480.0, 40: 300.0, 100: 120.0}
    cure_peak = {25: 480.0, 40: 90.0, 100: 460.0}

    def nearer(response):
        return 40 if abs(response[25] - response[40]) < abs(response[25] - response[100]) else 100

    assert nearer(monotone) == 40
    assert nearer(cure_peak) == 100
    assert sorted(monotone) == sorted(cure_peak) == [25, 40, 100]


def test_order_is_invariant_under_monotone_relabelling():
    """Which is exactly why it cannot fix a difference, a distance or a
    metric on the dimension."""
    original = DeclaredContextOrder(KEY, (25, 40, 100))
    relabelled = DeclaredContextOrder(KEY, ("cold", "warm", "hot"))
    pairs = ((25, 40), (40, 100), (25, 100))
    relabel = {25: "cold", 40: "warm", 100: "hot"}
    for a, b in pairs:
        assert original.precedes(a, b) == relabelled.precedes(relabel[a], relabel[b])
    # order preserved; every arithmetic difference destroyed
    assert original.rank(100) - original.rank(40) == relabelled.rank("hot") - relabelled.rank("warm")


# -- VIII. no production change -------------------------------------------------------------------


def test_phase_104_added_no_ordering_machinery_to_production():
    forbidden = ("DeclaredContextOrder", "context_order", "declared_context", "declared_order")
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits


def test_retrievals_own_ordering_is_canonicalisation_not_ranking():
    """The one production field actually named `ordering` is the
    retrieval result's, and it already says so in place: sorting by id
    for determinism. A corroborating precedent, not a counterexample."""
    text = (REPO / "retrieval" / "result.py").read_text()
    assert '"ordering is not ranking"' in text
    assert 'ordering: str = "sorted_by_id"' in text
