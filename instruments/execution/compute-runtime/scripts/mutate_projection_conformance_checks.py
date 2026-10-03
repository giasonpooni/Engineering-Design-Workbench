#!/usr/bin/env python3
"""Probe the projection conformance probe."""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
PROBE = REPO / "architecture" / "projection_conformance.py"
ARTIFACT = REPO / "architecture" / "exchange" / "projection_conformance.yaml"
SUITE = "tests/test_projection_conformance.py"

MUTATIONS = [
    # -- the refusal is the point -------------------------------------------
    ("an uncovered projection passes silently", PROBE,
     lambda s: s.replace("    if uncovered:\n        raise ProjectionConformanceError(",
                         "    if False:  # MUTANT\n        raise ProjectionConformanceError("),
     "test_a_projection_the_probe_does_not_cover_is_a_refusal"),
    ("a probe for an absent module tolerated", PROBE,
     lambda s: s.replace("    if stale:\n        raise ProjectionConformanceError(",
                         "    if False:  # MUTANT\n        raise ProjectionConformanceError("),
     "test_a_probe_for_a_module_no_longer_in_the_tree_is_a_refusal"),
    ("a module excluded with no reason", PROBE,
     lambda s: s.replace('    "__init__": "package marker",',
                         '    "__init__": "",  # MUTANT'),
     "test_every_discovered_projection_is_probed_or_excluded_with_a_reason"),

    # -- the classifier's arms -----------------------------------------------
    ("every projection graded rebuildable", PROBE,
     lambda s: s.replace("    if not barrier_held:\n        return WRITES_UPSTREAM",
                         "    if False:  # MUTANT\n        return WRITES_UPSTREAM"),
     "test_all_three_verdicts_are_reachable_from_constructed_measurements"),
    ("a failed rebuild outranks a write", PROBE,
     lambda s: s.replace("    if not barrier_held:\n        return WRITES_UPSTREAM\n"
                         "    if not rebuilt_identically:\n        return NOT_REBUILDABLE",
                         "    if not rebuilt_identically:\n        return NOT_REBUILDABLE\n"
                         "    if not barrier_held:\n        return WRITES_UPSTREAM  # MUTANT"),
     "test_a_write_outranks_a_failed_rebuild"),

    # -- the barrier is measured ---------------------------------------------
    ("a backend barrier asserted as a literal again", PROBE,
     lambda s: s.replace("    return unchanged and takes_no_pool, first, second",
                         "    return True, first, second  # MUTANT"),
     "test_the_ir_barrier_fails_when_a_backend_mutates_its_input"),
    ("a mutated IR no longer breaks the barrier", PROBE,
     lambda s: s.replace("    unchanged = (ir.entities, ir.relations) == before",
                         "    unchanged = True  # MUTANT"),
     "test_the_ir_barrier_fails_when_a_backend_mutates_its_input"),
    ("the core projection allowed to alias canonical state", PROBE,
     lambda s: s.replace("    return projected.fields is version.state.fields",
                         "    return False  # MUTANT"),
     "test_the_core_projection_shares_no_mutable_reference_with_the_version"),

    # -- the canonical state must not be empty -------------------------------
    ("the probe runs over an empty canonical layer", PROBE,
     lambda s: s.replace("            return (PAPER_DOCUMENT, GITHUB_REPO_DOCUMENT)",
                         "            return ()  # MUTANT"),
     "test_the_canonical_state_the_probe_uses_is_not_empty"),
    ("the emptiness refusal removed", PROBE,
     lambda s: s.replace("    if not pool.all_referents() or not pool.all_claimed_relationships():",
                         "    if False:  # MUTANT"),
     "test_an_empty_canonical_layer_is_refused_rather_than_measured"),
    ("the fixture hand-minted again instead of acquired", PROBE,
     lambda s: s.replace("    findings, _failures = run_scout(_Fixtures(), DeterministicExtractor(), pool)",
                         "    findings, _failures = run_scout(_Fixtures(), DeterministicExtractor(), pool)\n"
                         "    _ = 'make_observation'  # MUTANT"),
     "test_the_canonical_layer_arrives_through_the_acquisition_seam"),
    ("the analysis subject hardcoded again", PROBE,
     lambda s: s.replace("    for referent in pool.all_referents():",
                         '    subject = MaterialQuestion(material_natural_key="alpha", property="mass")  # MUTANT\n'
                         "    for referent in ():"),
     "test_the_analysis_subject_is_discovered_not_hardcoded"),

    # -- the artifact ---------------------------------------------------------
    ("a uniform result presented as a guarantee", ARTIFACT,
     lambda s: s.replace("not a guarantee about the eighth",
                         "and a guarantee for any future one"),
     "test_the_artifact_states_that_a_uniform_result_is_not_a_guarantee"),
    ("the reason for measuring early dropped", ARTIFACT,
     lambda s: s.replace("cheap finding today", "thing to look at eventually"),
     "test_the_artifact_says_why_this_is_measured_before_the_infrastructure"),
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
    print("=== MUTATION VERIFICATION: projection conformance ===")
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
