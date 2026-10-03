"""The core, identified by its bytes rather than by its label.

WHY. `architecture/core.yaml` declares `version: 1.0.0`, and that
version moves ONLY under bend_protocol -- correctly, since a routine
release must not renumber the core. The consequence is that many
different core commits legitimately carry the same label, and a sibling
that pins `core@1.0.0` cannot tell which of them it bound.

THAT IS NOT A HYPOTHETICAL. The acquisition channel's independently
recorded census observed exactly it: two checkouts of this repository,
on different commits, three days apart, both reporting the version
string 1.0.0, with the ancestry between them undeterminable from that
machine. It recorded the finding and said plainly that it could not act
on it -- "what Phase 39 did not do, and could not, is say anything about
the OTHER parties". Naming which core a label refers to is this
repository's act, because this repository declares the label.

SO THE LABEL GAINS A DIGEST. `core@1.0.0` stays the compatibility
statement; the digest says WHICH core. A party can then check the core
it holds against the core it bound -- bytes, not trust, applied to the
version string itself, which is the one place this project had been
trusting a name.

WHAT IS HASHED, AND WHY IT IS NOT EVERYTHING. Only what a bend changes.
Adding an invariant row, writing a doc, or landing a vertical is not a
bend and must not move a digest -- if it did, the digest would move on
almost every commit and would stop distinguishing anything, which is the
failure mode of a fingerprint that covers too much.

AND THERE ARE TWO OF THEM, WHICH IS A CORRECTION AND NOT A FEATURE. The
first version published ONE digest, over `core/canonical` and
`core/projection`, described as the thing a binding party checks. No
binding party imports that code: the acquisition channel reaches into
this repository hundreds of times -- 291 when first measured on
2026-09-03, 293 on 2026-09-05 as that party develops -- and into that
track ZERO, on every measurement. The digest covered
exactly what nobody uses. See the note on TWIN_SURFACE below -- it is
the original core-version defect one level down, and every function
here now takes the surface it is about rather than assuming one.
"""

from __future__ import annotations

import hashlib
import pathlib
from typing import Dict, List, Optional, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: THE DIGEST HAD THE WRONG REFERENT, AND THE MEASUREMENT IS EXACT.
#:
#: This surface covers `core/canonical` and `core/projection`. The
#: acquisition channel -- the party that BINDS this core -- imports from
#: this repository 291 times when first measured (2026-09-03): evidence
#: 125, materials 105, scout 46, retrieval 11, structures 4. That total
#: MOVES as the party develops -- 293 two days later -- and the count is
#: recorded with its date for that reason. What does not move is the
#: other column: it imports from `core` ZERO times, and that zero is the
#: load-bearing half.
#:
#: So the digest published as "the thing a binding party checks" covered
#: exactly the packages that party never touches, and none of what it
#: does. A change to `evidence/types.py` would not have moved it.
#:
#: THIS IS THE ORIGINAL CORE-VERSION DEFECT, RECURRING. That one set the
#: version from this repository's packaging -- the wrong referent, in a
#: way that quietly weakened every claim made against it. This is the
#: same error one level down: the right KIND of identity, over the wrong
#: BODY of code.
#:
#: The cause is that this repository holds TWO DISJOINT TRACKS. The
#: acquisition channel's own reconnaissance says so, and it is confirmed
#: here by import analysis: zero imports in either direction between
#: {core, morpho, backends, runtime, adapters, renderer} and {evidence,
#: scout, retrieval, materials, experiment, workbench}. Two unrelated
#: projects sharing one repository. One digest could never have been
#: right for both.
#:
#: So there are two surfaces, each named, each digested, and the
#: register records WHICH ONE A PARTY BINDS -- measured from what it
#: imports, not assumed.

#: Track 1: the deterministic scene compiler. Canonical state, its
#: schema, versioning, deltas, validation, and the projection contract.
#: The "digital twin" track.
#:
#: Deliberately a DECLARED list and not a glob. A glob would silently
#: widen the core the first time somebody added a file next to these,
#: and widening the core without a bend is exactly what bend_protocol
#: forbids. Adding a path here is therefore itself a core change and
#: shows up as a moved digest.
TWIN_SURFACE: Tuple[str, ...] = (
    "core/__init__.py",
    "core/canonical/__init__.py",
    "core/canonical/delta.py",
    "core/canonical/schema.py",
    "core/canonical/state.py",
    "core/canonical/validation.py",
    "core/canonical/version.py",
    "core/projection/__init__.py",
    "core/projection/project.py",
)

