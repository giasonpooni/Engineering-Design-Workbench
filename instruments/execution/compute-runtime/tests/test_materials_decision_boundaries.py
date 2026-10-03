"""Phase 32 boundary check: `materials/decision.py` sits above
`materials/program.py` but must remain subject to the exact same
one-way boundary discipline as the rest of `materials/`.
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


def test_evidence_never_imports_materials_decision():
    for path in _python_files(REPO_ROOT / "evidence"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- evidence/ must not depend on materials/"
            )


def test_retrieval_never_imports_materials_decision():
    for path in _python_files(REPO_ROOT / "retrieval"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- retrieval/ must not depend on materials/"
            )


def test_core_never_imports_materials_decision():
    for path in _python_files(REPO_ROOT / "core"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- core/ must not depend on materials/"
            )


def test_runtime_never_imports_materials_decision():
    for path in _python_files(REPO_ROOT / "runtime"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- runtime/ must not depend on materials/"
            )


def test_scout_never_imports_materials_decision():
    for path in _python_files(REPO_ROOT / "scout"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- scout/ must not depend on materials/"
            )


def test_decision_only_imports_materials_evidence_retrieval():
    """materials/decision.py may depend on materials.program,
    materials.analysis, evidence/, and retrieval/ -- never core/,
    runtime/, or scout/."""
    forbidden_prefixes = ("core", "runtime", "scout")
    path = REPO_ROOT / "materials" / "decision.py"
    for module in _imported_modules(path):
        assert not module.startswith(forbidden_prefixes), (
            f"materials/decision.py imports {module!r} -- must depend only on materials/evidence/retrieval"
        )


def test_decision_never_mutates_pool():
    """No admission or put_* call anywhere in materials/decision.py --
    read-only, and in fact evaluate_program never even receives an
    EvidencePool argument."""
    path = REPO_ROOT / "materials" / "decision.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
            raise AssertionError(f"materials/decision.py calls .{node.attr}(...) -- must be read-only")
        if isinstance(node, ast.Name) and node.id.startswith("admit_"):
            raise AssertionError(f"materials/decision.py references {node.id} -- must not admit evidence")


def test_decision_never_imports_evidence_pool_directly():
    """evaluate_program consumes an already-computed MaterialProgramAnswer
    -- it has no reason to import EvidencePool at all (Phase 31 §10's
    one-responsibility-per-layer discipline: this layer does not
    rebuild the program traversal). Checked via the actual import list
    (AST-based, per _imported_modules), not a text search -- the
    module's own docstring legitimately mentions EvidencePool in prose."""
    path = REPO_ROOT / "materials" / "decision.py"
    assert "evidence.pool" not in _imported_modules(path)
