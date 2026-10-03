#!/usr/bin/env python3
"""Probe the release deriver's refusals.

A build script whose checks cannot fire ships whatever it finds, and the
failure surfaces on a stranger's first `pip install`. Each mutation below
disables one refusal; the named test must notice.
"""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
BUILD = REPO / "release" / "provenance_pool" / "build.py"
PYPROJECT = REPO / "release" / "provenance_pool" / "template" / "pyproject.toml"
README = REPO / "release" / "provenance_pool" / "template" / "README.md"
NOTICE = REPO / "release" / "provenance_pool" / "template" / "NOTICE"
SUITE = "tests/test_release_provenance_pool.py"

MUTATIONS = [
    ("the import check stops refusing and only warns", BUILD,
     lambda s: s.replace("    if offenders:\n        raise ReleaseRefusal(\n"
                         '            "the distribution imports code it does not ship',
                         "    if False:  # MUTANT\n        raise ReleaseRefusal(\n"
                         '            "the distribution imports code it does not ship'),
     "test_the_import_check_passes_a_clean_tree_and_fails_a_dirty_one"),
    ("TYPE_CHECKING blocks skipped, so annotation-only leaks ship", BUILD,
     lambda s: s.replace(
         "    heads: Set[str] = set()\n    for node in ast.walk(tree):",
         "    heads: Set[str] = set()\n"
         "    tree.body = [n for n in tree.body if not isinstance(n, ast.If)]  # MUTANT\n"
         "    for node in ast.walk(tree):"),
     "test_the_import_check_reads_type_checking_blocks"),
    ("a file that does not parse is skipped instead of refused", BUILD,
     lambda s: s.replace("    except SyntaxError as error:\n        raise ReleaseRefusal(",
                         "    except SyntaxError as error:\n        return set()  # MUTANT\n"
                         "        raise ReleaseRefusal("),
     "test_a_file_that_does_not_parse_is_refused_rather_than_shipped"),
    ("machine paths tolerated in the emitted tree", BUILD,
     lambda s: s.replace('    needles = ("/home/user", "/Users/", "notationsystems/notations-",',
                         '    needles = ("__never_matches__", "/Users/", "notationsystems/notations-",  # MUTANT'),
     "test_machine_paths_are_refused_and_a_clean_tree_is_not"),
    ("an empty test selection ships as a silent success", BUILD,
     lambda s: s.replace("    if not tests:\n        raise ReleaseRefusal(",
                         "    if False:  # MUTANT\n        raise ReleaseRefusal("),
     "test_an_empty_test_selection_would_be_refused"),
    ("a missing declared package is skipped rather than refused", BUILD,
     lambda s: s.replace("        if not source.is_dir():\n            raise ReleaseRefusal(",
                         "        if False:  # MUTANT\n            raise ReleaseRefusal("),
     "test_a_missing_declared_package_is_refused"),
    ("the derived tree's suite is never run", BUILD,
     lambda s: s.replace("    summary = _run_tests(dest)",
                         '    summary = "0 passed"  # MUTANT'),
     "test_the_distribution_derives_and_its_own_suite_passes"),
    ("a failing derived suite reported as success", BUILD,
     lambda s: s.replace("    if result.returncode != 0:",
                         "    if False:  # MUTANT"),
     "test_a_failing_suite_in_the_derived_tree_is_refused"),
    ("the test filter becomes a pass-through", BUILD,
     lambda s: s.replace("        if internal and internal <= allowed:",
                         "        if True:  # MUTANT"),
     "test_test_selection_excludes_files_reaching_outside_the_distribution"),
    ("an excluded package loses its stated reason", BUILD,
     lambda s: s.replace('''    "architecture": (
        "cross-repository operational tooling. It hardcodes sibling "
        "clone paths on one machine and measures THIS organisation's "
        "repositories; outside here it would measure nothing"),''',
                         '    "architecture": "tooling",  # MUTANT'),
     "test_what_is_left_out_is_listed_with_a_reason"),

    ("build artefacts ship with the distribution", BUILD,
     lambda s: s.replace("    for cached in dest.rglob(\"__pycache__\"):\n"
                         "        shutil.rmtree(cached, ignore_errors=True)",
                         "    for cached in []:  # MUTANT\n"
                         "        shutil.rmtree(cached, ignore_errors=True)"),
     "test_the_emitted_tree_carries_no_build_artefacts"),

    ("a lock on shipped behaviour silently falls out of the release", BUILD,
     lambda s: s.replace('    "evidence", "scout", "retrieval", "materials", "experiment", "operations",',
                         '    "scout", "retrieval", "materials", "experiment", "operations",  # MUTANT'),
     "test_the_locks_on_shipped_behaviour_actually_ship"),

    # -- the release files ------------------------------------------------
    ("a runtime dependency appears in the packaging", PYPROJECT,
     lambda s: s.replace("dependencies = []", 'dependencies = ["numpy>=1.24"]'),
     "test_the_packaging_declares_no_runtime_dependency"),
    ("a shipped package is left out of the wheel", PYPROJECT,
     lambda s: s.replace('"experiment", "operations"]', '"experiment"]'),
     "test_the_packaging_declares_no_runtime_dependency"),
    ("the licence text is altered", REPO / "release" / "provenance_pool" / "template" / "LICENSE",
     lambda s: s.replace("Copyright [yyyy] [name of copyright owner]",
                         "Copyright 2026 Notation Systems Inc."),
     "test_the_licence_is_the_verbatim_apache_text"),
    ("the notice drops the copyright holder", NOTICE,
     lambda s: s.replace("Copyright 2026 Notation Systems Inc.", "Copyright 2026"),
     "test_the_notice_names_the_copyright_holder_and_the_licence"),
    ("a README example imports something the wheel does not ship", README,
     lambda s: s.replace("from evidence.pool import EvidencePool",
                         "from execution.engine import run\nfrom evidence.pool import EvidencePool"),
     "test_the_readme_examples_name_only_shipped_packages"),
]


