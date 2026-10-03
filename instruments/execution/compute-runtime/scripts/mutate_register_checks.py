"""Probe each register lock against the defect it claims to catch.

A check that has never failed is an untested assertion. Each mutation
below reaches executable semantics; a mutation whose diff does not is
MALFORMED, not SURVIVED, and is reported as such. Attribution is
per-test: "caught by something" is not evidence.
"""

import os
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DERIVE = REPO / "architecture" / "derive_register.py"
CONFORMANCE = REPO / "architecture" / "conformance.py"
INVARIANTS = REPO / "architecture" / "invariants.yaml"
CORE = REPO / "architecture" / "core.yaml"
EVIDENCE_CLASS = REPO / "architecture" / "evidence_class.yaml"
REGISTER = REPO / "architecture" / "exchange" / "invariant_register.yaml"

MUTATIONS = [
    ("unreachable repo tolerated", DERIVE,
     lambda s: s.replace(
         "        if not root.is_dir():",
         "        if False:  # MUTANT"),
     "test_unreachable_bound_repository_fails_the_derivation"),
    ("citation check always passes", DERIVE,
     lambda s: s.replace(
         "    if not evidence:\n        return False",
         "    return True  # MUTANT\n    if not evidence:\n        return False"),
     "test_enforced_claims_must_cite_their_own_id"),
    ("commit not recorded per claim", DERIVE,
     lambda s: s.replace("source_commit=local_commit,", 'source_commit="0"*40,  # MUTANT'),
     "test_every_derived_record_carries_the_commit_it_was_read_at"),
    ("contest detection disabled", DERIVE,
     lambda s: s.replace(
         '    statuses = {c.status for c in claims if c.scope != LOCAL_SCOPE}',
         '    return False  # MUTANT\n    statuses = {c.status for c in claims if c.scope != LOCAL_SCOPE}'),
     "test_a_planted_disagreement_IS_detected_as_contested"),

    # RETARGETED TWICE THIS PHASE, and the second time is the
    # instructive one. This mutation used to edit invariants.yaml, which
    # no longer holds the version -- MALFORMED, reporting nothing. Moved
    # to core.yaml, it SURVIVED: both target tests manipulate core.yaml
    # themselves and restore what they found, so the test's own
    # save/restore silently reverted the mutant. A mutation of a file a
    # test rewrites measures the test's bookkeeping, not its assertion.
    #
    # So both now mutate the ENFORCING CODE. That is also the more
    # honest probe of what changed this phase: with the referent
    # decoupled from packaging, nothing outside the declaration pins its
    # value, and the closure gate is the only thing that can still
    # falsify a moved core version.
    ("core version moves without breaking the closure", CONFORMANCE,
     lambda s: s.replace("        if declared != expected:",
                         "        if False:  # MUTANT"),
     "test_moving_the_declared_core_version_breaks_every_artifact_that_binds_it"),
    ("core version inferred from packaging", CONFORMANCE,
     lambda s: s.replace(
         '    if declaration.get("referent", {}).get("derived_from_packaging") is not False:',
         "    if False:  # MUTANT"),
     "test_a_packaging_derived_core_version_is_refused"),

    # THE THREE-PARTY MUTATIONS.
    ("sourceless party silently dropped", DERIVE,
     lambda s: s.replace(
         "        binding_mode=INVARIANT_REGISTRY if records else EXTENDS_ONLY,",
         "        binding_mode=INVARIANT_REGISTRY,  # MUTANT"),
     "test_a_bound_party_with_no_invariant_source_is_represented_not_dropped"),
    ("unbound party accepted as sourceless", DERIVE,
     lambda s: s.replace(
         "    if not records and not binding_files:",
         "    if False:  # MUTANT"),
     "test_a_party_with_neither_invariants_nor_a_binding_fails"),
    ("currency asked of the local clone only", DERIVE,
     lambda s: s.replace(
         "    if local == remote:\n        return IN_SYNC",
         "    return IN_SYNC  # MUTANT\n    if local == remote:\n        return IN_SYNC"),
     "test_a_clone_behind_its_remote_fails_the_derivation"),
    ("offline derivation claims currency", DERIVE,
     lambda s: s.replace(
         '"checked_against_remotes": derivation.remotes_checked,',
         '"checked_against_remotes": True,  # MUTANT'),
     "test_an_offline_derivation_never_claims_currency_it_did_not_check"),
    # -- a mirror is not a source: the three positions, one rule --
    ("mirror read as the holder's own name", DERIVE,
     lambda s: s.replace(
         "        return self.authored_here is True",
         "        return True  # MUTANT"),
     "test_a_mirror_is_not_a_source__the_general_rule"),
    ("an emitted projection read as a canonical source", DERIVE,
     lambda s: s.replace(
         "        return not self.emitted and not self.shared",
         "        return not self.shared  # MUTANT"),
     "test_deriving_twice_is_a_fixed_point"),
    ("provenance decided per-repository instead of across parties", DERIVE,
     lambda s: s.replace(
         "            elif len(set(holders[digest])) > 1:",
         "            elif False:  # MUTANT"),
     "test_a_JOINT_artifact_is_not_read_as_either_party_s_self_declaration"),
    ("unresolved authorship credited to whoever holds it", DERIVE,
     lambda s: s.replace(
         "        return not self.names_one_author",
         "        return True  # MUTANT"),
     "test_a_single_authored_artifact_two_parties_hold_credits_neither"),

    # -- currency is directional, and per sibling --
    ("deriving party exempted by tolerance, not construction", DERIVE,
     lambda s: s.replace(
         "    if is_deriving:",
         "    if False:  # MUTANT"),
     "test_the_deriving_party_is_exempt_by_construction_not_by_tolerance"),
    ("the deriving party counted as its own worst sibling", DERIVE,
     lambda s: s.replace(
         "        return [b for b in self.bindings.values() if not b.is_deriving_party]",
         "        return list(self.bindings.values())  # MUTANT"),
     "test_currency_is_reported_per_sibling_and_never_collapsed"),
    ("worst sibling collapsed to whichever was read first", DERIVE,
     lambda s: s.replace(
         "        return min(siblings, key=lambda b: _CURRENCY_ORDER.index(b.currency))",
         "        return siblings[0]  # MUTANT"),
     "test_the_worst_sibling_is_selected_not_the_first_one_read"),
    ("deferral to a silent party tolerated", DERIVE,
     lambda s: s.replace(
         "def _check_deferrals(derivation: Derivation) -> None:",
         "def _check_deferrals(derivation: Derivation) -> None:\n    return  # MUTANT"),
     "test_a_repository_that_defers_cannot_be_derived_alone"),
    ("owner status transcribed instead of resolved", EVIDENCE_CLASS,
     lambda s: s.replace(
         "  - id: generation_depth_bounded\n    scope: this_repository\n    owner_elsewhere: DAQ\n",
         "  - id: generation_depth_bounded\n    scope: this_repository\n"),
     "test_a_deferred_row_resolves_to_the_owner_s_LIVE_status"),

    ("an open decision silently dropped from the register", DERIVE,
     lambda s: s.replace(
         '        "awaiting_a_decision": sorted(derivation.awaiting_a_decision),',
         '        "awaiting_a_decision": [],  # MUTANT'),
     "test_open_decisions_are_derived_and_re_emitted_not_left_in_prose"),
    ("an open decision reported as a contest", DERIVE,
     lambda s: s.replace(
         "            if any(c.awaiting_decision for c in claims)",
         "            if False  # MUTANT"),
     "test_an_open_decision_is_not_the_same_as_a_contest"),
    ("the deriving-party exclusion widened to swallow sibling commits", DERIVE,
     lambda s: s.replace(
         '         if not (entry.get("repository") == deriving_party and k == "commit")}',
         '         if k != "commit"}  # MUTANT'),
     "test_a_sibling_commit_is_never_excluded_from_the_comparison"),
    ("committed register goes stale", REGISTER,
     lambda s: s.replace('"contested_count": 0', '"contested_count": 9', 1),
     "test_the_committed_register_is_faithful_to_the_commits_it_names"),
]


