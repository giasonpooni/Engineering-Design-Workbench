"""RetrievalQuery: content-addressed identity determinism."""

from retrieval.query import make_retrieval_query


def test_query_identity_deterministic_for_identical_fields():
    q1 = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)
    q2 = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)
    assert q1.id == q2.id


def test_query_identity_ignores_input_order_and_duplicates():
    q1 = make_retrieval_query(entity_natural_keys=("FEP", "extrusion"))
    q2 = make_retrieval_query(entity_natural_keys=("extrusion", "FEP", "FEP"))
    assert q1.id == q2.id
    assert q1.entity_natural_keys == ("FEP", "extrusion")


def test_query_identity_changes_with_traversal_depth():
    q1 = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=1)
    q2 = make_retrieval_query(entity_natural_keys=("FEP",), traversal_depth=2)
    assert q1.id != q2.id


def test_query_identity_changes_with_filters():
    q1 = make_retrieval_query(entity_natural_keys=("FEP",), relationship_types=("used_in",))
    q2 = make_retrieval_query(entity_natural_keys=("FEP",), relationship_types=("models",))
    assert q1.id != q2.id


def test_negative_traversal_depth_rejected():
    import pytest

    with pytest.raises(ValueError):
        make_retrieval_query(traversal_depth=-1)


def test_negative_limit_rejected():
    import pytest

    with pytest.raises(ValueError):
        make_retrieval_query(limit=-1)
