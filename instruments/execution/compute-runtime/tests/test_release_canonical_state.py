"""Locks on the `canonical-state` distribution and its refusals.

Every refusal is driven over BOTH answers. A refusal only ever observed
refusing has not been shown to distinguish anything -- it could be
raising unconditionally -- so each one here is also given the input it
must accept.

Two of these exist because of defects found while building the deriver,
and both are recorded in the code they lock:

  * a page naming a file that does not ship (the renderer resolves
    `three` through an importmap pointing into `vendor/`), and

  * a packaging list that declares five top-level names while the tree
    contains twelve packages. `pip install .` then emitted `core/` and
    `backends/` holding nothing but `__init__.py`. The derived suite
    passed the whole time, because it runs inside the emitted directory
    and imports the source tree -- never an installed copy.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import pathlib
import re
import shutil
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: Loaded by path under a distinct name. Both releases' derivers are
#: called `build.py`, and a plain `import build` would hand whichever
#: ran first to whichever ran second.
_SPEC = importlib.util.spec_from_file_location(
    "canonical_state_build", ROOT / "release" / "canonical_state" / "build.py")
release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release)


@pytest.fixture(scope="module")
def emitted():
    """One derivation, shared. Deriving copies 1.6 MB and runs a suite."""
    with tempfile.TemporaryDirectory() as directory:
        dest = pathlib.Path(directory) / "dist"
        facts = release.derive(dest)
        yield dest, facts


# ------------------------------------------------ it derives at all --


def test_the_distribution_derives_and_its_own_suite_passes(emitted):
    _, facts = emitted
    assert facts["modules"] == 35
    assert facts["tests"] >= 13
    assert "failed" not in facts["suite"]
    # a real count: "0 passed" would satisfy a substring check while
    # having verified nothing
    passed = int(facts["suite"].split(" passed")[0].split()[-1])
    assert passed > 50, f"the derived suite ran almost nothing: {facts['suite']}"


def test_the_emitted_tree_carries_no_build_artefacts(emitted):
    dest, _ = emitted
    assert not list(dest.rglob("__pycache__"))
    assert not list(dest.rglob("*.pyc"))
    assert not list(dest.rglob(".pytest_cache"))


def test_every_shipped_package_is_actually_in_this_tree():
    for package in release.PACKAGES:
        assert (ROOT / package).is_dir(), package
    for directory in release.ASSET_DIRS:
        assert (ROOT / directory).is_dir(), directory


def test_what_is_left_out_is_listed_with_a_reason():
    assert release.DELIBERATELY_OUTSIDE
    for what, why in release.DELIBERATELY_OUTSIDE.items():
        assert len(why) > 40, f"{what} is left out without a stated reason"


def test_no_shipped_package_is_also_listed_as_left_out():
    """A package in both lists would make the release's own account of
    itself contradictory, and the reader would have no way to tell which
    half was stale."""
    named = {token.strip()
             for key in release.DELIBERATELY_OUTSIDE
             for token in key.split(":")[0].split(",")}
    for package in release.PACKAGES:
        assert package not in named, package


# ------------------------------------------- the two tracks are two --


def test_the_two_distributions_share_no_package():
    """The reason this is a separate release at all. If the two ever
    overlapped, one of them would be shipping the other's code under its
    own name."""
    spec = importlib.util.spec_from_file_location(
        "provenance_pool_build",
        ROOT / "release" / "provenance_pool" / "build.py")
    other = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(other)
    assert not set(release.PACKAGES) & set(other.PACKAGES)


def test_no_shipped_module_imports_the_other_track(emitted):
    dest, _ = emitted
    spec = importlib.util.spec_from_file_location(
        "provenance_pool_build2",
        ROOT / "release" / "provenance_pool" / "build.py")
    other = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(other)
    forbidden = set(other.PACKAGES)
    for package in release.PACKAGES:
        for path in release._python_files(dest / package):
            heads = release._internal_imports(path.read_text(), path)
            assert not (heads & forbidden), f"{path} reaches the other track"


# ----------------------------------------------- refusals, both ways --


def test_the_import_check_passes_a_clean_tree_and_fails_a_dirty_one(emitted):
    dest, _ = emitted
    release._check_imports(dest)          # the accepting branch

    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        target = dirty / "core" / "canonical" / "state.py"
        target.write_text("import evidence.pool\n" + target.read_text())
        with pytest.raises(release.ReleaseRefusal, match="does not ship"):
            release._check_imports(dirty)


def test_a_file_that_does_not_parse_is_refused_rather_than_shipped():
    with pytest.raises(release.ReleaseRefusal, match="does not parse"):
        release._internal_imports("def (:\n", pathlib.Path("broken.py"))
    assert release._internal_imports("import json\n", pathlib.Path("ok.py")) == {"json"}


def test_machine_paths_are_refused_and_a_clean_tree_is_not(emitted):
    dest, _ = emitted
    release._check_no_machine_paths(dest)   # the accepting branch

    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        (dirty / "core" / "canonical" / "state.py").write_text(
            "# see /home/user/somewhere\n")
        with pytest.raises(release.ReleaseRefusal, match="machine that built it"):
            release._check_no_machine_paths(dirty)


def test_the_vendored_third_party_file_is_not_searched_for_machine_paths(emitted):
    """three.js is somebody else's source. Rewriting it to satisfy our
    own check would be editing a third party's code to make our build
    pass, which is the wrong direction entirely."""
    dest, _ = emitted
    vendored = dest / "renderer" / "vendor" / "three.module.js"
    assert vendored.exists()
    release._check_no_machine_paths(dest)


# ------------------------------------- the refusal the renderer needs --


def test_a_page_naming_a_missing_file_is_refused_and_a_complete_one_is_not(emitted):
    """THE IMPORT CHECK'S DEFECT IN ANOTHER LANGUAGE.

    `renderer/index.html` resolves `three` through an importmap pointing
    at `./vendor/three.module.js`, vendored deliberately so the page has
    no CDN dependency. Emitting the page without the file it names would
    produce something that fails on open -- and no amount of parsing
    Python would notice."""
    dest, _ = emitted
    release._check_assets_resolve(dest)     # the accepting branch

    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        (dirty / "renderer" / "vendor" / "three.module.js").unlink()
        with pytest.raises(release.ReleaseRefusal, match="does not ship"):
            release._check_assets_resolve(dirty)


def test_the_asset_check_is_not_vacuous(emitted):
    """A check that found no references to test would pass on anything."""
    dest, _ = emitted
    page = (dest / "renderer" / "index.html").read_text()
    found = release._ASSET_REFERENCE.findall(page)
    assert found, "the asset check examined a page with no local references"
    assert any("three.module.js" in reference for reference in found)


# -------------------------- the refusal the packaging defect needs --


def test_packaging_that_omits_a_subpackage_is_refused(emitted):
    """THE DEFECT THIS RELEASE ACTUALLY HAD.

    The first pyproject listed `core` and `backends` without their
    subpackages, and `pip install .` produced a distribution whose
    `core/` contained only `__init__.py`. The derived suite passed
    throughout: it runs inside the emitted tree, so `.` is on the path
    and it imports the source -- the one thing a user never has.
    """
    dest, _ = emitted
    release._check_packaging_covers_the_tree(dest)   # the accepting branch

    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        toml = dirty / "pyproject.toml"
        toml.write_text(toml.read_text().replace(
            '"core", "core.canonical", "core.projection",', '"core",'))
        with pytest.raises(release.ReleaseRefusal, match="NOT declared"):
            release._check_packaging_covers_the_tree(dirty)


def test_packaging_that_names_a_package_not_in_the_tree_is_refused(emitted):
    """The other direction: a declaration resolving to nothing."""
    dest, _ = emitted
    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        toml = dirty / "pyproject.toml"
        toml.write_text(toml.read_text().replace(
            '    "adapters",', '    "adapters", "nosuchpackage",'))
        with pytest.raises(release.ReleaseRefusal, match="NOT in the tree"):
            release._check_packaging_covers_the_tree(dirty)


def test_an_asset_directory_the_packaging_drops_is_refused(emitted):
    """THE DEFECT EVERY OTHER CHECK HERE MISSED.

    `renderer/` was in the emitted tree, complete, and
    `_check_assets_resolve` confirmed the page's importmap resolved
    against it. `pip wheel .` then produced 47 entries with none under
    `renderer/`, because a wheel installs packages and a plain directory
    is dropped -- while the NOTICE that did install stated the three.js
    notice "ships with it".

    `_check_packaging_covers_the_tree` could not see it: it compares
    declared packages against actual packages, so it examined only the
    half of the tree made of Python. A check written for "the packaging
    omits part of the tree" that looked at one kind of part.
    """
    dest, _ = emitted
    release._check_assets_are_packaged(dest)     # the accepting branch

    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        toml = dirty / "pyproject.toml"
        toml.write_text(toml.read_text().replace('    "renderer",\n', ""))
        with pytest.raises(release.ReleaseRefusal, match="wheel drops it"):
            release._check_assets_are_packaged(dirty)


def test_an_asset_file_no_pattern_covers_is_refused(emitted):
    """Declared but uncovered installs as a bare `__init__.py`, which is
    the same outcome by a different route."""
    dest, _ = emitted
    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        toml = dirty / "pyproject.toml"
        toml.write_text(toml.read_text().replace(
            'renderer = ["*.html", "*.json", "vendor/*.js", "vendor/*.md"]',
            'renderer = ["*.html", "*.json"]'))
        with pytest.raises(release.ReleaseRefusal, match="no package-data pattern"):
            release._check_assets_are_packaged(dirty)


def test_an_asset_directory_with_no_patterns_at_all_is_refused(emitted):
    dest, _ = emitted
    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        toml = dirty / "pyproject.toml"
        text = toml.read_text()
        start = text.index("[tool.setuptools.package-data]")
        end = text.index("[tool.pytest.ini_options]")
        toml.write_text(text[:start] + text[end:])
        with pytest.raises(release.ReleaseRefusal, match="no package-data patterns"):
            release._check_assets_are_packaged(dirty)


def test_the_packaging_shim_exists_only_in_the_release(emitted):
    """`renderer/__init__.py` is there so packaging carries the
    directory. It is a release concern, so it lives in the template
    beside the licence -- not in the source tree, where nothing needs
    it."""
    dest, _ = emitted
    assert (dest / "renderer" / "__init__.py").exists()
    assert not (ROOT / "renderer" / "__init__.py").exists(), (
        "the shim leaked into the source tree, where it makes `renderer` "
        "look like an importable package it is not")


def test_every_asset_the_notice_names_is_one_the_packaging_carries(emitted):
    """The NOTICE makes a licensing claim about specific files. A claim
    about a file the wheel does not contain is a false statement about
    somebody else's licence, not a missing feature."""
    dest, _ = emitted
    notice = (dest / "NOTICE").read_text()
    named = re.findall(r"renderer/[\w./-]+", notice)
    assert named, "the notice names no file, so this check verifies nothing"
    globs = release._package_data_globs(dest)["renderer"]
    for reference in named:
        relative = reference.split("renderer/", 1)[1]
        assert (dest / reference).exists(), f"{reference} is not in the tree"
        assert any(fnmatch.fnmatch(relative, pattern) for pattern in globs), (
            f"the notice names {reference}, which no package-data pattern "
            f"carries, so it would not be installed")


