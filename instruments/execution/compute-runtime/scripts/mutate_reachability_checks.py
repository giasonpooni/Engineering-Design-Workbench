"""Probe the reachability probe.

A probe whose job is to refuse to manufacture a measurement has to be
shown refusing. Each mutation makes it manufacture one; the named test
must catch it.
"""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
PROBE = REPO / "scripts" / "chemistry_reachability.py"
ARTIFACT = REPO / "architecture" / "chemistry_reachability.yaml"
PIPELINE = REPO / "scout" / "pipeline.py"
INGEST = REPO / "structures" / "ingest.py"
CONTRACT = REPO / "architecture" / "verticals" / "chemistry" / "vertical.yaml"
REGISTRY = REPO / "architecture" / "invariants.yaml"
THREE_GATE = REPO / "scripts" / "ingest_reachability_probe.py"

MUTATIONS = [
    ("a dead gate passes as live", PROBE,
     lambda s: s.replace(
         '    return "DEAD", "the violating payload was ACCEPTED"',
         '    return "LIVE", "the violating payload was ACCEPTED"  # MUTANT'),
     "test_the_liveness_classifier_reports_a_dead_gate_as_dead"),
    ("a misaimed plant counts as a measurement", PROBE,
     lambda s: s.replace(
         '        return "MALFORMED_PLANT", f"right type, wrong refusal: {str(error)[:100]}"',
         '        return "LIVE", ""  # MUTANT'),
     "test_the_liveness_classifier_reports_a_misaimed_plant_as_malformed"),
    ("a wrong-TYPE plant counts as a measurement", PROBE,
     lambda s: s.replace(
         '        return "MALFORMED_PLANT", f"{type(error).__name__}: {str(error)[:100]}"',
         '        return "LIVE", ""  # MUTANT'),
     "test_the_liveness_classifier_reports_a_misaimed_plant_as_malformed"),
    ("the second refusal of the two-refusal guard is dropped", PROBE,
     lambda s: s.replace(
         '    Code("STRUCTURE_STRING_ONLY", "structures.substance.assert_distribution_identity",',
         '    Code("DROPPED_BY_MUTANT", "structures.substance.assert_distribution_identity",'),
     "test_both_refusals_of_the_two_refusal_guard_are_enumerated"),
    ("an unreachable verdict with no traced termination", PROBE,
     lambda s: s.replace(
         '            code.blocked_by["acquisition"] = (\n'
         '                "no module under scout/ imports structures/ at all,',
         '            code.blocked_by["acquisition"] = ""  # MUTANT\n'
         '            _unused = (\n'
         '                "no module under scout/ imports structures/ at all,'),
     "test_an_unreachable_verdict_carries_a_traced_termination"),
    ("a vacuous plant reported as a termination", PROBE,
     lambda s: s.replace(
         '        "terminated": admitted > 0 and chemistry_refusals == 0,',
         '        "terminated": chemistry_refusals == 0,  # MUTANT'),
     "test_a_plant_that_lands_nothing_is_not_counted_as_terminated"),
    ("a refused path reported as a termination", PROBE,
     lambda s: s.replace(
         '        "terminated": admitted > 0 and chemistry_refusals == 0,',
         '        "terminated": admitted > 0,  # MUTANT'),
     "test_a_plant_that_lands_nothing_is_not_counted_as_terminated"),
    ("the remaining silences folded into the reachable count", ARTIFACT,
     lambda s: s.replace('"reachable_from_any_entry": 15',
                         '"reachable_from_any_entry": 20'),
     "test_the_artifact_reports_silences_as_silences_not_as_clean"),
    ("the silences dropped from the summary entirely", ARTIFACT,
     lambda s: s.replace('"not_expressible_as_a_document": 5',
                         '"not_expressible_as_a_document": 0'),
     "test_the_artifact_reports_silences_as_silences_not_as_clean"),
    ("a code admitted despite arriving, reported as reachable", ARTIFACT,
     lambda s: s.replace('"admitted_despite_arriving": 0',
                         '"admitted_despite_arriving": 3'),
     "test_the_artifact_reports_silences_as_silences_not_as_clean"),
    ("the superseded import trace restored as the verdict", ARTIFACT,
     lambda s: s.replace('"acquisition_trace_superseded"', '"acquisition"'),
     "test_the_artifact_carries_the_ingest_measurement_not_the_import_trace"),
    ("a per-invariant count that no gate id declares", ARTIFACT,
     lambda s: s.replace('"quantity_is_typed": 5', '"quantity_typed": 5'),
     "test_the_artifact_carries_the_ingest_measurement_not_the_import_trace"),
    ("the alias correction reduced to a note without its cost", ARTIFACT,
     lambda s: s.replace('"measured_cost": "the derived register holds 58',
                         '"measured_cost": "no measurable cost; the register holds 9'),
     "test_the_artifact_records_the_alias_correction"),
    ("the bytecode collision recorded without the fix that answers it", ARTIFACT,
     lambda s: s.replace("Applied to scripts/mutate_register_checks.py without",
                         "Not applied elsewhere without"),
     "test_the_artifact_records_the_two_battery_defects"),
    # -- THE WIRING ITSELF -----------------------------------------------
    #
    # The probe measures whether a gate is reached. These mutate the
    # thing that makes it reached. Each one leaves the gate CORRECT and
    # the suite otherwise green -- which is exactly the state the
    # vertical was already in when it measured 0 of 20 reachable.
    ("the gate result is computed and discarded", PIPELINE,
     lambda s: s.replace("            if failing:",
                         "            if False and failing:  # MUTANT"),
     "test_the_same_document_is_refused_once_gated"),
    ("a refused candidate is dropped instead of held", PIPELINE,
     lambda s: s.replace("                if quarantine is not None:\n"
                         "                    quarantine.hold(",
                         "                if False:  # MUTANT\n"
                         "                    quarantine.hold("),
     "test_quarantine_retains_the_payload"),
    ("the refusal loses its invariant id", PIPELINE,
     lambda s: s.replace('AdmissionError("ExtractionCandidate", invariant_id,',
                         'AdmissionError("ExtractionCandidate", "REJECTED",  # MUTANT'),
     "test_refusal_carries_the_invariant_id"),
    ("the refusal is filed under the wrong stage", PIPELINE,
     lambda s: s.replace('stage="content_gate",', 'stage="extraction",  # MUTANT'),
     "test_refusal_names_its_stage"),
    ("gates run for every caller, not the ones that ask", PIPELINE,
     lambda s: s.replace("    content_gates: Tuple[ContentGate, ...] = (),",
                         "    content_gates: Tuple[ContentGate, ...] = (__import__('structures.ingest', fromlist=['x']).chemistry_content_gate,),  # MUTANT"),
     "test_run_scout_without_gates_is_unchanged"),
    ("the vertical stops supplying its gate", INGEST,
     lambda s: s.replace("content_gates=(chemistry_content_gate,),",
                         "content_gates=(),  # MUTANT"),
     "test_the_same_document_is_refused_once_gated"),
    ("a quantity refusal filed under the property invariant", INGEST,
     lambda s: s.replace(
         "    return QUANTITY_TYPED if any(f in message for f in _QUANTITY_REFUSALS) else PROPERTY_CONTEXT",
         "    return PROPERTY_CONTEXT  # MUTANT"),
     "test_a_quantity_refusal_is_not_filed_under_the_property_invariant"),
    ("a property refusal filed under the quantity invariant", INGEST,
     lambda s: s.replace(
         "    return QUANTITY_TYPED if any(f in message for f in _QUANTITY_REFUSALS) else PROPERTY_CONTEXT",
         "    return QUANTITY_TYPED  # MUTANT"),
     "test_a_context_refusal_is_not_filed_under_the_quantity_invariant"),
    # `else:` is what makes applicability conditional on a well-formed
    # block. Turning it into `if True:` runs both gates over the same
    # payload, so one defect is counted against two invariants.
    ("applicability double-counted against a malformed block", INGEST,
     lambda s: s.replace("            failing.append(METHOD_BLOCK)\n        else:",
                         "            failing.append(METHOD_BLOCK)\n        if True:  # MUTANT"),
     "test_applicability_runs_only_on_a_well_formed_block"),
    ("the gate refuses everything it does not recognise", INGEST,
     lambda s: s.replace("    failing = []", "    failing = [PROPERTY_CONTEXT]  # MUTANT"),
     "test_a_non_chemistry_candidate_passes_untouched"),
    ("a gate id that no registry declares", INGEST,
     lambda s: s.replace('QUANTITY_TYPED = "quantity_is_typed"',
                         'QUANTITY_TYPED = "quantity_typed"  # MUTANT'),
     "test_the_five_ids_are_the_verticals_own_invariants"),
    ("the alias reintroduced under a second name", REGISTRY,
     lambda s: s.replace("  - id: no_point_identity_for_distributions",
                         "  - id: distribution_has_no_point_identity  # MUTANT"),
     "test_the_five_ids_are_the_verticals_own_invariants"),
    # -- the three-gate probe, which had no test for several phases ---
    ("a misaimed plant reported as an unreached gate", THREE_GATE,
     lambda s: s.replace("    if codes:\n        return MALFORMED",
                         "    if False:  # MUTANT\n        return MALFORMED"),
     "test_a_plant_refused_by_another_gate_is_malformed_not_unreached"),
    ("the plants reverted to a format that cannot isolate a gate", THREE_GATE,
     lambda s: s.replace('"PROPERTY: density | method=pycnometry | conditions=T:298 "',
                         '"PROPERTY: density | "  # MUTANT'),
     "test_each_plant_isolates_the_gate_it_names"),
    ("the probe run against the ungated path again", THREE_GATE,
     lambda s: s.replace(
         "    return ingest_documents(_PlantedSource(raw), PropertyExtractor(), pool)",
         "    return run_scout(_PlantedSource(raw), PropertyExtractor(), pool)  # MUTANT"),
     "test_the_three_gate_probe_reaches_both_gates_a_plant_can_violate"),
    # -- the vertical contract's DECLARED POSITION ---------------------
    ("the contract claims a gate the code cannot emit", CONTRACT,
     lambda s: s.replace("    - applicability_domain_declared\n",
                         "    - applicability_domain_declared\n    - identity_policy_declared\n"),
     "test_the_contract_claims_exactly_the_gates_the_code_can_emit"),
    ("the LIVE-but-unreachable gate quietly promoted to reachable", CONTRACT,
     lambda s: s.replace("  gate_LIVE_but_not_reachable_here:\n    identity_policy_declared:",
                         "  gate_LIVE_but_not_reachable_here: {}\n  _retired:\n    identity_policy_declared:"),
     "test_the_gate_that_is_live_but_unreachable_is_named_and_kept_apart"),
    ("the contract points at an entry point that does not wire the gates", CONTRACT,
     lambda s: s.replace("  entry_point: structures.ingest.ingest_documents",
                         "  entry_point: scout.pipeline.run_scout"),
     "test_the_contract_names_an_entry_point_that_exists_and_wires_the_gates"),
    ("the generic path takes on a domain dependency", PIPELINE,
     lambda s: s.replace("from scout.interface import Extractor, SourceAdapter",
                         "from scout.interface import Extractor, SourceAdapter\nimport structures.ingest  # MUTANT"),
     "test_the_contracts_declared_direction_matches_the_import_graph"),
    ("the corrections quietly dropped", ARTIFACT,
     lambda s: s.replace('"found": "a VACUOUS confirmation, on the second run"',
                         '"found": "nothing worth recording"'),
     "test_the_artifact_records_its_own_two_corrections"),
]


