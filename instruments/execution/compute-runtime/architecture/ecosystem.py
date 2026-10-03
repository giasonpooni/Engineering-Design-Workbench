"""The ecosystem register: what is an apparatus, what is a vendored
input, and what is merely present.

WHY THIS IS DERIVED AND NOT WRITTEN. A company-level map of "our
systems" is exactly the kind of claim that is true when written and
false a month later, and its falseness is invisible because nothing
recomputes it. So this measures the tree on every run and refuses to
name anything it cannot evidence.

THE FINDING IT WAS BUILT AROUND: ORG OWNERSHIP IS NOT AUTHORSHIP.
Twenty-two of the twenty-four repositories in reach are third-party
snapshots, and ELEVEN of those sit under the `notationsystems/` GitHub
org while being someone else's work -- `notationsystems/topopy` is Dan
Maljovec's topopy, `notationsystems/RiemannFM` carries Yongli Mou's
copyright, `notationsystems/SP1-zero-knowledge-virtual-machine` is
Succinct's SP1. A coherence exercise that read the org prefix as a
provenance claim would have declared twenty-four apparatuses and been
wrong about twenty-one of them.

That is the mirror rule at REPOSITORY SCALE, and it is the same rule
the invariant register already enforces per file: a mirror is not a
source, byte-identity is what makes it dangerous, and only provenance
separates a copy from its origin. A fork under your own org is the most
convincing mirror there is, because the URL agrees with the claim.

A FOLDER IS NOT AN ECOSYSTEM. Twelve of the vendored repositories are
referenced by NOTHING in any apparatus. They are present, and presence
is not participation. They are recorded UNREFERENCED rather than listed
as components, on exactly the reasoning that an unreached gate is a
silence rather than a clean result: a component nothing calls
contributes nothing, and counting it inflates the system.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SIBLING_ROOT = pathlib.Path("/home/user/notationsystems")

#: The GitHub org this company publishes under. Named here so the rule
#: below can be stated against it: membership of this org is NOT
#: evidence of authorship, and this constant exists to be disbelieved.
ORG = "notationsystems"

#: Verdicts. Deliberately three, not two: a repository this cannot
#: evidence either way is UNRESOLVED and is never rounded toward ours.
APPARATUS = "APPARATUS"
VENDORED_INPUT = "VENDORED_INPUT"
UNRESOLVED = "UNRESOLVED"

#: How much of the system a vendored input actually carries.
INTEGRATED = "INTEGRATED"      # named by production or build files
MENTIONED = "MENTIONED"        # named only in prose
UNREFERENCED = "UNREFERENCED"  # named nowhere in any apparatus

#: THE MEASURING APPARATUS IS NOT EVIDENCE ABOUT WHAT IT MEASURES.
#:
#: Found by running this: `topopy` and `RiemannFM` came back INTEGRATED
#: while a plain grep found no reference to either anywhere. The only
#: file matching was THIS ONE -- its docstring cites them as examples of
#: the mirror finding, and the citation counted as evidence of the
#: integration it was written to deny. An instrument that names the
#: things it classifies will classify its own prose.
#:
#: The same class as the emitted invariant register being re-read as its
#: own source (26 rows became 77, every one contested), and as the three
#: contaminated attempts to locate a derived fact in prose BY ITS VALUE.
#: It is the deriving-party exclusion, one level out: a party cannot
#: witness a fact about the act it is currently performing.
#:
#: Declared rather than pattern-matched, and locked both ways -- every
#: path must exist, and nothing outside the instrument may be listed,
#: since a too-wide exclusion would hide a real dependency.
MEASURING_APPARATUS: Tuple[str, ...] = (
    "architecture/ecosystem.py",
    "architecture/exchange/ecosystem_register.yaml",
    "architecture/exchange/ecosystem_register.sha256",
    "tests/test_ecosystem_register.py",
    "scripts/mutate_ecosystem_checks.py",
    "docs/ECOSYSTEM_REGISTER.md",
)

#: BUILD OUTPUT IS NOT SOURCE. `zk/` alone is 5.6 GB of Rust build
#: artifacts in this repository, and the first version of the scan read
#: every file under it into memory: the process was OOM-KILLED. A
#: measurement that cannot run is worth exactly as much as one nobody
#: runs, which is the same failure as the 75-second version by a
#: different route.
#:
#: These directories are skipped because what is in them is GENERATED,
#: and a generated file naming a dependency is evidence about the
#: generator, not about what this repository depends on.
SKIP_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".tox",
    "target", "build", "dist", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "site-packages", ".cargo",
})

#: A source file naming a dependency is a sentence; a 2 MB file that
#: happens to contain the string is a haystack. Capped rather than
#: unbounded so one vendored blob cannot dominate the reading.
MAX_FILE_BYTES = 2 * 1024 * 1024

#: Files whose mention of a name is prose rather than dependence.
_PROSE_SUFFIXES = (".md", ".txt", ".rst")
#: Files whose mention is dependence.
_LOAD_BEARING_SUFFIXES = (".py", ".rs", ".toml", ".yaml", ".yml", ".cfg", ".sh")


#: An apparatus states its own role HERE, in its own repository. The
#: file is deliberately per-repository and not a central list: a central
#: roster is one party writing every other party's self-description,
#: which is the authorship error this whole register exists to catch.
APPARATUS_DECLARATION = "architecture/apparatus.yaml"
NOT_DECLARED = "NOT_DECLARED"


class EcosystemError(RuntimeError):
    """A repository could not be classified on evidence."""


@dataclass(frozen=True)
class RepoFacts:
    """What was READ from one repository, before any verdict."""

    name: str
    path: pathlib.Path
    remote: str
    branch: str
    commit: str
    commit_count: int
    authors: Tuple[str, ...]
    copyright_holders: Tuple[str, ...]
    declares_core: Tuple[str, ...]   # architecture files naming `extends: core@`
    bound_core: str
    declared_upstream: str = ""
    role: str = NOT_DECLARED
    role_source: str = ""

    @property
    def under_our_org(self) -> bool:
        return self.remote.startswith(f"{ORG}/")


@dataclass(frozen=True)
class Classification:
    """A verdict, and the evidence that forced it."""

    facts: RepoFacts
    verdict: str
    because: str
    #: Set when the repository is under our org and is NOT ours. This is
    #: the field the whole module exists to be able to populate.
    mirrored_under_our_org: bool
    upstream_authors: Tuple[str, ...]
    integration: str = ""
    referenced_by: Tuple[Tuple[str, int], ...] = ()


def _git(path: pathlib.Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(path), *args],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


#: Phrases that appear in LICENCE BOILERPLATE rather than in a grant.
#: Apache-2.0 says "Licensor shall mean the copyright owner or entity
#: authorized by the copyright owner" -- and the first version of the
#: extractor read that as a copyright holder, which handed a
#: VENDORED_INPUT verdict to every Apache-licensed repository on no
#: evidence at all. `morphohdl` was disowned that way, and the sibling's
#: independently-recorded census -- which lists it as a company
#: repository -- is what exposed it.
#:
#: The error ran in the direction that made the ecosystem look SMALLER
#: and the classifier look more decisive, which is the harder direction
#: to notice: a wrong exclusion produces no loud consequence.
_BOILERPLATE = (
    "shall mean", "owner or entity", "notice", "means the", "as defined",
    "holder or", "holders and", "and/or",
)


def _copyright_holders(path: pathlib.Path) -> Tuple[str, ...]:
    """Whoever a LICENSE actually GRANTS as. A third-party copyright in
    a repository under our org is the most direct evidence that the org
    prefix is not a provenance claim -- which is exactly why it must not
    be matched out of the licence's own definitions section.

    A real grant carries a YEAR. That is what separates
    `Copyright (c) 2018, Dan Maljovec` from `the copyright owner or
    entity authorized by`, and it is checked rather than assumed.
    """
    holders: List[str] = []
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "NOTICE"):
        candidate = path / name
        if not candidate.is_file():
            continue
        head = candidate.read_text(errors="replace")[:8000]
        for match in re.finditer(r"[Cc]opyright\s+(?:\(c\)\s*)?([^\n]{3,80})", head):
            holder = match.group(1).strip()
            if not re.search(r"(19|20)\d\d", holder):
                continue
            if any(phrase in holder.lower() for phrase in _BOILERPLATE):
                continue
            holders.append(holder)
    return tuple(dict.fromkeys(holders))[:4]


#: Where a package states its own origin. A repository URL pointing
#: outside our org, written by the project itself, is the strongest
#: evidence available and beats every heuristic here: it is a
#: SELF-DECLARATION of provenance, which is the one form of authorship
#: evidence this project already trusts everywhere else.
_METADATA_FILES = ("Cargo.toml", "pyproject.toml", "setup.py", "package.json")


def _declared_upstream(path: pathlib.Path) -> str:
    for name in _METADATA_FILES:
        candidate = path / name
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(errors="replace")[:20000]
        except OSError:
            continue
        for match in re.finditer(
                r'(?:repository|homepage|url)"?\s*[:=]\s*"([^"]+)"', text):
            url = match.group(1)
            if "github.com" not in url and "gitlab" not in url:
                continue
            owner = re.sub(r"^https?://[^/]+/", "", url).split("/")[0]
            if owner and owner.lower() != ORG:
                return url
    return ""


def _declares_core(path: pathlib.Path) -> Tuple[Tuple[str, ...], str]:
    """Architecture files binding a core version. THIS is what an
    apparatus does that a vendored snapshot does not: it declares which
    core it resolves against, in files it authored."""
    architecture = path / "architecture"
    if not architecture.is_dir():
        return (), ""
    declaring: List[str] = []
    version = ""
    for candidate in sorted(architecture.rglob("*.yaml")):
        try:
            text = candidate.read_text(errors="replace")
        except OSError:
            continue
        match = re.search(r"extends:\s*(core@[\w.\-]+)", text)
        if match:
            declaring.append(candidate.relative_to(path).as_posix())
            version = version or match.group(1)
    return tuple(declaring), version


def _declared_role(path: pathlib.Path) -> Tuple[str, str]:
    """`(role, source_file)` as the apparatus states it, or NOT_DECLARED.

    An absent declaration is REPORTED, never filled in from here. A role
    written on another party's behalf would be a self-declaration this
    party is not entitled to make -- provenance entitlement, applied to
    the sentence that says what a repository is for.
    """
    candidate = path / APPARATUS_DECLARATION
    if not candidate.is_file():
        return NOT_DECLARED, ""
    match = re.search(r"^role:\s*(?:[|>][-+]?\s*\n\s+)?(.+)$",
                      candidate.read_text(errors="replace"), re.MULTILINE)
    if not match:
        return NOT_DECLARED, APPARATUS_DECLARATION
    return match.group(1).strip(), APPARATUS_DECLARATION


def read_facts(name: str, path: pathlib.Path) -> RepoFacts:
    remote = _git(path, "remote", "get-url", "origin")
    remote = re.sub(r"^https?://[^/]+/", "", remote)
    remote = re.sub(r"\.git$", "", remote)
    authors = tuple(dict.fromkeys(
        line for line in _git(path, "log", "--format=%an").splitlines() if line))
    declaring, bound = _declares_core(path)
    role, role_source = _declared_role(path)
    count = _git(path, "rev-list", "--count", "HEAD")
    return RepoFacts(
        name=name,
        path=path,
        remote=remote,
        branch=_git(path, "rev-parse", "--abbrev-ref", "HEAD"),
        commit=_git(path, "rev-parse", "HEAD")[:12],
        commit_count=int(count) if count.isdigit() else 0,
        authors=authors[:6],
        copyright_holders=_copyright_holders(path),
        declares_core=declaring,
        bound_core=bound,
        declared_upstream=_declared_upstream(path),
        role=role,
        role_source=role_source,
    )


#: The author every apparatus's history is written by in this
#: environment. Named rather than inferred: inferring "ours" from
#: "whoever committed most" is how a vendored repo with one prolific
#: upstream maintainer would be adopted.
AUTHORED_BY = "Claude"


def classify(facts: RepoFacts) -> Classification:
    """The verdict, from evidence, in a stated order.

    THE ORDER IS THE POINT. Core declaration is checked FIRST and org
    membership is never checked at all as a positive signal -- it only
    ever appears in the output as a warning that a mirror is wearing our
    name. A classifier that asked "is it under our org?" first would
    produce a confident, wrong, and flattering answer.
    """
    upstream = tuple(a for a in facts.authors if a != AUTHORED_BY)

    if facts.declares_core and AUTHORED_BY in facts.authors:
        return Classification(
            facts=facts, verdict=APPARATUS,
            because=(f"declares {facts.bound_core} in "
                     f"{len(facts.declares_core)} architecture file(s) and its "
                     f"history is authored here"),
            mirrored_under_our_org=False, upstream_authors=())

    # STRONG EVIDENCE ONLY. Three things settle it, and a squashed
    # commit's author is not among them -- every repository here has one
    # commit, so that author is whoever last touched the UPSTREAM, which
    # says nothing about whether the project is ours.
    strong = []
    if not facts.under_our_org:
        strong.append(f"its remote is {facts.remote}, outside this org")
    if facts.declared_upstream:
        strong.append(f"it declares its own upstream as {facts.declared_upstream}")
    if facts.copyright_holders:
        strong.append(f"a copyright grant names {facts.copyright_holders[0]}")

    if strong:
        return Classification(
            facts=facts, verdict=VENDORED_INPUT,
            because="; ".join(strong),
            # THE FIELD THIS MODULE EXISTS FOR.
            mirrored_under_our_org=facts.under_our_org,
            upstream_authors=upstream)

    return Classification(
        facts=facts, verdict=UNRESOLVED,
        because=("under our org, no core declaration, no declared upstream "
                 "and no copyright grant. A squashed snapshot's commit "
                 "author is NOT evidence of ownership -- it is whoever last "
                 "touched whatever was imported. Unsettled, and rounded "
                 "toward NEITHER party"),
        mirrored_under_our_org=False, upstream_authors=upstream)


def _candidate_files(apparatus: pathlib.Path):
    """Source and prose files, skipping generated trees. Yields paths
    rather than contents: the whole point is not to hold them."""
    excluded = {(apparatus / rel).resolve() for rel in MEASURING_APPARATUS}
    stack = [apparatus]
    while stack:
        directory = stack.pop()
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    stack.append(entry)
                continue
            if entry.suffix not in _LOAD_BEARING_SUFFIXES + _PROSE_SUFFIXES:
                continue
            try:
                if entry.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            if entry.resolve() in excluded:
                continue
            yield entry


def verdict_for(counts: Dict[str, int], load_bearing: int
                ) -> Tuple[str, Tuple[Tuple[str, int], ...]]:
    """The classification, given a tally. Pure, so it can be driven over
    constructed inputs instead of over whatever the tree happens to
    contain."""
    if load_bearing:
        return INTEGRATED, tuple(sorted(counts.items()))
    if counts:
        return MENTIONED, tuple(sorted(counts.items()))
    return UNREFERENCED, ()


def measure_integration(name: str, corpus: List[Tuple[str, str, bool]]
                        ) -> Tuple[str, Tuple[Tuple[str, int], ...]]:
    """Does any apparatus actually name this input, and where?

    LOAD-BEARING AND PROSE ARE KEPT APART. A repository named only in a
    markdown file is MENTIONED, not INTEGRATED -- the distinction the
    per-invariant reachability work turns on, applied to dependencies: a
    component nothing calls contributes nothing, however often it is
    written about.

    Takes a materialised corpus, so a test can hand it three lines. The
    scan below does NOT materialise one; it streams.
    """
    counts: Dict[str, int] = {}
    load_bearing = 0
    for apparatus_name, text, is_load_bearing in corpus:
        if name not in text:
            continue
        counts[apparatus_name] = counts.get(apparatus_name, 0) + 1
        if is_load_bearing:
            load_bearing += 1
    return verdict_for(counts, load_bearing)


def tally(names: Tuple[str, ...], apparatuses: Tuple[pathlib.Path, ...]
          ) -> Dict[str, Tuple[str, Tuple[Tuple[str, int], ...]]]:
    """Every name measured in ONE pass, holding no file in memory past
    the line that reads it."""
    counts: Dict[str, Dict[str, int]] = {name: {} for name in names}
    load_bearing: Dict[str, int] = {name: 0 for name in names}
    for apparatus in apparatuses:
        for path in _candidate_files(apparatus):
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            is_load_bearing = path.suffix in _LOAD_BEARING_SUFFIXES
            for name in names:
                if name in text:
                    counts[name][apparatus.name] = counts[name].get(apparatus.name, 0) + 1
                    if is_load_bearing:
                        load_bearing[name] += 1
    return {name: verdict_for(counts[name], load_bearing[name]) for name in names}


def scan(root: pathlib.Path = SIBLING_ROOT,
         deriving: pathlib.Path = REPO_ROOT) -> List[Classification]:
    """Every repository in reach, classified, integration measured."""
    candidates: List[Tuple[str, pathlib.Path]] = [(deriving.name, deriving)]
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / ".git").exists() and child != deriving:
                candidates.append((child.name, child))

    classified = [classify(read_facts(name, path)) for name, path in candidates]
    apparatuses = tuple(c.facts.path for c in classified if c.verdict == APPARATUS)
    if not apparatuses:
        raise EcosystemError(
            "no apparatus found: nothing in reach declares a core version in "
            "authored architecture files, so there is no system to be "
            "coherent ABOUT. Refusing to emit a map of vendored snapshots")

    measured = tally(tuple(c.facts.name for c in classified
                           if c.verdict != APPARATUS), apparatuses)
    resolved: List[Classification] = []
    for entry in classified:
        if entry.verdict == APPARATUS:
            resolved.append(entry)
            continue
        integration, referenced = measured[entry.facts.name]
        resolved.append(Classification(
            facts=entry.facts, verdict=entry.verdict, because=entry.because,
            mirrored_under_our_org=entry.mirrored_under_our_org,
            upstream_authors=entry.upstream_authors,
            integration=integration, referenced_by=referenced))
    return resolved


# ------------------------------------------------------------ document --


def _bound_digest_or_reason() -> Dict[str, object]:
    """The digest of the track the parties ACTUALLY bind.

    An earlier version of this register published one digest and called
    it "the core they bind". Measured, no binding party imports that
    track at all -- the acquisition channel reaches into this repository
    hundreds of times -- 291 measured 2026-09-03, 293 on 2026-09-05 --
    and into that track zero on every measurement. The register was
    publishing a
    fingerprint of code nobody uses, under a heading claiming otherwise.
    """
    try:
        import sys as _sys
        if str(REPO_ROOT) not in _sys.path:
            _sys.path.insert(0, str(REPO_ROOT))
        from architecture.core_identity import (
            CONSUMERS, SURFACES, binding_track, core_digest, imported_tracks)

        bound = {}
        for label, location in CONSUMERS.items():
            consumer = pathlib.Path(location)
            track = binding_track(consumer) if consumer.is_dir() else None
            bound[label] = {
                "binds": track or "NEITHER",
                "imports": imported_tracks(consumer) if consumer.is_dir() else {},
            }
        tracks = {name: core_digest(REPO_ROOT, surface)
                  for name, surface in SURFACES.items()}
        return {"tracks": tracks, "who_binds_what": bound}
    except Exception as error:   # noqa: BLE001 -- the reason is the point
        return {"NOT_TAKEN": f"{type(error).__name__}: {error}"}


def _core_digest_or_reason() -> str:
    """The core's content identity, or why it could not be taken.

    Reported rather than omitted on failure: a register that silently
    dropped the field would look like a register that never had one.
    """
    try:
        import sys as _sys
        if str(REPO_ROOT) not in _sys.path:
            _sys.path.insert(0, str(REPO_ROOT))
        from architecture.core_identity import core_digest
        return core_digest()
    except Exception as error:   # noqa: BLE001 -- the reason is the point
        return f"NOT_TAKEN: {type(error).__name__}: {error}"


def ecosystem_document(classified: List[Classification]) -> dict:
    """The register, in the same emitted shape the invariant register
    uses, so the two read side by side."""
    apparatuses = [c for c in classified if c.verdict == APPARATUS]
    vendored = [c for c in classified if c.verdict == VENDORED_INPUT]
    unresolved = [c for c in classified if c.verdict == UNRESOLVED]
    mirrored = [c for c in vendored if c.mirrored_under_our_org]
    unreferenced = [c for c in vendored if c.integration == UNREFERENCED]
    undeclared = [c for c in apparatuses if c.facts.role == NOT_DECLARED]
    cores = sorted({c.facts.bound_core for c in apparatuses})

    return {
        "extends": "core@1.0.0",
        "generated_by": "architecture/ecosystem.py",
        "artifact": "ecosystem_register",
        "owner": "STE",
        "company_claim": (
            "Notation Systems builds and operates provenance-bearing "
            "computational corpora"),
        "method": (
            "every repository in reach is classified on EVIDENCE -- an "
            "authored core declaration, external commit authorship, a "
            "third-party copyright -- and never on the GitHub org it sits "
            "under. Integration is then measured rather than assumed: an "
            "input named only in prose is MENTIONED and an input named "
            "nowhere is UNREFERENCED"),
        "summary": {
            "repositories_in_reach": len(classified),
            "apparatuses": len(apparatuses),
            "vendored_inputs": len(vendored),
            "unresolved": len(unresolved),
            "vendored_but_under_our_org": len(mirrored),
            "vendored_and_referenced_by_nothing": len(unreferenced),
            "apparatuses_declaring_a_role": len(apparatuses) - len(undeclared),
            "cores_bound": cores,
        },
        "the_core_they_bind": {
            "measured": _bound_digest_or_reason(),
            "digest": _core_digest_or_reason(),
            "the_digest_field_is_the_TWIN_track": (
                "kept for continuity and NAMED, because an earlier version "
                "published it as 'the core they bind' when no binding party "
                "imports that track. What each party actually binds is under "
                "`measured` -- read that one"),
            "why_it_is_here": (
                "every apparatus binds core@1.0.0 BY LABEL, and the label "
                "moves only under bend_protocol -- so many core commits "
                "carry it and a binding party cannot tell which one it "
                "bound. The digest is what makes the binding checkable "
                "rather than nominal, and it is published beside the "
                "bindings so a party reading this register has both"),
            "how_to_check": (
                "architecture/core_identity.py::covers_what_is_bound(your "
                "path, the surface name) FIRST -- to establish the digest is "
                "about code you actually import -- then verify(digest, root, "
                "surface_name) over your own copy. A mismatch names the "
                "file. BOTH steps matter: verify() without a surface name "
                "checks the twin track, which is not what any party measured "
                "here binds, and checking a digest without checking its "
                "referent is what produced the defect this field records"),
            "what_it_does_not_settle": (
                "whether a party HAS this core. This register reads the "
                "sibling clones on one machine; it does not know what any "
                "party has checked out elsewhere, and does not pretend to"),
        },
        "the_finding": {
            "org_ownership_is_not_authorship": (
                f"{len(mirrored)} of {len(vendored)} vendored repositories sit "
                f"under the {ORG}/ org while being other parties' work, by "
                "their own commit history and copyright. A map that read the "
                "org prefix as a provenance claim would have declared "
                f"{len(classified)} apparatuses and been wrong about "
                f"{len(vendored) + len(unresolved)} of them"),
            "which_rule_this_is": (
                "a mirror is not a source, at REPOSITORY scale. The same rule "
                "the invariant register enforces per file, and a fork under "
                "your own org is the most convincing mirror there is because "
                "the URL agrees with the claim"),
            "a_folder_is_not_an_ecosystem": (
                f"{len(unreferenced)} vendored repositories are referenced by "
                "NOTHING in any apparatus. Presence is not participation, and "
                "they are recorded unreferenced rather than listed as "
                "components -- the same reasoning that makes an unreached gate "
                "a silence rather than a clean result"),
            "no_apparatus_declares_its_role": (
                f"{len(undeclared)} of {len(apparatuses)} apparatuses carry no "
                f"{APPARATUS_DECLARATION}. All bind {', '.join(cores) or 'no core'}, "
                "so they agree on the core and none states what it IS within "
                "the company. That is the coherence gap, and it is filled "
                "per-repository BY EACH PARTY: a role written here on another "
                "party's behalf would be a self-declaration this party is not "
                "entitled to make"),
        },
        "apparatuses": [
            {
                "name": c.facts.name,
                "remote": c.facts.remote,
                "branch": c.facts.branch,
                "commit": c.facts.commit,
                "commits": c.facts.commit_count,
                "bound_core": c.facts.bound_core,
                "core_declaring_files": len(c.facts.declares_core),
                "role": c.facts.role,
                "role_source": c.facts.role_source,
                "verdict_because": c.because,
            }
            for c in sorted(apparatuses, key=lambda c: c.facts.name)
        ],
        "vendored_inputs": [
            {
                "name": c.facts.name,
                "remote": c.facts.remote,
                "under_our_org_but_not_ours": c.mirrored_under_our_org,
                "upstream_authors": list(c.upstream_authors[:3]),
                "copyright": list(c.facts.copyright_holders[:2]),
                "integration": c.integration,
                "referenced_by": [{"apparatus": a, "files": n}
                                  for a, n in c.referenced_by],
            }
            for c in sorted(vendored, key=lambda c: (c.integration, c.facts.name))
        ],
        "unresolved": [
            {"name": c.facts.name, "remote": c.facts.remote, "because": c.because}
            for c in sorted(unresolved, key=lambda c: c.facts.name)
        ],
        "the_namesake_question": {
            "what_was_asked": (
                "the sibling census records that this repository contains a "
                "morpho/ package naming a Morpho IR, and that whether that "
                "IR is notationsystems/morphohdl's or a namesake is NOT "
                "determined there and must not be assumed from the name. "
                "Settled here as far as evidence allows, because it is this "
                "repository's package"),
            "the_name_is_MORE_shared_than_the_census_knew": (
                "this repository's package does not merely say `morpho`. Its "
                "modules call themselves MORPHO HDL, in their own docstrings "
                "-- the same two words, not a prefix in common"),
            "and_the_substance_is_LESS_shared_than_the_name_suggests": (
                "measured across both trees: ZERO shared domain vocabulary "
                "(circuit, netlist, verilog, cell definition, rewiring, wasm "
                "appear in neither direction), zero cross-reference in "
                "either direction, and disjoint subject matter -- a "
                "content-addressed language front-end with provenance here, "
                "an experimental graph-rewrite system for growing circuits "
                "there"),
            "the_artifact_that_would_settle_it": (
                "this package implements FROZEN SPECIFICATION v1.0.0, "
                "sections 7.A and 7.B, cited by name in morpho/lexer.py, "
                "morpho/parser.py and morpho/ast.py. Nothing in morphohdl "
                "references that specification, and its only grammar hit is "
                "inside a vendored syntax highlighter"),
            "verdict": (
                "SHARED NAME, UNSHARED REFERENT AS FAR AS THIS TREE SHOWS. "
                "Not asserted as unrelated: two implementations of one idea "
                "in two languages would look exactly like this, and this "
                "machine holds no document that decides it. What is settled "
                "is that nothing HERE licenses treating them as one thing, "
                "and the census's instruction not to assume from the name "
                "stands, now with the evidence behind it"),
        },
        "reconciled_against_an_independent_census": {
            "the_sibling_measured_the_same_question": (
                "the acquisition channel recorded "
                "architecture/ecosystem_census.yaml independently, against "
                "this repository at an OLDER pin than this register existed "
                "at -- so it is not derived from this artifact and the two "
                "are genuinely independent readings"),
            "and_it_counts_differently": (
                "it enumerates 6 repositories carrying the name and 7 "
                "APPARATUSES; this register reports 3. The predicates "
                "differ and neither count is wrong: this one measures "
                "BOUND-TO-THE-CORE (an authored architecture declaration), "
                "the census measures CARRIES-THE-NAME. A repository can "
                "carry the name and bind nothing"),
            "the_correction_it_forced": (
                "the census lists morphohdl as a company repository. This "
                "register had it VENDORED_INPUT -- on a copyright match that "
                "turned out to be Apache-2.0 BOILERPLATE ('Licensor shall "
                "mean the copyright owner...'), which would have disowned "
                "every Apache-licensed repository on no evidence at all. "
                "Six repositories moved from VENDORED_INPUT to UNRESOLVED "
                "once strong evidence was required"),
            "what_this_register_structurally_cannot_see": (
                "an apparatus with NO REPOSITORY. The census records "
                "Notation Physical Commerce living in commerce/ inside the "
                "acquisition channel, deliberately, with no repository of "
                "its own. This register is keyed on repositories and would "
                "never have a row for it. Recorded as a limitation rather "
                "than closed, because closing it means keying on something "
                "other than what is being enumerated"),
            "not_transcribed": (
                "the census's rows are POINTED AT, not copied here. It is "
                "that party's artifact and its claims are its own to state; "
                "duplicating them would create a second copy that drifts and "
                "a reader could not tell which was the source"),
        },
        "what_this_does_not_claim": (
            "that the vendored inputs are unimportant, that anything here is "
            "a licence review, or that APPARATUS means 'belongs to the "
            "company'. It means BOUND TO THE CORE, which is narrower and is "
            "what the evidence supports. It classifies AUTHORSHIP and "
            "measures REFERENCE: an INTEGRATED input is one an apparatus "
            "names in a load-bearing file, which is a fact about this tree "
            "and not an assessment of the input"),
    }


#: Fields of the DERIVING apparatus's own row that its own act of
#: committing changes.
SELF_MOVING_FIELDS = ("commit", "commits")


def without_self_report(document: dict) -> dict:
    """The register minus the deriving apparatus's own moving fields.

    A PARTY CANNOT WITNESS A FACT ABOUT THE ACT IT IS CURRENTLY
    PERFORMING -- the fourth time this project has met that, and the
    first three are worth naming because the shape is identical every
    time:

      the invariant register recorded the commit its sources were read
      at, and committing the register advanced that commit;

      the emitted register was re-read as its own source, turning 26
      invariants into 77, every row contested;

      this module's own docstring, citing repositories as examples of
      the mirror finding, counted as evidence that those repositories
      were integrated;

      and now this register records its own repository's HEAD and commit
      count, which its own commit advances.

    The fields STAY IN THE ARTIFACT, because a reader wants to know
    which commit a reading was taken at. They are excluded only from the
    comparison the artifact makes WITH ITSELF, which is the one place
    they cannot be evidence. Narrow by construction: only the deriving
    apparatus's row is touched, so a SIBLING moving is still a
    difference the fixed point must see.
    """
    import copy

    trimmed = copy.deepcopy(document)
    deriving = REPO_ROOT.name
    for row in trimmed.get("apparatuses", []):
        if row.get("name") == deriving:
            for field in SELF_MOVING_FIELDS:
                row.pop(field, None)
    return trimmed


def emit(root: pathlib.Path = REPO_ROOT) -> pathlib.Path:
    import sys as _sys
    _sys.path.insert(0, str(root / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes, canonical_sha256

    document = ecosystem_document(scan(deriving=root))
    out = root / "architecture" / "exchange" / "ecosystem_register.yaml"
    out.write_bytes(canonical_bytes(document))
    (root / "architecture" / "exchange" / "ecosystem_register.sha256").write_text(
        canonical_sha256(document) + "\n")
    return out


def main() -> int:
    classified = scan()
    apparatuses = [c for c in classified if c.verdict == APPARATUS]
    vendored = [c for c in classified if c.verdict == VENDORED_INPUT]

    print("=== APPARATUSES ===")
    for c in sorted(apparatuses, key=lambda c: c.facts.name):
        print(f"  {c.facts.name:34} {c.facts.bound_core:12} role={c.facts.role}")

    print("\n=== VENDORED INPUTS, by how much they carry ===")
    for level in (INTEGRATED, MENTIONED, UNREFERENCED):
        group = [c for c in vendored if c.integration == level]
        print(f"\n  {level} ({len(group)})")
        for c in sorted(group, key=lambda c: c.facts.name):
            flag = "  <- under OUR org, NOT ours" if c.mirrored_under_our_org else ""
            print(f"    {c.facts.name:56}{flag}")

    mirrored = [c for c in vendored if c.mirrored_under_our_org]
    unreferenced = [c for c in vendored if c.integration == UNREFERENCED]
    undeclared = [c for c in apparatuses if c.facts.role == NOT_DECLARED]
    print("\n=== THE NUMBERS THAT MATTER ===")
    print(f"  repositories in reach              : {len(classified)}")
    print(f"  apparatuses                        : {len(apparatuses)}")
    print(f"  vendored inputs                    : {len(vendored)}")
    print(f"  vendored, under OUR org            : {len(mirrored)}")
    print(f"  vendored, referenced by nothing    : {len(unreferenced)}")
    print(f"  apparatuses declaring a role       : "
          f"{len(apparatuses) - len(undeclared)} of {len(apparatuses)}")
    if "--emit" in _argv():
        out = emit()
        print(f"\n  wrote {out.relative_to(REPO_ROOT)}")
    return 0


def _argv() -> List[str]:
    import sys
    return sys.argv


if __name__ == "__main__":
    raise SystemExit(main())