#: Track 2: the evidence platform. What the acquisition channel actually
#: binds -- the types whose identities those imports resolve against.
#: Deliberately the IDENTITY-BEARING modules only, not every file in
#: those packages: a digest that moved on any change to any of six large
#: packages would move on nearly every commit and distinguish nothing,
#: which is the failure of a fingerprint that covers too much.
EVIDENCE_SURFACE: Tuple[str, ...] = (
    "evidence/types.py",
    "evidence/identity.py",
    "evidence/classes.py",
    "evidence/admission.py",
    "evidence/pool.py",
)

#: name -> surface. Two tracks, because the repository holds two.
SURFACES: Dict[str, Tuple[str, ...]] = {
    "twin_compiler": TWIN_SURFACE,
    "evidence_platform": EVIDENCE_SURFACE,
}

#: Kept as the default so existing callers keep the meaning they had,
#: and so the change shows up as an ADDITION rather than a silent
#: redefinition of what `core_digest()` returns.
CORE_SURFACE: Tuple[str, ...] = TWIN_SURFACE

#: NOT hashed, and each for a stated reason -- so that a later reader
#: can tell "left out deliberately" from "forgotten".
DELIBERATELY_OUTSIDE: Dict[str, str] = {
    "architecture/invariants.yaml": (
        "invariant ROWS are added without bending; a registry that moved "
        "the core digest would move it on almost every commit"),
    "architecture/core.yaml": (
        "it declares the version this digest annotates. Hashing it would "
        "make the digest depend on the digest's own publication"),
    "architecture/exchange/": (
        "derived artifacts. A projection is not a source, and a fixed "
        "point cannot be reached by an artifact that feeds itself"),
    "structures/, materials/, evidence/, scout/, execution/": (
        "verticals and layers EXTEND the core; they never define it. A "
        "vertical that changed the core digest would mean the core had "
        "been widened to admit it, which is the thing bend_protocol "
        "forbids by name"),
}


