"""Dependency-direction check for SCOUT (`docs/SCOUT_ARCHITECTURE.md`
§10-11): `evidence/` and `scout/` must never reach `core.canonical`'s
version-minting machinery, must never call `validate_candidate`, and
must never import `backends/`, `renderer/`, or `runtime/`. Same
AST-walking technique as `tests/test_architecture_boundaries.py` and
`tests/test_data_ingestion.py::test_adapters_never_import_validation_or_mint_machinery`
-- this is what makes "SCOUT never becomes an authority over canonical
state" an enforced invariant, not just a design intention.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_MODULE_PREFIXES = ("backends", "renderer", "runtime")
_FORBIDDEN_VALIDATION_SYMBOLS = {"validate_candidate", "make_version", "create_genesis_version"}


def _python_files(package_dir: Path):
    return [p for p in package_dir.rglob("*.py") if "test_" not in p.name]


def _imported_modules_and_names(path: Path):
    tree = ast.parse(path.read_text())
    modules = []
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
            names.update(alias.name for alias in node.names)
    return modules, names


def test_evidence_and_scout_never_import_downstream_packages():
    for package in ("evidence", "scout"):
        for path in _python_files(REPO_ROOT / package):
            modules, _ = _imported_modules_and_names(path)
            for module in modules:
                assert not module.startswith(_FORBIDDEN_MODULE_PREFIXES), (
                    f"{path.relative_to(REPO_ROOT)} imports {module!r} "
                    f"(evidence/scout must not depend on backends/renderer/runtime)"
                )


def test_evidence_and_scout_never_import_canonical_validation_or_mint_machinery():
    for package in ("evidence", "scout"):
        for path in _python_files(REPO_ROOT / package):
            modules, names = _imported_modules_and_names(path)
            for module in modules:
                assert module != "core.canonical.validation", (
                    f"{path.relative_to(REPO_ROOT)} imports core.canonical.validation directly "
                    f"-- SCOUT must never reach validate_candidate (docs/SCOUT_ARCHITECTURE.md §10-11)"
                )
            assert not (names & _FORBIDDEN_VALIDATION_SYMBOLS), (
                f"{path.relative_to(REPO_ROOT)} imports one of {_FORBIDDEN_VALIDATION_SYMBOLS} directly"
            )


def test_evidence_and_scout_never_call_validate_candidate():
    """Belt-and-suspenders over the import check: even an indirect
    reference (`core.canonical.validation.validate_candidate(...)`) would
    show up as a `validate_candidate` Name/Attribute *call* somewhere in
    the AST of these packages. Checked via AST call-expressions, not raw
    source text -- a plain substring check would also flag this
    module's own docstrings, which discuss `validate_candidate` by name
    precisely to explain why it is deliberately never reached (the same
    false-positive class `tests/test_data_ingestion.py`'s
    `test_adapters_never_import_validation_or_mint_machinery` already
    had to avoid)."""
    for package in ("evidence", "scout"):
        for path in _python_files(REPO_ROOT / package):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    called_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                    assert called_name != "validate_candidate", (
                        f"{path.relative_to(REPO_ROOT)} calls validate_candidate"
                    )


def test_evidence_never_imports_scout():
    """One-directional dependency: scout (the agent side) depends on
    evidence (the pool), never the reverse -- evidence/ must stay usable
    by any future producer, not just SCOUT."""
    for path in _python_files(REPO_ROOT / "evidence"):
        modules, _ = _imported_modules_and_names(path)
        for module in modules:
            assert not module.startswith("scout"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} (evidence must not depend on scout)"
            )


def test_core_canonical_never_imports_evidence_or_scout():
    """The reverse-direction check: nothing in core/ knows evidence/scout
    exist, exactly as it must not know adapters/backends/runtime exist
    (`tests/test_architecture_boundaries.py`)."""
    for path in _python_files(REPO_ROOT / "core"):
        modules, _ = _imported_modules_and_names(path)
        for module in modules:
            assert not module.startswith(("evidence", "scout")), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} (core must not depend on evidence/scout)"
            )
