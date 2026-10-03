from schematics import quadratic_drag, run
from schematics.project_usd import usda
from schematics.project_usd_read import read_usda


def test_emitted_usda_roundtrips_function_and_sensor():
    text = usda(run(quadratic_drag()).schematic)
    again = read_usda(text)
    assert again.node("f").get("class") == "nonlinear"
    assert again.node("ySensor").kind.value == "measurement"


def test_schema_without_function_refused():
    text = '#usda 1.0\n(\n    customLayerData = { string ns.schematicSchema = "NsObservabilitySchematic@0.1" }\n)\ndef Xform "World" {\n    def Scope "onlySensor" (\n        apiSchemas = ["NsSensorAPI"]\n    )\n    {\n        token ns:kind = "measurement"\n    }\n}\n'
    try:
        read_usda(text)
        raise AssertionError("expected refuse")
    except ValueError as exc:
        assert "function" in str(exc)


def test_foreign_usda_refused():
    try:
        read_usda("#usda 1.0\ndef Xform \"World\" { }\n")
        raise AssertionError("expected refuse")
    except ValueError as exc:
        assert "UNRESOLVED" in str(exc)