class CoreIdentityError(RuntimeError):
    """The declared core surface does not match the tree."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digests(root: pathlib.Path = REPO_ROOT,
                 surface: Optional[Tuple[str, ...]] = None
                 ) -> Tuple[Tuple[str, str], ...]:
    """Each surface file, hashed. Sorted by path so the result does not
    depend on how the filesystem happens to enumerate."""
    missing: List[str] = []
    digests: List[Tuple[str, str]] = []
    for relative in sorted(CORE_SURFACE if surface is None else surface):
        candidate = root / relative
        if not candidate.is_file():
            missing.append(relative)
            continue
        digests.append((relative, _sha256(candidate.read_bytes())))
    if missing:
        raise CoreIdentityError(
            f"the declared core surface names files that are not here: "
            f"{missing}. A digest over a surface that has moved is a digest "
            f"of something else, and computing one anyway would be worse "
            f"than failing")
    return tuple(digests)


def core_digest(root: pathlib.Path = REPO_ROOT,
                surface: Optional[Tuple[str, ...]] = None) -> str:
    """One digest over the whole surface.

    Over the PATH AND THE CONTENT of each file, not the content alone:
    two files whose bodies were swapped are a different core, and a
    digest that could not tell them apart would be hashing a multiset
    rather than a schema.
    """
    joined = "\n".join(f"{path}:{digest}"
                       for path, digest in file_digests(root, surface))
    return "sha256:" + _sha256(joined.encode("utf-8"))


#: The packages each surface belongs to, for deciding which track a
#: consumer actually binds.
TRACK_PACKAGES: Dict[str, Tuple[str, ...]] = {
    "twin_compiler": ("core", "morpho", "backends", "runtime", "adapters",
                      "renderer"),
    "evidence_platform": ("evidence", "scout", "retrieval", "materials",
                          "experiment", "workbench", "structures"),
}


def imported_tracks(consumer: pathlib.Path) -> Dict[str, int]:
    """Which of this repository's tracks a consumer actually imports.

    MEASURED, NOT DECLARED. A party's binding is what its code reaches
    for, and the whole defect this function exists to prevent was a
    digest published for a track the binding party never touches. Its
    own submodule copy is skipped -- a vendored checkout importing
    itself is not a consumer.
    """
    import ast

    counts: Dict[str, int] = {name: 0 for name in TRACK_PACKAGES}
    for path in consumer.rglob("*.py"):
        parts = set(path.parts)
        if parts & {".git", "__pycache__", "node_modules", "vendor"}:
            continue
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            names = ([alias.name for alias in node.names]
                     if isinstance(node, ast.Import)
                     else [node.module] if isinstance(node, ast.ImportFrom)
                     else [])
            for name in names:
                head = (name or "").split(".")[0]
                for track, packages in TRACK_PACKAGES.items():
                    if head in packages:
                        counts[track] += 1
    return counts


def binding_track(consumer: pathlib.Path) -> Optional[str]:
    """The track a consumer binds, or None when it imports neither.

    Returns the track it imports MORE of, and None on a tie -- a
    consumer split evenly across two disjoint tracks is not bound to
    either in any sense this can name, and guessing would put a digest
    against a binding nobody made.
    """
    counts = imported_tracks(consumer)
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    if not ranked or ranked[0][1] == 0:
        return None
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def covers_what_is_bound(consumer: pathlib.Path,
                         surface_name: str) -> Tuple[bool, str]:
    """Does a published digest cover the track this consumer imports?

    THE REFUSAL THIS MODULE NOW EXISTS FOR. A digest over a track the
    binding party never touches is the right KIND of identity over the
    wrong BODY of code, and a party checking it would verify something
    it does not use while a change to what it does use moved nothing.
    """
    bound = binding_track(consumer)
    if bound is None:
        return False, ("this consumer imports neither track, or splits evenly "
                       "between them -- there is no binding for a digest to "
                       "be about")
    if bound != surface_name:
        counts = imported_tracks(consumer)
        return False, (
            f"it imports {bound} {counts[bound]} times and {surface_name} "
            f"{counts[surface_name]} times, so a {surface_name} digest is "
            f"about code this party does not use")
    return True, f"it imports {bound}, which is what this digest covers"


def verify(expected: str, root: pathlib.Path = REPO_ROOT,
           surface: Optional[str] = None) -> Dict[str, object]:
    """Check the core HELD against the core BOUND.

    This is the function a binding party runs. It answers the question
    the version string cannot: not "is this core 1.0.0" -- many are --
    but "is this the 1.0.0 I bound".

    IT TAKES THE SURFACE BY NAME, and that is not a convenience. Without
    it this function could only ever check the twin track, so a party
    binding the evidence platform -- which is every party measured --
    had no way to check what it actually bound. The correction one call
    up would have been cosmetic if the checking function itself still
    only spoke about the track nobody imports.

    Returns the per-file comparison rather than a bare boolean, because
    a mismatch that cannot say WHICH file moved leaves the reader with
    the same problem the label left them: a difference with no address.
    """
    if surface is not None and surface not in SURFACES:
        raise CoreIdentityError(
            f"no surface named {surface!r}; this repository publishes "
            f"{sorted(SURFACES)}. Verifying against a surface that does not "
            f"exist would either fail for the wrong reason or, worse, fall "
            f"back to a default and report a match about other code")
    files = SURFACES[surface] if surface is not None else None
    actual = core_digest(root, files)
    return {
        "matches": actual == expected,
        "surface": surface or "twin_compiler",
        "expected": expected,
        "actual": actual,
        "files": [{"path": path, "sha256": digest}
                  for path, digest in file_digests(root, files)],
    }


def compare(other: Tuple[Tuple[str, str], ...],
            root: pathlib.Path = REPO_ROOT,
            surface: Optional[Tuple[str, ...]] = None) -> Tuple[str, ...]:
    """Which surface files differ from another party's reading of them.

    A party holding a core that does not match can call this with its
    own file digests and be told exactly which files moved. Paths
    present on one side only are reported too -- a surface that gained
    or lost a file is a bend, and the most important thing to say about
    it is which file.
    """
    mine = dict(file_digests(root, surface))
    theirs = dict(other)
    differing = [path for path in sorted(set(mine) | set(theirs))
                 if mine.get(path) != theirs.get(path)]
    return tuple(differing)


# --------------------------------------------------------------- emit --


#: Where the binding parties live, for measuring what they import.
CONSUMERS: Dict[str, str] = {
    "DAQ": "/home/user/notationsystems/notations-acquisition-channel",
    "SCL": "/home/user/notationsystems/scientific-compute-layer",
}


def identity_document(root: pathlib.Path = REPO_ROOT) -> dict:
    import re

    core_yaml = (root / "architecture" / "core.yaml").read_text()
    match = re.search(r"^version:\s*\"?([\w.\-]+)\"?", core_yaml, re.MULTILINE)
    version = match.group(1) if match else ""

    surfaces = {}
    for name, files in SURFACES.items():
        digests = file_digests(root, files)
        surfaces[name] = {
            "digest": core_digest(root, files),
            "files": [{"path": path, "sha256": digest} for path, digest in digests],
            "empty_files": [path for path, digest in digests
                            if digest == _sha256(b"")],
        }

    bindings = {}
    for label, location in CONSUMERS.items():
        consumer = pathlib.Path(location)
        if not consumer.is_dir():
            bindings[label] = {"binds": "NOT_READABLE",
                               "imports": {}, "reason": f"{location} is not here"}
            continue
        bound = binding_track(consumer)
        bindings[label] = {
            "binds": bound or "NEITHER",
            "imports": imported_tracks(consumer),
            "digest_it_should_check": surfaces[bound]["digest"] if bound else "",
        }

    return {
        "extends": f"core@{version}",
        "generated_by": "architecture/core_identity.py",
        "artifact": "core_identity",
        "owner": "STE",
        "core_version": version,
        "the_correction": (
            "AN EARLIER VERSION OF THIS ARTIFACT PUBLISHED ONE DIGEST, over "
            "core/canonical and core/projection, described as the thing a "
            "binding party checks. Measured: the acquisition channel imports "
            "from this repository hundreds of times (291 measured "
            "2026-09-03, 293 on 2026-09-05) and from those packages ZERO "
            "times; the compute layer imports 41 and zero. The digest "
            "covered exactly the code no binding party touches, and a change "
            "to evidence/types.py -- imported 125 times -- would not have "
            "moved it. That is the ORIGINAL CORE-VERSION DEFECT RECURRING: "
            "the right KIND of identity over the wrong BODY of code"),
        "why_a_digest_as_well_as_a_version": (
            "the version moves only under bend_protocol, so many different "
            "core commits legitimately carry the same label. THE ACQUISITION "
            "CHANNEL'S CENSUS OBSERVED EXACTLY THAT: two checkouts of this "
            "repository, on different commits, three days apart, both "
            "reporting 1.0.0, ancestry undeterminable from where it stood. It "
            "recorded the finding and said plainly it could not act on it -- "
            "naming which core a label refers to is this repository's act, "
            "because this repository declares the label"),
        "why_there_are_two": (
            "this repository holds TWO DISJOINT TRACKS. The acquisition "
            "channel's own reconnaissance says so, and import analysis "
            "confirms it: ZERO imports in either direction between {core, "
            "morpho, backends, runtime, adapters, renderer} and {evidence, "
            "scout, retrieval, materials, experiment, workbench}. Two "
            "unrelated projects sharing one repository, so one digest could "
            "never have been right for both"),
        "surfaces": surfaces,
        "bindings": bindings,
        "what_each_one_is_for": {
            "version": "the COMPATIBILITY statement -- what a party may rely on",
            "digest": "the IDENTITY -- which core that statement was made about",
            "surface": "WHICH BODY OF CODE the identity is over, which is the "
                       "part the first version got wrong",
        },
        "surface_is_declared_not_globbed": (
            "a glob would silently widen a track the first time a file was "
            "added beside these, and widening the core without a bend is "
            "what bend_protocol forbids. The evidence surface is the "
            "IDENTITY-BEARING modules only, not every file in six packages: "
            "a digest moving on any change to any of them would move on "
            "nearly every commit and distinguish nothing"),
        "deliberately_outside": dict(DELIBERATELY_OUTSIDE),
        "how_a_party_checks_it": (
            "core_identity.covers_what_is_bound(consumer_path, surface_name) "
            "first -- to establish the digest is about code the party "
            "actually imports -- then verify(digest, root, surface_name) "
            "over its own copy. BOTH arguments matter: checking a digest "
            "without checking its referent is what produced the defect "
            "above, and verify() without a surface name checks the twin "
            "track, which is not what any measured party binds"),
        "what_this_does_not_claim": (
            "that a matching digest means two parties agree about anything "
            "beyond those bytes. It is an identity, not a warrant: it says "
            "which code, and says nothing about whether that code is right"),
    }


def emit(root: pathlib.Path = REPO_ROOT) -> pathlib.Path:
    import sys as _sys
    _sys.path.insert(0, str(root / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes, canonical_sha256

    document = identity_document(root)
    out = root / "architecture" / "exchange" / "core_identity.yaml"
    out.write_bytes(canonical_bytes(document))
    (root / "architecture" / "exchange" / "core_identity.sha256").write_text(
        canonical_sha256(document) + "\n")
    return out


def main() -> int:
    import sys

    document = identity_document()
    print("=== CORE IDENTITY: TWO TRACKS, AND WHICH ONE IS BOUND ===")
    print(f"  version : {document['core_version']}")
    for name, surface in sorted(document["surfaces"].items()):
        print(f"\n  {name}")
        print(f"    digest : {surface['digest']}")
        print(f"    files  : {len(surface['files'])} "
              f"({len(surface['empty_files'])} empty)")
    print("\n=== WHAT EACH PARTY ACTUALLY IMPORTS ===")
    for label, binding in sorted(document["bindings"].items()):
        print(f"  {label}: binds {binding['binds']}  imports={binding['imports']}")
    print("\n  The first version published ONE digest, over the track no")
    print("  binding party imports. That is the original core-version")
    print("  defect recurring: right kind of identity, wrong body of code.")
    if "--emit" in sys.argv:
        out = emit()
        print(f"\n  wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
