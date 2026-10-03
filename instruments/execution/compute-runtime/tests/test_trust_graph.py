"""Trust Graph: derived-view correctness, multigraph coexistence,
connected-component determinism."""

import subprocess
import sys
from pathlib import Path

from evidence.pool import EvidencePool
from evidence.trust_graph import build_trust_graph
from evidence.types import make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pool_with_two_referents():
    pool = EvidencePool()
    source = make_source(kind="paper", name="X")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="x", retrieval_method="m", retrieved_at="t")
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="p1", raw_content="x")
    pool.put_record(record)
    obs = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1", content={"v": 1}, confidence=1.0, extracted_at="t"
    )
    pool.put_observation(obs)
    fep = make_referent(natural_key="FEP", kind="material")
    extrusion = make_referent(natural_key="extrusion", kind="process")
    pool.put_referent(fep)
    pool.put_referent(extrusion)
    return pool, fep, extrusion, obs


def test_build_trust_graph_reflects_pool_state():
    pool, fep, extrusion, obs = _pool_with_two_referents()
    graph = build_trust_graph(pool)
    assert set(n.id for n in graph.nodes) == {fep.id, extrusion.id}
    assert graph.edges == ()


def test_trust_graph_is_a_pure_derived_view_not_a_second_store():
    """Calling build_trust_graph again after the pool changes reflects
    the new state -- there is no cached/stale graph object anywhere."""
    pool, fep, extrusion, obs = _pool_with_two_referents()
    before = build_trust_graph(pool)
    rel = make_claimed_relationship(
        from_referent_id=fep.id, to_referent_id=extrusion.id, type="used_in", observation_id=obs.id, confidence=1.0
    )
    pool.put_claimed_relationship(rel)
    after = build_trust_graph(pool)
    assert before.edges == ()
    assert after.edges == (rel,)


def test_multigraph_preserves_conflicting_claims_as_distinct_edges():
    """Two different observations claiming different relationship types
    between the same two Referents must both appear as edges -- never
    merged into one."""
    pool, fep, extrusion, obs = _pool_with_two_referents()
    obs2 = make_observation(
        record_ids=(obs.record_ids[0],), extraction_method="regex:kv_v1", content={"v": 2}, confidence=1.0, extracted_at="t"
    )
    pool.put_observation(obs2)
    rel1 = make_claimed_relationship(
        from_referent_id=fep.id, to_referent_id=extrusion.id, type="used_in", observation_id=obs.id, confidence=1.0
    )
    rel2 = make_claimed_relationship(
        from_referent_id=fep.id, to_referent_id=extrusion.id, type="incompatible_with", observation_id=obs2.id, confidence=0.4
    )
    pool.put_claimed_relationship(rel1)
    pool.put_claimed_relationship(rel2)
    graph = build_trust_graph(pool)
    assert len(graph.edges) == 2
    assert {e.type for e in graph.edges} == {"used_in", "incompatible_with"}


def test_neighbors():
    pool, fep, extrusion, obs = _pool_with_two_referents()
    rel = make_claimed_relationship(
        from_referent_id=fep.id, to_referent_id=extrusion.id, type="used_in", observation_id=obs.id, confidence=1.0
    )
    pool.put_claimed_relationship(rel)
    graph = build_trust_graph(pool)
    assert graph.neighbors(fep.id) == (extrusion.id,)
    assert graph.neighbors(extrusion.id) == (fep.id,)


def test_connected_components_isolated_nodes():
    pool, fep, extrusion, obs = _pool_with_two_referents()
    graph = build_trust_graph(pool)
    components = graph.connected_components()
    assert len(components) == 2
    assert frozenset({fep.id}) in components
    assert frozenset({extrusion.id}) in components


def test_connected_components_merges_linked_nodes():
    pool, fep, extrusion, obs = _pool_with_two_referents()
    rel = make_claimed_relationship(
        from_referent_id=fep.id, to_referent_id=extrusion.id, type="used_in", observation_id=obs.id, confidence=1.0
    )
    pool.put_claimed_relationship(rel)
    graph = build_trust_graph(pool)
    components = graph.connected_components()
    assert components == (frozenset({fep.id, extrusion.id}),)


def test_connected_components_deterministic_regardless_of_hash_seed():
    """Same discipline as `tests/test_versioning.py`'s cross-process
    PYTHONHASHSEED check, applied to graph traversal ordering."""
    script = (
        "from evidence.pool import EvidencePool\n"
        "from evidence.trust_graph import build_trust_graph\n"
        "from evidence.types import make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source\n"
        "pool = EvidencePool()\n"
        "source = make_source(kind='paper', name='X')\n"
        "pool.put_source(source)\n"
        "document = make_document(source_id=source.id, raw_content='x', retrieval_method='m', retrieved_at='t')\n"
        "pool.put_document(document)\n"
        "record = make_record(document_id=document.id, locator='p1', raw_content='x')\n"
        "pool.put_record(record)\n"
        "obs = make_observation(record_ids=(record.id,), extraction_method='regex:kv_v1', content={'v': 1}, confidence=1.0, extracted_at='t')\n"
        "pool.put_observation(obs)\n"
        "for key in ('a', 'b', 'c'):\n"
        "    pool.put_referent(make_referent(natural_key=key, kind='material'))\n"
        "refs = {key: make_referent(natural_key=key, kind='material').id for key in ('a', 'b', 'c')}\n"
        "pool.put_claimed_relationship(make_claimed_relationship(from_referent_id=refs['a'], to_referent_id=refs['b'], type='r', observation_id=obs.id, confidence=1.0))\n"
        "graph = build_trust_graph(pool)\n"
        "print([sorted(c) for c in graph.connected_components()])\n"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout)
    assert len(outputs) == 1, f"connected_components ordering differed across PYTHONHASHSEED values: {outputs}"
