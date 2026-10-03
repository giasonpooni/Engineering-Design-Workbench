#!/usr/bin/env python3
"""Derive the `canonical-state` open-source distribution from this tree.

WHAT THIS SHIPS, AND WHY IT IS A SEPARATE DISTRIBUTION FROM
`provenance-pool`. This repository contains two programs that share
nothing. Measured, across every file in both: the twin compiler
(`core`, `morpho`, `backends`, `runtime`, `adapters`, `renderer`) and
the evidence platform (`evidence`, `scout`, ...) have ZERO imports in
either direction, and no production code outside the twin compiler
imports it at all -- not here, not in either sibling repository. Two
programs under one name would be one distribution claiming to be two
things, so they are derived separately.

WHAT THIS IS NOT. It is not a numerical or scientific library, and the
packaging deliberately does not say it is. Measured: the shipped
packages import no numeric module at all -- no `math`, no `statistics`,
nothing -- and the arithmetic in them is set difference, list
concatenation, SVG margins and token indices. `backends/simulation` and
`backends/neural` say so in their own docstrings: INTERFACE SHAPES
ONLY, no dynamics and no model. They are declared seams, and a seam that
implements nothing is the honest thing to ship as long as nobody calls
it an implementation.

What it IS: one immutable versioned canonical state, and every view of
it a derived projection that can never write back.

WHY A DERIVER AND NOT A DIRECTORY OF COPIED SOURCE. A MIRROR IS NOT A
SOURCE, and byte-identity is exactly what makes a mirror dangerous. The
same argument as `release/provenance_pool/build.py`, which see. The
packages named below are the source; the distribution is derived on
demand and never committed.

WHAT THIS REFUSES. The four refusals `provenance-pool` carries -- an
import outside the shipped set (measured by PARSING, because a source
grep tests spelling and a parse tests what the module does), a machine
path anywhere in the emitted tree, an empty test selection, and a suite
that does not pass IN THE DERIVED TREE -- plus one this distribution
needs and that one does not:

  * a browser asset referring to a file that does not ship is a
    REFUSAL. `renderer/index.html` resolves `three` through an importmap
    pointing at `./vendor/three.module.js`, vendored on purpose so the
    page has no runtime dependency on a CDN. Shipping the page without
    the file it names would emit something that fails on open, which is
    the same class of defect as a package that cannot import itself --
    just in a language the import check cannot see.

Usage:
    python3 release/canonical_state/build.py --out DIR   emit + verify
    python3 release/canonical_state/build.py --check     verify only
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import pathlib
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from typing import Dict, List, Sequence, Set, Tuple

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
TEMPLATE = HERE / "template"

#: The importable packages the distribution carries. DECLARED, not
#: globbed: a glob would adopt a new sibling the first time somebody
#: added one, and silently widening what ships is how a release acquires
#: a dependency nobody chose.
PACKAGES: Tuple[str, ...] = ("core", "morpho", "backends", "runtime", "adapters")

#: Directories of non-Python assets that ship whole. `renderer` is a
#: browser view of a projected state; it is not importable and carries
#: no Python, so the import check cannot see it and the asset check
#: below exists for it.
ASSET_DIRS: Tuple[str, ...] = ("renderer",)

#: Files matched here are never emitted, whatever directory they are in.
EXCLUDED = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")

DELIBERATELY_OUTSIDE: Dict[str, str] = {
    "evidence, scout, retrieval, materials, experiment, operations": (
        "the OTHER track, and its own distribution -- `provenance-pool`. "
        "Zero imports in either direction, measured over every file in "
        "both. Two programs under one name would be one distribution "
        "claiming to be two things"),
    "execution, structures, transformer, campaign, zk, crates": (
        "the proving substrate. It invokes external toolchains (SP1, "
        "Nexus, GROMACS) a user would have to install before anything "
        "ran, and nothing in the twin compiler imports any of it"),
    "architecture": (
        "cross-repository operational tooling. It measures THIS "
        "organisation's repositories and hardcodes sibling clone paths; "
        "outside here it would measure nothing"),
    "workbench, api": (
        "the evidence platform's presentation and plane contract. Not "
        "this program"),
    "renderer/vendor (kept, not cut)": (
        "three.js r160, MIT, vendored so the page has no runtime "
        "dependency on a CDN -- a deliberate choice this release "
        "preserves rather than undoes. It ships WITH its notices, and "
        "the asset check refuses the page if the file it names is "
        "absent. Stripping it to save 1.3 MB would emit a page that "
        "fails on open"),
}


class ReleaseRefusal(RuntimeError):
    """The distribution could not be emitted on evidence."""


def _stdlib_names() -> Set[str]:
    names = set(sys.stdlib_module_names)
    stdlib_dir = sysconfig.get_paths().get("stdlib")
    if stdlib_dir:
        for entry in pathlib.Path(stdlib_dir).glob("*"):
            if entry.suffix == ".py":
                names.add(entry.stem)
            elif entry.is_dir() and (entry / "__init__.py").exists():
                names.add(entry.name)
    return names


def _internal_imports(source: str, path: pathlib.Path) -> Set[str]:
    """Top-level module names this file imports, by PARSING it."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ReleaseRefusal(
            f"{path} does not parse ({error}). A distribution containing a "
            f"file that cannot be parsed would fail at import for whoever "
            f"installed it") from error
    heads: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            heads.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            heads.add(node.module.split(".")[0])
    return heads