#: See scripts/mutate_reachability_checks.py for the finding these two
#: guards come from. In short: a mutant that does not PARSE can only be
#: killed by an import error, and a mutant is NOT identified by
#: `(mtime, size)` -- two mutants of one file with the same byte length
#: written in the same second are indistinguishable to CPython's `.pyc`
#: validity check, so the second run executes the first one's bytecode
#: and its result is printed under the wrong label.
#:
#: THE SAME MECHANISM, APPLIED HERE WITHOUT WAITING FOR IT TO FIRE. The
#: sibling battery was reporting a stable SURVIVED for a mutant it had
#: never run; this one mutates the same handful of files repeatedly and
#: is exposed to exactly the same collision. A defect found in one
#: instrument is a defect in the other until it is checked, not until it
#: is observed -- an absence of anyone finding one is not a verdict.
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


def run_one(target_test, path=None):
    if path is not None:
        _purge_cache(path)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-x",
         f"tests/test_invariant_register.py::{target_test}"],
        cwd=REPO, capture_output=True, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    return result.returncode != 0


def main():
    print("=== MUTATION VERIFICATION (per-test attribution) ===")
    verdicts = []
    for label, path, mutate, target in MUTATIONS:
        original = path.read_text()
        mutated = mutate(original)
        if mutated == original:
            print(f"  MALFORMED  {label:34} (diff reached nothing)")
            verdicts.append(("MALFORMED", label)); continue
        broken = _compiles(path, mutated)
        if broken:
            print(f"  MALFORMED  {label:34} (mutant does not parse: {broken})")
            verdicts.append(("MALFORMED", label)); continue
        path.write_text(mutated)
        try:
            caught = run_one(target, path)
        finally:
            path.write_text(original)
        status = "KILLED" if caught else "SURVIVED"
        print(f"  {status:10} {label:34} -> {target}")
        verdicts.append((status, label))
    bad = [v for v in verdicts if v[0] != "KILLED"]
    print(f"\n{len(verdicts)-len(bad)}/{len(verdicts)} mutants killed by their named test")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