def test_the_packaging_list_covers_every_subpackage_that_exists(emitted):
    """Stated as the property rather than as a count, so adding a
    subpackage and forgetting the declaration fails here."""
    dest, _ = emitted
    assert set(release._declared_packages(dest)) == set(release._actual_packages(dest))
    assert "core.canonical" in release._actual_packages(dest)
    assert "backends.threejs" in release._actual_packages(dest)


# --------------------------------- selection, and the test it recovers --


def test_an_empty_test_selection_would_be_refused():
    with tempfile.TemporaryDirectory() as directory:
        empty = pathlib.Path(directory)
        (empty / "tests").mkdir()
        for package in release.PACKAGES:
            (empty / package).mkdir()
            (empty / package / "__init__.py").write_text("")
        for asset in release.ASSET_DIRS:
            (empty / asset).mkdir()
        with pytest.raises(release.ReleaseRefusal, match="verify nothing"):
            release.derive(pathlib.Path(directory) / "dist", root=empty)


def test_selection_excludes_a_test_reaching_outside_the_distribution():
    selected = {path.name for path in release.selected_tests()}
    assert "test_projection_conformance.py" not in selected, (
        "that test needs architecture, evidence, scout and yaml")
    assert selected, "the selection is empty"


def test_the_test_whose_only_outside_import_was_a_sibling_helper_ships():
    """THE SILENT LOSS THIS RULE WAS CHANGED FOR.

    `test_time_series_representation.py` imports
    `tests.fixtures_time_series`, whose own imports are nothing but
    `core.canonical`. The head `tests` is not a package name, so the
    original rule dropped the test -- and the release simply contained
    one fewer test while still reporting success."""
    selected = {path.name for path in release.selected_tests()}
    assert "test_time_series_representation.py" in selected

    shipped = {path.name for path in release.support_files()}
    assert "fixtures_time_series.py" in shipped


