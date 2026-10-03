from schematics import EdgeKind, NodeKind, SchematicError, quadratic_drag, require, validate
from schematics.ir import Node


def test_quadratic_drag_validates():
    sch = quadratic_drag()
    assert validate(sch) == []
    require(sch)
    assert {n.kind for n in sch.nodes.values()} >= {NodeKind.VARIABLE, NodeKind.FUNCTION, NodeKind.MEASUREMENT, NodeKind.OBSERVER}


def test_bad_edge_refused():
    sch = quadratic_drag()
    sch.add(Node(id="ghost", kind=NodeKind.CERTIFICATE, attrs={"owner": "jspt"}))
    sch.connect(EdgeKind.MEASURES, "ghost", "y")
    assert validate(sch)
    try:
        require(sch)
        raise AssertionError("expected SchematicError")
    except SchematicError:
        pass
