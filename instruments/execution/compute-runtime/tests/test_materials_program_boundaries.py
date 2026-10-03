"""Phase 31 boundary check: `materials/program.py` sits above
`materials/analysis.py` but must remain subject to the exact same
one-way boundary discipline as the rest of `materials/` --
`evidence`/`retrieval`/`core`/`runtime`/`scout` must stay completely
unaware it exists, and it must never mutate the pool. Same AST-based
convention as `tests/test_materials_boundaries.py`.
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


def test_evidence_never_imports_materials_program():
    for path in _python_files(REPO_ROOT / "evidence"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- evidence/ must not depend on materials/"
            )


def test_retrieval_never_imports_materials_program():
    for path in _python_files(REPO_ROOT / "retrieval"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- retrieval/ must not depend on materials/"
            )


def test_core_never_imports_materials_program():
    for path in _python_files(REPO_ROOT / "core"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- core/ must not depend on materials/"
            )


def test_runtime_never_imports_materials_program():
    for path in _python_files(REPO_ROOT / "runtime"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- runtime/ must not depend on materials/"
            )


def test_scout_never_imports_materials_program():
    for path in _python_files(REPO_ROOT / "scout"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- scout/ must not depend on materials/"
            )


def test_program_only_imports_evidence_retrieval_and_materials_analysis():
    """materials/program.py may depend on materials.analysis, evidence/,
    and retrieval/ (and the standard library) -- never core/, runtime/,
    or scout/."""
    forbidden_prefixes = ("core", "runtime", "scout")
    path = REPO_ROOT / "materials" / "program.py"
    for module in _imported_modules(path):
        assert not module.startswith(forbidden_prefixes), (
            f"materials/program.py imports {module!r} -- must depend only on materials.analysis/evidence/retrieval"
        )


def test_program_never_mutates_pool():
    """No admission or put_* call anywhere in materials/program.py --
    read-only, exactly like materials/analysis.py and retrieval/."""
    path = REPO_ROOT / "materials" / "program.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
            raise AssertionError(f"materials/program.py calls .{node.attr}(...) -- must be read-only")
        if isinstance(node, ast.Name) and node.id.startswith("admit_"):
            raise AssertionError(f"materials/program.py references {node.id} -- must not admit evidence")