#: Which suite holds which target. A mutation aimed at a test in another
#: file silently passes as "not caught" otherwise -- measuring the
#: dispatch, not the check.
SUITES = ("tests/test_chemistry_reachability.py", "tests/test_process_decisions.py",
          "tests/test_chemistry_ingest.py")


def _suite_for(target):
    for suite in SUITES:
        if f"def {target}(" in (REPO / suite).read_text():
            return suite
    raise SystemExit(f"no suite defines {target}")


#: A MUTANT THAT DOES NOT COMPILE IS NOT A MUTANT. It can only ever be
#: "killed" by an import error, which is a fact about the edit and not
#: about the named test -- the malformed-plant problem, in the battery
#: rather than in the probe it verifies. Found by writing one: a
#: `stage="extraction"  # MUTANT` replacement commented out the trailing
#: comma, and the run that followed proved nothing either way.
#:
#: YAML targets are parsed as YAML for the same reason.
def _compiles(path, source):
    if path.suffix == ".yaml":
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


#: A MUTANT IS NOT IDENTIFIED BY ITS SIZE AND TIMESTAMP. CPython
#: validates a cached `.pyc` against `(source_mtime, source_size)`, and
#: two mutants of the same file written in the same second with the same
#: byte length are INDISTINGUISHABLE to that check -- the second run
#: silently executes the FIRST one's bytecode.
#:
#: That is not hypothetical. Two mutations of `scout/pipeline.py` here
#: -- "the refusal loses its invariant id" and "the refusal is filed
#: under the wrong stage" -- both change the file by exactly +8 bytes.
#: The battery reported the second as SURVIVED across repeated runs
#: while a direct run killed it in 0.07s: the stage mutant never
#: executed, and another mutant's PASS was printed under its label.
#:
#: The battery was reporting a result for an edit it had not run. So:
#: no bytecode is written during a battery run, and any cache entry for
#: the mutated file is removed before the run. Both, not either --
#: suppressing the write does not invalidate a stale entry already on
#: disk from an ordinary test run.
def _purge_cache(path):
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for stale in cache.glob(f"{path.stem}.*.pyc"):
            stale.unlink()


