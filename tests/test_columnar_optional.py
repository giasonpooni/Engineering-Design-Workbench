def test_columnar_module_import_does_not_require_pyarrow():
    import sys
    before = set(sys.modules)
    import ciw.columnar as columnar
    assert columnar.QUALIFIED_PYARROW == "25.0.1"
    assert "pyarrow" not in set(sys.modules) - before
