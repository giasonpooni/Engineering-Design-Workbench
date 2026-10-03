#!/usr/bin/env python3
"""Probe the core identity's refusals."""

import os
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
IDENTITY = REPO / "architecture" / "core_identity.py"
ARTIFACT = REPO / "architecture" / "exchange" / "core_identity.yaml"
SUITE = "tests/test_core_identity.py"

MUTATIONS = [
    # -- it must distinguish ----------------------------------------------
    ("the digest stops covering paths, so swapped files look identical", IDENTITY,
     lambda s: s.replace('    joined = "\\n".join(f"{path}:{digest}"\n'
                         "                       for path, digest in file_digests(root, surface))",
                         '    joined = "\\n".join(  # MUTANT\n'
                         "        d for _, d in sorted(file_digests(root, surface), key=lambda kv: kv[1]))"),
     "test_the_digest_covers_paths_and_not_only_contents"),
    ("the surface globbed, so a new neighbour widens the core", IDENTITY,
     lambda s: s.replace("    for relative in sorted(CORE_SURFACE if surface is None else surface):",
                         "    for relative in sorted(p.relative_to(root).as_posix() for p in (root / 'core').rglob('*.py') if '__pycache__' not in p.parts):  # MUTANT"),
     "test_the_surface_is_declared_and_a_new_neighbour_does_not_widen_it"),
    ("the registry pulled into the surface", IDENTITY,
     lambda s: s.replace('    "core/projection/project.py",\n)',
                         '    "core/projection/project.py",\n    "architecture/invariants.yaml",  # MUTANT\n)'),
     "test_a_change_outside_the_surface_does_not_move_the_digest"),
    ("the content ignored, so a changed core hashes the same", IDENTITY,
     lambda s: s.replace("        digests.append((relative, _sha256(candidate.read_bytes())))",
                         "        digests.append((relative, _sha256(relative.encode())))  # MUTANT"),
     "test_a_change_to_the_core_surface_moves_the_digest"),

    # -- it must refuse ----------------------------------------------------
    ("a missing surface file hashed around instead of refused", IDENTITY,
     lambda s: s.replace("    if missing:\n        raise CoreIdentityError(",
                         "    if False:  # MUTANT\n        raise CoreIdentityError("),
     "test_a_missing_surface_file_refuses_rather_than_hashing_what_is_left"),

    # -- a party must be able to act on it ---------------------------------
    ("verify returns a bare verdict with no address", IDENTITY,
     lambda s: s.replace('        "files": [{"path": path, "sha256": digest}\n'
                         "                  for path, digest in file_digests(root, files)],",
                         '        "files": [],  # MUTANT'),
     "test_verify_names_the_file_that_moved_rather_than_saying_no"),
    ("compare misses a path present on only one side", IDENTITY,
     lambda s: s.replace("    differing = [path for path in sorted(set(mine) | set(theirs))",
                         "    differing = [path for path in sorted(set(mine) & set(theirs))  # MUTANT"),
     "test_compare_reports_a_surface_that_gained_or_lost_a_file"),
    ("verify reports a match it did not check", IDENTITY,
     lambda s: s.replace('        "matches": actual == expected,',
                         '        "matches": True,  # MUTANT'),
     "test_verify_names_the_file_that_moved_rather_than_saying_no"),

    # -- which track a party binds, which is what the first version got
    # -- wrong. Each of these RESTORES a form the shipped defect had.
    ("only one surface published, the way the defect shipped", IDENTITY,
     lambda s: s.replace('SURFACES: Dict[str, Tuple[str, ...]] = {\n'
                         '    "twin_compiler": TWIN_SURFACE,\n'
                         '    "evidence_platform": EVIDENCE_SURFACE,\n}',
                         'SURFACES: Dict[str, Tuple[str, ...]] = {  # MUTANT\n'
                         '    "twin_compiler": TWIN_SURFACE,\n}'),
     "test_the_two_surfaces_are_published_with_different_digests"),
    ("the binding declared rather than measured", IDENTITY,
     lambda s: s.replace("    counts = imported_tracks(consumer)\n"
                         "    ranked = sorted(counts.items(), key=lambda kv: -kv[1])",
                         '    return "evidence_platform"  # MUTANT\n'
                         "    counts = imported_tracks(consumer)\n"
                         "    ranked = sorted(counts.items(), key=lambda kv: -kv[1])"),
     "test_binding_track_answers_either_track_and_not_only_one"),
    ("a tie resolved by guessing instead of refused", IDENTITY,
     lambda s: s.replace("    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:\n"
                         "        return None",
                         "    if False:  # MUTANT\n        return None"),
     "test_binding_track_refuses_a_tie_rather_than_picking_one"),
    ("a mismatched surface accepted, which is the defect itself", IDENTITY,
     lambda s: s.replace("    if bound != surface_name:",
                         "    if False:  # MUTANT"),
     "test_covers_what_is_bound_refuses_the_exact_defect_that_shipped"),
    ("the refusal loses the counts and becomes an opinion", IDENTITY,
     lambda s: s.replace('        counts = imported_tracks(consumer)\n'
                         '        return False, (\n'
                         '            f"it imports {bound} {counts[bound]} times and {surface_name} "\n'
                         '            f"{counts[surface_name]} times, so a {surface_name} digest is "\n'
                         '            f"about code this party does not use")',
                         '        return False, "wrong surface"  # MUTANT'),
     "test_covers_what_is_bound_refuses_the_exact_defect_that_shipped"),
    ("an unbound party reported as a mismatched one", IDENTITY,
     lambda s: s.replace('        return False, ("this consumer imports neither track, or splits evenly "\n'
                         '                       "between them -- there is no binding for a digest to "\n'
                         '                       "be about")',
                         '        return False, "not this surface"  # MUTANT'),
     "test_covers_what_is_bound_refuses_when_there_is_no_binding_at_all"),
    ("a vendored copy of this repository counted as a consumer", IDENTITY,
     lambda s: s.replace('        if parts & {".git", "__pycache__", "node_modules", "vendor"}:',
                         '        if parts & {".git", "__pycache__", "node_modules"}:  # MUTANT'),
     "test_a_vendored_checkout_importing_itself_is_not_counted"),
    ("the tracks overlap, so one file could move both digests", IDENTITY,
     lambda s: s.replace('    "evidence_platform": ("evidence", "scout", "retrieval", "materials",',
                         '    "evidence_platform": ("evidence", "scout", "retrieval", "materials", "core",  # MUTANT'),
     "test_the_two_tracks_share_no_packages"),
    ("a binding published without the counts behind it", IDENTITY,
     lambda s: s.replace('            "imports": imported_tracks(consumer),',
                         '            "imports": {n: 0 for n in TRACK_PACKAGES},  # MUTANT'),
     "test_the_artifact_records_which_track_each_party_binds_and_from_what"),
    ("a party pointed at the digest of a track it does not import", IDENTITY,
     lambda s: s.replace('            "digest_it_should_check": surfaces[bound]["digest"] if bound else "",',
                         '            "digest_it_should_check": surfaces["twin_compiler"]["digest"],  # MUTANT'),
     "test_the_artifact_records_which_track_each_party_binds_and_from_what"),
    ("the correction quietly dropped from the record", IDENTITY,
     lambda s: s.replace("ORIGINAL CORE-VERSION DEFECT RECURRING",
                         "a refinement"),
     "test_the_artifact_states_the_correction_rather_than_quietly_replacing_it"),
    ("the emitted artifact edited without re-deriving it", ARTIFACT,
     # NOT a literal count: DAQ's import total moves as that party
     # develops (291 on 2026-09-03, 293 on 2026-09-05), and a mutation
     # string pinned to today's number goes MALFORMED the next time they
     # commit -- reporting a broken battery rather than a broken lock.
     lambda s: s.replace('"twin_compiler": 0', '"twin_compiler": 99'),
     "test_the_artifact_is_a_fixed_point"),

    ("verify ignores the surface it was asked about", IDENTITY,
     lambda s: s.replace("    files = SURFACES[surface] if surface is not None else None",
                         "    files = None  # MUTANT"),
     "test_verify_checks_the_surface_it_is_asked_about"),
    ("an unknown surface name falls back instead of refusing", IDENTITY,
     lambda s: s.replace("    if surface is not None and surface not in SURFACES:",
                         "    if False:  # MUTANT"),
     "test_verify_refuses_a_surface_name_it_does_not_publish"),
    ("compare drops the surface and reads the default one", IDENTITY,
     lambda s: s.replace("    mine = dict(file_digests(root, surface))",
                         "    mine = dict(file_digests(root))  # MUTANT"),
     "test_compare_reports_the_surface_it_is_given"),

    # -- the artifact -------------------------------------------------------
    ("version and digest collapsed into one thing", ARTIFACT,
     lambda s: s.replace("the IDENTITY -- which core that statement was made about",
                         "the version"),
     "test_the_artifact_keeps_version_and_digest_as_different_things"),
    ("a reason that is not a reason", ARTIFACT,
     lambda s: re.sub(r'"architecture/invariants.yaml": "[^"]*"',
                      '"architecture/invariants.yaml": "no"', s),
     "test_the_artifact_says_what_is_outside_the_surface_and_why"),
    ("the finding's origin quietly dropped", ARTIFACT,
     lambda s: s.replace("could not act on it", "was not worth acting on"),
     "test_the_artifact_credits_the_party_that_found_the_gap"),
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
    print("=== MUTATION VERIFICATION: the core identity's refusals ===")
    verdicts = []
    for label, path, mutate, target in MUTATIONS:
        original = path.read_text()
        mutated = mutate(original)
        if mutated == original:
            print(f"  MALFORMED  {label:60} (diff reached nothing)")
            verdicts.append(("MALFORMED", label)); continue
        broken = _compiles(path, mutated)
        if broken:
            print(f"  MALFORMED  {label:60} (does not parse: {broken})")
            verdicts.append(("MALFORMED", label)); continue
        path.write_text(mutated)
        try:
            caught = run_one(target, path)
        finally:
            path.write_text(original)
        status = "KILLED" if caught else "SURVIVED"
        print(f"  {status:10} {label:60} -> {target}")
        verdicts.append((status, label))
    bad = [v for v in verdicts if v[0] != "KILLED"]
    print(f"\n{len(verdicts)-len(bad)}/{len(verdicts)} mutants killed by their named test")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