def run_one(target, path=None):
    if path is not None:
        _purge_cache(path)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-x",
         f"{_suite_for(target)}::{target}"],
        cwd=REPO, capture_output=True, text=True, env=environment)
    return result.returncode != 0


def main():
    print("=== MUTATION VERIFICATION: the probe's own refusals ===")
    verdicts = []
    for label, path, mutate, target in MUTATIONS:
        original = path.read_text()
        mutated = mutate(original)
        if mutated == original:
            print(f"  MALFORMED  {label:48} (diff reached nothing)")
            verdicts.append(("MALFORMED", label)); continue
        broken = _compiles(path, mutated)
        if broken:
            print(f"  MALFORMED  {label:48} (mutant does not parse: {broken})")
            verdicts.append(("MALFORMED", label)); continue
        path.write_text(mutated)
        try:
            caught = run_one(target, path)
        finally:
            path.write_text(original)
        status = "KILLED" if caught else "SURVIVED"
        print(f"  {status:10} {label:48} -> {target}")
        verdicts.append((status, label))
    bad = [v for v in verdicts if v[0] != "KILLED"]
    print(f"\n{len(verdicts)-len(bad)}/{len(verdicts)} mutants killed by their named test")
    return 1 if bad else 0


# Appended: the deferred-decision mechanism. A trigger that cannot be
# shown firing is the shape it was built to prevent.
REGISTRY = REPO / "architecture" / "invariants.yaml"
PROCESS = REPO / "tests" / "test_process_decisions.py"

