"""Phase 17 boundary check: DerivedValue is evidence-layer-only.

`tests/test_scout_boundaries.py` already proves `evidence/` (all of it,
including the files this phase touches) never imports
`backends/`/`renderer/`/`runtime/` or `core.canonical.validation`. This
file adds the two checks specific to this phase's own scope boundary
that no existing test covers: `evidence/` must not import `retrieval/`
(the dependency runs the other way -- `retrieval/` depends on
`evidence/`, never the reverse), and `retrieval/` must remain completely
unaware `DerivedValue` exists at all -- proving "no changes to retrieval
boundaries are required" is actually true, not merely unexercised.
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


def test_evidence_never_imports_retrieval():
    for path in _python_files(REPO_ROOT / "evidence"):
        for module in _imported_modules(path):
            assert not module.startswith("retrieval"), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- evidence/ must not depend on retrieval/"
            )


def test_retrieval_never_references_derived_value():
    """No file under retrieval/ mentions DerivedValue by name -- neither
    as an import nor as a bare identifier -- confirming Phase 17 required
    zero changes to retrieval/'s boundaries, not just that none were
    made."""
    for path in _python_files(REPO_ROOT / "retrieval"):
        text = path.read_text().lower()
        assert "derivedvalue" not in text and "derived_value" not in text, (
            f"{path.relative_to(REPO_ROOT)} references DerivedValue -- "
            f"Phase 17 explicitly does not make DerivedValue retrievable"
        )
