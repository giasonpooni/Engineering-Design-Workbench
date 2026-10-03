"""Locks on the open-source release deriver.

WHAT THESE PROTECT. The distribution is a PROJECTION of packages that
live in this repository, and the whole reason it is derived rather than
copied is that a second committed copy would be a mirror nothing
recomputes. That buys correctness only if the deriver actually refuses
the things it says it refuses -- a build script whose checks cannot fire
is a build script that ships whatever it finds.

So every refusal below is driven over BOTH answers: a tree that passes
and a tree that does not. A check whose inputs cannot reach both
branches tests nothing about the branch, which is the failure this
project has now met more times than any other.

THE FIRST RUN OF THIS DERIVER FOUND A REAL ONE. `experiment/step.py`
annotated a parameter with `operations.trace` under `TYPE_CHECKING`.
That import does not execute, so importing every module succeeded and
said nothing -- but `mypy` and `typing.get_type_hints()` would both have
broken for whoever installed the package. It is why `operations` ships,
and `test_the_import_check_reads_type_checking_blocks` is why it stays
found.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "release" / "provenance_pool"))

import build as release  # noqa: E402


# ------------------------------------------------ it derives at all --


def test_the_distribution_derives_and_its_own_suite_passes():
    """The claim a release makes is that the code works with nothing
    else on the path. Passing in the source tree is not evidence about
    that, so the deriver runs the suite in the DERIVED tree and this
    lock is what keeps that step from being quietly dropped."""
    with tempfile.TemporaryDirectory() as directory:
        facts = release.derive(pathlib.Path(directory) / "dist")
        assert facts["modules"] > 50
        assert facts["tests"] > 20
        assert "failed" not in facts["suite"]
        # a real count, not merely the word "passed" -- `0 passed` would
        # satisfy a substring check while having verified nothing
        passed = int(facts["suite"].split(" passed")[0].split()[-1])
        assert passed > 100, f"the derived suite ran almost nothing: {facts['suite']}"


def test_the_emitted_tree_carries_no_build_artefacts():
    """VERIFYING THE TREE IS WHAT DIRTIED IT. `copytree` refuses to carry
    `__pycache__` across, and then the verification step runs pytest
    inside the emitted tree and writes fresh bytecode there -- after the
    copy that was careful about it.

    Found by looking at the emitted directory rather than at the build
    log. The log said everything passed and was telling the truth about
    a tree that also held six `__pycache__` folders."""
    with tempfile.TemporaryDirectory() as directory:
        dest = pathlib.Path(directory) / "dist"
        release.derive(dest)
        assert list(dest.rglob("*.py")), "an empty tree would pass this vacuously"
        assert not list(dest.rglob("__pycache__")), "ships compiled bytecode"
        assert not list(dest.rglob("*.pyc")), "ships compiled bytecode"
        assert not list(dest.rglob(".pytest_cache")), "ships a test cache"


def test_every_shipped_package_is_actually_in_this_tree():
    for package in release.PACKAGES:
        assert (ROOT / package).is_dir(), f"declared but not here: {package}"


def test_what_is_left_out_is_listed_with_a_reason():
    """So a later reader can tell `left out deliberately` from
    `forgotten` -- the same courtesy the core identity surface extends
    to what it does not hash."""
    assert release.DELIBERATELY_OUTSIDE
    for what, why in release.DELIBERATELY_OUTSIDE.items():
        assert len(why) > 40, f"a reason that is not a reason: {what}"
    named = " ".join(release.DELIBERATELY_OUTSIDE)
    for excluded in ("core", "execution", "architecture", "api"):
        assert excluded in named, f"{excluded} ships or is unexplained"


def test_no_shipped_package_is_also_listed_as_left_out():
    """A package on both lists would mean the deriver's own account of
    itself contradicts what it does."""
    named = " ".join(release.DELIBERATELY_OUTSIDE)
    for package in release.PACKAGES:
        # word-boundary check: `experiment` must not match `experiments`
        assert f" {package}," not in named and f" {package} " not in named, (
            f"{package} both ships and is listed as excluded")


# --------------------------------------------------- it refuses -----


def _tree(directory, files):
    root = pathlib.Path(directory)
    for name, body in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return root


def test_the_import_check_passes_a_clean_tree_and_fails_a_dirty_one():
    """Driven both ways. A check that could only ever refuse would fail
    the real distribution too, and one that could only ever pass would
    be decorative."""
    with tempfile.TemporaryDirectory() as directory:
        root = _tree(directory, {
            f"{release.PACKAGES[0]}/__init__.py": "import json\nfrom typing import Tuple\n",
        })
        for package in release.PACKAGES[1:]:
            (root / package).mkdir()
            (root / package / "__init__.py").write_text("")
        release._check_imports(root)          # clean: must not raise

        (root / release.PACKAGES[0] / "leak.py").write_text(
            "from execution.engine import run\n")
        with pytest.raises(release.ReleaseRefusal) as caught:
            release._check_imports(root)
        assert "execution" in str(caught.value)
        assert "leak.py" in str(caught.value)


def test_the_import_check_reads_type_checking_blocks():
    """THE DEFECT THIS DERIVER FOUND ON ITS FIRST RUN. An annotation-only
    import does not execute, so importing every module proves nothing
    about it -- and it still breaks `mypy` and `get_type_hints()` for
    whoever installed the package."""
    with tempfile.TemporaryDirectory() as directory:
        root = _tree(directory, {
            f"{release.PACKAGES[0]}/annotated.py":
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from execution.engine import Engine\n",
        })
        for package in release.PACKAGES[1:]:
            (root / package).mkdir()
            (root / package / "__init__.py").write_text("")
        with pytest.raises(release.ReleaseRefusal):
            release._check_imports(root)


def test_a_file_that_does_not_parse_is_refused_rather_than_shipped():
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "broken.py"
        with pytest.raises(release.ReleaseRefusal):
            release._internal_imports("def (:\n", path)


def test_machine_paths_are_refused_and_a_clean_tree_is_not():
    """This tree currently has no machine path in the library layer.
    This check is what keeps that true rather than coincidental -- and
    the first person to find such a path otherwise would be a stranger
    running `pip install`."""
    with tempfile.TemporaryDirectory() as directory:
        root = _tree(directory, {"pkg/mod.py": "PATH = 'data/local.json'\n"})
        release._check_no_machine_paths(root)     # clean: must not raise

        (root / "pkg" / "bad.py").write_text("ROOT = '/home/user/notationsystems'\n")
        with pytest.raises(release.ReleaseRefusal) as caught:
            release._check_no_machine_paths(root)
        assert "/home/user" in str(caught.value)


def test_an_empty_test_selection_would_be_refused():
    """A released suite that selected nothing would report success
    having verified nothing. Driven by deriving from a tree whose
    `tests/` holds no eligible file."""
    with tempfile.TemporaryDirectory() as directory:
        fake_root = pathlib.Path(directory) / "src"
        for package in release.PACKAGES:
            (fake_root / package).mkdir(parents=True)
            (fake_root / package / "__init__.py").write_text("")
        (fake_root / "tests").mkdir()
        (fake_root / "tests" / "test_unrelated.py").write_text(
            "from execution.engine import run\n\ndef test_x(): pass\n")

        with pytest.raises(release.ReleaseRefusal) as caught:
            release.derive(pathlib.Path(directory) / "dist", root=fake_root)
        assert "verify nothing" in str(caught.value)


def test_a_failing_suite_in_the_derived_tree_is_refused():
    """THE GAP A MUTANT FOUND. Every other lock here exercises the happy
    path, where the derived suite passes -- so disabling the returncode
    check changed nothing observable and the mutant survived. Proving a
    refusal fires requires a tree where it SHOULD fire, and nothing but
    a deliberately failing suite provides one."""
    with tempfile.TemporaryDirectory() as directory:
        tree = pathlib.Path(directory) / "tree"
        (tree / "tests").mkdir(parents=True)
        (tree / "tests" / "test_fails.py").write_text(
            "def test_this_must_fail():\n    assert False, 'deliberate'\n")
        with pytest.raises(release.ReleaseRefusal) as caught:
            release._run_tests(tree)
        assert "does not pass" in str(caught.value)


def test_a_passing_suite_in_the_derived_tree_is_accepted():
    """The other direction, so the check is about the RESULT rather than
    about refusing everything it is handed."""
    with tempfile.TemporaryDirectory() as directory:
        tree = pathlib.Path(directory) / "tree"
        (tree / "tests").mkdir(parents=True)
        (tree / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
        assert "passed" in release._run_tests(tree)


def test_a_missing_declared_package_is_refused():
    with tempfile.TemporaryDirectory() as directory:
        empty = pathlib.Path(directory) / "src"
        empty.mkdir()
        with pytest.raises(release.ReleaseRefusal) as caught:
            release.derive(pathlib.Path(directory) / "dist", root=empty)
        assert "not in this tree" in str(caught.value)


#: Test files that MUST reach the release, because they are the locks on
#: behaviour the distribution ships. Declared, not inferred: there is no
#: structural signal that separates "this file is about a shipped
#: package" from "this file merely touches one", and guessing intent
#: from an import list would be the wrong kind of inference.
MUST_SHIP = (
    "test_numerics.py",              # the published correlation and variance
    "test_evidence_admission.py",    # the admission gate
    "test_replicate_join.py",        # the pairing recovery
    "test_evidence_identity.py",     # content-addressed identity
)

#: Deliberately NOT here: the chemistry gate suites. The gate itself
#: lives in `structures/`, which the distribution does not ship, so
#: their absence from the release is correct rather than a defect. Named
#: so a later reader does not "fix" it.


def test_the_locks_on_shipped_behaviour_actually_ship():
    """THE DEFECT THIS EXISTS FOR, and it was found by noticing a count.

    Prover checks were added to `test_numerics.py`. That file imports
    `evidence` and `materials`, both shipped -- but one import of
    `execution`, which is not, removed the WHOLE FILE from the release.
    The locks protecting the published correlation and variance stopped
    shipping, and nothing failed: the derived suite went from 48 files
    to 47 and 557 tests to 545. Only the count said so, and only because
    someone happened to read it.

    A test file is the unit the selection works on, so one stray import
    costs every lock in that file its place. This names the files whose
    absence would matter and fails with the reason rather than leaving
    it to a number nobody is watching."""
    selected = {path.name for path in release.selected_tests(ROOT)}
    present = {name for name in MUST_SHIP if (ROOT / "tests" / name).exists()}
    assert present, "none of the named files exist -- this test guards nothing"

    missing = present - selected
    assert not missing, (
        f"locks on shipped behaviour are excluded from the release: "
        f"{sorted(missing)}. Each covers a package the distribution ships; "
        f"check whether an import of an unshipped package was added to it.")


def test_test_selection_excludes_files_reaching_outside_the_distribution():
    """A test importing `execution` is not a test of this distribution,
    and shipping it would make the released suite fail for a reason the
    distribution cannot fix."""
    selected = {path.name for path in release.selected_tests(ROOT)}
    assert selected, "selecting nothing would pass this vacuously"

    stdlib = release._stdlib_names()
    allowed = set(release.PACKAGES)
    for name in selected:
        heads = release._internal_imports(
            (ROOT / "tests" / name).read_text(), ROOT / "tests" / name)
        internal = {h for h in heads if h not in stdlib and h != "pytest"}
        assert internal <= allowed, f"{name} reaches outside: {internal - allowed}"

    # and something WAS excluded -- otherwise the filter is a pass-through
    everything = {p.name for p in (ROOT / "tests").glob("test_*.py")}
    assert selected < everything, "the filter excluded nothing at all"


# ------------------------------------------------ the release files --


def test_the_licence_is_the_verbatim_apache_text():
    """Sourced from three independent copies in unrelated repositories
    that agree byte for byte, rather than transcribed. A licence is a
    legal document and a typo in one is not a cosmetic defect."""
    licence = (ROOT / "release" / "provenance_pool" / "template" / "LICENSE").read_text()
    assert "Apache License" in licence and "Version 2.0, January 2004" in licence
    assert "http://www.apache.org/licenses/" in licence
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in licence
    # the appendix placeholder is intact: the LICENSE ships verbatim and
    # the copyright lives in NOTICE, which is Apache's own guidance
    assert "Copyright [yyyy] [name of copyright owner]" in licence
    assert len(licence.splitlines()) == 202


def test_the_notice_names_the_copyright_holder_and_the_licence():
    """The COPYRIGHT LINE specifically, not merely the company name
    somewhere in the file. A mutant that deleted the holder from the
    copyright line survived an earlier version of this check, because
    the name also appears in the prose sentence below it -- a substring
    test over a whole file cannot tell those two apart."""
    notice = (ROOT / "release" / "provenance_pool" / "template" / "NOTICE").read_text()
    copyright_lines = [line.strip() for line in notice.splitlines()
                       if line.strip().startswith("Copyright")]
    assert copyright_lines, "NOTICE carries no copyright line at all"
    for line in copyright_lines:
        holder = line.removeprefix("Copyright").strip()
        # strip a leading year or year range, then require a real holder
        holder = holder.lstrip("0123456789-, ")
        assert len(holder) > 3, f"copyright line names no holder: {line!r}"
    assert "Apache License" in notice and "2.0" in notice


def test_the_packaging_declares_no_runtime_dependency():
    """The zero-dependency property is the distribution's main promise.
    Declared here, exercised by CI on four interpreters and three
    operating systems -- because a promise checked nowhere decays."""
    text = (ROOT / "release" / "provenance_pool" / "template" / "pyproject.toml").read_text()
    assert "dependencies = []" in text
    assert 'license = "Apache-2.0"' in text
    for package in release.PACKAGES:
        assert f'"{package}"' in text, f"{package} ships but is not packaged"


def test_the_readme_examples_name_only_shipped_packages():
    """A README example importing something the wheel does not contain
    fails for the reader on their first paste, which is the worst place
    to discover it."""
    readme = (ROOT / "release" / "provenance_pool" / "template" / "README.md").read_text()
    imported = {line.split()[1].split(".")[0]
                for line in readme.splitlines()
                if line.startswith("from ") or line.startswith("import ")}
    assert imported, "no example imports at all would pass this vacuously"
    assert imported <= set(release.PACKAGES), (
        f"README imports what the wheel does not ship: "
        f"{imported - set(release.PACKAGES)}")