def _python_files(root: pathlib.Path) -> List[pathlib.Path]:
    return [p for p in sorted(root.rglob("*.py"))
            if "__pycache__" not in p.parts]


def _is_clean(path: pathlib.Path) -> bool:
    """True when every internal import of `path` is a shipped package."""
    stdlib = _stdlib_names()
    heads = _internal_imports(path.read_text(errors="replace"), path)
    internal = {h for h in heads if h not in stdlib and h != "pytest"}
    return internal <= set(PACKAGES)


def support_files(root: pathlib.Path = REPO_ROOT) -> Tuple[pathlib.Path, ...]:
    """Pytest support the selected tests need, when it is clean enough to ship.

    Two kinds, both emitted into the derived `tests/`:

      * the repository's root `conftest.py`, which defines the two
        fixtures (`sample_schema`, `genesis_version`) that most of these
        tests take as arguments. Without it the derived suite does not
        fail -- it ERRORS at setup, 30 times, which reads as a broken
        release rather than a missing file;

      * non-test modules in `tests/`, such as `fixtures_time_series.py`.

    WHY THE SECOND KIND NEEDS THE SELECTION RULE CHANGED TOO. That rule
    keeps a test when its internal imports are all shipped packages. A
    test importing a helper from its own directory --
    `from tests.fixtures_time_series import ...` -- has an internal head
    of `tests`, which is not a package name, so the rule dropped it. A
    false rejection, and a silent one: the release would simply contain
    one fewer test and still report success. It cost
    `test_time_series_representation.py`, whose helper imports nothing
    but `core.canonical`.

    Both kinds are shipped only after checking they are clean. An
    allowance granted without that check would readmit exactly what the
    rule exists to exclude, and an unclean conftest would break the
    derived suite for a reason the distribution cannot fix -- which the
    suite run would then report as a refusal, correctly, but later and
    less clearly than here.
    """
    keep: List[pathlib.Path] = []
    conftest = root / "conftest.py"
    if conftest.is_file() and _is_clean(conftest):
        keep.append(conftest)
    for path in sorted((root / "tests").glob("*.py")):
        if path.name.startswith("test_"):
            continue
        if _is_clean(path):
            keep.append(path)
    return tuple(keep)