def test_a_test_reaching_for_an_UNSHIPPED_sibling_helper_is_still_excluded():
    """The allowance is for helpers this release ships, and only those.

    Constructed rather than found: no test in this repository imports an
    unclean `tests.` helper today, so the branch that must refuse has no
    natural input. Without driving it, granting the allowance
    unconditionally passes every other lock here -- it did, and a mutant
    that replaced the condition with `True` survived.
    """
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        (root / "tests").mkdir()
        # a helper that reaches OUTSIDE the distribution, so it does not ship
        (root / "tests" / "unclean_helper.py").write_text(
            "import evidence.pool\nVALUE = 1\n")
        # and a test whose only non-stdlib imports are core + that helper
        (root / "tests" / "test_uses_unclean_helper.py").write_text(
            "import core.canonical.state\n"
            "from tests.unclean_helper import VALUE\n"
            "def test_x():\n    assert VALUE\n")

        shipped = {path.name for path in release.support_files(root)}
        assert "unclean_helper.py" not in shipped, (
            "a helper reaching outside the distribution was shipped anyway")

        selected = {path.name for path in release.selected_tests(root)}
        assert "test_uses_unclean_helper.py" not in selected, (
            "a test binding to a helper this release does not ship was "
            "selected; installed, it would fail at import")


