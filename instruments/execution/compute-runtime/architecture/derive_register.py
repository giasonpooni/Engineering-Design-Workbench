"""Derive the invariant register from every bound repository's canonical
sources -- never from a local copy, and never from a copy of one.

WHY THIS EXISTS. The systems report at d4d0c19 stated "26 invariants,
14 enforced" from STE's own reading of STE's own file. Two other
repositories bind the same core and had since changed what it supports:
`generation_depth_bounded` was reported `identified` here while the
acquisition layer had closed it. Nine of the eighteen shared invariant
ids disagreed on status. No local check caught it, because every local
check verifies an artifact against itself.

--------------------------------------------------------------------
A MIRROR IS NOT A SOURCE
--------------------------------------------------------------------

The same defect has now arrived three times in three positions:

  1. the emitted register was re-read by its own derivation
  2. a top-level owner was read as though it were a row's owner
  3. a party's self-declaration was read out of another party's
     artifact, which that party merely HOLDS

All three are one rule. BYTE-IDENTITY IS EXACTLY WHAT MAKES IT
DANGEROUS: a mirror and its origin are the same bytes by design, so
nothing in the CONTENT can separate them. Only provenance can. So this
module establishes provenance FIRST, across all parties at once, and
every subsequent read asks what it is entitled to read rather than
trusting where the file sits.

Provenance is computed, not assumed, from two facts:

  - do any other bound parties hold these exact bytes?
  - does the document name a generator, and does that generator resolve
    in THIS repository?

Generator resolution is the load-bearing test because it is the only
one that needs no name resolution. Asking "is this party the owner
named in the file" would be circular here -- the acquisition layer
calls itself `daf`, the compute layer addresses it as `daq`, and this
derivation labels it `DAQ`. A path either exists in a repository or it
does not.

From those two facts each read gets a different entitlement:

  canonical source   not emitted, and no other party holds these bytes.
                     An emitted projection is never a canonical source,
                     whoever emitted it -- that is defect 1, generalized
                     past the directory convention that used to stand in
                     for it.
  self-declaration   authored here, provably. `joint` is NOT authored
                     here: an artifact two parties agreed on says what
                     they agreed, not what either is called. That is
                     defect 3.
  binding evidence   anything not authored ELSEWHERE. A joint record
                     both parties signed does evidence both parties'
                     binding; a mirror of one party's artifact does not
                     evidence the holder's.

--------------------------------------------------------------------
CURRENCY IS DIRECTIONAL, AND ITS VERDICT IS PER-SIBLING
--------------------------------------------------------------------

A party's own HEAD is authoritative FOR ITSELF. It cannot be stale
against itself, and it diverges from its remote the moment it commits
the very work being derived. So the deriving party is exempt BY
CONSTRUCTION -- not by a tolerance that happens to let it through,
which is what the first implementation had and which would have
silently excused a sibling in the same position.

The real question is "am I current with respect to what I DERIVED
FROM", and that has one answer per sibling. They are recorded per
sibling and never collapsed: a derivation is only ever as current as
its WORST sibling, and a single boolean cannot say which one is the
binding constraint or how far behind it is.

--------------------------------------------------------------------

THE RULES (this module is their executable form):

  - no repository may report a status for an invariant it does not own
    without citing the owning repository's source
  - an invariant claimed `enforced` must name a test that cites its id
  - the derivation FAILS if any bound repository is unreachable, rather
    than reporting a partial count as a total
  - a sibling clone missing published state FAILS the derivation.
    Measured 2026-08-26: both sibling clones were behind at the moment
    the previous derivation recorded their local HEADs as the commits
    it had derived from, and one moved three more times that day.
  - a party's NAME is read from that party's own artifacts, never
    assigned here. The labels below are local handles for the join.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The repositories that bind the core. The string is a LOCAL LABEL used
#: to join claims, not the party's name -- see the module docstring. A
#: bound repository that is not on disk is UNREACHABLE and fails the
#: derivation; it is never silently dropped from the count.
BOUND_REPOSITORIES: Tuple[Tuple[str, pathlib.Path], ...] = (
    ("STE", REPO_ROOT),
    ("DAQ", pathlib.Path("/home/user/notationsystems/notations-acquisition-channel")),
    ("SCL", pathlib.Path("/home/user/notationsystems/scientific-compute-layer")),
)

#: A status claiming enforcement must be backed by a test citing the id.
ENFORCING_STATUSES = frozenset({"enforced", "partially_enforced", "vacuously_enforced"})

#: The two ways a party can be bound. Both are successful outcomes; they
#: differ in what the party contributes, not in whether it is bound.
INVARIANT_REGISTRY = "invariant_registry"
EXTENDS_ONLY = "extends_only"

#: A claim about the claiming repository's own state, rather than about
#: the invariant. Excluded from contests; see Derivation.contested.
LOCAL_SCOPE = "this_repository"
PROJECT_SCOPE = "project"

#: Currency states. `AUTHORITATIVE` is the deriving party's, and is not
#: a pass -- it is the absence of a question.
AUTHORITATIVE = "authoritative_for_itself"
IN_SYNC = "in_sync"
AHEAD = "local_ahead_of_remote"
NOT_CHECKED = "not_checked"

#: Worst-first. The derivation is as current as its worst sibling, so
#: the rollup needs an order, not a boolean.
_CURRENCY_ORDER = (NOT_CHECKED, AHEAD, IN_SYNC)


class DerivationError(RuntimeError):
    """The derivation failed. Never downgraded to a partial result."""


def _is_contested(claims) -> bool:
    """Disagreement among the claims that are ABOUT THE INVARIANT."""
    statuses = {c.status for c in claims if c.scope != LOCAL_SCOPE}
    return len(statuses) > 1


# ----------------------------------------------------------- provenance --


@dataclass(frozen=True)
class Provenance:
    """What one party is entitled to be read as saying about one file.

    Computed across all parties at once, because the question "is this a
    mirror" cannot be answered from inside one repository -- which is
    precisely why the defect reached three separate positions before
    anything caught it.
    """

    emitted: bool               # names a generator: a projection
    holders: Tuple[str, ...]    # every bound party holding these bytes
    authored_here: Optional[bool]   # None when not established
    names_one_author: bool      # the document claims a single author

    @property
    def shared(self) -> bool:
        return len(self.holders) > 1

    @property
    def is_canonical_source(self) -> bool:
        """May its `invariants:` be read as this party's own claims?

        An emitted projection never may, whoever emitted it -- that is
        the circular-derivation defect, generalized past the directory
        convention that used to stand in for it. Neither may a file
        another party also holds: a shared registry is not evidence of
        who wrote it.
        """
        return not self.emitted and not self.shared

    @property
    def is_self_declaration(self) -> bool:
        """May a claim about the party's own identity be read from it?

        Requires provable authorship. `None` is not a pass: an artifact
        two parties agreed on says what they agreed, not what either one
        is called.
        """
        return self.authored_here is True

    @property
    def is_binding_evidence(self) -> bool:
        """May its `extends` be read as this party binding that core?

        A joint record both parties signed evidences both parties'
        binding. A mirror of one party's artifact evidences only that
        party's.

        THE CASE THAT SEPARATES THEM, and it leaked once before this
        distinction existed: shared bytes that NAME a single author.
        Exactly one holder wrote it and this derivation cannot say
        which, so it evidences nobody's binding here -- crediting the
        holder would assert a binding the party never declared, and
        that is the mirror-as-source defect wearing a different hat.
        Under-crediting the true author is the safe direction: a party
        that really binds says so somewhere it authored alone.
        """
        if self.authored_here is True:
            return True
        if self.authored_here is False:
            return False
        return not self.names_one_author

    @property
    def label(self) -> str:
        """A word for the register to carry, so a reader can audit the
        classification instead of trusting the entitlements."""
        if self.emitted:
            return "projection_origin" if self.authored_here else "projection_mirror"
        if not self.shared:
            return "sole"
        return "one_author_unresolved" if self.names_one_author else "joint"


def _classify(corpus: Dict[str, Dict[pathlib.Path, Tuple[str, dict]]],
              roots: Dict[str, pathlib.Path]) -> Dict[Tuple[str, pathlib.Path], Provenance]:
    """Establish provenance for every artifact, across every party.

    Two passes, and the first one is the whole point: holders are found
    by DIGEST rather than by path, because a mirror may sit at a
    different path and identical bytes are the only thing that makes two
    files the same artifact.
    """
    holders: Dict[str, List[str]] = {}
    for label, files in corpus.items():
        for digest, _ in files.values():
            holders.setdefault(digest, []).append(label)

    provenance: Dict[Tuple[str, pathlib.Path], Provenance] = {}
    for label, files in corpus.items():
        for relative, (digest, document) in files.items():
            generator = document.get("generated_by")
            emitted = isinstance(generator, str) and bool(generator)
            # A document naming an author claims to be ONE party's. The
            # token is in that party's own vocabulary, so it cannot say
            # WHICH party non-circularly -- the acquisition layer calls
            # itself `daf`. It can still say "not joint", which is the
            # half that matters.
            names_one_author = any(
                isinstance(document.get(key), str) and document.get(key)
                for key in ("authored_by", "owner"))
            if emitted:
                # A path resolves or it does not. No name resolution,
                # so no exposure to the one-party-two-names problem
                # that makes an owner-token comparison circular here.
                authored = (roots[label] / generator).exists()
            elif len(set(holders[digest])) > 1:
                authored = None     # joint: undecidable, and left so
            else:
                authored = True
            provenance[(label, relative)] = Provenance(
                emitted=emitted,
                holders=tuple(sorted(set(holders[digest]))),
                authored_here=authored,
                names_one_author=names_one_author,
            )
    return provenance


# ------------------------------------------------------------- records --


@dataclass(frozen=True)
class InvariantRecord:
    """One invariant as ONE repository asserts it."""

    invariant_id: str
    status: str
    asserted_by: str          # the LOCAL LABEL of the repository claiming this
    source_file: str          # path, relative to that repository
    source_commit: str        # the commit the claim was read at
    evidence: Optional[str]   # the test or module cited as enforcing it
    evidence_cites_id: bool   # whether that evidence actually names the id
    scope: str                # project | this_repository
    owner_elsewhere: Optional[str]  # the party that owns this invariant
    awaiting_decision: Optional[str]  # the decision, when one is pending


@dataclass(frozen=True)
class RepositoryBinding:
    """How one party is bound, and what it contributed."""

    label: str
    is_deriving_party: bool
    binding_mode: str
    bound_core: str
    local_commit: str
    branch: str
    remote_commit: Optional[str]
    currency: str
    binding_files: Tuple[str, ...]
    invariant_sources: Tuple[str, ...]
    mirrors_held: Tuple[str, ...]   # artifacts held but authored elsewhere
    unresolved_authorship: Tuple[str, ...]  # shared, single-authored, unattributable
    record_count: int
    self_declared_names: Tuple[str, ...]


@dataclass
class Derivation:
    records: Dict[str, List[InvariantRecord]] = field(default_factory=dict)
    commits: Dict[str, str] = field(default_factory=dict)
    bindings: Dict[str, RepositoryBinding] = field(default_factory=dict)
    remotes_checked: bool = False

    @property
    def contested(self) -> Dict[str, List[InvariantRecord]]:
        """Ids more than one repository asserts a DIFFERENT status for AT
        THE SAME SCOPE. These are the register's real finding: a claim
        about the core that the core no longer supports.

        SCOPE IS WHAT MAKES THE FINDING MEAN ANYTHING. Joining nine
        disagreeing rows on the id alone put three different things in
        one bucket: an invariant one party owns and another reports
        stale (the defect), a development-process rule whose state is
        genuinely per-repository and differs truthfully in each (not a
        defect), and a real disagreement about a shared claim (the
        defect the register is for). Averaging those into "nine
        contested" overstates two thirds of it.

        A claim declaring `scope: this_repository` is a statement about
        its own repository's state, so it is excluded rather than
        compared. The DEFAULT is `project`: an unscoped claim is read as
        a claim about the invariant globally, so silence never buys the
        exemption.

        (The first implementation grouped BY scope and flagged any group
        that disagreed, which is a different rule wearing the same
        words: two claims both scoped `this_repository` still contested.
        The planted-disagreement test found it, which is the argument
        for planting one.)
        """
        return {
            key: claims for key, claims in self.records.items()
            if _is_contested(claims)
        }

    @property
    def scoped_local(self) -> Dict[str, List[InvariantRecord]]:
        """Ids where some claim is scoped to its own repository. Surfaced
        BECAUSE the scope declaration is what stops them contesting: a
        reader can see how much of a zero contested-count was reached by
        agreement and how much by scoping."""
        return {
            key: [c for c in claims if c.scope == LOCAL_SCOPE]
            for key, claims in self.records.items()
            if any(c.scope == LOCAL_SCOPE for c in claims)
        }

    @property
    def deferrals(self) -> Dict[str, List[InvariantRecord]]:
        """Claims that name an owner elsewhere. The point of the pointer
        is that this repository never writes the owner's status down --
        it names the owner, and the register resolves the live value at
        derivation time. A copied status is the exact artifact that went
        two corrections stale while every local suite stayed green."""
        return {
            key: [c for c in claims if c.owner_elsewhere]
            for key, claims in self.records.items()
            if any(c.owner_elsewhere for c in claims)
        }

    @property
    def awaiting_a_decision(self) -> Dict[str, List[InvariantRecord]]:
        """Rows that will not resolve by being measured harder.

        A PROPERTY OF THIS PROJECT, not a list of stragglers: every
        instrument here converts an assumption into a MEASUREMENT, and
        none converts a measurement into a CHOICE. Probes, mutation
        batteries, reachability traces, currency gates and this register
        all answer "what is true"; not one of them answers "what should
        be done about it".

        Surfaced here because that is what stops them fading. A prose
        note survives by inertia; a derived field is re-emitted on every
        run, so an open decision stays as visible as a contested row.
        """
        return {
            key: [c for c in claims if c.awaiting_decision]
            for key, claims in self.records.items()
            if any(c.awaiting_decision for c in claims)
        }

    @property
    def siblings(self) -> List[RepositoryBinding]:
        """Every bound party except the one doing the deriving."""
        return [b for b in self.bindings.values() if not b.is_deriving_party]

    @property
    def worst_sibling(self) -> Optional[RepositoryBinding]:
        """THE BINDING CONSTRAINT ON THIS DERIVATION'S CURRENCY.

        A derivation is only ever as current as its worst sibling. That
        is a fact about a specific sibling at a specific commit, and
        collapsing it into one boolean throws away both halves: which
        party is the constraint, and how far behind it is. The deriving
        party is not a candidate -- it is authoritative for itself, so
        it is not a sibling and cannot be the constraint.
        """
        siblings = self.siblings
        if not siblings:
            return None
        return min(siblings, key=lambda b: _CURRENCY_ORDER.index(b.currency))


# ---------------------------------------------------------------- git --


def _git(path: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True,
    )


def _commit_of(path: pathlib.Path) -> str:
    result = _git(path, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise DerivationError(f"{path} is not a git checkout; cannot record its commit")
    return result.stdout.strip()


def _remote_head(path: pathlib.Path, branch: str) -> Optional[str]:
    """The REMOTE's head for this branch, or None if it cannot be asked.
    A local commit proves authorship; only this proves currency."""
    if not branch:
        return None
    result = _git(path, "ls-remote", "origin", f"refs/heads/{branch}")
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip().split("\t")[0]


def _uncommitted(path: pathlib.Path) -> Tuple[str, ...]:
    """Files in a clone that differ from its own HEAD.

    THE HALF THE CURRENCY CHECK WAS MISSING, and it is the sharper half.
    `_sibling_currency` asks whether a clone's HEAD has fallen behind its
    remote. It never asked whether the WORKING TREE matches that HEAD.

    A stale clone at least names an older commit honestly -- the register
    records a real commit, and a reader can go and look at it. A DIRTY
    clone names a commit that never contained what was read: the
    derivation reports `SCL @ 5e62820` while having read a file that is
    at no commit at all. That is not staleness; it is a citation to a
    source that does not say what it is quoted as saying.

    FOUND BY CAUSING IT. A patch was applied to a sibling's working tree
    and left uncommitted; the registers went out of fixed point and the
    deriver had nothing to say about why. Recorded here rather than in a
    comment somewhere, because the next person to apply a patch to a
    sibling will not read the comment.
    """
    result = _git(path, "status", "--porcelain")
    if result.returncode != 0:
        return ()
    return tuple(sorted(
        line[3:].strip() for line in result.stdout.splitlines() if line.strip()))


def _sibling_currency(path: pathlib.Path, local: str, remote: str) -> Optional[str]:
    """How a SIBLING's clone stands against its remote, or None if behind.

    Only ever asked of a sibling. The deriving party never reaches here,
    because its own HEAD is authoritative for itself -- exempting it by
    construction rather than by a tolerance that would also excuse a
    sibling in the same position.

    A clone that does not CONTAIN the remote head is missing state the
    party has published: stale, and the failure this check exists for. A
    sibling clone that is AHEAD means this session has commits in
    someone else's repository, which is recorded rather than treated as
    equivalent to in-sync.
    """
    if local == remote:
        return IN_SYNC
    contains = _git(path, "merge-base", "--is-ancestor", remote, local)
    return AHEAD if contains.returncode == 0 else None


def _evidence_cites_id(root: pathlib.Path, evidence: Optional[str], invariant_id: str) -> bool:
    """The meta-test bar, applied across repositories: an invariant
    claimed enforced must name a test that CITES ITS ID. A cited file
    that never mentions the id is not evidence for it."""
    if not evidence:
        return False
    for candidate in str(evidence).replace(",", " ").split():
        target = root / candidate.strip()
        if target.is_file() and invariant_id in target.read_text(errors="replace"):
            return True
    return False


# --------------------------------------------------------------- read --


def _read_corpus(label: str, root: pathlib.Path):
    """Every parsed architecture document, with its digest."""
    files: Dict[pathlib.Path, Tuple[str, dict]] = {}
    architecture = root / "architecture"
    if not architecture.is_dir():
        return files
    for source in sorted(architecture.rglob("*.yaml")):
        raw = source.read_bytes()
        try:
            document = yaml.safe_load(raw.decode())
        except (yaml.YAMLError, UnicodeDecodeError) as error:
            raise DerivationError(f"{label}:{source} does not parse: {error}") from error
        if isinstance(document, dict):
            files[source.relative_to(root)] = (
                hashlib.sha256(raw).hexdigest(), document)
    return files


def _build_binding(label, root, files, provenance, is_deriving, check_remote):
    local_commit = _commit_of(root)
    branch = _git(root, "branch", "--show-current").stdout.strip()

    remote_commit: Optional[str] = None
    currency = NOT_CHECKED
    if is_deriving:
        # EXEMPT BY CONSTRUCTION, not by tolerance. A party's own HEAD is
        # authoritative for itself: it cannot be stale against itself,
        # and it diverges from its remote the instant it commits the
        # work being derived. The first implementation gave every party
        # the same lenient comparison, which let this one through for
        # the wrong reason -- and would have excused a SIBLING sitting
        # in exactly the same position.
        currency = AUTHORITATIVE
        if check_remote:
            remote_commit = _remote_head(root, branch)
    elif check_remote:
        # LOCAL FACTS BEFORE NETWORK ONES. Dirtiness is cheap, certain
        # and independent of whether any remote answers, and a dirty
        # clone is a problem either way -- so asking the network first
        # would report "cannot reach origin" about a tree whose real
        # defect is sitting on disk.
        dirty = _uncommitted(root)
        if dirty:
            raise DerivationError(
                f"{label}: {len(dirty)} file(s) differ from its own HEAD "
                f"{local_commit[:12]} -- {list(dirty[:5])}. A derivation over a "
                f"DIRTY clone would record a commit that never contained what "
                f"it read, which is worse than recording a stale one: a stale "
                f"commit can at least be looked up. Commit or revert the "
                f"sibling, then derive.")
        remote_commit = _remote_head(root, branch)
        if remote_commit is None:
            raise DerivationError(
                f"{label}: cannot reach origin/{branch or '<detached>'} to establish "
                f"currency. A derivation that cannot ask a sibling's remote must not "
                f"claim the clone is current -- run with check_remotes=False to derive "
                f"from the local clones with the register recording that it did")
        currency = _sibling_currency(root, local_commit, remote_commit)
        if currency is None:
            raise DerivationError(
                f"{label}: clone is at {local_commit[:12]} but origin/{branch} is at "
                f"{remote_commit[:12]}, which this clone does not contain. A "
                f"derivation against a stale sibling is a FAILED derivation, not a "
                f"successful one carrying old data -- fetch first. (Measured "
                f"2026-08-26: both sibling clones were behind at the moment a "
                f"derivation recorded their local HEADs as the commits it had "
                f"derived from, and one moved three more times that day.)")

    records: List[InvariantRecord] = []
    invariant_sources: List[str] = []
    binding_files: List[str] = []
    mirrors_held: List[str] = []
    unresolved: List[str] = []
    bound_cores = set()
    self_names: List[str] = []

    for relative, (_, document) in files.items():
        entitlement = provenance[(label, relative)]

        if entitlement.authored_here is False:
            mirrors_held.append(str(relative))
        elif entitlement.label == "one_author_unresolved":
            unresolved.append(str(relative))

        declared = document.get("extends")
        if (isinstance(declared, str) and declared.startswith("core@")
                and entitlement.is_binding_evidence):
            binding_files.append(str(relative))
            bound_cores.add(declared)

        known_as = document.get("also_known_as")
        if isinstance(known_as, str) and entitlement.is_self_declaration:
            self_names.append(known_as)

        if not entitlement.is_canonical_source:
            continue
        entries = document.get("invariants") or []
        if not isinstance(entries, list):
            continue
        contributed = False
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            evidence = entry.get("enforcement") or entry.get("implementation")
            if isinstance(evidence, dict):
                evidence = evidence.get("locks") or evidence.get("validator")
            owner = entry.get("owner_elsewhere")
            pending = entry.get("decision") if entry.get("awaiting_decision") else None
            records.append(InvariantRecord(
                invariant_id=entry["id"],
                status=str(entry.get("status", "unstated")),
                asserted_by=label,
                source_file=str(relative),
                source_commit=local_commit,
                evidence=str(evidence) if evidence else None,
                evidence_cites_id=_evidence_cites_id(root, evidence, entry["id"]),
                scope=str(entry.get("scope", PROJECT_SCOPE)),
                owner_elsewhere=str(owner) if owner else None,
                awaiting_decision=str(pending) if pending else None,
            ))
            contributed = True
        if contributed:
            invariant_sources.append(str(relative))

    if len(bound_cores) > 1:
        raise DerivationError(
            f"{label} declares more than one core version {sorted(bound_cores)}; a "
            f"party binds one core, and a split binding is a bend nobody recorded")
    if not records and not binding_files:
        # THE DISTINCTION THIS BRANCH EXISTS FOR. A party that declares
        # no invariants is representable (extends_only). A party that
        # declares neither invariants nor a binding is not a party with
        # no source -- nothing establishes it is bound at all, and
        # counting it as a contributor of zero would be the register
        # asserting a binding on the party's behalf.
        raise DerivationError(
            f"{label} declares no invariants AND no `extends: core@<version>` in any "
            f"artifact it authored; it is not demonstrably bound. Zero records is a "
            f"claim needing evidence like any other -- this is not the extends_only "
            f"case")

    return records, RepositoryBinding(
        label=label,
        is_deriving_party=is_deriving,
        binding_mode=INVARIANT_REGISTRY if records else EXTENDS_ONLY,
        bound_core=next(iter(bound_cores)) if bound_cores else "",
        local_commit=local_commit,
        branch=branch,
        remote_commit=remote_commit,
        currency=currency,
        binding_files=tuple(sorted(binding_files)),
        invariant_sources=tuple(sorted(invariant_sources)),
        mirrors_held=tuple(sorted(mirrors_held)),
        unresolved_authorship=tuple(sorted(unresolved)),
        record_count=len(records),
        self_declared_names=tuple(sorted(set(self_names))),
    )


def derive(repositories: Sequence[Tuple[str, pathlib.Path]] = BOUND_REPOSITORIES,
           check_remotes: bool = True) -> Derivation:
    """Read every bound repository, establishing provenance first.

    Fails closed on an unreachable repository, on a party that is not
    demonstrably bound, and -- when `check_remotes` is set -- on a
    SIBLING clone missing published state. The deriving party is exempt
    by construction; see `_build_binding`.

    `check_remotes=False` derives from the local clones and the emitted
    register records that currency was NOT established, so an offline
    derivation can never be mistaken for one that checked.
    """
    roots = {}
    for label, root in repositories:
        if not root.is_dir():
            raise DerivationError(
                f"bound repository {label} is unreachable at {root}; a partial count "
                f"is not a total -- the derivation fails rather than under-reporting")
        roots[label] = root

    # PASS 1: read everything, from every party, before classifying
    # anything. "Is this a mirror" is not answerable from inside one
    # repository, which is why the defect reached three positions.
    corpus = {label: _read_corpus(label, root) for label, root in roots.items()}
    provenance = _classify(corpus, roots)

    derivation = Derivation(remotes_checked=check_remotes)
    for label, root in repositories:
        records, binding = _build_binding(
            label, root, corpus[label], provenance,
            is_deriving=root.resolve() == REPO_ROOT,
            check_remote=check_remotes)
        derivation.commits[label] = binding.local_commit
        derivation.bindings[label] = binding
        for record in records:
            derivation.records.setdefault(record.invariant_id, []).append(record)
    _check_deferrals(derivation)
    return derivation


def _check_deferrals(derivation: Derivation) -> None:
    """A pointer to an owner is only worth more than a copied status if
    the pointer RESOLVES. An `owner_elsewhere` naming a party this
    derivation does not read is worse than no pointer at all: it reads
    as deference while deferring to nobody, and nothing would ever
    contradict it."""
    known = set(derivation.bindings)
    for invariant_id, claims in derivation.records.items():
        for claim in claims:
            if not claim.owner_elsewhere:
                continue
            if claim.owner_elsewhere not in known:
                raise DerivationError(
                    f"{claim.asserted_by}:{invariant_id} defers to "
                    f"{claim.owner_elsewhere!r}, which is not a bound party "
                    f"{sorted(known)}. A pointer to a party nobody reads is not "
                    f"deference -- it is an unfalsifiable claim wearing deference's "
                    f"shape")
            if claim.scope != LOCAL_SCOPE:
                raise DerivationError(
                    f"{claim.asserted_by}:{invariant_id} names an owner elsewhere "
                    f"but claims scope {claim.scope!r}. A claim that defers is a "
                    f"claim about its OWN repository's state; asserting project "
                    f"scope while deferring is asserting the owner's answer and "
                    f"pointing at the owner in the same breath")
            if not any(c.asserted_by == claim.owner_elsewhere for c in claims):
                raise DerivationError(
                    f"{claim.asserted_by}:{invariant_id} defers to "
                    f"{claim.owner_elsewhere}, but that party asserts nothing for "
                    f"this id. The deferral would resolve to silence and read as "
                    f"settled")


# ------------------------------------------------------------- emit --


def currency_report(derivation: Derivation) -> dict:
    """Currency, PER SIBLING, with the binding constraint named.

    Never a single verdict. A derivation is only ever as current as its
    worst sibling, and a boolean throws away both halves of that: which
    party is the constraint, and how far behind it is. The deriving
    party appears with `authoritative_for_itself` -- present so its
    exemption is visible and auditable, absent from the rollup because
    it is not a sibling and cannot be the constraint.
    """
    worst = derivation.worst_sibling
    return {
        "checked_against_remotes": derivation.remotes_checked,
        "deriving_party": next(
            (b.label for b in derivation.bindings.values() if b.is_deriving_party), ""),
        "deriving_party_is_exempt_by_construction": True,
        "as_current_as_its_worst_sibling": (
            f"{worst.label} at {worst.local_commit[:12]} ({worst.currency})"
            if worst else "no siblings"),
        "per_party": {
            label: {
                "role": "deriving_party" if b.is_deriving_party else "sibling",
                "currency": b.currency,
                "local": b.local_commit,
                "remote": b.remote_commit or "",
            }
            for label, b in sorted(derivation.bindings.items())
        },
    }


def register_document(derivation: Derivation) -> dict:
    """The emitted register: per-invariant provenance, never a bare count."""
    invariants = []
    for invariant_id in sorted(derivation.records):
        claims = sorted(derivation.records[invariant_id], key=lambda r: r.asserted_by)
        enforcing = [c for c in claims if c.status in ENFORCING_STATUSES]
        owner = enforcing[0].asserted_by if enforcing else ""
        invariants.append({
            "id": invariant_id,
            "owning_repository": owner,
            "contested": _is_contested(claims),
            "claims": [{
                "asserted_by": c.asserted_by,
                "status": c.status,
                "scope": c.scope,
                "defers_to": c.owner_elsewhere or "",
                "awaiting_decision": c.awaiting_decision or "",
                # RESOLVED AT DERIVATION TIME, NEVER COPIED. A deferring
                # repository writes the owner's NAME; this field is
                # filled in from the owner's live source on every run,
                # so it cannot go stale the way a transcribed status did
                # while every local suite stayed green.
                "owner_status_resolved": next(
                    (o.status for o in claims if o.asserted_by == c.owner_elsewhere),
                    "") if c.owner_elsewhere else "",
                "source_file": c.source_file,
                "source_commit": c.source_commit,
                "evidence": c.evidence or "",
                "evidence_cites_id": c.evidence_cites_id,
            } for c in claims],
        })
    derived_from = []
    for label in sorted(derivation.bindings):
        binding = derivation.bindings[label]
        derived_from.append({
            "repository": label,
            "label_is_a_local_handle_not_the_party_s_name": True,
            "self_declared_names": list(binding.self_declared_names),
            "binding_mode": binding.binding_mode,
            "bound_core": binding.bound_core,
            "branch": binding.branch,
            # For the deriving party this is the PARENT of the commit
            # that will carry this file -- see without_currency.
            "commit": binding.local_commit,
            "binding_files": list(binding.binding_files),
            "invariant_sources": list(binding.invariant_sources),
            # Held, but authored by another party. Emitted so a reader
            # can see WHAT was excluded rather than only that something
            # was -- a mirror silently skipped is indistinguishable from
            # a mirror never noticed.
            "artifacts_held_but_authored_elsewhere": list(binding.mirrors_held),
            # SET ASIDE, AND SAID SO. These name a single author and are
            # held byte-identically by more than one party, so exactly
            # one holder wrote each and this derivation cannot say
            # which: the author tokens are in each party's own
            # vocabulary and resolving them here would be the deriving
            # party deciding another party's identity. Excluded from
            # both holders rather than credited to whoever happens to be
            # read first -- and listed, because a limitation that costs
            # a party evidence should be visible to that party.
            "artifacts_set_aside_authorship_unresolved": list(
                binding.unresolved_authorship),
            "invariants_contributed": binding.record_count,
        })
    return {
        # THE ARTIFACT DECLARES ITSELF EMITTED. This is what makes the
        # "a projection is never a canonical source" rule general rather
        # than a directory convention: the register used to be excluded
        # because of where it sits, which protected exactly one path and
        # silently re-admitted it the moment the rule was generalized.
        # A projection that says so is excluded wherever it is filed,
        # and so is any other party's.
        "generated_by": "architecture/exchange/build_invariant_register.py",
        "derived_from": derived_from,
        "currency": currency_report(derivation),
        "bound_parties": len(derivation.bindings),
        "parties_with_no_invariant_source": sorted(
            b.label for b in derivation.bindings.values()
            if b.binding_mode == EXTENDS_ONLY),
        "invariant_count": len(invariants),
        "contested_count": len(derivation.contested),
        "deferred_count": len(derivation.deferrals),
        # HOW THE CONTESTED COUNT GOT WHERE IT IS. A bare zero cannot be
        # told apart from a detector that finds nothing, so the register
        # states how many rows carry a local-scope claim -- the rows a
        # reader should check for themselves rather than take on the
        # count's word.
        "rows_with_a_local_scope_claim": sorted(derivation.scoped_local),
        # WAITING ON A PERSON, and saying so. These do not resolve by
        # being measured harder -- every instrument in this project turns
        # an assumption into a measurement and none turns a measurement
        # into a choice. Derived and re-emitted, so an open decision
        # cannot survive by inertia the way a prose note can.
        "awaiting_a_decision": sorted(derivation.awaiting_a_decision),
        "invariants": invariants,
        "rules": [
            "a mirror is not a source: provenance is established across all "
            "parties before anything is read, and byte-identity is what makes "
            "content unable to establish it",
            "an emitted projection is never a canonical source, whoever emitted it",
            "a party's own name is read only from an artifact it provably "
            "authored; a jointly agreed artifact says what was agreed, not what "
            "either party is called",
            "no repository may report a status for an invariant it does not own "
            "without citing the owning repository's source",
            "an invariant claimed enforced must name a test that cites its id",
            "the derivation fails if any bound repository is unreachable",
            "currency is directional: the deriving party is authoritative for "
            "itself and exempt by construction; every sibling is checked against "
            "its remote and a sibling missing published state fails",
            "currency is reported per sibling and never collapsed -- a derivation "
            "is only as current as its worst sibling, and which sibling that is "
            "is part of the answer",
            "a claim scoped to this_repository is a statement about its own "
            "repository's state; two such claims differing is a fact, not a "
            "contest. scope defaults to project, so silence never buys the "
            "exemption",
            "a repository reporting an invariant another party owns names that "
            "party and never transcribes its status; the owner's live status is "
            "resolved on every derivation, and a deferral that does not resolve "
            "fails",
            "an open decision is flagged and re-emitted rather than left in "
            "prose: no instrument here converts a measurement into a choice, so "
            "a row waiting on a person stays visible instead of fading",
            "the repository labels in this register are local handles for the "
            "join, not the parties' names",
        ],
    }


#: Fields recorded at EMISSION, describing the remote check rather than
#: the sources read. A faithfulness comparison must exclude exactly this
#: and nothing more -- a SIBLING's `commit` in particular stays in,
#: because it is the identity of what was read and is the whole point of
#: the artifact.
CURRENCY_FIELDS = ("currency",)


def without_currency(document: dict, deriving_party: str = "") -> dict:
    """The document minus what cannot be stable across the act of
    recording it.

    TWO EXCLUSIONS, AND THE SECOND IS THE DERIVING-PARTY ASYMMETRY
    AGAIN -- third appearance, after currency and after the mirror rule.

    CURRENCY. Faithfulness ("the register is what derivation produces
    from the commits it names") is checkable offline and forever;
    currency ("those commits are still the remote heads") stops being
    true the moment someone else pushes. Comparing them together makes
    an honest artifact read as corrupt.

    THE DERIVING PARTY'S OWN COMMIT. Found by the faithfulness gate
    failing, which is the gate working: the register records the commit
    its sources were read at, and committing the register ADVANCES that
    commit. So the artifact is always one commit stale about itself, and
    no emission order fixes it -- the value it would need is the hash of
    a commit that does not exist yet and will contain this file. It
    passed until now only because every emission was immediately
    followed by exactly one commit; two commits since an emission
    exposed it.

    A party cannot record, inside an artifact it is about to commit, the
    commit that will contain that artifact. So the deriving party's
    commit is recorded (it is the PARENT of the commit carrying this
    file, which is the honest reading) and excluded from the comparison.
    Sibling commits are not excluded and must match exactly: for them
    the value is not self-referential, and that is where drift would
    actually hide.
    """
    stripped = {k: v for k, v in document.items() if k not in CURRENCY_FIELDS}
    if not deriving_party:
        return stripped
    stripped["derived_from"] = [
        {k: v for k, v in entry.items()
         if not (entry.get("repository") == deriving_party and k == "commit")}
        for entry in stripped.get("derived_from", [])
    ]
    stripped["invariants"] = [
        {**entry, "claims": [
            {k: v for k, v in claim.items()
             if not (claim.get("asserted_by") == deriving_party and k == "source_commit")}
            for claim in entry.get("claims", [])]}
        for entry in stripped.get("invariants", [])
    ]
    return stripped


def deriving_party_of(document: dict) -> str:
    """Which party emitted this register, from the artifact itself."""
    return str(document.get("currency", {}).get("deriving_party", ""))
