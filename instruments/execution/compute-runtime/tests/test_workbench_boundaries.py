"""Phase 68: boundary checks for workbench/, mirroring tests/
test_experiment_boundaries.py's AST-based convention exactly (which
itself mirrors tests/test_materials_boundaries.py). Enforces the
one-way dependency direction workbench sits on top of without altering:
workbench -> experiment -> materials -> evidence/retrieval, never the
reverse, and never a semantic write outside materials.results.
admit_experimental_result.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# workbench/ sits ABOVE experiment/ with no orchestrator of its own above
# IT -- unlike experiment/, which always receives an already-admitted
# document_id from its caller (see experiment/session.py's own
# docstring), workbench/ IS that caller: something has to admit the
# initial Source/Document/Referent corpus before a session can exist at
# all. This is the exact same "caller is responsible for admission"
# discipline the existing test fixtures (tests/test_experiment_residual_
# loop.py's _setup(), tests/test_experiment_interactive_session.py's
# _setup()) already exercise directly -- workbench/interaction.py's
# bootstrap_default_scenario() plays that same fixture role, just as
# production code rather than a test. Corpus bootstrapping
# (Source/Document/Referent) is therefore permitted here, wider than
# experiment/'s own narrower admission surface -- but the SEMANTIC
# write boundary is not widened at all: admit_record/put_record (raw
# structural bookkeeping) and admit_experimental_result (the sole
# semantic write door) remain the only calls workbench/ makes once a
# session already exists, exactly mirroring experiment/step.py.
_ALLOWED_PUT_SUFFIXES = ("put_record", "put_source", "put_document", "put_referent")
_ALLOWED_ADMIT_NAMES = ("admit_record", "admit_experimental_result", "admit_document", "admit_referent")


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


def test_workbench_only_imports_evidence_retrieval_materials_experiment():
    """workbench/ may depend on evidence/, retrieval/, materials/,
    experiment/ (and the standard library) -- never core/, runtime/,
    scout/, morpho/, backends/, adapters/, renderer/."""
    forbidden_prefixes = ("core", "runtime", "scout", "morpho", "backends", "adapters", "renderer")
    for path in _python_files(REPO_ROOT / "workbench"):
        for module in _imported_modules(path):
            assert not module.startswith(forbidden_prefixes), (
                f"{path.relative_to(REPO_ROOT)} imports {module!r} -- workbench/ must depend "
                "only on evidence/retrieval/materials/experiment"
            )


def test_workbench_never_admits_semantic_evidence_directly():
    """No file under workbench/ calls admit_observation/
    admit_claimed_relationship, or pool.put_observation/
    put_claimed_relationship, directly -- see the module-level comment
    above for exactly which OTHER admit_/put_ calls ARE permitted here
    (corpus bootstrapping plus the same admit_record/admit_experimental_
    result exception experiment/step.py already relies on) and why."""
    for path in _python_files(REPO_ROOT / "workbench"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
                assert node.attr in _ALLOWED_PUT_SUFFIXES, (
                    f"{path.relative_to(REPO_ROOT)} calls .{node.attr}(...) -- only "
                    f"{_ALLOWED_PUT_SUFFIXES} are permitted directly under workbench/"
                )
            if isinstance(node, ast.Name) and node.id.startswith("admit_"):
                assert node.id in _ALLOWED_ADMIT_NAMES, (
                    f"{path.relative_to(REPO_ROOT)} references {node.id} -- only "
                    f"{_ALLOWED_ADMIT_NAMES} are permitted directly under workbench/"
                )


def test_materials_results_remains_the_sole_semantic_write_boundary():
    """Repeats materials/'s own pin, extended to workbench/: admit_
    observation/admit_claimed_relationship (and their pool.put_ forms)
    are found ONLY in materials/results.py, across materials/,
    experiment/, AND workbench/."""
    semantic_admit_names = ("admit_observation", "admit_claimed_relationship")
    semantic_put_suffixes = ("put_observation", "put_claimed_relationship")
    mutators = []
    for package in ("materials", "experiment", "workbench"):
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


def test_materials_never_imports_workbench():
    """materials/ (and experiment/, and core/ -- the entirely unrelated
    scene-graph/rendering system Phase 62 confirmed shares this
    repository but never communicates with SCOUT/materials/experiment/
    workbench in either direction) must remain completely unaware that
    an interactive interface exists -- nothing beneath workbench/ ever
    imports it (Phase 70 sec.13's explicit `core --X--> workbench` check,
    alongside the pre-existing `materials --X--> workbench`/`experiment
    --X--> workbench` checks)."""
    # PHASE 88: `evidence`/`retrieval` sit BELOW materials and were never in
    # this sweep, though the invariant ("no lower layer imports workbench")
    # always covered them. Added rather than assumed.
    for package in ("materials", "experiment", "core", "evidence", "retrieval"):
        for path in _python_files(REPO_ROOT / package):
            for module in _imported_modules(path):
                assert not module.startswith("workbench"), (
                    f"{path.relative_to(REPO_ROOT)} imports {module!r} -- {package}/ must "
                    "remain unaware that workbench/ exists"
                )