def test_a_test_reaching_for_a_SHIPPED_sibling_helper_is_selected():
    """The other branch, constructed the same way, so the rule is shown
    to distinguish the two cases rather than to refuse both."""
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        (root / "tests").mkdir()
        (root / "tests" / "clean_helper.py").write_text(
            "import core.canonical.state\nVALUE = 1\n")
        (root / "tests" / "test_uses_clean_helper.py").write_text(
            "import core.canonical.state\n"
            "from tests.clean_helper import VALUE\n"
            "def test_x():\n    assert VALUE\n")

        assert "clean_helper.py" in {p.name for p in release.support_files(root)}
        assert "test_uses_clean_helper.py" in {
            p.name for p in release.selected_tests(root)}


def test_the_conftest_ships_so_the_fixtures_resolve(emitted):
    """Without it the derived suite does not fail -- it ERRORS at setup
    thirty times, which reads as broken code rather than a missing
    file."""
    dest, _ = emitted
    conftest = dest / "tests" / "conftest.py"
    assert conftest.exists()
    assert "sample_schema" in conftest.read_text()
    assert "genesis_version" in conftest.read_text()


def test_support_files_are_only_shipped_when_they_are_clean():
    """The allowance is conditional. Granted unconditionally it would
    readmit exactly what the selection rule exists to exclude."""
    assert release._is_clean(ROOT / "conftest.py")
    assert release._is_clean(ROOT / "tests" / "fixtures_time_series.py")
    assert not release._is_clean(ROOT / "tests" / "test_projection_conformance.py")


def test_a_missing_declared_package_is_refused():
    with tempfile.TemporaryDirectory() as directory:
        partial = pathlib.Path(directory)
        for package in release.PACKAGES[:-1]:
            shutil.copytree(ROOT / package, partial / package,
                            ignore=release.EXCLUDED)
        (partial / "tests").mkdir()
        with pytest.raises(release.ReleaseRefusal, match="not in this tree"):
            release.derive(pathlib.Path(directory) / "dist", root=partial)


# ------------------------------------------- what the README claims --


