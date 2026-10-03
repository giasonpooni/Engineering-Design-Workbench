#!/usr/bin/env python3
"""Probe the derivation's refusal to read a dirty sibling.

A register that derives over an uncommitted working tree records a
commit that never contained what it read. That is a citation to a source
which does not say what it is quoted as saying, and it is worse than
recording a stale commit -- a stale one can at least be looked up.
"""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DERIVE = REPO / "architecture" / "derive_register.py"
SUITE = "tests/test_invariant_register.py"

MUTATIONS = [
    ("the dirtiness refusal is disabled entirely", DERIVE,
     lambda s: s.replace("        dirty = _uncommitted(root)\n        if dirty:",
                         "        dirty = _uncommitted(root)\n        if False:  # MUTANT"),
     "test_a_dirty_sibling_clone_is_refused_and_names_the_files"),
    ("a dirty tree reports clean, so nothing ever fires", DERIVE,
     lambda s: s.replace("    result = _git(path, \"status\", \"--porcelain\")",
                         "    return ()  # MUTANT\n    result = _git(path, \"status\", \"--porcelain\")"),
     "test_a_dirty_sibling_clone_is_refused_and_names_the_files"),
    ("the refusal stops naming which files differ", DERIVE,
     lambda s: s.replace('                f"{local_commit[:12]} -- {list(dirty[:5])}. A derivation over a "',
                         '                f"{local_commit[:12]}. A derivation over a "  # MUTANT'),
     "test_a_dirty_sibling_clone_is_refused_and_names_the_files"),
    ("dirtiness and staleness collapse into one message", DERIVE,
     lambda s: s.replace('                f"sibling, then derive.")',
                         '                f"sibling -- fetch first.")  # MUTANT'),
     "test_the_dirtiness_refusal_is_distinct_from_the_staleness_one"),
    ("the local check goes back behind the network call", DERIVE,
     lambda s: s.replace(
         '        dirty = _uncommitted(root)\n'
         '        if dirty:\n'
         '            raise DerivationError(\n'
         '                f"{label}: {len(dirty)} file(s) differ from its own HEAD "\n'
         '                f"{local_commit[:12]} -- {list(dirty[:5])}. A derivation over a "\n'
         '                f"DIRTY clone would record a commit that never contained what "\n'
         '                f"it read, which is worse than recording a stale one: a stale "\n'
         '                f"commit can at least be looked up. Commit or revert the "\n'
         '                f"sibling, then derive.")\n'
         '        remote_commit = _remote_head(root, branch)',
         '        remote_commit = _remote_head(root, branch)  # MUTANT: network first'),
     "test_the_dirtiness_refusal_is_distinct_from_the_staleness_one"),
]


def _compiles(path, source):
    if path.suffix != ".py":
        return ""
    try:
        compile(source, str(path), "exec")
    except SyntaxError as error:
        return f"does not parse: {error}"
    return ""


def _purge_cache():
    for cached in REPO.rglob("__pycache__"):
        for item in cached.glob("*.pyc"):
            item.unlink(missing_ok=True)


def main() -> int:
    print("=== MUTATION VERIFICATION: the dirty-sibling refusal ===")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    killed = malformed = 0
    for description, target, mutate, test_name in MUTATIONS:
        original = target.read_text()
        mutated = mutate(original)
        if mutated == original:
            print(f"  MALFORMED  {description:<52} (diff reached nothing)")
            malformed += 1
            continue
        problem = _compiles(target, mutated)
        if problem:
            print(f"  MALFORMED  {description:<52} ({problem})")
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
            print(f"  KILLED     {description:<52} -> {test_name}")
            killed += 1
        else:
            print(f"  SURVIVED   {description:<52} -> {test_name}")
    total = len(MUTATIONS)
    print(f"\n{killed}/{total} mutants killed by their named test"
          + (f" ({malformed} malformed)" if malformed else ""))
    return 0 if killed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
