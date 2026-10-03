#!/usr/bin/env python3
"""Derive the `provenance-pool` open-source distribution from this tree.

WHY THIS IS A DERIVER AND NOT A DIRECTORY OF COPIED SOURCE. The obvious
way to prepare a release is to copy the packages into `release/` and
commit them. That would put two byte-identical copies of nine thousand
lines in one repository, and the moment one of them was edited the other
would be silently wrong -- with nothing recomputing the difference.

This project has a name for that: A MIRROR IS NOT A SOURCE, and
byte-identity is exactly what makes a mirror dangerous. The rule was
found at file scale (an emitted register re-read as its own input) and
again at repository scale (eleven third-party repos under our own GitHub
org, where the URL agreed with the claim). Committing a second copy of
`evidence/` here would be the same defect a third time, introduced
deliberately, by the party that wrote the rule.

So the release is a PROJECTION. The packages named in `PACKAGES` below
are the source, here in this repository; the distribution is derived
from them on demand and is never committed. The only things stored in
this directory are the parts that exist ONLY in the release: licence,
notices, packaging metadata, README, CI.

WHAT THIS REFUSES, AND WHY EACH REFUSAL IS HERE. A build script that
emits whatever it finds would let a release ship code that cannot run
outside this machine -- and the failure would be discovered by a
stranger, on their first `pip install`, which is the worst possible
place to find it. So:

  * a module importing anything outside the declared packages and the
    standard library is a REFUSAL, not a warning. Measured by AST, not
    by grepping for `import`: a source grep tests spelling, a parse
    tests what the module actually does.

  * a machine path (`/home/user`, `/Users/`) anywhere in the emitted
    tree is a REFUSAL. This tree currently has none in the library
    layer, and this check is what keeps that true rather than
    coincidental.

  * an empty test selection is a REFUSAL. A release whose test suite
    selected nothing would report success having verified nothing --
    the vacuous-pass failure this project has met repeatedly.

  * a test suite that does not pass in the DERIVED tree is a REFUSAL.
    Passing here is not evidence about there: the whole question a
    release answers is whether the code works with nothing else on the
    path, and only running it there can answer it.

Usage:
    python3 release/provenance_pool/build.py --out DIR   emit + verify
    python3 release/provenance_pool/build.py --check     verify only
"""

from __future__ import annotations

import argparse
import ast
import os
import pathlib
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from typing import Dict, List, Sequence, Set, Tuple

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
TEMPLATE = HERE / "template"

#: The packages the distribution carries. DECLARED, not globbed: a glob
#: would adopt a new sibling package the first time somebody added one,
#: and silently widening what ships is how a release acquires a
#: dependency nobody chose.
PACKAGES: Tuple[str, ...] = (
    "evidence", "scout", "retrieval", "materials", "experiment", "operations",
)

#: Packages that exist in this repository and deliberately do NOT ship,
#: each with the reason -- so a later reader can tell "left out on
#: purpose" from "forgotten", which is the same courtesy the core
#: identity surface extends to what it does not hash.
DELIBERATELY_OUTSIDE: Dict[str, str] = {
    "core, morpho, backends, runtime, adapters, renderer": (
        "the OTHER track. Zero imports in either direction, measured -- "
        "a separate project sharing this repository, and shipping it "
        "here would be one distribution claiming to be two things"),
    "core, morpho (again): the TYPE_CHECKING subtlety": (
        "the import check deliberately reads TYPE_CHECKING blocks too, "
        "and that is not overreach. Such an import does not break at "
        "runtime -- which is exactly why an import test misses it -- but "
        "it DOES break `mypy` and `typing.get_type_hints()` for whoever "
        "installed the package. It found one on its first run: "
        "`experiment/step.py` annotating with `operations.trace`, which "
        "is why `operations` ships"),
    "execution, structures, transformer, campaign": (
        "they invoke external toolchains (SP1, Nexus, GROMACS) that a "
        "user would have to install before anything ran. A first "
        "`pip install` that cannot execute is worse than a smaller "
        "package that can"),
    "architecture": (
        "cross-repository operational tooling. It hardcodes sibling "
        "clone paths on one machine and measures THIS organisation's "
        "repositories; outside here it would measure nothing"),
    "api": (
        "the plane contract is declared but its tenancy, auth and "
        "transport concepts do not exist in this tree. Shipping an "
        "envelope that names a tenant nothing enforces would read as "
        "isolated while isolating nothing"),
}