def selected_tests(root: pathlib.Path = REPO_ROOT) -> Tuple[pathlib.Path, ...]:
    """Test files whose every internal import is shipped.

    A test reaching for `evidence` or `execution` is not a test of this
    distribution; including it would make the released suite fail for a
    reason the distribution cannot fix.
    """
    helper_names = {p.stem for p in support_files(root)}
    allowed = set(PACKAGES)
    stdlib = _stdlib_names()
    keep: List[pathlib.Path] = []
    for path in sorted((root / "tests").glob("test_*.py")):
        source = path.read_text(errors="replace")
        heads = _internal_imports(source, path)
        internal = {h for h in heads if h not in stdlib and h != "pytest"}
        if "tests" in internal:
            # allowed only if every `tests.<name>` it reaches for is a
            # helper this release actually ships
            wanted = set(re.findall(r"from\s+tests\.(\w+)\s+import", source))
            wanted |= set(re.findall(r"import\s+tests\.(\w+)", source))
            if wanted and wanted <= helper_names:
                internal.discard("tests")
        if internal and internal <= allowed:
            keep.append(path)
    return tuple(keep)


def _check_imports(dest: pathlib.Path) -> None:
    allowed = set(PACKAGES)
    stdlib = _stdlib_names()
    offenders: List[str] = []
    for package in PACKAGES:
        for path in _python_files(dest / package):
            heads = _internal_imports(path.read_text(errors="replace"), path)
            for head in sorted(heads):
                if head in stdlib or head in allowed or head == "pytest":
                    continue
                offenders.append(f"{path.relative_to(dest)} imports {head!r}")
    if offenders:
        raise ReleaseRefusal(
            "the distribution imports code it does not ship:\n  "
            + "\n  ".join(offenders)
            + "\nA release that cannot import itself on a clean machine is "
              "not a release. Either ship what it needs or cut the import.")


def _check_no_machine_paths(dest: pathlib.Path) -> None:
    needles = ("/home/user", "/Users/", "notationsystems/notations-",
               "notationsystems/scientific-compute")
    offenders: List[str] = []
    for path in sorted(dest.rglob("*")):
        if not path.is_file() or path.suffix not in {
                ".py", ".toml", ".md", ".yml", ".yaml", ".html", ".json"}:
            continue
        if "vendor" in path.parts:
            continue   # a third party's file, not ours to rewrite
        text = path.read_text(errors="replace")
        for needle in needles:
            if needle in text:
                offenders.append(f"{path.relative_to(dest)} contains {needle!r}")
    if offenders:
        raise ReleaseRefusal(
            "the distribution carries paths from the machine that built it:\n  "
            + "\n  ".join(offenders)
            + "\nThese resolve to nothing on a user's machine, and the first "
              "person to find that would be a stranger running `pip install`.")


#: Relative paths an HTML asset points at. Covers the two forms this
#: renderer uses -- an importmap value and a src/href attribute.
_ASSET_REFERENCE = re.compile(
    r"""(?:"|')(\./[^"']+|[\w./-]+\.(?:js|css|json|png|svg))(?:"|')""")


def _check_assets_resolve(dest: pathlib.Path) -> None:
    """Every local file an emitted page names must be in the emitted tree.

    The import check reads Python. This reads the other language in the
    distribution, for the same reason: an artefact that names a file it
    did not ship fails for whoever opens it, and they find out first.
    """
    offenders: List[str] = []
    for directory in ASSET_DIRS:
        base = dest / directory
        if not base.is_dir():
            continue
        for page in sorted(base.rglob("*.html")):
            text = page.read_text(errors="replace")
            for reference in sorted(set(_ASSET_REFERENCE.findall(text))):
                if reference.startswith(("http://", "https://", "//")):
                    continue
                target = (page.parent / reference).resolve()
                if not target.exists():
                    offenders.append(
                        f"{page.relative_to(dest)} names {reference!r}, "
                        f"which is not in the emitted tree")
    if offenders:
        raise ReleaseRefusal(
            "an emitted page refers to a file that does not ship:\n  "
            + "\n  ".join(offenders)
            + "\nThe page would fail on open. This is the import check's "
              "defect in another language, and it fails the same way: the "
              "first person to find it is the one who installed it.")


def _declared_packages(dest: pathlib.Path) -> List[str]:
    """The package list `pyproject.toml` declares, read without a TOML
    parser so this works on any supported Python."""
    text = (dest / "pyproject.toml").read_text(errors="replace")
    match = re.search(r"\[tool\.setuptools\]\s*\npackages\s*=\s*\[(.*?)\]",
                      text, re.DOTALL)
    if not match:
        raise ReleaseRefusal(
            "pyproject.toml declares no [tool.setuptools] packages list, so "
            "what gets installed is whatever setuptools guesses")
    return sorted(re.findall(r'"([^"]+)"', match.group(1)))


