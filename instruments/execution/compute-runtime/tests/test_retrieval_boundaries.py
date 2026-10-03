"""Dependency-direction check for `retrieval/`
(`docs/RETRIEVAL_ARCHITECTURE.md` §authority-boundary): retrieval code
must never reach `core.canonical.validation`, never call
`validate_candidate`/`make_version`/`create_genesis_version`, never
import `backends/`/`renderer/`/`runtime/`, and must never write to the
evidence pool (no `pool.put_*` calls anywhere in this package). Same
AST-walking technique as `tests/test_architecture_boundaries.py` and
`tests/test_scout_boundaries.py`.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_MODULE_PREFIXES = ("backends", "renderer", "runtime")
_FORBIDDEN_VALIDATION_SYMBOLS = {"validate_candidate", "make_version", "create_genesis_version"}
_FORBIDDEN_MUTATION_METHODS = {
    "put_source",
    "put_document",
    "put_record",
    "put_observation",
    "put_referent",
    "put_claimed_relationship",
}


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
    return tree, modules, names


def test_retrieval_never_imports_downstream_packages():
    for path in _python_files(REPO_ROOT / "retrieval"):
        _, modules, _ = _imported_modules_and_names(path)
        for module in modules:
            assert not module.startswith(_FORBIDDEN_MODULE_PREFIXES), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} "
                f"(retrieval must not depend on backends/renderer/runtime)"
            )


def test_retrieval_never_imports_canonical_validation_or_mint_machinery():
    for path in _python_files(REPO_ROOT / "retrieval"):
        _, modules, names = _imported_modules_and_names(path)
        for module in modules:
            assert module != "core.canonical.validation", (
                f"{path.relative_to(REPO_ROOT)} imports core.canonical.validation directly "
                f"-- retrieval must never reach validate_candidate"
            )
        assert not (names & _FORBIDDEN_VALIDATION_SYMBOLS), (
            f"{path.relative_to(REPO_ROOT)} imports one of {_FORBIDDEN_VALIDATION_SYMBOLS} directly"
        )


def test_retrieval_never_calls_validate_candidate():
    for path in _python_files(REPO_ROOT / "retrieval"):
        tree, _, _ = _imported_modules_and_names(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                called_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                assert called_name != "validate_candidate", (
                    f"{path.relative_to(REPO_ROOT)} calls validate_candidate"
                )


def test_retrieval_never_writes_to_the_evidence_pool():
    """Retrieval is read-only with respect to `evidence/` too, not just
    `core.canonical`: no file in `retrieval/` may call any `pool.put_*`
    method."""
    for path in _python_files(REPO_ROOT / "retrieval"):
        tree, _, _ = _imported_modules_and_names(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in _FORBIDDEN_MUTATION_METHODS, (
                    f"{path.relative_to(REPO_ROOT)} calls {node.func.attr!r} -- retrieval must never write to the pool"
                )


def test_retrieval_never_constructs_a_version_or_canonical_state():
    for path in _python_files(REPO_ROOT / "retrieval"):
        _, _, names = _imported_modules_and_names(path)
        assert "Version" not in names, f"{path.relative_to(REPO_ROOT)} imports Version"
        assert "CanonicalState" not in names, f"{path.relative_to(REPO_ROOT)} imports CanonicalState"


def test_core_canonical_never_imports_retrieval():
    for path in _python_files(REPO_ROOT / "core"):
        _, modules, _ = _imported_modules_and_names(path)
        for module in modules:
            assert not module.startswith("retrieval"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} (core must not depend on retrieval)"
            )
