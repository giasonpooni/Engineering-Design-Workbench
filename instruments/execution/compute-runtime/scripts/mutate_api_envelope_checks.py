#!/usr/bin/env python3
"""Probe the envelope's refusals and the coverage measurement."""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
ENVELOPE = REPO / "api" / "envelope.py"
COVERAGE = REPO / "architecture" / "plane_coverage.py"
ARTIFACT = REPO / "architecture" / "exchange" / "plane_coverage.yaml"
SUITES = ("tests/test_api_envelope.py", "tests/test_plane_coverage.py")

MUTATIONS = [
    # -- there is no third arm ---------------------------------------------
    ("a response that is neither grounded nor honest is admitted", ENVELOPE,
     lambda s: s.replace("        if not isinstance(self.grounding, (CanonicalReference, OperationalObservation)):",
                         "        if False:  # MUTANT"),
     "test_there_is_no_third_construction"),
    ("a reference without a proof root admitted", ENVELOPE,
     lambda s: s.replace("        if not self.proof_root:", "        if False:  # MUTANT"),
     "test_a_reference_without_a_proof_root_is_refused"),
    ("an observation with no limitations admitted", ENVELOPE,
     lambda s: s.replace("        if not self.limitations:", "        if False:  # MUTANT"),
     "test_an_observation_with_no_limitations_is_refused"),
    ("an observation that never says why it is not canonical", ENVELOPE,
     lambda s: s.replace("        if not self.not_canonical_because:",
                         "        if False:  # MUTANT"),
     "test_an_observation_must_say_why_it_is_not_canonical"),

    # -- never public canonical CRUD ----------------------------------------
    ("a read-only plane allowed to report a mutation", ENVELOPE,
     lambda s: s.replace("        if self.reports_mutation and not PLANES[self.plane]:",
                         "        if False:  # MUTANT"),
     "test_a_read_only_plane_cannot_report_a_mutation"),
    ("the tenant read plane made mutating", ENVELOPE,
     lambda s: s.replace("    TENANT_READ: False,", "    TENANT_READ: True,  # MUTANT"),
     "test_the_operator_plane_is_the_only_one_that_may"),
    ("an undeclared plane accepted", ENVELOPE,
     lambda s: s.replace("        if self.plane not in PLANES:", "        if False:  # MUTANT"),
     "test_every_declared_plane_is_in_the_table_and_no_others"),

    # -- the engine digest ---------------------------------------------------
    ("a response with no engine digest accepted", ENVELOPE,
     lambda s: s.replace("        if not self.engine_digest:", "        if False:  # MUTANT"),
     "test_a_response_without_an_engine_digest_is_refused"),

    # -- what it must NOT claim ---------------------------------------------
    ("a tenant field added that nothing enforces", ENVELOPE,
     lambda s: s.replace('    engine_digest: str = ""\n    reports_mutation: bool = False',
                         '    engine_digest: str = ""\n    tenant_id: str = ""  # MUTANT\n    reports_mutation: bool = False'),
     "test_the_envelope_makes_no_tenancy_claim"),
    ("the payload made mutable through the envelope", ENVELOPE,
     lambda s: s.replace('        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))',
                         '        object.__setattr__(self, "payload", dict(self.payload))  # MUTANT'),
     "test_the_payload_is_not_mutable_through_the_envelope"),

    # -- the coverage measurement --------------------------------------------
    ("the gap transcribed instead of measured", COVERAGE,
     lambda s: s.replace('            "present": len(present),\n            "absent": len(absent),',
                         '            "present": 61,  # MUTANT\n            "absent": 0,'),
     "test_the_gap_is_measured_not_transcribed"),
    ("a concept counted on both sides", COVERAGE,
     lambda s: s.replace('        "absent": {name: [] for name in every if not present.get(name)},',
                         '        "absent": {name: [] for name in every},  # MUTANT'),
     "test_every_named_concept_lands_in_exactly_one_side"),
    ("the unenforceable ones folded into the merely unbuilt", COVERAGE,
     lambda s: s.replace("    unenforceable = [name for name in LOAD_BEARING if name in absent]",
                         "    unenforceable = []  # MUTANT"),
     "test_the_unenforceable_ones_are_separated_from_the_merely_unbuilt"),
    ("the matcher's direction of failure no longer stated", ARTIFACT,
     lambda s: s.replace("LOWER", "some kind of"),
     "test_the_matcher_states_which_direction_it_fails_in"),
    ("the matcher returns a constant", COVERAGE,
     lambda s: s.replace("                if any(concept in name for name in names):",
                         "                if True:  # MUTANT"),
     "test_a_concept_that_exists_is_found_and_one_that_does_not_is_not"),
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


def _suite_for(target):
    for suite in SUITES:
        if f"def {target}(" in (REPO / suite).read_text():
            return suite
    raise SystemExit(f"no suite defines {target}")


def run_one(target, path):
    _purge_cache(path)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-x",
         f"{_suite_for(target)}::{target}"],
        cwd=REPO, capture_output=True, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    return result.returncode != 0


def main():
    print("=== MUTATION VERIFICATION: the envelope and the coverage ===")
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
