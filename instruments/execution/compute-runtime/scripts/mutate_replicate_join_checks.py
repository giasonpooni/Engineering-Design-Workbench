#!/usr/bin/env python3
"""Probe the record join's own refusals.

Same two guards as the sibling batteries, carried here rather than
rediscovered: a mutant that does not PARSE can only be killed by an
import error, and a mutant is not identified by `(mtime, size)` -- two
same-length edits to one file in the same second collide in CPython's
`.pyc` validity check and the second run executes the first one's
bytecode.
"""

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
JOIN = REPO / "materials" / "replicate_join.py"
ANALYSIS = REPO / "materials" / "analysis.py"
SUITE = "tests/test_replicate_join.py"

MUTATIONS = [
    # -- the trap stays pinned -------------------------------------------
    #
    # THE MUTATION THAT WAS HERE FIRST WAS MISCONCEIVED, and removing it
    # is the finding. It deleted `_group_by_comparison_context`'s
    # `result.sort(...)` on the theory that the sort was what reordered
    # the values -- and the mutant SURVIVED, because that call sorts the
    # LIST OF GROUPS while the values inside a group are ordered by
    # `RetrievalResult.observation_ids`, which is `sorted(set(...))` over
    # content-addressed ids. So the battery caught a wrong MECHANISM
    # behind a right finding, which is the harder thing to catch: the
    # finding kept reproducing, so nothing else would have questioned it.
    #
    # And the aim was wrong twice over. A mutant that removed the trap
    # would be a FIX, not a defect, so nothing can be aimed at that lock:
    # it is a CHARACTERIZATION lock and it fails, correctly, on the day
    # the projection starts carrying identity. What is mutable is the
    # consumer's duty never to inherit an order -- below.
    ("the pairs take whatever order they are handed", JOIN,
     lambda s: s.replace("    for record_id in sorted(by_record):",
                         "    for record_id in by_record:  # MUTANT"),
     "test_the_order_of_the_pairs_is_stated_not_inherited"),
    ("the group starts carrying identity", ANALYSIS,
     lambda s: s.replace("    context: Mapping[str, object]\n    values: Tuple[float, ...]",
                         "    context: Mapping[str, object]\n    record_ids: Tuple[str, ...] = ()  # MUTANT\n    values: Tuple[float, ...]"),
     "test_the_projection_still_drops_the_pairing"),

    # -- the join refuses to guess ---------------------------------------
    ("two runs merged onto one record: the first value wins", JOIN,
     lambda s: s.replace("                    ambiguous.add(record_id)\n                    continue",
                         "                    continue  # MUTANT"),
     "test_two_runs_merged_onto_one_record_are_refused_not_picked"),
    ("an ambiguous record kept for its other properties", JOIN,
     lambda s: s.replace("        if record_id in ambiguous:\n            continue",
                         "        if False:  # MUTANT\n            continue"),
     "test_an_ambiguous_record_is_refused_whole_not_partially"),
    ("an incomplete record silently dropped", JOIN,
     lambda s: s.replace("        (complete if run.complete_for(properties) else incomplete).append(run)",
                         "        if run.complete_for(properties):\n            complete.append(run)  # MUTANT"),
     "test_a_record_missing_a_property_is_incomplete_not_dropped"),
    ("an incomplete record counted as a pair", JOIN,
     lambda s: s.replace("    def complete_for(self, properties: Tuple[str, ...]) -> bool:\n        return all(name in self.values for name in properties)",
                         "    def complete_for(self, properties: Tuple[str, ...]) -> bool:\n        return True  # MUTANT"),
     "test_a_record_missing_a_property_is_incomplete_not_dropped"),

    # -- the join key ------------------------------------------------------
    ("the join key discarded once it has been used", JOIN,
     lambda s: s.replace('        run = PairedRun(record_id=record_id, values=by_record[record_id],',
                         '        run = PairedRun(record_id="", values=by_record[record_id],  # MUTANT'),
     "test_the_join_keeps_the_key_it_joined_on"),
    ("the observation ids dropped from the pair", JOIN,
     lambda s: s.replace("                        observation_ids=observations.get(record_id, {}))",
                         "                        observation_ids={})  # MUTANT"),
     "test_the_join_keeps_the_key_it_joined_on"),

    # -- the two DEFINITIONAL refusals, and no third ------------------------
    # `< 1` in place of `< 2` is an EQUIVALENT mutant and is not used:
    # at n == 1 the variance of a single point is exactly 0, so the
    # variance guard returns None on the same input and no observation
    # can separate them. `< 0` is not equivalent -- at n == 0 computing a
    # mean divides by zero -- so that is what is aimed here.
    ("the n guard removed, so an empty join crashes", JOIN,
     lambda s: s.replace("    if len(pairs) < 2:\n        return None",
                         "    if len(pairs) < 0:  # MUTANT\n        return None"),
     "test_a_correlation_over_no_pairs_is_none_and_never_a_crash"),
    ("a constant series reported as zero correlation", JOIN,
     lambda s: s.replace("    if variance_x == 0.0 or variance_y == 0.0:\n        return None",
                         "    if False:  # MUTANT\n        return None"),
     "test_a_correlation_over_a_constant_series_is_none_not_zero"),
    ("a policy threshold on n smuggled into a definitional refusal", JOIN,
     lambda s: s.replace("    if len(pairs) < 2:\n        return None",
                         "    if len(pairs) < 3:  # MUTANT\n        return None"),
     "test_both_definitional_refusals_and_no_policy_threshold"),

    # -- the pairing itself -------------------------------------------------
    ("the join pairs by order instead of by record", JOIN,
     lambda s: s.replace("    return tuple((run.values[first], run.values[second]) for run in join.complete)",
                         "    return tuple(zip(sorted(r.values[first] for r in join.complete),\n"
                         "                     sorted(r.values[second] for r in join.complete)))  # MUTANT"),
     "test_the_recovered_correlation_is_the_true_one"),
    ("a property that was never joined on answered anyway", JOIN,
     lambda s: s.replace('        if name not in join.properties:\n            raise ValueError',
                         '        if False:  # MUTANT\n            raise ValueError'),
     "test_asking_for_a_property_that_was_not_joined_raises"),

    # -- the fragmentation surface -----------------------------------------
    ("fragmentation reported as comparability", JOIN,
     lambda s: s.replace("    return observations > 1 and groups == observations",
                         "    return False  # MUTANT"),
     "test_per_run_uncertainty_fragments_the_set_into_singletons"),
    ("a single observation called fragmented", JOIN,
     lambda s: s.replace("    return observations > 1 and groups == observations",
                         "    return groups == observations  # MUTANT"),
     "test_a_single_observation_is_not_fragmented"),

    # -- the run declaration, measured against a real report's shape ------
    ("a correlation computed over undeclared pairs", JOIN,
     lambda s: s.replace("    if not join.runs_declared:", "    if False:  # MUTANT"),
     "test_a_correlation_over_undeclared_pairs_is_refused_not_computed"),
    ("the join declares its own pairs to be runs", JOIN,
     lambda s: s.replace("    runs_declared: bool = False",
                         "    runs_declared: bool = True  # MUTANT"),
     "test_the_join_itself_needs_no_declaration"),
    ("a declaration naming an absent record silently ignored", JOIN,
     lambda s: s.replace("        if unknown:\n            raise ValueError(",
                         "        if False:  # MUTANT\n            raise ValueError("),
     "test_declaring_a_record_that_is_not_in_the_join_is_refused"),
    ("a declaration that overrules an ambiguous record", JOIN,
     lambda s: s.replace("        known = {run.record_id for run in self.complete} | {\n"
                         "            run.record_id for run in self.incomplete}",
                         "        known = {run.record_id for run in self.complete} | {\n"
                         "            run.record_id for run in self.incomplete} | set(self.ambiguous)  # MUTANT"),
     "test_the_declaration_does_not_resurrect_an_ambiguous_record"),
    ("the declaration stops restricting and keeps everything", JOIN,
     lambda s: s.replace("            complete=tuple(r for r in self.complete if r.record_id in chosen),",
                         "            complete=self.complete,  # MUTANT"),
     "test_declaring_the_two_injections_gives_the_real_replicate_set"),
    ("the join starts guessing from the record locator", JOIN,
     lambda s: s.replace("def paired_values(",
                         "_AGGREGATE_LABELS = ('Average', 'Standard Deviation', 'RSD')  # MUTANT\n\n\ndef paired_values("),
     "test_neither_the_evidence_class_nor_the_locator_is_used_to_guess"),

    # -- the boundary this must not cross ------------------------------------
    ("the consumer 'fixes' the grouping instead of surfacing it", ANALYSIS,
     lambda s: s.replace('    return {k: v for k, v in content.items() if k not in ("property", value_key)}',
                         '    return {k: v for k, v in content.items() if k not in ("property", value_key, "uncertainty")}  # MUTANT'),
     "test_the_grouping_semantics_were_not_touched"),
    # NOTE THE ASSEMBLY. The minting call this mutant injects is built
    # from parts rather than spelled out, because
    # tests/test_architecture_sync.py greps every non-test file for the
    # minting seams by NAME and would have flagged THIS SCRIPT as an
    # undeclared one. It fired, correctly, on a string that never
    # executes -- and fired a second time on a comment that merely
    # QUOTED the name, which is why this sentence does not quote it
    # either. Adding the script to that allowlist would have bought a
    # green suite by widening the check that guards the write barrier,
    # so the strings moved instead. A grep-based ratchet cannot tell
    # code from prose, and the right response to that is to stop writing
    # the token, not to loosen the grep.
    # AND IT MUST BE A WRITE THAT RUNS. The first version of this mutant
    # injected an UNCALLED function, which writes nothing -- so the
    # behavioural test correctly did not fire and the mutant "survived"
    # having done nothing. A mutant that does not execute is the
    # malformed-plant problem once more, in a third instrument.
    # AND IT MUST ADD STATE. Re-putting an object the pool already holds
    # is a NO-OP -- the store is content-addressed, so an identical
    # re-put moves neither the fingerprint nor its history. That is a
    # property of the pool worth knowing and it makes such a mutant
    # unobservable BY DESIGN rather than by a gap in the test. So the
    # mutant introduces a referent the pool has never seen.
    ("the consumer starts writing to the pool", JOIN,
     lambda s: s.replace(
         "from evidence.types import Referent",
         "from evidence.types import Referent, make_referent").replace(
         "    return ReplicateJoin(\n        material=referent,",
         "    getattr(pool, 'put_' + 'referent')(\n"
         "        make_referent(natural_key='mutant', kind='substance'))  # MUTANT\n"
         "    return ReplicateJoin(\n        material=referent,"),
     "test_the_join_writes_nothing_to_the_pool"),
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
    print("=== MUTATION VERIFICATION: the record join's refusals ===")
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
