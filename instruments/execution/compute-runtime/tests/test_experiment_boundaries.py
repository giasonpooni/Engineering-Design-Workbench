"""Phase 63 implementation: boundary checks for experiment/, mirroring
tests/test_materials_boundaries.py's AST-based convention exactly.
Enforces docs/EXPERIMENT_ARCHITECTURE.md §5.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The only admission surface experiment/ is permitted to touch directly
# -- raw structural bookkeeping (a Record logging one dispatched
# measurement against an already-admitted Document), plus the one
# function that IS the sole semantic write boundary
# (materials.results.admit_experimental_result -- experiment/ is
# REQUIRED to call this, never a raw admit_observation/
# admit_claimed_relationship directly). See experiment/step.py's own
# module docstring for the full argument.
_ALLOWED_PUT_SUFFIXES = ("put_record",)
_ALLOWED_ADMIT_NAMES = ("admit_record", "admit_experimental_result")


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


def test_experiment_only_imports_evidence_retrieval_materials():
    """experiment/ may depend on evidence/, retrieval/, materials/ (and
    the standard library) -- never core/, runtime/, scout/, morpho/,
    backends/, adapters/, renderer/ -- exactly docs/EXPERIMENT_ARCHITECTURE.md
    §5's first rule."""
    forbidden_prefixes = ("core", "runtime", "scout", "morpho", "backends", "adapters", "renderer")
    for path in _python_files(REPO_ROOT / "experiment"):
        for module in _imported_modules(path):
            assert not module.startswith(forbidden_prefixes), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- experiment/ must depend "
                "only on evidence/retrieval/materials"
            )


def test_experiment_never_admits_semantic_evidence_directly():
    """No file under experiment/ calls admit_observation/
    admit_claimed_relationship/admit_document, or pool.put_observation/
    put_claimed_relationship/put_document/put_source, directly.
    admit_record/pool.put_record ARE permitted (see module-level
    comment above and experiment/step.py's own docstring for why record
    admission was never part of the write boundary
    materials.results.admit_experimental_result protects)."""
    for path in _python_files(REPO_ROOT / "experiment"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
                assert node.attr in _ALLOWED_PUT_SUFFIXES, (
                    f"{path.relative_to(REPO_ROOT)} calls .{node.attr}(...) -- only "
                    f"{_ALLOWED_PUT_SUFFIXES} are permitted directly under experiment/"
                )
            if isinstance(node, ast.Name) and node.id.startswith("admit_"):
                assert node.id in _ALLOWED_ADMIT_NAMES, (
                    f"{path.relative_to(REPO_ROOT)} references {node.id} -- only "
                    f"{_ALLOWED_ADMIT_NAMES} are permitted directly under experiment/"
                )


def test_materials_results_remains_the_sole_semantic_write_boundary():
    """Repeats materials/'s own pin (test_materials_boundaries.py::
    test_only_results_module_mutates_pool) but scoped to admit_observation/
    admit_claimed_relationship specifically, across BOTH materials/ and
    experiment/ -- confirming experiment/'s own narrower admission
    surface (admit_record only) never grows to include the semantic
    admission calls that must remain exclusive to materials/results.py."""
    semantic_admit_names = ("admit_observation", "admit_claimed_relationship")
    semantic_put_suffixes = ("put_observation", "put_claimed_relationship")
    mutators = []
    for package in ("materials", "experiment"):
        for path in _python_files(REPO_ROOT / package):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in semantic_put_suffixes:
                    mutators.append(str(path.relative_to(REPO_ROOT)))
                    break
                if isinstance(node, ast.Name) and node.id in semantic_admit_names:
                    mutators.append(str(path.relative_to(REPO_ROOT)))
                    break
    assert set(mutators) == {"materials/results.py"}