def test_the_two_seams_ship_and_implement_nothing(emitted):
    """The README says `backends/simulation` and `backends/neural` are
    interface shapes only. If either ever grew an implementation, the
    packaging would be describing something that is no longer true."""
    dest, _ = emitted
    for seam in ("simulation", "neural"):
        source = (dest / "backends" / seam / "interface.py").read_text()
        assert "INTERFACE SHAPES ONLY" in source
        assert "Do not implement" in source


def test_nothing_shipped_imports_a_numeric_module(emitted):
    """The README says this is not a numerical library, and that is a
    measurement rather than a positioning statement. Locked so it stays
    one."""
    dest, _ = emitted
    numeric = {"math", "statistics", "cmath", "decimal", "fractions",
               "random", "numpy", "scipy"}
    for package in release.PACKAGES:
        for path in release._python_files(dest / package):
            heads = release._internal_imports(path.read_text(), path)
            offending = heads & numeric
            assert not offending, (
                f"{path.relative_to(dest)} imports {offending}; the README's "
                f"claim that this ships no mathematics is no longer true")


def test_the_distribution_ships_ci_that_exercises_what_it_claims(emitted):
    """A zero-dependency library that supports four interpreters and
    three platforms has made a claim nothing here can check, because
    this repository runs on one of each. CI is where that claim is
    tested rather than asserted, so it has to actually ship."""
    dest, _ = emitted
    workflow = dest / ".github" / "workflows" / "ci.yml"
    assert workflow.exists(), "the distribution ships no CI"
    text = workflow.read_text()
    for version in ("3.10", "3.11", "3.12", "3.13"):
        assert version in text, f"CI does not exercise Python {version}"
    for platform in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert platform in text, f"CI does not exercise {platform}"


def test_the_shipped_ci_checks_the_installed_artefact_not_just_the_checkout(emitted):
    """THE JOB THAT EXISTS BECAUSE OF THIS RELEASE'S TWO DEFECTS.

    A suite run in a checkout has the source on its path, so it can
    never see a packaging failure. Both defects here were invisible to
    it: a declaration that omitted every subpackage, and a wheel that
    carried no `renderer/` while the NOTICE said the notice shipped with
    it. The second CI job builds the wheel and looks inside."""
    dest, _ = emitted
    text = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "--target /tmp/installed" in text or "--target" in text, (
        "CI never installs the wheel anywhere, so it only ever tests the "
        "checkout")
    assert "renderer" in text, (
        "CI does not check that the renderer survives packaging, which is "
        "the thing that failed")
    assert "THIRD_PARTY_NOTICES" in text, (
        "CI does not check that the file the NOTICE points at is installed")


def test_the_source_url_names_a_repository_that_exists():
    """Metadata is read by strangers. A `Source` pointing at a repository
    nobody created 404s on the first release, and both distributions are
    derived from one repository rather than living in their own, so both
    name it."""
    urls = set()
    for name in ("canonical_state", "provenance_pool"):
        toml = (ROOT / "release" / name / "template" / "pyproject.toml").read_text()
        found = re.findall(r'^Source = "([^"]+)"', toml, re.MULTILINE)
        assert len(found) == 1, f"{name} declares {len(found)} Source URLs"
        urls.add(found[0])
    assert len(urls) == 1, (
        f"the two distributions are derived from one repository but name "
        f"different ones: {urls}")
    url = urls.pop()
    assert "notationsystems/canonical-state" not in url
    assert "notationsystems/provenance-pool" not in url
    assert url.startswith("https://github.com/")


def test_a_manifest_that_drops_test_support_is_refused(emitted):
    """THE DEFECT THE SDIST HAD, AND THE ONE THE WHEEL COULD NOT SHOW.

    setuptools' default sdist rules carry `tests/test_*.py` and not the
    conftest beside them, so the released sdist held thirteen test
    modules and none of the support they bind to. Unpacked, `pytest
    tests/` failed at COLLECTION -- the command the README gives
    contributors.

    Nothing already checked could see it. The wheel is correct and
    deliberately ships no tests; the emitted tree is correct; and
    `provenance-pool`'s sdist is correct only because it has no test
    support files for the defaults to miss."""
    dest, _ = emitted
    release._check_sdist_carries_the_suite(dest)      # the accepting branch

    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        manifest = dirty / "MANIFEST.in"
        manifest.write_text(
            manifest.read_text().replace("recursive-include tests *.py", ""))
        with pytest.raises(release.ReleaseRefusal, match="conftest.py"):
            release._check_sdist_carries_the_suite(dirty)