class ReleaseRefusal(RuntimeError):
    """The distribution could not be emitted on evidence."""


def _stdlib_names() -> Set[str]:
    names = set(sys.stdlib_module_names)
    # `sys.stdlib_module_names` omits nothing we rely on, but a vendored
    # or frozen build can differ; the path check is a cheap second view.
    stdlib_dir = sysconfig.get_paths().get("stdlib")
    if stdlib_dir:
        for entry in pathlib.Path(stdlib_dir).glob("*"):
            if entry.suffix == ".py":
                names.add(entry.stem)
            elif entry.is_dir() and (entry / "__init__.py").exists():
                names.add(entry.name)
    return names


def _internal_imports(source: str, path: pathlib.Path) -> Set[str]:
    """Top-level module names this file imports, by PARSING it.

    A source grep tests spelling; a parse tests what the module does.
    That distinction has caught real defects in this project, including
    a check evaded by `getattr` plus a split string literal.
    """
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


def selected_tests(root: pathlib.Path = REPO_ROOT) -> Tuple[pathlib.Path, ...]:
    """Test files whose every internal import is a shipped package.

    A test that reaches for `execution` or `core` is not a test of this
    distribution; including it would make the released suite fail for a
    reason the distribution cannot fix.
    """
    allowed = set(PACKAGES)
    stdlib = _stdlib_names()
    keep: List[pathlib.Path] = []
    for path in sorted((root / "tests").glob("test_*.py")):
        heads = _internal_imports(path.read_text(errors="replace"), path)
        internal = {h for h in heads if h not in stdlib and h != "pytest"}
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
        if not path.is_file() or path.suffix not in {".py", ".toml", ".md", ".yml", ".yaml"}:
            continue
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


def _purge_bytecode(dest: pathlib.Path) -> None:
    """Verifying the tree is what dirties it.

    `shutil.copytree` correctly refuses to carry `__pycache__` across --
    and then `_run_tests` runs pytest INSIDE the emitted tree and writes
    fresh bytecode there, after the copy that was careful about it. The
    result shipped compiled artefacts of the host interpreter, which
    another Python would ignore at best and trip over at worst.

    Found by looking at the emitted tree rather than at the build log:
    the log said everything passed, and it was telling the truth about a
    directory that also contained six `__pycache__` folders."""
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
        shutil.copytree(source, dest / package,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    tests = selected_tests(root)
    if not tests:
        raise ReleaseRefusal(
            "no test file depends only on the shipped packages, so the "
            "released suite would verify nothing while reporting success")
    (dest / "tests").mkdir()
    for path in tests:
        shutil.copyfile(path, dest / "tests" / path.name)

    for item in sorted(TEMPLATE.rglob("*")):
        if item.is_dir():
            continue
        target = dest / item.relative_to(TEMPLATE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)

    _check_imports(dest)
    _check_no_machine_paths(dest)
    summary = _run_tests(dest)
    shutil.rmtree(dest / ".pytest_cache", ignore_errors=True)
    _purge_bytecode(dest)

    return {
        "packages": list(PACKAGES),
        "modules": sum(len(_python_files(dest / p)) for p in PACKAGES),
        "lines": sum(len(f.read_text(errors="replace").splitlines())
                     for p in PACKAGES for f in _python_files(dest / p)),
        "tests": len(tests),
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
        print("=== provenance-pool: derived and verified ===")
        print(f"  packages : {', '.join(facts['packages'])}")
        print(f"  modules  : {facts['modules']}")
        print(f"  lines    : {facts['lines']}")
        print(f"  tests    : {facts['tests']} files -- {facts['suite']}")
        print("\n  not shipped, each for a stated reason:")
        for what, why in sorted(facts["deliberately_outside"].items()):
            print(f"    {what}\n      {why}")
        if args.out:
            print(f"\n  wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