def _actual_packages(dest: pathlib.Path) -> List[str]:
    """Every importable package in the emitted tree, subpackages included."""
    found: List[str] = []
    for package in PACKAGES + ASSET_DIRS:
        base = dest / package
        for directory in sorted(base.rglob("")):
            if not directory.is_dir() or "__pycache__" in directory.parts:
                continue
            if (directory / "__init__.py").exists():
                found.append(str(directory.relative_to(dest)).replace(os.sep, "."))
    return sorted(found)


def _check_packaging_covers_the_tree(dest: pathlib.Path) -> None:
    """What the packaging installs must be what the tree contains.

    THE DEFECT THIS EXISTS FOR, WHICH IS THIS PROJECT'S OLDEST SHAPE.
    The first `pyproject.toml` here listed the five top-level package
    names. `pip install .` then produced a distribution in which `core/`
    and `backends/` held nothing but `__init__.py`: `core.canonical`,
    `core.projection` and all four backend subpackages were simply
    absent, and every documented import failed.

    The derived suite passed throughout, and was telling the truth about
    the wrong artefact. It runs with `cwd` inside the emitted directory,
    so `.` is on `sys.path` and it imports the SOURCE TREE -- the one
    thing a user will never have. A CHECK THAT CANNOT FAIL WHERE THE
    DEFECT LIVES, again, and found only by installing the result and
    importing it from somewhere else.

    Compared both ways on purpose. A declared package missing from the
    tree ships a name that resolves to nothing; a tree package missing
    from the declaration is the defect above.
    """
    declared = set(_declared_packages(dest))
    actual = set(_actual_packages(dest))
    missing = sorted(actual - declared)
    phantom = sorted(declared - actual)
    if missing or phantom:
        lines = []
        if missing:
            lines.append(
                "in the tree but NOT declared, so `pip install` would drop "
                "them and every import of them would fail:\n    "
                + "\n    ".join(missing))
        if phantom:
            lines.append(
                "declared but NOT in the tree, so the packaging names "
                "something that does not exist:\n    "
                + "\n    ".join(phantom))
        raise ReleaseRefusal(
            "pyproject.toml and the emitted tree disagree about what ships.\n"
            + "\n".join(lines)
            + "\nThe derived suite cannot see this: it runs inside the "
              "emitted directory, so it imports the source tree rather than "
              "an installed copy.")


def _package_data_globs(dest: pathlib.Path) -> Dict[str, List[str]]:
    """The [tool.setuptools.package-data] table, read without a TOML parser."""
    text = (dest / "pyproject.toml").read_text(errors="replace")
    block = re.search(r"\[tool\.setuptools\.package-data\]\s*\n(.*?)(?=\n\[|\Z)",
                      text, re.DOTALL)
    if not block:
        return {}
    table: Dict[str, List[str]] = {}
    for line in block.group(1).splitlines():
        entry = re.match(r"\s*([\w.]+)\s*=\s*\[(.*?)\]", line)
        if entry:
            table[entry.group(1)] = re.findall(r'"([^"]+)"', entry.group(2))
    return table


