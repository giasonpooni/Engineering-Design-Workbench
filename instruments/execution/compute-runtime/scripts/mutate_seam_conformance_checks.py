#!/usr/bin/env python3
"""Probe the engine-seam conformance battery.

The seam's whole promise is that any engine behind it observes one
contract about identity, refusal and determinism. A battery that cannot
notice a violated contract is a claim, not a check.
"""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SPEC = REPO / "execution" / "specification.py"
SUITE = "tests/test_engine_seam_conformance.py"

MUTATIONS = [
    # -- identity must be the SPECIFICATION's --------------------------------
    ("the program identity becomes a constant, so engines collide", SPEC,
     lambda s: s.replace(
         '        return commit_hex(PROGRAM_TAG, [self.program])',
         '        return commit_hex(PROGRAM_TAG, [b"same-for-everyone"])  # MUTANT'),
     "test_two_engines_can_never_be_mistaken_for_one_another"),
    ("the input identity ignores the payload", SPEC,
     lambda s: s.replace(
         '        return commit_hex(INPUT_TAG, [self.input_payload])',
         '        return commit_hex(INPUT_TAG, [b""])  # MUTANT'),
     "test_a_different_input_is_a_different_specification"),
    ("the specification identity drops its input", SPEC,
     lambda s: s.replace(
         "        return commit_hex(\n"
         "            SPECIFICATION_TAG, [self.program, self.configuration, self.input_payload]\n"
         "        )",
         "        return commit_hex(  # MUTANT\n"
         "            SPECIFICATION_TAG, [self.program, self.configuration]\n"
         "        )"),
     "test_a_different_input_is_a_different_specification"),
    ("the specification identity ignores the program", SPEC,
     lambda s: s.replace(
         "        return commit_hex(\n"
         "            SPECIFICATION_TAG, [self.program, self.configuration, self.input_payload]\n"
         "        )",
         "        return commit_hex(  # MUTANT\n"
         "            SPECIFICATION_TAG, [self.configuration, self.input_payload]\n"
         "        )"),
     "test_the_same_input_under_a_different_program_is_a_different_request"),
    ("the specification identity ignores the configuration", SPEC,
     lambda s: s.replace(
         "        return commit_hex(\n"
         "            SPECIFICATION_TAG, [self.program, self.configuration, self.input_payload]\n"
         "        )",
         "        return commit_hex(  # MUTANT\n"
         "            SPECIFICATION_TAG, [self.program, self.input_payload]\n"
         "        )"),
     "test_the_same_program_under_a_different_configuration_is_a_different_request"),

    # -- the battery must not be able to run on nothing ----------------------
    ("the engine list is empty, so every parameterised check vanishes",
     REPO / SUITE,
     lambda s: s.replace("ENGINES = _available()", "ENGINES = []  # MUTANT"),
     "test_at_least_one_engine_is_present_and_the_battery_is_not_vacuous"),
    # NOT LISTED: neutering the collision assertion itself (e.g. deduping
    # `programs` before comparing its length). That mutant is ill-posed
    # rather than surviving: it makes a test vacuous and then asks THAT
    # SAME TEST to notice, which no test can do. Killing it would need a
    # separate meta-test asserting the collision check operates on more
    # than one element -- testing the test, which is a regress with no
    # natural stopping point. What actually protects the check is
    # structural: it is skipped below two engines, and its assertion
    # compares a set's size to a list's, which says nothing at all
    # unless there are at least two entries to compare.
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
    print("=== MUTATION VERIFICATION: the engine-seam contract ===")
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