def test_a_missing_manifest_is_refused_rather_than_left_to_the_defaults(emitted):
    dest, _ = emitted
    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        (dirty / "MANIFEST.in").unlink()
        with pytest.raises(release.ReleaseRefusal, match="no MANIFEST.in"):
            release._check_sdist_carries_the_suite(dirty)


def test_the_manifest_carries_the_renderer_into_the_sdist_too(emitted):
    """`package-data` is a WHEEL mechanism and says nothing about the
    sdist. Two separate declarations, two separate ways to lose the same
    directory."""
    dest, _ = emitted
    assert release._manifest_covers(
        dest, pathlib.PurePosixPath("renderer/vendor/three.module.js"))
    assert release._manifest_covers(
        dest, pathlib.PurePosixPath("tests/conftest.py"))

    with tempfile.TemporaryDirectory() as directory:
        dirty = pathlib.Path(directory) / "dist"
        shutil.copytree(dest, dirty)
        manifest = dirty / "MANIFEST.in"
        manifest.write_text(manifest.read_text().replace("graft renderer", ""))
        with pytest.raises(release.ReleaseRefusal, match="three.module.js"):
            release._check_sdist_carries_the_suite(dirty)


def test_the_build_requirement_is_the_version_that_actually_works():
    """MEASURED, NOT REMEMBERED: 76.1.0 rejects this metadata and 77.0.1
    builds it, because PEP 639's `license` expression and `license-files`
    landed in setuptools 77.

    The old pin said 68 and survived anyway, because `pip wheel` builds
    in an isolated environment where ">=68" resolves to the newest
    setuptools there is. The declaration was never the thing being
    tested -- the same shape as a derived suite importing the source
    tree instead of the install."""
    for name in ("canonical_state", "provenance_pool"):
        toml = (ROOT / "release" / name / "template" / "pyproject.toml").read_text()
        found = re.findall(r'requires = \["setuptools>=(\d+)"\]', toml)
        assert len(found) == 1, f"{name}: {len(found)} build requirements"
        assert int(found[0]) >= 77, (
            f"{name} declares setuptools>={found[0]}, which cannot build its "
            f"own PEP 639 metadata; measured, 76 rejects it and 77 builds it")


def test_the_licence_is_the_verbatim_apache_text():
    import hashlib
    text = (ROOT / "release" / "canonical_state" / "template" / "LICENSE").read_bytes()
    other = (ROOT / "release" / "provenance_pool" / "template" / "LICENSE").read_bytes()
    assert text == other, "the two releases disagree about the Apache text"
    assert hashlib.sha256(text).hexdigest().startswith("cfc7749b")
    assert b"Apache License" in text and b"Version 2.0" in text


def test_the_notice_names_the_vendored_third_party_code():
    """A distribution that redistributes somebody else's MIT code and
    does not say so is a licensing defect, not a documentation one.

    Checked on the VERSION and the file, not on the string "three.js".
    The first version of this lock asserted that name and could not
    fail: the project URL in the same sentence contains it, so a notice
    that had stopped saying WHICH three.js still passed. A check whose
    input cannot span its branches tests nothing about the branch."""
    notice = (ROOT / "release" / "canonical_state" / "template" / "NOTICE").read_text()
    assert "r160" in notice, "the notice does not say which version is included"
    assert "three.module.js" in notice, "the notice does not say which file"
    assert "MIT" in notice
    assert "Notation Systems" in notice


def test_the_packaging_declares_no_runtime_dependency():
    toml = (ROOT / "release" / "canonical_state" / "template" / "pyproject.toml").read_text()
    assert "dependencies = []" in toml
    assert 'name = "canonical-state"' in toml


def test_the_readme_names_only_shipped_packages():
    readme = (ROOT / "release" / "canonical_state" / "template" / "README.md").read_text()
    for line in readme.splitlines():
        if line.startswith("from ") or line.startswith("import "):
            head = line.split()[1].split(".")[0]
            assert head in release.PACKAGES, (
                f"README imports {head!r}, which this release does not ship")