def _check_assets_are_packaged(dest: pathlib.Path) -> None:
    """Every asset file must be carried by the packaging, not just present.

    THE DEFECT THIS EXISTS FOR, AND WHY THE EXISTING CHECKS ALL MISSED IT.
    `renderer/` was in the emitted tree, complete and self-consistent, and
    `_check_assets_resolve` confirmed the page's importmap resolved. Then
    `pip wheel .` produced 41 entries with NOT ONE under `renderer/`,
    because a wheel installs packages and a plain directory is dropped.
    The NOTICE that did install said the three.js notice "ships with it".
    It did not, which makes it a false statement about a third party's
    licence rather than a missing feature.

    `_check_packaging_covers_the_tree` could not see this: it compares
    DECLARED PACKAGES against ACTUAL PACKAGES, so it only ever examined
    the half of the tree made of Python. A check built for "the packaging
    omits part of the tree" that looks at one kind of part.
    """
    declared = set(_declared_packages(dest))
    globs = _package_data_globs(dest)
    offenders: List[str] = []
    for directory in ASSET_DIRS:
        base = dest / directory
        if not base.is_dir():
            continue
        if directory not in declared:
            offenders.append(
                f"{directory!r} is not in [tool.setuptools] packages, so a "
                f"wheel drops it entirely")
            continue
        patterns = globs.get(directory, [])
        if not patterns:
            offenders.append(
                f"{directory!r} is declared but has no package-data patterns, "
                f"so it installs as a bare __init__.py")
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix == ".py":
                continue
            relative = path.relative_to(base)
            if not any(fnmatch.fnmatch(str(relative), pattern)
                       for pattern in patterns):
                offenders.append(
                    f"{directory}/{relative} matches no package-data pattern "
                    f"{patterns}, so it would not be installed")
    if offenders:
        raise ReleaseRefusal(
            "the packaging does not carry files the distribution ships:\n  "
            + "\n  ".join(offenders)
            + "\nThe emitted tree is not the installed one. A file present "
              "here and absent from the wheel is exactly the gap the NOTICE "
              "and the README describe as shipping.")


def _manifest_covers(dest: pathlib.Path, relative: pathlib.PurePosixPath) -> bool:
    """Whether MANIFEST.in carries `relative` into the sdist."""
    manifest = dest / "MANIFEST.in"
    if not manifest.is_file():
        return False
    parts = relative.parts
    for line in manifest.read_text(errors="replace").splitlines():
        tokens = line.split()
        if not tokens or tokens[0].startswith("#"):
            continue
        directive, rest = tokens[0], tokens[1:]
        if directive == "include" and str(relative) in rest:
            return True
        if directive == "graft" and rest and parts[:1] == (rest[0],):
            return True
        if directive == "recursive-include" and len(rest) >= 2:
            root, patterns = rest[0], rest[1:]
            if parts[:1] == (root,) and any(
                    fnmatch.fnmatch(parts[-1], pattern) for pattern in patterns):
                return True
    return False


def _check_sdist_carries_the_suite(dest: pathlib.Path) -> None:
    """The sdist must contain everything its own suite needs to run.

    THE DEFECT, AND WHY NOTHING ELSE HERE COULD SEE IT. setuptools'
    default sdist rules pick up `tests/test_*.py` and NOT the support
    beside them. So the released sdist held all thirteen test modules
    and none of `conftest.py`, `fixtures_time_series.py` or
    `__init__.py`, and unpacking it and running `python -m pytest tests/`
    -- the command the README gives contributors -- failed at
    COLLECTION.

    Invisible from every direction already checked. The wheel is correct
    and ships no tests at all, by design. The emitted tree is correct.
    And `provenance-pool`'s sdist is correct -- but only because it has
    no test support files for the default rules to miss, which is
    accident rather than agreement.

    Checked statically against MANIFEST.in rather than by building,
    because building an sdist needs a newer setuptools than a deriver
    should require. CI builds it and runs the suite inside it; this is
    the part that can fail here.
    """
    if not (dest / "MANIFEST.in").is_file():
        raise ReleaseRefusal(
            "the distribution declares no MANIFEST.in, so what reaches the "
            "sdist is whatever setuptools guesses -- and its guess omits "
            "test support files while keeping the tests that need them")
    offenders: List[str] = []
    for directory in ("tests",) + ASSET_DIRS:
        base = dest / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = pathlib.PurePosixPath(path.relative_to(dest).as_posix())
            if not _manifest_covers(dest, relative):
                offenders.append(str(relative))
    if offenders:
        raise ReleaseRefusal(
            "MANIFEST.in does not carry files the sdist needs:\n  "
            + "\n  ".join(offenders)
            + "\nAn sdist whose own suite cannot collect is what `pip "
              "install --no-binary` and every distribution packager get.")


