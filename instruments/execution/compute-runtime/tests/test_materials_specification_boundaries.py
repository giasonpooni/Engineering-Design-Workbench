"""Phase 35 boundary check: `materials/specification.py` sits above
`materials/experiment.py` but must remain subject to the exact same
one-way boundary discipline as the rest of `materials/`. In particular:
it must perform no retrieval and must import neither `evidence.pool` nor
any `retrieval` module at all -- it consumes an already-computed
`ExperimentGapAnalysis` only.
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


def test_evidence_never_imports_materials_specification():
    for path in _python_files(REPO_ROOT / "evidence"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- evidence/ must not depend on materials/"
            )


def test_retrieval_never_imports_materials_specification():
    for path in _python_files(REPO_ROOT / "retrieval"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- retrieval/ must not depend on materials/"
            )


def test_core_never_imports_materials_specification():
    for path in _python_files(REPO_ROOT / "core"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- core/ must not depend on materials/"
            )


def test_runtime_never_imports_materials_specification():
    for path in _python_files(REPO_ROOT / "runtime"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- runtime/ must not depend on materials/"
            )


def test_scout_never_imports_materials_specification():
    for path in _python_files(REPO_ROOT / "scout"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- scout/ must not depend on materials/"
            )


def test_specification_only_imports_materials_and_evidence_types():
    """materials/specification.py may depend on materials.experiment,
    materials.decision (for the Criterion type hint), and evidence.types
    (for the Referent type hint) -- never core/, runtime/, scout/, or
    retrieval/, since it performs no retrieval at all."""
    forbidden_prefixes = ("core", "runtime", "scout", "retrieval")
    path = REPO_ROOT / "materials" / "specification.py"
    for module in _imported_modules(path):
        assert not module.startswith(forbidden_prefixes), (
            f"materials/specification.py imports {module!r} -- must depend only on materials/evidence, never retrieval"
        )


def test_specification_never_imports_evidence_pool_or_retrieval():
    """specify_experiment_requirements takes only an
    ExperimentGapAnalysis -- it has no reason to import EvidencePool or
    any retrieval module at all."""
    path = REPO_ROOT / "materials" / "specification.py"
    modules = _imported_modules(path)
    assert "evidence.pool" not in modules
    assert "retrieval.engine" not in modules
    assert "retrieval.query" not in modules


def test_specification_never_mutates_pool():
    """No admission or put_* call anywhere in materials/specification.py."""
    path = REPO_ROOT / "materials" / "specification.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
            raise AssertionError(f"materials/specification.py calls .{node.attr}(...) -- must be read-only")
        if isinstance(node, ast.Name) and node.id.startswith("admit_"):
            raise AssertionError(f"materials/specification.py references {node.id} -- must not admit evidence")


def test_specification_does_not_mutate_gap_analysis():
    """specify_experiment_requirements must never call setattr/
    object.__setattr__ on anything other than its own newly-constructed
    dataclasses (the __post_init__ tuple-coercion pattern every
    materials/ dataclass already uses) -- it never reaches back into its
    ExperimentGapAnalysis argument to modify it."""
    path = REPO_ROOT / "materials" / "specification.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            raise AssertionError(f"materials/specification.py assigns to an attribute ({node.attr}) -- must not mutate its input")