def _compiles(path, source):
    """A mutant that does not parse can only ever be killed by an import
    error, which would credit the named test with a catch it did not
    make. Found for real twice in this project."""
    if path.suffix != ".py":
        return ""
    try:
        compile(source, str(path), "exec")
    except SyntaxError as error:
        return f"does not parse: {error}"
    return ""


def _purge_cache():
    """Two mutants differing by a few bytes can share an (mtime, size)
    and silently execute each other's bytecode. Measured, not feared."""
    for cached in REPO.rglob("__pycache__"):
        for item in cached.glob("*.pyc"):
            item.unlink(missing_ok=True)


def main() -> int:
    print("=== MUTATION VERIFICATION: the release deriver's refusals ===")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    killed = malformed = 0
    for description, target, mutate, test_name in MUTATIONS:
        original = target.read_text()
        mutated = mutate(original)
        if mutated == original:
            print(f"  MALFORMED  {description:<62} (diff reached nothing)")
            malformed += 1
            continue
        problem = _compiles(target, mutated)
        if problem:
            print(f"  MALFORMED  {description:<62} ({problem})")
            malformed += 1
            continue
        try:
            _purge_cache()
            target.write_text(mutated)
            result = subprocess.run(
                [sys.executable, "-m", "pytest", f"{SUITE}::{test_name}",
                 "-q", "-p", "no:cacheprovider"],
                cwd=REPO, capture_output=True, text=True, env=env)
        finally:
            target.write_text(original)
            _purge_cache()
        if result.returncode != 0:
            print(f"  KILLED     {description:<62} -> {test_name}")
            killed += 1
        else:
            print(f"  SURVIVED   {description:<62} -> {test_name}")
    total = len(MUTATIONS)
    print(f"\n{killed}/{total} mutants killed by their named test"
          + (f" ({malformed} malformed)" if malformed else ""))
    return 0 if killed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
