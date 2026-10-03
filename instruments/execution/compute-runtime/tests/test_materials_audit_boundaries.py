"""Phase 33 boundary check: `materials/audit.py` sits above
`materials/decision.py` but must remain subject to the exact same
one-way boundary discipline as the rest of `materials/`. In particular:
it must not perform retrieval and must not import `evidence.pool` or
`retrieval.engine` at all -- it consumes an already-computed
`ProgramDecision` only.
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


def test_evidence_never_imports_materials_audit():
    for path in _python_files(REPO_ROOT / "evidence"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- evidence/ must not depend on materials/"
            )


def test_retrieval_never_imports_materials_audit():
    for path in _python_files(REPO_ROOT / "retrieval"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- retrieval/ must not depend on materials/"
            )


def test_core_never_imports_materials_audit():
    for path in _python_files(REPO_ROOT / "core"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- core/ must not depend on materials/"
            )


def test_runtime_never_imports_materials_audit():
    for path in _python_files(REPO_ROOT / "runtime"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- runtime/ must not depend on materials/"
            )


def test_scout_never_imports_materials_audit():
    for path in _python_files(REPO_ROOT / "scout"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- scout/ must not depend on materials/"
            )


def test_audit_only_imports_materials_and_evidence():
    """materials/audit.py may depend on materials.decision,
    materials.program, materials.analysis, and evidence/ (for the
    Referent type hint) -- never core/, runtime/, scout/, or
    retrieval/, since it performs no retrieval at all."""
    forbidden_prefixes = ("core", "runtime", "scout", "retrieval")
    path = REPO_ROOT / "materials" / "audit.py"
    for module in _imported_modules(path):
        assert not module.startswith(forbidden_prefixes), (
            f"materials/audit.py imports {module!r} -- must depend only on materials/evidence, never retrieval"
        )


def test_audit_never_mutates_pool():
    """No admission or put_* call anywhere in materials/audit.py."""
    path = REPO_ROOT / "materials" / "audit.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
            raise AssertionError(f"materials/audit.py calls .{node.attr}(...) -- must be read-only")
        if isinstance(node, ast.Name) and node.id.startswith("admit_"):
            raise AssertionError(f"materials/audit.py references {node.id} -- must not admit evidence")


def test_audit_never_imports_evidence_pool_or_retrieval_engine():
    """audit_program takes only a ProgramDecision -- it has no reason
    to import EvidencePool or RetrievalEngine/DeterministicRetrievalEngine
    at all (Phase 31/32's one-responsibility-per-layer discipline,
    carried one layer further: this layer does not perform retrieval)."""
    path = REPO_ROOT / "materials" / "audit.py"
    modules = _imported_modules(path)
    assert "evidence.pool" not in modules
    assert "retrieval.engine" not in modules
    assert "retrieval.query" not in modules