def _purge_bytecode(dest: pathlib.Path) -> None:
    """Verifying the tree is what dirties it -- pytest writes bytecode
    into the emitted tree after the copy that was careful about it."""
    for cached in dest.rglob("__pycache__"):
        shutil.rmtree(cached, ignore_errors=True)
    for stale in dest.rglob("*.pyc"):
        stale.unlink(missing_ok=True)


def _run_tests(dest: pathlib.Path) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider"],
        cwd=dest, capture_output=True, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    _purge_bytecode(dest)
    tail = (result.stdout or result.stderr).strip().splitlines()
    summary = tail[-1] if tail else "(no output)"
    if result.returncode != 0:
        raise ReleaseRefusal(
            f"the derived tree's own suite does not pass: {summary}\n"
            f"Passing in the source tree is not evidence about the derived "
            f"one -- the question a release answers is whether the code "
            f"works with nothing else on the path.\n\n"
            + "\n".join(tail[-25:]))
    return summary


def derive(dest: pathlib.Path, root: pathlib.Path = REPO_ROOT) -> Dict[str, object]:
    """Emit the distribution into `dest`, refusing rather than shipping
    something that cannot stand on its own."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for package in PACKAGES:
        source = root / package
        if not source.is_dir():
            raise ReleaseRefusal(
                f"declared package {package!r} is not in this tree. A "
                f"distribution derived from a surface that has moved is a "
                f"distribution of something else")
        shutil.copytree(source, dest / package, ignore=EXCLUDED)

    for directory in ASSET_DIRS:
        source = root / directory
        if not source.is_dir():
            raise ReleaseRefusal(
                f"declared asset directory {directory!r} is not in this tree")
        shutil.copytree(source, dest / directory, ignore=EXCLUDED)

    tests = selected_tests(root)
    if not tests:
        raise ReleaseRefusal(
            "no test file depends only on the shipped packages, so the "
            "released suite would verify nothing while reporting success")
    (dest / "tests").mkdir()
    helpers = support_files(root)
    for path in list(tests) + list(helpers):
        shutil.copyfile(path, dest / "tests" / path.name)

    for item in sorted(TEMPLATE.rglob("*")):
        if item.is_dir():
            continue
        target = dest / item.relative_to(TEMPLATE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)

    _check_imports(dest)
    _check_no_machine_paths(dest)
    _check_assets_resolve(dest)
    _check_packaging_covers_the_tree(dest)
    _check_assets_are_packaged(dest)
    _check_sdist_carries_the_suite(dest)
    summary = _run_tests(dest)
    shutil.rmtree(dest / ".pytest_cache", ignore_errors=True)
    _purge_bytecode(dest)

    return {
        "packages": list(PACKAGES),
        "modules": sum(len(_python_files(dest / p)) for p in PACKAGES),
        "lines": sum(len(f.read_text(errors="replace").splitlines())
                     for p in PACKAGES for f in _python_files(dest / p)),
        "tests": len(tests),
        "support": len(helpers),
        "suite": summary,
        "deliberately_outside": dict(DELIBERATELY_OUTSIDE),
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path,
                        help="emit the distribution here")
    parser.add_argument("--check", action="store_true",
                        help="derive into a temporary directory and verify")
    args = parser.parse_args(argv)

    if not args.out and not args.check:
        parser.error("pass --out DIR or --check")

    with tempfile.TemporaryDirectory() as scratch:
        dest = args.out.resolve() if args.out else pathlib.Path(scratch) / "dist"
        try:
            facts = derive(dest)
        except ReleaseRefusal as error:
            print(f"REFUSED\n\n{error}", file=sys.stderr)
            return 1
        print("=== canonical-state: derived and verified ===")
        print(f"  packages : {', '.join(facts['packages'])}")
        print(f"  modules  : {facts['modules']}")
        print(f"  lines    : {facts['lines']}")
        print(f"  tests    : {facts['tests']} files "
              f"(+{facts['support']} support) -- {facts['suite']}")
        print("\n  not shipped, each for a stated reason:")
        for what, why in sorted(facts["deliberately_outside"].items()):
            print(f"    {what}\n      {why}")
        if args.out:
            print(f"\n  wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
