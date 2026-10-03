"""Dependency-direction check (§2): core -> morpho -> backends -> runtime,
never reversed. Morpho must not import backends. Backends must not import
each other. Nothing under core/, morpho/, or backends/ may import
runtime/ or reference renderer/.

This walks the actual Python source under each package (not a hardcoded
list), so it catches a violation introduced by any future file, not just
the ones that existed when this test was written.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _imports_in(path: Path):
    tree = ast.parse(path.read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _python_files(package_dir: Path):
    return [p for p in package_dir.rglob("*.py") if "test_" not in p.name]


def test_core_never_imports_downstream_packages():
    # inference_never_produces_canonical_truth (I3) and
    # representation_never_enters_canonical_state (I8), structurally:
    # nothing downstream can reach back into the canonical core.
    for path in _python_files(REPO_ROOT / "core"):
        for module in _imports_in(path):
            assert not module.startswith(("morpho", "backends", "runtime")), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} (core must not depend on downstream packages)"
            )


def test_morpho_never_imports_backends_or_runtime():
    for path in _python_files(REPO_ROOT / "morpho"):
        for module in _imports_in(path):
            assert not module.startswith(("backends", "runtime")), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} (morpho must not depend on backends/runtime)"
            )


def test_backends_never_import_each_other_or_runtime():
    backend_packages = {"threejs", "diagram", "graph", "simulation", "neural"}
    for backend_dir in (REPO_ROOT / "backends").iterdir():
        if not backend_dir.is_dir() or backend_dir.name not in backend_packages:
            continue
        for path in _python_files(backend_dir):
            for module in _imports_in(path):
                assert not module.startswith("runtime"), (
                    f"{path.relative_to(REPO_ROOT)} imports {module!r} (backends must not depend on runtime)"
                )
                for other_backend in backend_packages - {backend_dir.name}:
                    assert not module.startswith(f"backends.{other_backend}"), (
                        f"{path.relative_to(REPO_ROOT)} imports {module!r} "
                        f"(backends must not import each other)"
                    )


def test_nothing_upstream_of_renderer_references_it():
    for package in ("core", "morpho", "backends", "runtime"):
        for path in _python_files(REPO_ROOT / package):
            for module in _imports_in(path):
                assert not module.startswith("renderer"), (
                    f"{path.relative_to(REPO_ROOT)} imports {module!r} (renderer must never be a dependency)"
                )