MUTATIONS += [
    ("a conditional deferral with no trigger", REGISTRY,
     lambda s: s.replace("    trigger_enforced_by: tests/test_process_decisions.py",
                         "    trigger_enforced_by_MUTANT: none"),
     "test_every_conditional_deferral_names_the_check_that_ends_it"),
    ("a trigger naming a file that never mentions the row", REGISTRY,
     lambda s: s.replace("    trigger_enforced_by: tests/test_process_decisions.py",
                         "    trigger_enforced_by: tests/test_adapters.py"),
     "test_every_conditional_deferral_names_the_check_that_ends_it"),
    ("a second writer tolerated", PROCESS,
     lambda s: s.replace("    assert len(implementations) == 1, (",
                         "    assert True, (  # MUTANT"),
     "test_the_multi_writer_trigger_fires_when_a_second_writer_is_planted"),
    ("a shared-vendor lineage with no review record", PROCESS,
     lambda s: s.replace("    return bool(record) and len(record) > 20",
                         "    return True  # MUTANT"),
     "test_both_process_predicates_reject_what_they_are_meant_to_reject"),
    ("a bare 'reviewed' accepted as a record", PROCESS,
     lambda s: s.replace("    return bool(record) and len(record) > 20",
                         "    return bool(record)  # MUTANT"),
     "test_both_process_predicates_reject_what_they_are_meant_to_reject"),
    ("the validator sharing a vendor with what it validates", PROCESS,
     lambda s: s.replace("    return validator not in {spec[\"vendor\"] for role, spec in topology.items()",
                         "    return True or validator not in {spec[\"vendor\"] for role, spec in topology.items()"),
     "test_both_process_predicates_reject_what_they_are_meant_to_reject"),
]


if __name__ == "__main__":
    raise SystemExit(main())
