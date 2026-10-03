"""Phase 37 boundary check: `materials/candidates.py` sits above
`materials/specification.py` (and, for the six gap-category constants,
`materials/experiment.py`) but must remain subject to the exact same
one-way boundary discipline as the rest of `materials/`. In particular:
it must perform no retrieval and must import neither `evidence.pool` nor
any `retrieval` module at all -- it consumes an already-computed
ExperimentSpecification only.
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


def test_evidence_never_imports_materials_candidates():
    for path in _python_files(REPO_ROOT / "evidence"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- evidence/ must not depend on materials/"
            )


def test_retrieval_never_imports_materials_candidates():
    for path in _python_files(REPO_ROOT / "retrieval"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- retrieval/ must not depend on materials/"
            )


def test_core_never_imports_materials_candidates():
    for path in _python_files(REPO_ROOT / "core"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- core/ must not depend on materials/"
            )


def test_runtime_never_imports_materials_candidates():
    for path in _python_files(REPO_ROOT / "runtime"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- runtime/ must not depend on materials/"
            )


def test_scout_never_imports_materials_candidates():
    for path in _python_files(REPO_ROOT / "scout"):
        for module in _imported_modules(path):
            assert not module.startswith("materials"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- scout/ must not depend on materials/"
            )


def test_candidates_only_imports_materials_and_evidence_types():
    """materials/candidates.py may depend on materials.specification,
    materials.experiment (for the six gap-category constants), and
    evidence.types/evidence.identity (for the Referent type hint and
    content_hash) -- never core/, runtime/, scout/, or retrieval/, since
    it performs no retrieval at all."""
    forbidden_prefixes = ("core", "runtime", "scout", "retrieval")
    path = REPO_ROOT / "materials" / "candidates.py"
    for module in _imported_modules(path):
        assert not module.startswith(forbidden_prefixes), (
            f"materials/candidates.py imports {module!r} -- must depend only on materials/evidence, never retrieval"
        )


def test_candidates_never_imports_evidence_pool_or_retrieval():
    """generate_candidates takes only an ExperimentSpecification -- it
    has no reason to import EvidencePool or any retrieval module at
    all."""
    path = REPO_ROOT / "materials" / "candidates.py"
    modules = _imported_modules(path)
    assert "evidence.pool" not in modules
    assert "retrieval.engine" not in modules
    assert "retrieval.query" not in modules


def test_candidates_never_mutates_pool():
    """No admission or put_* call anywhere in materials/candidates.py."""
    path = REPO_ROOT / "materials" / "candidates.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
            raise AssertionError(f"materials/candidates.py calls .{node.attr}(...) -- must be read-only")
        if isinstance(node, ast.Name) and node.id.startswith("admit_"):
            raise AssertionError(f"materials/candidates.py references {node.id} -- must not admit evidence")


def test_candidates_does_not_mutate_specification():
    """generate_candidates must never call setattr/object.__setattr__ on
    anything other than its own newly-constructed dataclasses (the
    __post_init__ tuple/mapping-coercion pattern every materials/
    dataclass already uses, and the internal, non-dataclass
    `_CandidateGroup` accumulator, whose plain instance-attribute
    assignments are not `ast.Attribute` Store nodes on any object this
    module received as input) -- it never reaches back into its
    ExperimentSpecification argument to modify it. Assignments onto
    `self` inside `_CandidateGroup.__init__` and every dataclass's own
    `__post_init__` are expected and excluded; the check instead proves
    no attribute of a `group`/`requirement`/`entry`/`specification`
    loop or parameter variable is ever assigned to."""
    path = REPO_ROOT / "materials" / "candidates.py"
    tree = ast.parse(path.read_text())
    allowed_targets = {"self"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            root_name = root.id if isinstance(root, ast.Name) else None
            assert root_name in allowed_targets, (
                f"materials/candidates.py assigns to {root_name}.{node.attr} -- must not mutate its input "
                f"(only attribute assignment onto `self` inside a constructor is permitted)"
            )
