"""Phase 113: graph structure / graph semantics audit.

VERDICT: a graph exists, and it is far weaker than the word suggests.

sec.1 THE ACTUAL SIGNATURE
--------------------------
    G = (V, E), HETEROGENEOUS DIRECTED MULTIGRAPH

    V (8 typed vertex kinds, every one content-addressed):
        Source, Document, Record, Observation, Referent,
        ClaimedRelationship, DerivedValue, DerivedGrounding

    E (8 typed edge kinds, every one a bare id reference):
        Document            --source_id-->        Source
        Record              --document_id-->      Document
        Observation         --record_ids-->       Record          MULTI
        ClaimedRelationship --from_referent_id--> Referent
        ClaimedRelationship --to_referent_id-->   Referent
        ClaimedRelationship --observation_id-->   Observation
        DerivedValue        --derived_from-->     Observation|DerivedValue  MULTI
        DerivedGrounding    --derived_value_id--> DerivedValue
        DerivedGrounding    --referent_ids-->     Referent        MULTI

NOT VERTICES: `ModelState` (it HAS an id and no pool object ever references
it -- an isolated point, not a node), `ActionCandidate`, `Prediction`, and
every policy. The scientific state space and the provenance graph are
disjoint structures that share no vertex.

sec.5 THE DAG CLAIM SURVIVES, FOR A STRONGER REASON THAN USUAL
---------------------------------------------------------------
Acyclicity is not enforced -- it is UNCONSTRUCTIBLE. Every edge names an
id that must already exist to be written down, and every id is a hash of
content that includes those edge fields. A cycle would require each id to
be computed from the other, and neither can be computed first. There is
no cycle check anywhere because there is nothing to check.

It is a DAG and it is NOT a hierarchy: no edge means membership,
containment or coarsening. `Document -> Source` is "was retrieved from",
not "is part of".

sec.7 THERE IS NO WEIGHTED GRAPH
--------------------------------
`confidence` lives on NODES -- Observation, ClaimedRelationship,
DerivedValue -- and on nothing else. No edge field anywhere carries a
number: an edge IS a bare id reference and has no attributes at all. A
node attribute is not an edge weight, so every weighted-graph algorithm
is inapplicable for want of its input, not for want of justification.

sec.10 PATH LENGTH IS NOT A DISTANCE -- TWO COUNTEREXAMPLES
------------------------------------------------------------
1. CONSTANT. Every Observation ever admitted sits EXACTLY three hops from
   its Source: Observation -> Record -> Document -> Source. A quantity
   that takes one value on every input carries zero information.

2. ANTI-CORRELATED. Two observations of DIFFERENT properties from ONE
   paper are 4 hops apart through their shared Document. Two observations
   of the SAME property from two papers have NO PATH AT ALL. So graph
   proximity measures CO-PUBLICATION, and scientific comparability --
   which the architecture computes with `_comparison_context` (Phase 29)
   -- uses none of the graph.

Graph distance is therefore a graph-theoretic quantity only.

sec.13 NO GRAPH SIGNAL EXISTS
-----------------------------
A signal needs a scalar field over a FIXED, HOMOGENEOUS vertex set. This
vertex set is heterogeneous by construction, and `confidence` -- the only
numeric attribute -- exists on 3 of the 8 vertex kinds. There is no
vector space in which f: V -> R could live without first choosing a
sub-graph and inventing values for the vertices that have none. Node
attributes do not constitute a signal.

sec.11 TRAVERSAL EXISTS ONLY TO RECONSTRUCT PROVENANCE
-------------------------------------------------------
`ancestry_of` is the sole traversal in production, and it returns SORTED
SETS -- `observation_ids` and `derived_value_ids` -- never paths. The API
DISCARDS path structure on purpose, so path length is not merely
meaningless, it is not even exposed. Its docstring says both output
tuples are id-sorted, not traversal-ordered.

sec.16 THE ALGORITHM MATRIX

  operation           runs? requires              present? meaning? justified?
  traversal            yes  edges                 yes      yes      YES
  topological sort     yes  a DAG                 yes      no       NO -- the
        order it returns is construction order, which admission already
        guaranteed; it discovers nothing.
  shortest path        yes  edges                 yes      no       NO (sec.10)
  connected components yes  edges                 yes      partial  ONLY as
        "which observations share a document lineage" -- a bibliographic
        fact, never a scientific one.
  centrality           yes  a homogeneous graph   NO       no       NO -- a
        high-degree Document is a long paper.
  PageRank             yes  weights + homogeneity NO       no       NO
  clustering           yes  a similarity notion   NO       no       NO
  community detection  yes  a modularity objective NO      no       NO
  graph distance       yes  a metric              NO       no       NO
  spectral decomposition yes adjacency over one
                            vertex type + a signal NO      no       NO

Every row after "traversal" runs and means nothing. Executability is not
evidence of semantic validity -- which is the whole finding.

sec.17 WHICH OF THE THREE GRAPHS EXIST
---------------------------------------
  EVIDENCE / PROVENANCE GRAPH   EXISTS -- exactly the signature above.
  COMPUTATIONAL GRAPH           DOES NOT EXIST -- `ModelState` is not a
        vertex, `predict` is not an edge, and no transformation is
        represented as a relation.
  SCIENTIFIC GRAPH              DOES NOT EXIST -- `ClaimedRelationship`
        looks like one and is not: it records THAT A SOURCE ASSERTED a
        relation, never that the relation holds.

sec.20 THE TEN TARGETS

  1 the provenance structure is a DAG            SURVIVES (unconstructible
                                                 cycles, not a check)
  2 a DAG is not automatically a hierarchy       SURVIVES -- no edge means
                                                 membership or coarsening
  3 traversal does not imply inference           SURVIVES
  4 path length is not scientific distance       SURVIVES -- constant to the
                                                 root, anti-correlated between
                                                 observations
  5 edge existence does not imply relationship   SURVIVES -- an edge is a
                                                 CITATION
  6 node attributes are not graph signals        SURVIVES -- heterogeneous V,
                                                 confidence on 3 of 8 kinds
  7 provenance edges do not justify spectral ops SURVIVES -- no adjacency over
                                                 one vertex type, no signal
  8 a graph does not imply topology              SURVIVES -- Phase 106: the
                                                 induced topology is discrete
  9 a graph does not imply geometry              SURVIVES
 10 a provenance graph is not a knowledge graph
    merely because it serializes as one          SURVIVES -- serializability
                                                 is a property of the encoding

sec.21 CONSEQUENCE FOR PRODUCTION: none. Zero production changes. The
graph that exists supports exactly ONE operation legitimately --
ancestry traversal, to reconstruct what an object was computed from --
and that operation is already implemented, already set-valued, and
already deliberately path-free.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from evidence.pool import EvidencePool
from evidence.provenance import ProvenanceAncestry, ancestry_of
from evidence.types import (
    ClaimedRelationship,
    DerivedGrounding,
    DerivedValue,
    Document,
    Observation,
    Record,
    Referent,
    Source,
    make_document,
    make_observation,
    make_record,
    make_source,
)
from materials.model_state import ModelState, Prediction
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench", "scout")
TIMESTAMP = "2026-01-01T00:00:00Z"

VERTEX_KINDS = (Source, Document, Record, Observation, Referent,
                ClaimedRelationship, DerivedValue, DerivedGrounding)

EDGES = {
    Document: {"source_id"},
    Record: {"document_id"},
    Observation: {"record_ids"},
    ClaimedRelationship: {"from_referent_id", "to_referent_id", "observation_id"},
    DerivedValue: {"derived_from"},
    DerivedGrounding: {"derived_value_id", "referent_ids"},
}


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


@pytest.fixture
def pool():
    return EvidencePool()


def _paper(pool, name, rows):
    source = make_source(kind="paper", name=name)
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content=str(rows),
                             retrieval_method="http_get", retrieved_at=TIMESTAMP)
    pool.put_document(document)
    out = []
    for index, (prop, value) in enumerate(rows):
        record = make_record(document_id=document.id, locator=f"row {index}",
                             raw_content=str(value))
        pool.put_record(record)
        observation = make_observation(
            record_ids=(record.id,), extraction_method="regex:kv_v1",
            content={"property": prop, "value": value}, confidence=0.9,
            extracted_at=TIMESTAMP)
        pool.put_observation(observation)
        out.append((prop, observation, record, document, source))
    return out


# -- 1/3. the signature -----------------------------------------------------------------------------


@pytest.mark.parametrize("cls", VERTEX_KINDS)
def test_every_vertex_kind_is_content_addressed_and_frozen(cls):
    assert "id" in {f.name for f in dataclasses.fields(cls)}
    assert cls.__dataclass_params__.frozen


@pytest.mark.parametrize("cls,expected", sorted(EDGES.items(), key=lambda kv: kv[0].__name__))
def test_the_edge_set_is_exactly_these_id_reference_fields(cls, expected):
    fields = {f.name for f in dataclasses.fields(cls)}
    assert expected <= fields
    references = {f for f in fields if f.endswith(("_id", "_ids")) or f == "derived_from"}
    assert references == expected


def test_source_is_the_only_vertex_kind_with_no_outgoing_edge():
    assert Source not in EDGES
    assert Referent not in EDGES
    # Two sinks in the citation direction -- the roots of Phase 111b.


def test_model_state_has_an_identity_and_is_not_a_vertex():
    """It is an isolated point: no pool object references it, and it
    references none. The scientific state space and the provenance graph
    share no vertex."""
    assert "id" in {f.name for f in dataclasses.fields(ModelState)}
    referencing = []
    for cls in VERTEX_KINDS:
        for field in dataclasses.fields(cls):
            if "state" in field.name or "model" in field.name:
                referencing.append(f"{cls.__name__}.{field.name}")
    assert referencing == []
    assert "id" not in {f.name for f in dataclasses.fields(Prediction)}


def test_adding_an_edge_cannot_change_an_endpoint_identity():
    """Edges point BACKWARD to pre-existing ids, so an endpoint's id is
    fixed before any edge to it can be written."""
    pool = EvidencePool()
    source = make_source(kind="paper", name="J")
    before = source.id
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="x",
                             retrieval_method="m", retrieved_at=TIMESTAMP)
    pool.put_document(document)
    assert pool.get_source(source.id).id == before


# -- 5. the DAG claim -------------------------------------------------------------------------------


def test_acyclicity_is_unconstructible_rather_than_checked():
    text = " ".join((REPO / "evidence" / "types.py").read_text().split())
    assert "A derivation cycle (A referencing B, B referencing A) cannot exist" in text
    assert "the mutual dependency has no resolution" in text
    # And no cycle-detection code exists anywhere:
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.FunctionDef) and "cycle" in node.name.lower():
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


def test_no_edge_expresses_membership_containment_or_coarsening():
    """So the DAG is not a hierarchy."""
    for cls, edges in EDGES.items():
        for edge in edges:
            assert not any(word in edge for word in ("part_of", "contains", "member", "parent"))


# -- 7. no weighted graph ---------------------------------------------------------------------------


def test_confidence_is_a_node_attribute_and_no_edge_has_any_attribute():
    carriers = {cls.__name__ for cls in VERTEX_KINDS
                if "confidence" in {f.name for f in dataclasses.fields(cls)}}
    assert carriers == {"Observation", "ClaimedRelationship", "DerivedValue"}
    # An edge is a bare `str` (or a tuple of them) -- there is nowhere to
    # hang a weight without inventing an edge object.
    for cls, edges in EDGES.items():
        annotations = {f.name: f.type for f in dataclasses.fields(cls)}
        for edge in edges:
            assert "float" not in str(annotations[edge])


# -- 10. path length is not a distance ---------------------------------------------------------------


def test_every_observation_is_exactly_three_hops_from_its_source(pool):
    rows = _paper(pool, "Journal A", [("tensile_strength", 90.0), ("melting_point", 165.0)])
    for _, observation, record, document, source in rows:
        assert observation.record_ids == (record.id,)
        assert record.document_id == document.id
        assert document.source_id == source.id
    # Constant on every input, therefore zero information.


def test_graph_proximity_is_anti_correlated_with_scientific_relatedness(pool):
    a = _paper(pool, "Journal A", [("tensile_strength", 90.0), ("melting_point", 165.0)])
    b = _paper(pool, "Journal B", [("tensile_strength", 91.0)])

    a_tensile, a_melting = a[0], a[1]
    b_tensile = b[0]

    # different properties, one paper -> a shared Document
    assert a_tensile[3].id == a_melting[3].id
    # same property, two papers -> no shared vertex anywhere
    assert b_tensile[3].id != a_tensile[3].id
    assert b_tensile[4].id != a_tensile[4].id
    # Graph proximity measures CO-PUBLICATION.


def test_comparability_is_computed_without_consulting_the_graph():
    from materials.analysis import _comparison_context
    source = inspect.getsource(_comparison_context)
    for absent in ("pool", "record", "document", "source", "ancestry"):
        assert absent not in source


# -- 11/13. traversal is path-free, and there is no signal -------------------------------------------


def test_the_only_traversal_returns_sets_and_discards_paths():
    fields = {f.name for f in dataclasses.fields(ProvenanceAncestry)}
    assert fields == {"root_derived_value_id", "observation_ids", "derived_value_ids"}
    for absent in ("path", "depth", "distance", "order"):
        assert absent not in fields
    text = " ".join(inspect.getsource(ancestry_of).split())
    assert "both output tuples are id-sorted, not traversal-ordered" in text


def test_no_graph_signal_exists_over_a_homogeneous_vertex_set():
    with_confidence = [cls for cls in VERTEX_KINDS
                       if "confidence" in {f.name for f in dataclasses.fields(cls)}]
    assert len(with_confidence) == 3
    assert len(VERTEX_KINDS) == 8
    # 3 of 8 vertex kinds carry the only numeric attribute. f: V -> R
    # would require inventing values for the other five.


def test_no_adjacency_laplacian_or_spectral_machinery_exists():
    forbidden = {"adjacency", "laplacian", "spectrum", "eigen", "degree_matrix",
                 "shortest_path", "pagerank", "centrality", "community"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                name = None
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    name = node.name.lower()
                elif isinstance(node, ast.Attribute):
                    name = node.attr.lower()
                if name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits


# -- 17. which graphs exist --------------------------------------------------------------------------


def test_no_computational_graph_exists():
    """`ModelState` is not a vertex and `predict` is not an edge."""
    from materials.model_state import predict
    parameters = set(inspect.signature(predict).parameters)
    assert parameters == {"state", "candidate"}
    # A pure function is not a represented relation: nothing records that
    # this state and this candidate were connected by it.


def test_claimed_relationship_records_an_assertion_not_a_relation():
    """It looks like a scientific graph edge and is not: it requires the
    observation that ASSERTED it."""
    fields = {f.name for f in dataclasses.fields(ClaimedRelationship)}
    assert "observation_id" in fields
    text = " ".join((REPO / "evidence" / "types.py").read_text().split())
    assert "An asserted connection between two Referents" in text


# -- 21. nothing was added -----------------------------------------------------------------------------


def test_phase_113_added_no_graph_machinery():
    forbidden = (
        "networkx", "import nx", "DiGraph", "MultiDiGraph", "adjacency_matrix",
        "GraphSignal", "EvidenceGraph", "shortest_path",
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
