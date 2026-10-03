"""Locks on the core's content identity.

THE GAP THIS CLOSES was found by another party and could only be closed
here. The acquisition channel's census observed two checkouts of this
repository, different commits, three days apart, both reporting core
version 1.0.0, with the ancestry between them undeterminable from where
it stood. It recorded the finding and said plainly that it could not act
on it -- naming which core a label refers to is this repository's act,
because this repository declares the label.

So the label gains a digest. `core@1.0.0` stays the COMPATIBILITY
statement; the digest says WHICH core. The two properties that make that
worth anything are opposite and are both pinned below:

  a change to the core surface MUST move the digest
  a change that is not a bend MUST NOT move it

A digest that moved on every commit would distinguish nothing, and one
that moved on none would distinguish nothing either.

AND A THIRD PROPERTY, ADDED AFTER THE FIRST VERSION GOT IT WRONG: the
digest must be over the body of code the binding party actually imports.
This repository holds two disjoint tracks, and the first digest covered
the one no consumer touches. So the surface a party checks is now
MEASURED against what it imports, and that measurement is locked below
in both directions -- a check that could only ever answer one way would
be testing nothing about the answer.
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "architecture"))

from architecture import core_identity as ci

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "architecture" / "exchange" / "core_identity.yaml"


def _core_copy(directory, surface=None):
    """A tree carrying only the declared surface, so a test can move one
    file without touching the repository."""
    root = pathlib.Path(directory)
    for relative in (ci.CORE_SURFACE if surface is None else surface):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    (root / "architecture").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "architecture" / "core.yaml",
                    root / "architecture" / "core.yaml")
    return root


# ------------------------------------------------ it distinguishes --


def test_a_change_to_the_core_surface_moves_the_digest():
    with tempfile.TemporaryDirectory() as directory:
        root = _core_copy(directory)
        before = ci.core_digest(root)
        target = root / "core" / "canonical" / "state.py"
        target.write_text(target.read_text() + "\n# a change to the core\n")
        assert ci.core_digest(root) != before


def test_a_change_outside_the_surface_does_not_move_the_digest():
    """Adding an invariant row, writing a doc, landing a vertical --
    none of these is a bend, and a digest that moved on them would move
    on almost every commit and stop distinguishing anything."""
    with tempfile.TemporaryDirectory() as directory:
        root = _core_copy(directory)
        before = ci.core_digest(root)
        (root / "architecture" / "invariants.yaml").write_text(
            "invariants:\n  - id: something_new\n")
        (root / "docs").mkdir()
        (root / "docs" / "NOTE.md").write_text("a phase report\n")
        vertical = root / "structures"
        vertical.mkdir()
        (vertical / "ingest.py").write_text("# a vertical extends the core\n")
        assert ci.core_digest(root) == before


def test_the_digest_covers_paths_and_not_only_contents():
    """Two files whose bodies were swapped are a different core. A
    digest over the contents alone hashes a multiset, not a schema."""
    with tempfile.TemporaryDirectory() as directory:
        root = _core_copy(directory)
        before = ci.core_digest(root)
        first = root / "core" / "canonical" / "delta.py"
        second = root / "core" / "canonical" / "validation.py"
        first_text, second_text = first.read_text(), second.read_text()
        first.write_text(second_text)
        second.write_text(first_text)
        assert ci.core_digest(root) != before


def test_the_surface_is_declared_and_a_new_neighbour_does_not_widen_it():
    """A glob would have adopted this file silently. Widening the core
    without a bend is what bend_protocol forbids by name."""
    with tempfile.TemporaryDirectory() as directory:
        root = _core_copy(directory)
        before = ci.core_digest(root)
        (root / "core" / "canonical" / "extra.py").write_text("X = 1\n")
        assert ci.core_digest(root) == before


# ------------------------------------------------------- it refuses --


def test_a_missing_surface_file_refuses_rather_than_hashing_what_is_left():
    """A digest over a surface that has moved is a digest of something
    else, and computing one anyway would be worse than failing."""
    with tempfile.TemporaryDirectory() as directory:
        root = _core_copy(directory)
        (root / "core" / "canonical" / "schema.py").unlink()
        with pytest.raises(ci.CoreIdentityError):
            ci.core_digest(root)


# ------------------------------------------- a party can act on it --


def test_verify_names_the_file_that_moved_rather_than_saying_no():
    """A difference with no address leaves the reader exactly where the
    version label left them."""
    with tempfile.TemporaryDirectory() as directory:
        root = _core_copy(directory)
        expected = ci.core_digest(root)
        assert ci.verify(expected, root)["matches"] is True

        target = root / "core" / "canonical" / "version.py"
        target.write_text(target.read_text() + "\n# moved\n")
        result = ci.verify(expected, root)
        assert result["matches"] is False
        assert result["actual"] != result["expected"]
        assert any(entry["path"].endswith("version.py") for entry in result["files"])


def test_compare_reports_exactly_the_differing_paths():
    with tempfile.TemporaryDirectory() as directory:
        root = _core_copy(directory)
        theirs = ci.file_digests(root)
        assert ci.compare(theirs, root) == ()

        target = root / "core" / "canonical" / "delta.py"
        target.write_text("# a different delta\n")
        assert ci.compare(theirs, root) == ("core/canonical/delta.py",)


def test_verify_checks_the_surface_it_is_asked_about():
    """Without a surface argument this could only ever check the twin
    track -- so a party binding the evidence platform, which is every
    party measured, had no way to check what it bound. Driven over both,
    and cross-checked, because a verify that matched either digest
    against either surface would be reporting agreement it never tested."""
    for name, surface in ci.SURFACES.items():
        digest = ci.core_digest(ROOT, surface)
        result = ci.verify(digest, ROOT, name)
        assert result["matches"] is True
        assert result["surface"] == name
        assert {entry["path"] for entry in result["files"]} == set(surface)

    other = ci.core_digest(ROOT, ci.EVIDENCE_SURFACE)
    assert ci.verify(other, ROOT, "twin_compiler")["matches"] is False


def test_verify_refuses_a_surface_name_it_does_not_publish():
    """Falling back to a default would report a match about other code,
    which is the failure this whole module exists to refuse."""
    with pytest.raises(ci.CoreIdentityError):
        ci.verify("sha256:whatever", ROOT, "no_such_track")


def test_compare_reports_the_surface_it_is_given():
    with tempfile.TemporaryDirectory() as directory:
        root = _core_copy(directory, ci.EVIDENCE_SURFACE)
        theirs = ci.file_digests(root, ci.EVIDENCE_SURFACE)
        assert ci.compare(theirs, root, ci.EVIDENCE_SURFACE) == ()

        target = root / "evidence" / "types.py"
        target.write_text("# a different types module\n")
        assert ci.compare(theirs, root, ci.EVIDENCE_SURFACE) == ("evidence/types.py",)


def test_compare_reports_a_surface_that_gained_or_lost_a_file():
    """A surface that changed shape is a bend, and the most important
    thing to say about it is which file."""
    theirs = tuple(list(ci.file_digests(ROOT)) + [("core/canonical/new.py", "abc")])
    assert "core/canonical/new.py" in ci.compare(theirs, ROOT)


# ----------------------------------------------------- the artifact --


def test_the_artifact_is_a_fixed_point():
    sys.path.insert(0, str(ROOT / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes

    assert canonical_bytes(ci.identity_document(ROOT)) == ARTIFACT.read_bytes()


def test_the_artifact_keeps_version_and_digest_as_different_things():
    """One is a compatibility statement, the other an identity. Merging
    them is what created the gap."""
    document = yaml.safe_load(ARTIFACT.read_text())
    assert document["core_version"] == "1.0.0"
    for surface in document["surfaces"].values():
        assert surface["digest"].startswith("sha256:")
    assert "COMPATIBILITY" in document["what_each_one_is_for"]["version"]
    assert "IDENTITY" in document["what_each_one_is_for"]["digest"]


def test_the_two_surfaces_are_published_with_different_digests():
    """One digest for two disjoint tracks would have been a claim that
    they move together, and they have no imports between them at all.

    Derived fresh rather than read: the shape of the document is the
    DERIVER's property, and a lock that read the emitted file would pass
    unchanged while the code that writes it published one surface."""
    document = ci.identity_document(ROOT)
    surfaces = document["surfaces"]
    assert set(surfaces) == {"twin_compiler", "evidence_platform"}
    assert surfaces["twin_compiler"]["digest"] != surfaces["evidence_platform"]["digest"]


def test_the_artifact_records_which_track_each_party_binds_and_from_what():
    """`binds` without `imports` would be a declaration. The counts are
    what make it a measurement a reader can check."""
    document = ci.identity_document(ROOT)
    bindings = document["bindings"]
    assert set(bindings) >= {"DAQ", "SCL"}
    for label, binding in bindings.items():
        if binding["binds"] in ("NOT_READABLE", "NEITHER"):
            continue
        counts = binding["imports"]
        assert counts[binding["binds"]] > 0, f"{label} binds a track it never imports"
        assert binding["digest_it_should_check"] == (
            document["surfaces"][binding["binds"]]["digest"])


def test_the_artifact_states_the_correction_rather_than_quietly_replacing_it():
    """A defect fixed without a record reads, later, as though it never
    happened -- and the same class of defect has now recurred twice."""
    document = ci.identity_document(ROOT)
    correction = document["the_correction"]
    assert "ZERO times" in correction
    assert "ORIGINAL CORE-VERSION DEFECT RECURRING" in correction
    assert "ZERO imports in either direction" in document["why_there_are_two"]


def test_the_artifact_says_what_is_outside_the_surface_and_why():
    """So a later reader can tell `left out deliberately` from
    `forgotten`."""
    document = yaml.safe_load(ARTIFACT.read_text())
    outside = document["deliberately_outside"]
    assert "architecture/invariants.yaml" in outside
    assert "bend" in outside["structures/, materials/, evidence/, scout/, execution/"]
    for reason in outside.values():
        assert len(reason) > 30, "a reason that is not a reason"


def test_the_artifact_is_not_part_of_the_surface_it_describes():
    """A projection is not a source, and a fixed point cannot be reached
    by an artifact that feeds itself."""
    document = yaml.safe_load(ARTIFACT.read_text())
    paths = {entry["path"]
             for surface in document["surfaces"].values()
             for entry in surface["files"]}
    assert paths, "a surface listing no files would pass this vacuously"
    assert not any(p.startswith("architecture/") for p in paths)
    assert "architecture/exchange/" in document["deliberately_outside"]


def test_the_artifact_credits_the_party_that_found_the_gap():
    """The observation was another party's and could not be acted on
    there. Recording that is not politeness -- it is what lets a reader
    check the finding against its source."""
    document = yaml.safe_load(ARTIFACT.read_text())
    why = document["why_a_digest_as_well_as_a_version"].lower()
    assert "census" in why and "could not act on it" in why


def test_the_surface_matches_what_is_actually_in_the_core_package():
    """If a real core file is missing from the declared surface, the
    digest is silent about a file a bend would change. Measured against
    the tree rather than trusted."""
    actual = {p.relative_to(ROOT).as_posix()
              for p in (ROOT / "core").rglob("*.py")
              if "__pycache__" not in p.parts}
    assert actual == set(ci.CORE_SURFACE), (
        f"core package and declared surface disagree: "
        f"{actual ^ set(ci.CORE_SURFACE)}")


# ------------------------------------ which track a party actually binds --
#
# THE DEFECT THESE EXIST FOR. The first version of this module published
# ONE digest, over `core/canonical` + `core/projection`, and described it
# as the thing a binding party checks. The binding party imports from
# those packages ZERO times. So the surface a party checks is now
# measured, and every check below is driven over BOTH answers -- a lock
# whose inputs cannot reach both branches tests nothing about the branch.


def _consumer(directory, name, lines):
    """A tree that imports what it is told to, and nothing else."""
    root = pathlib.Path(directory) / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "consumer.py").write_text("\n".join(lines) + "\n")
    return root


def test_imported_tracks_counts_each_track_separately():
    with tempfile.TemporaryDirectory() as directory:
        both = _consumer(directory, "both", [
            "from evidence.types import Referent",
            "from evidence.pool import EvidencePool",
            "import scout.pipeline",
            "from core.canonical.state import State",
        ])
        counts = ci.imported_tracks(both)
        assert counts["evidence_platform"] == 3
        assert counts["twin_compiler"] == 1


def test_binding_track_answers_either_track_and_not_only_one():
    """Driven over both, because a check that could only ever return
    `evidence_platform` would pass just as well on a constant."""
    with tempfile.TemporaryDirectory() as directory:
        twin = _consumer(directory, "twin", [
            "from core.canonical.state import State",
            "import morpho.compiler",
        ])
        platform = _consumer(directory, "platform", [
            "from evidence.types import Referent",
            "import materials.registry",
        ])
        assert ci.binding_track(twin) == "twin_compiler"
        assert ci.binding_track(platform) == "evidence_platform"


def test_binding_track_refuses_a_tie_rather_than_picking_one():
    """A consumer split evenly across two disjoint tracks is not bound to
    either in any sense this can name, and guessing would put a digest
    against a binding nobody made."""
    with tempfile.TemporaryDirectory() as directory:
        split = _consumer(directory, "split", [
            "import core.canonical.state",
            "import evidence.types",
        ])
        assert ci.imported_tracks(split) == {"twin_compiler": 1,
                                             "evidence_platform": 1}
        assert ci.binding_track(split) is None


def test_binding_track_is_none_when_a_party_imports_neither():
    with tempfile.TemporaryDirectory() as directory:
        stranger = _consumer(directory, "stranger", [
            "import json", "from pathlib import Path"])
        assert ci.binding_track(stranger) is None


def test_covers_what_is_bound_refuses_the_exact_defect_that_shipped():
    """THIS IS THE ORIGINAL FAILURE, REPLAYED. A party importing only the
    evidence platform, checked against a twin-compiler digest, must be
    told the digest is about code it does not use -- and told with the
    counts, so the refusal is a measurement and not an opinion."""
    with tempfile.TemporaryDirectory() as directory:
        platform = _consumer(directory, "platform", [
            "from evidence.types import Referent",
            "from evidence.pool import EvidencePool",
        ])
        covers, why = ci.covers_what_is_bound(platform, "twin_compiler")
        assert covers is False
        assert "2 times" in why and "0 times" in why

        covers, why = ci.covers_what_is_bound(platform, "evidence_platform")
        assert covers is True
        assert "evidence_platform" in why


def test_covers_what_is_bound_refuses_in_the_other_direction_too():
    """Symmetric, so the check is about the binding rather than about
    which track happens to be named."""
    with tempfile.TemporaryDirectory() as directory:
        twin = _consumer(directory, "twin", ["import core.canonical.state"])
        assert ci.covers_what_is_bound(twin, "twin_compiler")[0] is True
        assert ci.covers_what_is_bound(twin, "evidence_platform")[0] is False


def test_covers_what_is_bound_refuses_when_there_is_no_binding_at_all():
    """`False` here means something different from `False` above, and the
    reason has to say which -- an unbound party is not a mismatched one."""
    with tempfile.TemporaryDirectory() as directory:
        stranger = _consumer(directory, "stranger", ["import json"])
        covers, why = ci.covers_what_is_bound(stranger, "evidence_platform")
        assert covers is False
        assert "neither" in why


def test_a_vendored_checkout_importing_itself_is_not_counted():
    """A consumer that vendors this repository would otherwise be
    measured as importing whatever the vendored copy imports, which is a
    mirror counted as a source."""
    with tempfile.TemporaryDirectory() as directory:
        consumer = _consumer(directory, "consumer", ["import evidence.types"])
        vendored = consumer / "vendor" / "ste" / "core" / "canonical"
        vendored.mkdir(parents=True)
        (vendored / "state.py").write_text(
            "import core.canonical.schema\nimport morpho.ir\n")
        counts = ci.imported_tracks(consumer)
        assert counts == {"twin_compiler": 0, "evidence_platform": 1}


def test_every_declared_evidence_surface_file_is_actually_here():
    """The twin surface is checked against the package it covers. The
    evidence surface is a chosen subset of six packages, so it cannot be
    checked that way -- but a declared path that does not exist would
    make `core_digest` refuse, and the refusal should be found here
    rather than by a binding party."""
    for relative in ci.EVIDENCE_SURFACE:
        assert (ROOT / relative).is_file(), f"declared but not here: {relative}"
    assert ci.core_digest(ROOT, ci.EVIDENCE_SURFACE).startswith("sha256:")


def test_the_two_tracks_share_no_packages():
    """The disjointness is the whole reason there are two digests. If
    the package lists overlapped, a single file could move both and the
    separation would be a label rather than a fact."""
    twin = set(ci.TRACK_PACKAGES["twin_compiler"])
    platform = set(ci.TRACK_PACKAGES["evidence_platform"])
    assert twin & platform == set()
    for name, surface in ci.SURFACES.items():
        heads = {path.split("/")[0] for path in surface}
        assert heads <= set(ci.TRACK_PACKAGES[name]), (
            f"{name} digests files outside the packages it claims to be about")
