"""Network metrics: each function tested against a small, hand-built
pool where the expected value is computable by inspection."""

from evidence.metrics import (
    aggregate_uncertainty,
    bridge_potential,
    connectivity,
    evidence_density,
    novelty,
    observation_uncertainty,
    redundancy,
    source_diversity,
)
from evidence.pool import EvidencePool
from evidence.trust_graph import build_trust_graph
from evidence.types import make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source


def _ingest(pool, source_name, referent_a, referent_b, rel_type, confidence=1.0):
    source = make_source(kind="paper", name=source_name)
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content=source_name, retrieval_method="m", retrieved_at="t")
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="p1", raw_content=source_name)
    pool.put_record(record)
    obs = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1", content={"v": source_name}, confidence=confidence, extracted_at="t"
    )
    pool.put_observation(obs)
    pool.put_referent(referent_a)
    pool.put_referent(referent_b)
    rel = make_claimed_relationship(
        from_referent_id=referent_a.id, to_referent_id=referent_b.id, type=rel_type, observation_id=obs.id, confidence=confidence
    )
    pool.put_claimed_relationship(rel)
    return obs, rel


def test_connectivity_counts():
    pool = EvidencePool()
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    _ingest(pool, "paper1", fep, extrusion, "used_in")
    graph = build_trust_graph(pool)
    metrics = connectivity(graph)
    assert metrics.node_count == 2
    assert metrics.edge_count == 1
    assert metrics.average_degree == 1.0


def test_connectivity_empty_graph_no_division_by_zero():
    metrics = connectivity(build_trust_graph(EvidencePool()))
    assert metrics == connectivity(build_trust_graph(EvidencePool()))
    assert metrics.average_degree == 0.0


def test_novelty_all_new():
    pool = EvidencePool()
    before = build_trust_graph(pool)
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    obs, rel = _ingest(pool, "paper1", fep, extrusion, "used_in")
    assert novelty(before, (fep.id, extrusion.id), (rel.id,)) == 1.0


def test_novelty_all_known():
    pool = EvidencePool()
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    obs, rel = _ingest(pool, "paper1", fep, extrusion, "used_in")
    after = build_trust_graph(pool)
    # nothing new relative to a graph that already contains everything
    assert novelty(after, (fep.id, extrusion.id), (rel.id,)) == 0.0


def test_novelty_empty_reference_set_is_zero_not_error():
    assert novelty(build_trust_graph(EvidencePool()), (), ()) == 0.0


def test_redundancy_counts_distinct_sources():
    pool = EvidencePool()
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    _ingest(pool, "paper1", fep, extrusion, "used_in")
    _ingest(pool, "paper2", fep, extrusion, "used_in")
    assert redundancy(pool, fep.id) == 2


def test_redundancy_single_source():
    pool = EvidencePool()
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    _ingest(pool, "paper1", fep, extrusion, "used_in")
    assert redundancy(pool, fep.id) == 1


def test_source_diversity_ratio():
    pool = EvidencePool()
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    _ingest(pool, "paper1", fep, extrusion, "used_in")
    _ingest(pool, "paper1", fep, extrusion, "also_used_in")  # same source, second claim
    # 1 distinct source / 2 relationships touching fep
    assert source_diversity(pool, fep.id) == 0.5


def test_source_diversity_no_relationships_is_zero():
    assert source_diversity(EvidencePool(), "nonexistent") == 0.0


def test_observation_uncertainty_is_one_minus_confidence():
    obs = make_observation(
        record_ids=("r1",), extraction_method="regex:kv_v1", content={"v": 1}, confidence=0.75, extracted_at="t"
    )
    assert observation_uncertainty(obs) == 0.25


def test_aggregate_uncertainty_mean():
    o1 = make_observation(record_ids=("r1",), extraction_method="m", content={"v": 1}, confidence=1.0, extracted_at="t")
    o2 = make_observation(record_ids=("r2",), extraction_method="m", content={"v": 2}, confidence=0.5, extracted_at="t")
    assert aggregate_uncertainty((o1, o2)) == 0.25


def test_aggregate_uncertainty_empty_is_zero():
    assert aggregate_uncertainty(()) == 0.0


def test_evidence_density_raw_count():
    pool = EvidencePool()
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    _ingest(pool, "paper1", fep, extrusion, "used_in")
    _ingest(pool, "paper2", fep, extrusion, "used_in")
    assert evidence_density(pool, fep.id) == 2


def test_bridge_potential_true_when_connecting_new_components():
    pool = EvidencePool()
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    before = build_trust_graph(pool)
    pool.put_referent(fep)
    pool.put_referent(extrusion)
    obs = make_observation(record_ids=("r1",), extraction_method="m", content={"v": 1}, confidence=1.0, extracted_at="t")
    rel = make_claimed_relationship(from_referent_id=fep.id, to_referent_id=extrusion.id, type="used_in", observation_id=obs.id, confidence=1.0)
    assert bridge_potential(before, rel) is True


def test_bridge_potential_false_when_already_connected():
    pool = EvidencePool()
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    obs, rel1 = _ingest(pool, "paper1", fep, extrusion, "used_in")
    before = build_trust_graph(pool)  # fep and extrusion already connected via rel1
    rel2 = make_claimed_relationship(
        from_referent_id=fep.id, to_referent_id=extrusion.id, type="also_used_in", observation_id=obs.id, confidence=1.0
    )
    assert bridge_potential(before, rel2) is False
