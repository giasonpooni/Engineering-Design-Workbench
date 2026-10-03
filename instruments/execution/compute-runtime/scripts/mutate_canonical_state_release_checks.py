#!/usr/bin/env python3
"""Probe the `canonical-state` deriver's refusals.

A build script whose checks cannot fire ships whatever it finds, and the
failure surfaces on a stranger's first `pip install`. Each mutation below
disables one refusal; the named test must notice.

Two of these disable checks that exist because the defect was real:
the asset check (a page naming a file that does not ship) and the
packaging-coverage check (a declaration that omits half the tree, which
the derived suite could not see because it imports the source).
"""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
BUILD = REPO / "release" / "canonical_state" / "build.py"
PYPROJECT = REPO / "release" / "canonical_state" / "template" / "pyproject.toml"
README = REPO / "release" / "canonical_state" / "template" / "README.md"
NOTICE = REPO / "release" / "canonical_state" / "template" / "NOTICE"
CI = REPO / "release" / "canonical_state" / "template" / ".github" / "workflows" / "ci.yml"
MANIFEST = REPO / "release" / "canonical_state" / "template" / "MANIFEST.in"
SUITE = "tests/test_release_canonical_state.py"

MUTATIONS = [
    ("the import check stops refusing", BUILD,
     lambda s: s.replace('    if offenders:\n        raise ReleaseRefusal(\n'
                         '            "the distribution imports code it does not ship',
                         '    if False:  # MUTANT\n        raise ReleaseRefusal(\n'
                         '            "the distribution imports code it does not ship'),
     "test_the_import_check_passes_a_clean_tree_and_fails_a_dirty_one"),
    ("a file that does not parse is skipped instead of refused", BUILD,
     lambda s: s.replace("    except SyntaxError as error:\n        raise ReleaseRefusal(",
                         "    except SyntaxError as error:\n        return set()  # MUTANT\n"
                         "        raise ReleaseRefusal("),
     "test_a_file_that_does_not_parse_is_refused_rather_than_shipped"),
    ("machine paths tolerated in the emitted tree", BUILD,
     lambda s: s.replace('    needles = ("/home/user", "/Users/",',
                         '    needles = ("__never_matches__", "/Users/",  # MUTANT'),
     "test_machine_paths_are_refused_and_a_clean_tree_is_not"),
    ("an empty test selection ships as a silent success", BUILD,
     lambda s: s.replace("    if not tests:\n        raise ReleaseRefusal(",
                         "    if False:  # MUTANT\n        raise ReleaseRefusal("),
     "test_an_empty_test_selection_would_be_refused"),
    ("a missing declared package is skipped rather than refused", BUILD,
     lambda s: s.replace("        if not source.is_dir():\n            raise ReleaseRefusal(\n"
                         '                f"declared package',
                         "        if False:  # MUTANT\n            raise ReleaseRefusal(\n"
                         '                f"declared package'),
     "test_a_missing_declared_package_is_refused"),
    ("the derived tree's suite is never run", BUILD,
     lambda s: s.replace("    summary = _run_tests(dest)",
                         '    summary = "0 passed"  # MUTANT'),
     "test_the_distribution_derives_and_its_own_suite_passes"),

    # --- the asset refusal ---
    ("a page may name a file that does not ship", BUILD,
     lambda s: s.replace("    if offenders:\n        raise ReleaseRefusal(\n"
                         '            "an emitted page refers to a file that does not ship',
                         "    if False:  # MUTANT\n        raise ReleaseRefusal(\n"
                         '            "an emitted page refers to a file that does not ship'),
     "test_a_page_naming_a_missing_file_is_refused_and_a_complete_one_is_not"),
    ("the asset check looks at no pages at all", BUILD,
     lambda s: s.replace('        for page in sorted(base.rglob("*.html")):',
                         '        for page in sorted(base.rglob("*.nothing")):  # MUTANT'),
     "test_a_page_naming_a_missing_file_is_refused_and_a_complete_one_is_not"),
    ("the asset reference pattern matches nothing", BUILD,
     lambda s: s.replace(
         r'''    r"""(?:"|')(\./[^"']+|[\w./-]+\.(?:js|css|json|png|svg))(?:"|')""")''',
         r'''    r"""(?:"|')(__never__)(?:"|')""")  # MUTANT'''),
     "test_the_asset_check_is_not_vacuous"),

    # --- the packaging refusal ---
    ("packaging may omit half the tree", BUILD,
     lambda s: s.replace("    if missing or phantom:", "    if False:  # MUTANT"),
     "test_packaging_that_omits_a_subpackage_is_refused"),
    ("only top-level packages are counted as real", BUILD,
     lambda s: s.replace('        for directory in sorted(base.rglob("")):',
                         '        for directory in [base]:  # MUTANT'),
     "test_the_packaging_list_covers_every_subpackage_that_exists"),
    ("the declared list is read as empty", BUILD,
     lambda s: s.replace("    return sorted(re.findall(r'\"([^\"]+)\"', match.group(1)))",
                         "    return []  # MUTANT"),
     "test_packaging_that_names_a_package_not_in_the_tree_is_refused"),

    # --- the asset-packaging refusal ---
    ("an asset directory may be dropped from the wheel", BUILD,
     lambda s: s.replace("    if offenders:\n        raise ReleaseRefusal(\n"
                         '            "the packaging does not carry files the distribution ships',
                         "    if False:  # MUTANT\n        raise ReleaseRefusal(\n"
                         '            "the packaging does not carry files the distribution ships'),
     "test_an_asset_directory_the_packaging_drops_is_refused"),
    ("an undeclared asset directory passes as declared", BUILD,
     lambda s: s.replace("        if directory not in declared:",
                         "        if False:  # MUTANT"),
     "test_an_asset_directory_the_packaging_drops_is_refused"),
    ("a declared directory with no patterns is accepted", BUILD,
     lambda s: s.replace("        if not patterns:", "        if False:  # MUTANT"),
     "test_an_asset_directory_with_no_patterns_at_all_is_refused"),
    ("every file counts as covered whatever the patterns say", BUILD,
     lambda s: s.replace("            if not any(fnmatch.fnmatch(str(relative), pattern)",
                         "            if False and any(fnmatch.fnmatch(str(relative), pattern)  # MUTANT"),
     "test_an_asset_file_no_pattern_covers_is_refused"),
    ("the package-data table is read as empty", BUILD,
     lambda s: s.replace("    if not block:\n        return {}",
                         "    if True:  # MUTANT\n        return {}"),
     "test_an_asset_directory_with_no_patterns_at_all_is_refused"),
    ("the packaging shim is not emitted", PYPROJECT,
     lambda s: s.replace('    "renderer",\n', ""),
     "test_an_asset_directory_the_packaging_drops_is_refused"),
    ("the notice names a file the packaging does not carry", PYPROJECT,
     lambda s: s.replace('renderer = ["*.html", "*.json", "vendor/*.js", "vendor/*.md"]',
                         'renderer = ["*.html", "*.json"]'),
     "test_every_asset_the_notice_names_is_one_the_packaging_carries"),

    # --- selection and support ---
    ("the sibling-helper allowance is granted without checking", BUILD,
     lambda s: s.replace("            if wanted and wanted <= helper_names:",
                         "            if True:  # MUTANT"),
     "test_a_test_reaching_for_an_UNSHIPPED_sibling_helper_is_still_excluded"),
    ("the sibling-helper allowance is never granted", BUILD,
     lambda s: s.replace("            if wanted and wanted <= helper_names:",
                         "            if False:  # MUTANT"),
     "test_a_test_reaching_for_a_SHIPPED_sibling_helper_is_selected"),
    ("support files ship whether or not they are clean", BUILD,
     lambda s: s.replace("    return internal <= set(PACKAGES)",
                         "    return True  # MUTANT"),
     "test_support_files_are_only_shipped_when_they_are_clean"),
    ("the conftest is left behind", BUILD,
     lambda s: s.replace('    conftest = root / "conftest.py"',
                         '    conftest = root / "__no_such_conftest__.py"  # MUTANT'),
     "test_the_conftest_ships_so_the_fixtures_resolve"),
    ("the test filter becomes a pass-through", BUILD,
     lambda s: s.replace("        if internal and internal <= allowed:",
                         "        if True:  # MUTANT"),
     "test_selection_excludes_a_test_reaching_outside_the_distribution"),

    # --- what the packaging and prose claim ---
    ("an excluded package loses its stated reason", BUILD,
     lambda s: s.replace('''    "architecture": (
        "cross-repository operational tooling. It measures THIS "
        "organisation's repositories and hardcodes sibling clone paths; "
        "outside here it would measure nothing"),''',
                         '    "architecture": "tooling",  # MUTANT'),
     "test_what_is_left_out_is_listed_with_a_reason"),
    ("a runtime dependency appears in the packaging", PYPROJECT,
     lambda s: s.replace("dependencies = []", 'dependencies = ["numpy"]'),
     "test_the_packaging_declares_no_runtime_dependency"),
    ("the notice stops saying WHICH three.js is included", NOTICE,
     lambda s: s.replace("three.js r160", "a library"),
     "test_the_notice_names_the_vendored_third_party_code"),
    ("the notice stops naming the vendored file", NOTICE,
     lambda s: s.replace("three.module.js", "a file"),
     "test_the_notice_names_the_vendored_third_party_code"),
    ("the shipped CI stops exercising an interpreter it claims", CI,
     lambda s: s.replace('"3.10", "3.11", "3.12", "3.13"', '"3.11"'),
     "test_the_distribution_ships_ci_that_exercises_what_it_claims"),
    ("the shipped CI stops exercising Windows", CI,
     lambda s: s.replace("macos-latest, windows-latest", "macos-latest"),
     "test_the_distribution_ships_ci_that_exercises_what_it_claims"),
    ("CI stops checking the renderer survived packaging", CI,
     lambda s: s.replace("THIRD_PARTY_NOTICES.md", "LICENSE_PLACEHOLDER"),
     "test_the_shipped_ci_checks_the_installed_artefact_not_just_the_checkout"),
    ("the Source URL goes back to a repository nobody created", PYPROJECT,
     lambda s: s.replace(
         'Source = "https://github.com/giasonpooni/Scientific-Computation-Runtime"',
         'Source = "https://github.com/notationsystems/canonical-state"'),
     "test_the_source_url_names_a_repository_that_exists"),
    # --- the sdist refusal ---
    ("the sdist check stops refusing", BUILD,
     lambda s: s.replace("    if offenders:\n        raise ReleaseRefusal(\n"
                         '            "MANIFEST.in does not carry files the sdist needs',
                         "    if False:  # MUTANT\n        raise ReleaseRefusal(\n"
                         '            "MANIFEST.in does not carry files the sdist needs'),
     "test_a_manifest_that_drops_test_support_is_refused"),
    ("a missing manifest is tolerated", BUILD,
     lambda s: s.replace('    if not (dest / "MANIFEST.in").is_file():',
                         "    if False:  # MUTANT"),
     "test_a_missing_manifest_is_refused_rather_than_left_to_the_defaults"),
    ("every path counts as covered whatever the manifest says", BUILD,
     lambda s: s.replace("            if not _manifest_covers(dest, relative):",
                         "            if False:  # MUTANT"),
     "test_a_manifest_that_drops_test_support_is_refused"),
    ("recursive-include is read as covering nothing", BUILD,
     lambda s: s.replace('        if directive == "recursive-include" and len(rest) >= 2:',
                         '        if False and directive == "recursive-include":  # MUTANT'),
     "test_a_manifest_that_drops_test_support_is_refused"),
    ("graft is read as covering nothing", BUILD,
     lambda s: s.replace('        if directive == "graft" and rest and parts[:1] == (rest[0],):',
                         '        if False:  # MUTANT'),
     "test_the_manifest_carries_the_renderer_into_the_sdist_too"),
    ("the manifest stops carrying test support", MANIFEST,
     lambda s: s.replace("recursive-include tests *.py", "include tests/test_delta.py"),
     "test_a_manifest_that_drops_test_support_is_refused"),
    ("the build requirement goes back to a version that cannot build it", PYPROJECT,
     lambda s: s.replace('requires = ["setuptools>=77"]', 'requires = ["setuptools>=68"]'),
     "test_the_build_requirement_is_the_version_that_actually_works"),

    ("a README example imports something the wheel does not ship", README,
     lambda s: s.replace("from core.canonical.schema import",
                         "from evidence.pool import EvidencePool\n"
                         "from core.canonical.schema import"),
     "test_the_readme_names_only_shipped_packages"),
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
    print("=== MUTATION VERIFICATION: the canonical-state deriver's refusals ===")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    killed = malformed = 0
    for description, target, mutate, test_name in MUTATIONS:
        original = target.read_text()
        mutated = mutate(original)
        if mutated == original:
            print(f"  MALFORMED  {description:<58} (diff reached nothing)")
            malformed += 1
            continue
        problem = _compiles(target, mutated)
        if problem:
            print(f"  MALFORMED  {description:<58} ({problem})")
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
            print(f"  KILLED     {description:<58} -> {test_name}")
            killed += 1
        else:
            print(f"  SURVIVED   {description:<58} -> {test_name}")
    total = len(MUTATIONS)
    print(f"\n{killed}/{total} mutants killed by their named test"
          + (f" ({malformed} malformed)" if malformed else ""))
    return 0 if killed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
