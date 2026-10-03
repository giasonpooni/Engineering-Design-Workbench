from schematics import EdgeKind, NodeKind, blanket, by_kind, path, quadratic_drag


def test_typed_path_sensor_to_port():
    assert path(quadratic_drag(), "ySensor", (EdgeKind.MEASURES,)) == ["ySensor", "y"]


def test_blanket_of_y_includes_sensor_and_function():
    keep = set(blanket(quadratic_drag(), "y"))
    assert {"ySensor", "f", "y"} <= keep


def test_functions_are_retrievable_by_kind():
    plants = by_kind(quadratic_drag(), NodeKind.FUNCTION)
    assert [p.id for p in plants] == ["f"]
    assert plants[0].get("class") == "nonlinear"
