"""Phase 27 boundary check: `materials/` is a one-way consumer above
`retrieval/`/`evidence/` -- the substrate must remain completely unaware
it exists. Same AST-based convention as
`tests/test_derived_value_boundaries.py`/`tests/test_scout_boundaries.py`.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _python_files(package_dir: Path):
    return [p for p in package_dir.rglob("*.py") if "test_" not in p.name]


def _imported_modules(path: Path):
    tree = ast.parse(path.read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_evidence_never_imports_materials():
    for path in _python_files(REPO_ROOT / "evidence"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- evidence/ must not depend on materials/"
            )


def test_retrieval_never_imports_materials():
    for path in _python_files(REPO_ROOT / "retrieval"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- retrieval/ must not depend on materials/"
            )


def test_core_never_imports_materials():
    for path in _python_files(REPO_ROOT / "core"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- core/ must not depend on materials/"
            )


def test_runtime_never_imports_materials():
    for path in _python_files(REPO_ROOT / "runtime"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- runtime/ must not depend on materials/"
            )


def test_scout_never_imports_materials():
    for path in _python_files(REPO_ROOT / "scout"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- scout/ must not depend on materials/"
            )


def test_materials_only_imports_evidence_and_retrieval():
    """materials/ may depend on evidence/ and retrieval/ (and the
    standard library) -- never core/, runtime/, or scout/."""
    forbidden_prefixes = ("core", "runtime", "scout")
    for path in _python_files(REPO_ROOT / "materials"):
        for module in _imported_modules(path):
            assert not module.startswith(forbidden_prefixes), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- materials/ must depend only on evidence/retrieval"
            )


def test_materials_never_mutates_pool():
    """No admission or put_* call anywhere in materials/ -- with exactly
    ONE deliberate exception, `materials/results.py` (Phase 44): the
    bridge from an executed campaign entry back into EvidencePool, using
    only the existing, unmodified admission API. Every other file in
    materials/ remains read-only, exactly like retrieval/ -- this test
    still fails if admission spreads anywhere else."""
    exempt = {"materials/results.py"}
    for path in _python_files(REPO_ROOT / "materials"):
        if str(path.relative_to(REPO_ROOT)) in exempt:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
                raise AssertionError(f"{path.relative_to(REPO_ROOT)} calls .{node.attr}(...) -- materials/ must be read-only")
            if isinstance(node, ast.Name) and node.id.startswith("admit_"):
                raise AssertionError(f"{path.relative_to(REPO_ROOT)} references {node.id} -- materials/ must not admit evidence")


def test_only_results_module_mutates_pool():
    """The exemption above is exactly one file, not a growing list --
    pins that `materials/results.py` is the ONLY module under materials/
    that calls put_*/admit_*."""
    mutators = []
    for path in _python_files(REPO_ROOT / "materials"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
                mutators.append(str(path.relative_to(REPO_ROOT)))
                break
            if isinstance(node, ast.Name) and node.id.startswith("admit_"):
                mutators.append(str(path.relative_to(REPO_ROOT)))
                break
    assert set(mutators) == {"materials/results.py"}
