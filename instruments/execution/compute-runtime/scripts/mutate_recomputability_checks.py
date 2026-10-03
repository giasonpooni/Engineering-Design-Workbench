#!/usr/bin/env python3
"""Probe the recomputability probe."""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
PROBE = REPO / "architecture" / "recomputability.py"
DECLARATION = REPO / "architecture" / "apparatus.yaml"
ARTIFACT = REPO / "architecture" / "exchange" / "recomputability.yaml"
SUITE = "tests/test_recomputability.py"

MUTATIONS = [
    ("a grade asserted without attempting anything", PROBE,
     lambda s: s.replace("        attempted=True,\n        succeeded=same,",
                         "        attempted=False,  # MUTANT\n        succeeded=same,"),
     "test_every_probe_actually_attempts_a_recomputation"),
    ("the failing demonstration reported as a success", PROBE,
     lambda s: s.replace("        succeeded=resolved is not None,",
                         "        succeeded=True,  # MUTANT"),
     "test_the_derivation_path_names_its_method_and_the_attempt_fails"),
    ("the derivation path graded self-contained", PROBE,
     lambda s: s.replace('        grade=NAMES_ITS_METHOD,\n        carries=carries,',
                         "        grade=SELF_CONTAINED,  # MUTANT\n        carries=carries,"),
     "test_both_grades_are_reachable_so_the_distinction_is_not_decorative"),
    ("the execution demonstration stops rebuilding from the record", PROBE,
     lambda s: s.replace("    decoded = {name: bytes.fromhex(value) for name, value in transmitted.items()}",
                         "    decoded = {name: value.encode() for name, value in transmitted.items()}  # MUTANT"),
     "test_the_execution_demonstration_can_fail_and_does_on_a_hollow_record"),
    ("the negative half dropped, making it a tautology again", PROBE,
     lambda s: s.replace("    return same and program_is_load_bearing",
                         "    return same  # MUTANT"),
     "test_the_execution_demonstration_can_fail_and_does_on_a_hollow_record"),
    ("the program stops being load-bearing in the identity", PROBE,
     lambda s: s.replace("    program_is_load_bearing = (\n"
                         "        ExecutionSpecification(**without_program).identity() != original.identity())",
                         "    program_is_load_bearing = True  # MUTANT"),
     "test_the_execution_demonstration_can_fail_and_does_on_a_hollow_record"),
    ("the unqualified claim restored to the declaration", DECLARATION,
     lambda s: s.replace("  is added here is that a computed result carries what it was computed\n  from.",
                         "  is added here is that a computed result carries what it was computed\n  from and can be recomputed by the party reading it."),
     "test_the_declaration_no_longer_claims_recomputation_unconditionally"),
    ("closing the gap demoted to a chore", DECLARATION,
     lambda s: s.replace("and it is a decision rather than a measurement.",
                         "and it is on the list."),
     "test_closing_the_gap_is_recorded_as_a_decision_not_a_todo"),
    ("the artifact starts claiming correctness", ARTIFACT,
     lambda s: s.replace("not that the computation was the right one to run",
                         "and that it was the right one to run"),
     "test_the_artifact_does_not_claim_a_self_contained_record_is_correct"),
]


def _compiles(path, source):
    if path.suffix in (".yaml", ".yml"):
        import yaml
        try:
            yaml.safe_load(source)
        except yaml.YAMLError as error:
            return str(error)[:120]
        return ""
    try:
        compile(source, str(path), "exec")
    except SyntaxError as error:
        return f"{error.msg} (line {error.lineno})"
    return ""


def _purge_cache(path):
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for stale in cache.glob(f"{path.stem}.*.pyc"):
            stale.unlink()


def run_one(target, path):
    _purge_cache(path)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-x", f"{SUITE}::{target}"],
        cwd=REPO, capture_output=True, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    return result.returncode != 0


def main():
    print("=== MUTATION VERIFICATION: the recomputability probe ===")
    verdicts = []
    for label, path, mutate, target in MUTATIONS:
        original = path.read_text()
        mutated = mutate(original)
        if mutated == original:
            print(f"  MALFORMED  {label:56} (diff reached nothing)")
            verdicts.append(("MALFORMED", label)); continue
        broken = _compiles(path, mutated)
        if broken:
            print(f"  MALFORMED  {label:56} (does not parse: {broken})")
            verdicts.append(("MALFORMED", label)); continue
        path.write_text(mutated)
        try:
            caught = run_one(target, path)
        finally:
            path.write_text(original)
        status = "KILLED" if caught else "SURVIVED"
        print(f"  {status:10} {label:56} -> {target}")
        verdicts.append((status, label))
    bad = [v for v in verdicts if v[0] != "KILLED"]
    print(f"\n{len(verdicts)-len(bad)}/{len(verdicts)} mutants killed by their named test")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
