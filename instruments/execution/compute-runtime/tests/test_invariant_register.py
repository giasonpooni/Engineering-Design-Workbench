"""Derived-register locks: the register is a projection of every bound
repository, and a stale projection is a FAILED derivation.

The defect these exist to catch actually occurred: the systems report
at d4d0c19 stated `generation_depth_bounded: identified` while the
acquisition layer had closed it, and eight further shared invariants
disagreed. No local check caught it, because every local check verifies
an artifact against itself.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from architecture.derive_register import (
    BOUND_REPOSITORIES,
    DerivationError,
    derive,
    register_document,
)
from architecture.exchange.canonical_yaml import canonical_bytes, canonical_sha256

REPO = pathlib.Path(__file__).resolve().parent.parent
EXCHANGE = REPO / "architecture" / "exchange"
PEERS_PRESENT = all(root.is_dir() for _, root in BOUND_REPOSITORIES)
peers_only = pytest.mark.skipif(
    not PEERS_PRESENT,
    reason="bound peer repositories not cloned here; environment gap, not an "
           "architectural pass -- the derivation itself fails closed on them",
)

#: THE SUITE DERIVES OFFLINE, AND THAT IS A DECISION WITH A REASON.
#:
#: The derivation establishes CURRENCY against the remotes, and that gate
#: is real -- it caught both sibling clones being behind, which is the
#: whole reason it exists. But a sibling pushed FOUR times during this
#: phase, and each push turned this repository's suite red for something
#: nobody here did wrong.
#:
#: A test that fails when a counterparty is productive is measuring the
#: counterparty, and it applies pressure in exactly the wrong direction:
#: the cheapest way to get green becomes weakening the staleness check.
#:
#: So the two properties are split. The suite asserts FAITHFULNESS -- the
#: committed register is exactly what derivation produces from the
#: commits it names -- which is this repository's responsibility and is
#: deterministic. CURRENCY is enforced where it belongs, at emission
#: (`build_invariant_register.py`, which asks every remote and refuses to
#: write a stale artifact) and reported on demand (`--currency`). The
#: currency gate's own behaviour is locked hermetically below, against a
#: local origin nobody else can push to.
OFFLINE = dict(check_remotes=False)


# -- the fail-closed contract (always runs, no peers needed) -----------------------------------------


def test_unreachable_bound_repository_fails_the_derivation():
    """A partial count is not a total. A bound repository that cannot be
    read fails the derivation rather than quietly shrinking it."""
    bogus = (("STE", REPO), ("GHOST", pathlib.Path("/nonexistent/repo")))
    with pytest.raises(DerivationError, match="unreachable"):
        derive(bogus, check_remotes=False)


def test_enforced_claims_must_cite_their_own_id(tmp_path):
    """The meta-test bar, applied across repositories: a claim of
    enforcement must name a file that CITES the invariant id. A cited
    file that never mentions it is not evidence for it."""
    fake = tmp_path / "repo"
    (fake / "architecture").mkdir(parents=True)
    (fake / "tests").mkdir()
    (fake / "tests" / "cites.py").write_text("# covers widget_is_bounded\n")
    (fake / "tests" / "silent.py").write_text("# covers something else\n")
    (fake / "architecture" / "invariants.yaml").write_text(
        "invariants:\n"
        "  - id: widget_is_bounded\n    status: enforced\n"
        "    enforcement: tests/cites.py\n"
        "  - id: gadget_is_bounded\n    status: enforced\n"
        "    enforcement: tests/silent.py\n"
    )
    subprocess.run(["git", "init", "-q", str(fake)], check=True)
    subprocess.run(["git", "-C", str(fake), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(fake), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "x"], check=True)

    records = derive((("FAKE", fake),), check_remotes=False).records
    assert records["widget_is_bounded"][0].evidence_cites_id is True
    assert records["gadget_is_bounded"][0].evidence_cites_id is False, (
        "a cited file that never names the id must not pass as evidence")


def test_every_derived_record_carries_the_commit_it_was_read_at():
    derivation = derive(check_remotes=False)
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert derivation.commits["STE"] == head
    for claims in derivation.records.values():
        for claim in claims:
            # each claim carries the commit of the repository that MADE
            # it, not the deriving repository's -- a register spanning
            # three parties has three answers to "as of when"
            assert claim.source_commit == derivation.commits[claim.asserted_by]
            assert len(claim.source_commit) == 40


# -- the core version is DECLARED, not inferred -------------------------------------------------------


def test_core_version_is_a_declaration_and_not_derived_from_packaging():
    """STE alone asserted core@0.1 -- about ITSELF -- while both peers
    had bound core@1.0.0.

    THE FIRST FIX WAS WRONG IN ITS REASONING and this test replaces the
    one that encoded it. That fix read the version out of pyproject.toml
    and asserted the two agreed. 1.0.0 is the right number, but a
    PACKAGE version moves on any release while a CORE-SCHEMA version
    moves only under bend_protocol. Binding them means a routine release
    renumbers the core with no invariant changing meaning -- and every
    `Bent: zero` this repository has ever claimed is asserted against a
    referent that moves without anyone bending anything.

    So the referent is declared, in one file, with the coupling
    explicitly denied.
    """
    declaration = yaml.safe_load(
        (REPO / "architecture" / "core.yaml").read_text())
    assert declaration["referent"]["derived_from_packaging"] is False
    assert declaration["referent"]["moves_only_under"] == "bend_protocol"
    assert declaration["referent"]["moves_on_release"] is False

    from architecture.conformance import core_version
    assert core_version() == f"core@{declaration['version']}"


def test_a_packaging_derived_core_version_is_refused():
    """The denial is enforced, not decorative: flip the flag and the
    gate refuses to produce a version at all."""
    from architecture import conformance

    original = (REPO / "architecture" / "core.yaml").read_text()
    try:
        (REPO / "architecture" / "core.yaml").write_text(
            original.replace("derived_from_packaging: false",
                             "derived_from_packaging: true"))
        with pytest.raises(conformance.ConformanceError, match="declaration"):
            conformance.core_version()
    finally:
        (REPO / "architecture" / "core.yaml").write_text(original)


def test_moving_the_declared_core_version_breaks_every_artifact_that_binds_it():
    """WHAT ACTUALLY FALSIFIES A WRONG CORE VERSION, once it is no longer
    derived from anything.

    Found by mutation: setting the declaration to 0.1 left the
    declaration test green. That test compares the declaration against
    itself, and a self-consistent declaration is unfalsifiable on its
    own -- which is the cost of decoupling the referent from packaging,
    and has to be paid somewhere else rather than pretended away.

    It is paid by the CLOSURE. Every architecture artifact binds
    `extends: core@<v>` and the gate requires all of them to match the
    declaration, so a version that moves stops the whole repository
    conforming at once. That is bend_protocol's teeth: the version
    cannot move quietly, because moving it invalidates every declared
    vertical and probe by construction rather than by anyone
    remembering to re-run them.
    """
    from architecture import conformance

    core = REPO / "architecture" / "core.yaml"
    original = core.read_text()
    assert conformance.check_core_closure(), "the closure must bind something"
    try:
        core.write_text(original.replace('version: "1.0.0"', 'version: "0.1"'))
        with pytest.raises(conformance.ConformanceError, match="re-running every"):
            conformance.check_core_closure()
    finally:
        core.write_text(original)
    # and it recovers -- the failure is the mismatch, not the check
    assert conformance.check_core_closure()


def test_the_core_version_is_stated_in_exactly_one_place():
    """One referent, one place. `invariants.yaml` used to restate the
    version beside the registry; it now points at the declaration. Two
    copies of a referent is how they diverge."""
    registry = yaml.safe_load(
        (REPO / "architecture" / "invariants.yaml").read_text())
    assert "core" not in registry, (
        "the registry must not restate the core version -- it points at "
        "architecture/core.yaml")
    assert registry["core_declaration"] == "architecture/core.yaml"


# -- the cross-repo derivation itself ----------------------------------------------------------------


@peers_only
def test_the_committed_register_is_faithful_to_the_commits_it_names():
    """FAITHFULNESS, not currency -- see the OFFLINE note above.

    Re-derive from the clones on disk and require byte equality. This is
    the check whose absence let the systems report go stale, in the half
    of it that is this repository's to guarantee: whatever the register
    says it read, it really read.
    """
    from architecture.derive_register import (
        CURRENCY_FIELDS, deriving_party_of, without_currency)

    raw = (EXCHANGE / "invariant_register.yaml").read_bytes()
    committed = yaml.safe_load(raw.decode())
    fresh = register_document(derive(**OFFLINE))
    party = deriving_party_of(committed)

    assert without_currency(committed, party) == without_currency(fresh, party), (
        "the committed register is not what derivation produces from the "
        "clones on disk -- either it was hand-edited, or a clone moved "
        "since emission (run build_invariant_register.py --currency)")

    # the digest covers the WHOLE artifact, currency fields included --
    # only the comparison above is narrowed, never what is signed
    assert (EXCHANGE / "invariant_register.sha256").read_text().strip() == \
        canonical_sha256(committed)
    assert canonical_bytes(committed) == raw

    # and the artifact records that its currency WAS established when it
    # was written, even though this check deliberately did not re-ask
    currency = committed["currency"]
    assert currency["checked_against_remotes"] is True
    assert currency["per_party"]["STE"]["currency"] == "authoritative_for_itself"
    for label in ("DAQ", "SCL"):
        entry = currency["per_party"][label]
        assert entry["currency"] in ("in_sync", "local_ahead_of_remote")
        assert len(entry["remote"]) == 40
    assert set(CURRENCY_FIELDS) == {"currency"}, (
        "widening the excluded set would let a real drift hide in the gap")


@peers_only
def test_a_deferred_row_resolves_to_the_owner_s_LIVE_status():
    """`generation_depth_bounded` is the row that started this phase: it
    read `identified` here while the acquisition layer had closed it.

    The fix is not a corrected copy -- a corrected copy is the same
    artifact one correction later, and this one had already gone two
    corrections stale in the sibling pair with every suite green. This
    repository now records the OWNER and no status for it at all, and
    the register resolves the owner's value on every derivation.
    """
    derivation = derive(**OFFLINE)
    claims = {c.asserted_by: c for c in derivation.records["generation_depth_bounded"]}
    assert claims["STE"].owner_elsewhere == "DAQ"
    assert claims["STE"].scope == "this_repository"

    entry = next(i for i in register_document(derivation)["invariants"]
                 if i["id"] == "generation_depth_bounded")
    ste = next(c for c in entry["claims"] if c["asserted_by"] == "STE")
    assert ste["defers_to"] == "DAQ"
    assert ste["owner_status_resolved"] == claims["DAQ"].status
    assert entry["owning_repository"] == "DAQ"
    assert entry["contested"] is False, (
        "a row that names its owner instead of asserting a competing "
        "status is deferred, not contested")

    # and the owner's value is never written down on this side: the row
    # names DAQ and states only what is true HERE
    row = next(
        i for i in yaml.safe_load(
            (REPO / "architecture" / "evidence_class.yaml").read_text())["invariants"]
        if i["id"] == "generation_depth_bounded")
    assert row["owner_elsewhere"] == "DAQ"
    assert row["status"] != claims["DAQ"].status, (
        "the owner's status must not be transcribed here at any version; a "
        "transcribed status is exactly the artifact that went stale")


@peers_only
def test_a_deferral_to_a_party_that_says_nothing_fails():
    """A pointer is only better than a copy if it RESOLVES. Deferring to
    a party that asserts nothing for the id would read as settled while
    resolving to silence."""
    document = register_document(derive(**OFFLINE))
    for entry in document["invariants"]:
        for claim in entry["claims"]:
            if claim["defers_to"]:
                assert claim["owner_status_resolved"], (
                    f"{entry['id']}: deferral to {claim['defers_to']} "
                    f"resolved to nothing")


def test_a_planted_disagreement_IS_detected_as_contested(tmp_path):
    """THE REACHABILITY PROOF, and it is required before the current
    count means anything.

    The derivation now reports ZERO contested rows, down from nine. Nine
    became zero through two real changes -- four rows now name their
    owner instead of copying a status, five declare the per-repository
    scope they always had -- but "zero" is also exactly what a broken
    detector reports, and this project does not interpret a rate it has
    not shown to be reachable. So: plant a genuine same-scope
    disagreement and require the derivation to find it.
    """
    roots = []
    for name, status in (("ALPHA", "enforced"), ("BETA", "identified")):
        root = tmp_path / name
        (root / "architecture").mkdir(parents=True)
        (root / "architecture" / "invariants.yaml").write_text(
            f"invariants:\n  - id: shared_claim\n    status: {status}\n")
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c",
                        "user.name=t", "commit", "-qm", "x"], check=True)
        roots.append((name, root))

    derivation = derive(tuple(roots), check_remotes=False)
    assert "shared_claim" in derivation.contested, (
        "the detector must find a planted same-scope disagreement; a zero "
        "count from a detector that finds nothing is not a measurement")

    # and scoping it per-repository is what makes it stop contesting --
    # so the exemption is shown to be the scope declaration doing work,
    # not the detector having failed.
    for _, root in roots:
        path = root / "architecture" / "invariants.yaml"
        path.write_text(path.read_text().replace(
            "  - id: shared_claim\n", "  - id: shared_claim\n    scope: this_repository\n"))
    assert "shared_claim" not in derive(tuple(roots), check_remotes=False).contested


@peers_only
def test_no_repository_reports_a_status_for_an_invariant_it_does_not_own():
    """Every claim in the register names the repository that made it and
    the file it was read from -- so a status can always be traced to a
    source rather than to the register's own reading."""
    document = register_document(derive(**OFFLINE))
    for entry in document["invariants"]:
        for claim in entry["claims"]:
            assert claim["asserted_by"] and claim["source_file"]
            assert len(claim["source_commit"]) == 40


def test_emitted_projections_are_never_read_as_canonical_sources():
    """The same defect appeared on two surfaces this phase: the derived
    register lives under architecture/ and was picked up BOTH by its own
    derivation (doubling the count, every status `unstated`) and by the
    core-closure lint (which demanded an `extends` a projection cannot
    honestly carry). Both excluded exchange/; this pins the rule so a
    third surface cannot reacquire it."""
    from architecture.conformance import check_core_closure
    from architecture.derive_register import derive

    register = EXCHANGE / "invariant_register.yaml"
    assert register.exists(), "the projection under test must be present"

    # the derivation does not read its own output
    ids = {k: v for k, v in derive(check_remotes=False).records.items()
           if any(c.asserted_by == "STE" for c in v)}
    document = yaml.safe_load(register.read_text())
    projection_ids = {i["id"] for i in document["invariants"]}
    canonical_ids = set(ids)
    assert len(canonical_ids) < len(projection_ids), (
        "the projection spans repositories; STE's own canonical sources "
        "must be strictly fewer -- equality means self-ingestion")

    # the core-closure lint does not demand a binding from a projection
    # -- and it now asks the same question the derivation asks, rather
    # than skipping a DIRECTORY that happened to contain the one file
    # anyone had noticed. A hand-authored declaration filed beside the
    # projection is checked; the projection is not.
    checked = {p.name for p in check_core_closure()}
    assert "invariant_register.yaml" not in checked
    assert "ste_invariant_declaration.yaml" in checked, (
        "an authored declaration must be held to the core it binds, "
        "wherever it is filed")


# -- three parties, one with no invariant source -----------------------------------------------------


@peers_only
def test_a_bound_party_with_no_invariant_source_is_represented_not_dropped():
    """The compute layer holds no `invariants.yaml` and no probe. That
    is a BINDING MODE, not an absence to route around.

    The distinction this pins: a party contributing zero records and a
    party the derivation failed to read produce the same number. Only
    one of them is a fact. So `extends_only` is recorded explicitly,
    with the files that bind it NAMED -- the register can be read to see
    that the compute layer declares none, rather than leaving a reader
    to infer it from a count.
    """
    document = register_document(derive(**OFFLINE))
    assert document["bound_parties"] == 3
    assert document["parties_with_no_invariant_source"] == ["SCL"]

    scl = next(e for e in document["derived_from"] if e["repository"] == "SCL")
    assert scl["binding_mode"] == "extends_only"
    assert scl["invariants_contributed"] == 0
    assert scl["invariant_sources"] == []
    assert scl["bound_core"] == "core@1.0.0"
    assert scl["binding_files"], (
        "a party with no invariant source must still NAME what binds it; "
        "zero records with no binding evidence is not a bound party")

    for label in ("STE", "DAQ"):
        entry = next(e for e in document["derived_from"] if e["repository"] == label)
        assert entry["binding_mode"] == "invariant_registry"
        assert entry["invariants_contributed"] > 0


def test_a_party_with_neither_invariants_nor_a_binding_fails(tmp_path):
    """`extends_only` is a claim with evidence, and this is the case it
    must not silently absorb: a repository declaring no invariants AND
    no `extends` is not bound with no source -- nothing establishes it
    is bound at all, and counting it as a contributor of zero would be
    the register asserting a binding on the party's behalf."""
    root = tmp_path / "unbound"
    (root / "architecture").mkdir(parents=True)
    (root / "architecture" / "notes.yaml").write_text("topic: nothing binding\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "x"], check=True)

    with pytest.raises(DerivationError, match="not demonstrably bound"):
        derive((("UNBOUND", root),), check_remotes=False)


# -- currency is established against the REMOTE ------------------------------------------------------


def test_a_clone_behind_its_remote_fails_the_derivation(tmp_path):
    """MEASURED, AND THIS IS WHY IT EXISTS. On 2026-08-26 the previous
    derivation recorded both sibling clones' local HEADs as the commits
    it had derived from, and called them current. Both were behind their
    remotes at that moment; one moved again between a fetch and the next
    derivation minutes later.

    A local commit proves authorship. Only the remote head proves the
    clone is current, and recording the wrong side of that question is
    a register that names its sources and is still stale.
    """
    upstream = tmp_path / "origin"
    subprocess.run(["git", "init", "-q", "--bare", str(upstream)], check=True)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(upstream), str(clone)], check=True)
    (clone / "architecture").mkdir(parents=True)
    (clone / "architecture" / "invariants.yaml").write_text(
        "extends: core@1.0.0\ninvariants:\n  - id: a\n    status: enforced\n")
    git = ["git", "-C", str(clone), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "-C", str(clone), "add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "one"], check=True)
    branch = subprocess.run(["git", "-C", str(clone), "branch", "--show-current"],
                            capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", branch], check=True)

    # in sync -- derives
    assert derive((("C", clone),)).bindings["C"].currency == "in_sync"

    # local ahead (unpushed work being derived) -- derives, and SAYS SO
    (clone / "architecture" / "invariants.yaml").write_text(
        "extends: core@1.0.0\ninvariants:\n  - id: a\n    status: enforced\n"
        "  - id: b\n    status: identified\n")
    subprocess.run(["git", "-C", str(clone), "add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "two"], check=True)
    assert derive((("C", clone),)).bindings["C"].currency == "local_ahead_of_remote"

    # remote ahead -- the stale case, and it FAILS
    subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", branch], check=True)
    subprocess.run(git + ["reset", "-q", "--hard", "HEAD~1"], check=True)
    with pytest.raises(DerivationError, match="FAILED derivation"):
        derive((("C", clone),))


def test_an_offline_derivation_never_claims_currency_it_did_not_check():
    """`check_remotes=False` is allowed and is recorded. What must not
    exist is a register that reads the same whether or not the question
    was asked."""
    offline = register_document(derive(check_remotes=False))["currency"]
    assert offline["checked_against_remotes"] is False
    for label, entry in offline["per_party"].items():
        assert entry["remote"] == ""
        if entry["role"] == "sibling":
            assert entry["currency"] == "not_checked"
    # the deriving party's exemption is structural and survives going
    # offline -- it was never the remote check that granted it
    assert offline["per_party"]["STE"]["currency"] == "authoritative_for_itself"


# -- one party, two names ----------------------------------------------------------------------------


@peers_only
def test_a_mirror_is_not_a_source__the_general_rule():
    """THE SAME DEFECT IN THREE POSITIONS, closed once.

    It arrived as a circular derivation (the emitted register re-read by
    its own derivation), as a top-level owner read as a row's owner, and
    as one party's self-declaration read out of another party's
    artifact. The invariant across all three: **a mirror is not a
    source**, and BYTE-IDENTITY IS WHAT MAKES IT DANGEROUS -- a mirror
    and its origin are the same bytes by design, so nothing in the
    content can separate them. Only provenance can.

    So provenance is established across all parties first, and each read
    asks what it is entitled to read. This pins the entitlements rather
    than any one of the three symptoms.
    """
    document = register_document(derive(**OFFLINE))
    by_label = {e["repository"]: e for e in document["derived_from"]}

    # (3) a self-declaration is readable only from a file the party
    #     provably authored. SCL holds a byte-identical mirror of DAQ's
    #     requirement response, which carries DAQ's `also_known_as`.
    assert by_label["DAQ"]["self_declared_names"], "DAQ declares a correspondence"
    assert by_label["SCL"]["self_declared_names"] == [], (
        "the mirror SCL holds is DAQ's self-declaration, not SCL's")
    assert "architecture/exchange/daq_requirement_response.yaml" in \
        by_label["SCL"]["artifacts_held_but_authored_elsewhere"]
    assert "architecture/exchange/scl_requirements.yaml" in \
        by_label["DAQ"]["artifacts_held_but_authored_elsewhere"], (
            "the rule is symmetric -- each party mirrors the other's artifact")

    # (1) an emitted projection is never a canonical invariant source,
    #     wherever it is filed and whoever emitted it
    for entry in document["derived_from"]:
        for source in entry["invariant_sources"]:
            held = yaml.safe_load(
                (dict(BOUND_REPOSITORIES)[entry["repository"]] / source).read_text())
            assert "generated_by" not in held, (
                f"{entry['repository']}:{source} declares a generator -- it is a "
                f"projection and must not be read as a canonical source")

    # ...and the labels are never asserted to BE the parties' names
    for entry in document["derived_from"]:
        assert entry["label_is_a_local_handle_not_the_party_s_name"] is True


@peers_only
def test_deriving_twice_is_a_fixed_point():
    """THE PROOF THAT A PROJECTION IS NOT A SOURCE, rather than the
    assertion that it isn't.

    If the emitted register were readable as a source, a second
    derivation would differ from the first -- that is exactly what
    happened when the directory-based exclusion was replaced by the
    general rule and the artifact did not yet declare itself emitted:
    26 invariants became 77 and every row read as contested.

    A fixed point cannot be reached by an artifact that feeds itself.
    """
    first = canonical_bytes(register_document(derive(**OFFLINE)))
    committed = yaml.safe_load(
        (EXCHANGE / "invariant_register.yaml").read_bytes().decode())
    from architecture.derive_register import deriving_party_of, without_currency
    party = deriving_party_of(committed)
    assert without_currency(yaml.safe_load(first.decode()), party) == \
        without_currency(committed, party)

    second = canonical_bytes(register_document(derive(**OFFLINE)))
    assert first == second, (
        "re-deriving over the emitted artifact changed the result -- the "
        "projection is being read as a source")


@peers_only
def test_a_single_authored_artifact_two_parties_hold_credits_neither():
    """The case that separates a joint record from a mirror.

    Shared bytes that NAME an author were written by exactly one holder,
    and this derivation cannot say which: the author tokens are in each
    party's own vocabulary, and resolving them here would be the
    deriving party deciding another party's identity. Crediting the
    holder would assert a binding the party never declared.

    Excluded from both, and LISTED -- a limitation that costs a party
    evidence should be visible to that party rather than silently
    applied.
    """
    document = register_document(derive(**OFFLINE))
    for entry in document["derived_from"]:
        set_aside = entry["artifacts_set_aside_authorship_unresolved"]
        assert not (set(set_aside) & set(entry["binding_files"])), (
            "an artifact whose author is unresolved must not also be counted "
            "as this party's binding evidence")
    scl = next(e for e in document["derived_from"] if e["repository"] == "SCL")
    assert scl["binding_files"], (
        "excluding unresolved authorship must not leave a bound party with no "
        "evidence at all -- a party that really binds says so somewhere it "
        "authored alone")


# -- currency is directional, and per sibling ---------------------------------------------------------


@peers_only
def test_the_deriving_party_is_exempt_by_construction_not_by_tolerance():
    """A party's own HEAD is authoritative FOR ITSELF.

    It cannot be stale against itself, and it diverges from its remote
    the instant it commits the work being derived. The first
    implementation gave every party the same lenient comparison, which
    let the deriving party through for the wrong reason -- and would
    have excused a SIBLING sitting in exactly the same position.

    The exemption is now structural and visible, so a reader can audit
    it instead of inferring it from a state that happens to pass.
    """
    currency = register_document(derive(**OFFLINE))["currency"]
    assert currency["deriving_party"] == "STE"
    assert currency["deriving_party_is_exempt_by_construction"] is True
    assert currency["per_party"]["STE"]["role"] == "deriving_party"
    # THE ASSERTION THE FIRST VERSION OF THIS TEST WAS MISSING, found by
    # mutation: routing the deriving party through the sibling check
    # left every line above true, because STE happened to be in sync at
    # that moment. It is the STATE that has to be structural -- a value
    # only reachable by being the deriving party, never by passing a
    # comparison.
    assert currency["per_party"]["STE"]["currency"] == "authoritative_for_itself"
    for label in ("DAQ", "SCL"):
        assert currency["per_party"][label]["role"] == "sibling"
        assert currency["per_party"][label]["currency"] != "authoritative_for_itself"


@peers_only
def test_currency_is_reported_per_sibling_and_never_collapsed():
    """A derivation is only as current as its WORST sibling -- and which
    sibling that is, at which commit, is part of the answer.

    A single boolean throws away both halves. This asserts the rollup
    names a specific sibling and that the deriving party can never be
    it, since it is not a sibling and cannot be the constraint."""
    derivation = derive(**OFFLINE)
    currency = register_document(derivation)["currency"]
    assert set(currency["per_party"]) == {"STE", "DAQ", "SCL"}

    worst = derivation.worst_sibling
    assert worst is not None and not worst.is_deriving_party
    assert worst.label in currency["as_current_as_its_worst_sibling"]
    assert currency["deriving_party"] not in \
        currency["as_current_as_its_worst_sibling"].split()[0]



def test_a_repository_that_defers_cannot_be_derived_alone():
    """A CONSEQUENCE OF DEFERRING, and it is the property working rather
    than a limitation of it.

    Once this repository names an owner instead of copying a status, its
    register is no longer self-contained: four of its rows have no
    status here at any version. Deriving it alone therefore FAILS
    instead of quietly producing a register with four unresolvable
    pointers in it.

    This is what the copied status bought and what giving it up costs.
    A copy always reads complete, which is precisely why it can be two
    corrections stale with every local suite green.
    """
    with pytest.raises(DerivationError, match="not a bound party"):
        derive((("STE", REPO),), check_remotes=False)


def _planted_party(root, body, *, with_origin=False):
    """A minimal bound repository, optionally with a real local remote."""
    (root / "architecture").mkdir(parents=True, exist_ok=True)
    for name, text in body.items():
        (root / "architecture" / name).write_text(text)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "x"], check=True)
    return root


def test_a_JOINT_artifact_is_not_read_as_either_party_s_self_declaration(tmp_path):
    """Shared bytes with no generator: neither party can be shown to
    have authored it, and `cannot establish` is never `authored`.

    FOUND BY MUTATION. Deciding provenance per-repository instead of
    across parties left the mirror test green, because the mirror in
    that pair carries a generator and took a different branch entirely.
    The branch the mutation actually broke — two parties holding
    identical bytes that name no author — had nothing asserting on it.
    A rule is not covered because one of its arms is.
    """
    shared = ('extends: core@1.0.0\n'
              'also_known_as: "the name in the jointly agreed file"\n'
              'invariants:\n  - id: agreed_row\n    status: enforced\n')
    parties = []
    for name in ("ALPHA", "BETA"):
        root = _planted_party(tmp_path / name, {
            "joint.yaml": shared,
            "own.yaml": f'extends: core@1.0.0\ninvariants:\n'
                        f'  - id: {name.lower()}_own\n    status: enforced\n',
        })
        parties.append((name, root))

    derivation = derive(tuple(parties), check_remotes=False)

    # neither party is credited with the name in the shared file
    for _, binding in derivation.bindings.items():
        assert binding.self_declared_names == (), (
            "a jointly held artifact says what was agreed, not what either "
            "party is called")
    # nor is its invariant row read as either party's own claim
    assert "agreed_row" not in derivation.records, (
        "a registry two parties hold identically is not evidence of who wrote it")
    for name in ("alpha_own", "beta_own"):
        assert name in derivation.records, "each party's sole-held rows still count"
    # but it DOES evidence both parties' binding -- a joint record both
    # signed binds both, which is what separates it from a mirror
    for _, binding in derivation.bindings.items():
        assert "architecture/joint.yaml" in binding.binding_files


def test_the_worst_sibling_is_selected_not_the_first_one_read(tmp_path):
    """A derivation is only as current as its WORST sibling.

    FOUND BY MUTATION: returning `siblings[0]` instead of the minimum
    was indistinguishable in production, because both siblings happened
    to be in sync. Two siblings in DIFFERENT states are what make the
    selection observable at all — so the worse one is planted second,
    where a first-one-read rule would miss it.
    """
    parties = []
    for name in ("AHEAD_ONE", "SYNCED_ONE"):
        upstream = tmp_path / f"{name}.git"
        subprocess.run(["git", "init", "-q", "--bare", str(upstream)], check=True)
        clone = tmp_path / name
        subprocess.run(["git", "clone", "-q", str(upstream), str(clone)], check=True)
        (clone / "architecture").mkdir(parents=True)
        (clone / "architecture" / "own.yaml").write_text(
            f'extends: core@1.0.0\ninvariants:\n  - id: {name.lower()}\n'
            f'    status: enforced\n')
        git = ["git", "-C", str(clone), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(["git", "-C", str(clone), "add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "one"], check=True)
        branch = subprocess.run(["git", "-C", str(clone), "branch", "--show-current"],
                                capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", branch],
                       check=True)
        parties.append((name, clone))

    # make the FIRST party the healthy one and the SECOND the worse one
    ahead = parties[0][1]
    (ahead / "architecture" / "own.yaml").write_text(
        (ahead / "architecture" / "own.yaml").read_text() + "  - id: extra\n    status: enforced\n")
    subprocess.run(["git", "-C", str(ahead), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(ahead), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "unpushed"], check=True)

    derivation = derive(tuple(reversed(parties)))   # synced read FIRST
    states = {b.label: b.currency for b in derivation.siblings}
    assert states == {"AHEAD_ONE": "local_ahead_of_remote", "SYNCED_ONE": "in_sync"}

    worst = derivation.worst_sibling
    assert worst.label == "AHEAD_ONE", (
        "the rollup must name the worst sibling, not whichever was read first")
    assert "AHEAD_ONE" in register_document(derivation)["currency"][
        "as_current_as_its_worst_sibling"]


@peers_only
def test_open_decisions_are_derived_and_re_emitted_not_left_in_prose():
    """A PROPERTY OF THIS PROJECT, made visible.

    Every instrument here converts an assumption into a MEASUREMENT and
    none converts a measurement into a CHOICE. Probes, mutation
    batteries, reachability traces, currency gates and this register all
    answer "what is true"; not one answers "what should be done about
    it". Five rows are therefore waiting on a person, which is a
    reasonable place to wait -- so long as the register keeps saying so.

    A prose note survives by inertia, which is how four of these reached
    twenty phases. A derived field cannot: it is re-emitted on every run
    and goes stale loudly.
    """
    document = register_document(derive(**OFFLINE))
    awaiting = document["awaiting_a_decision"]
    assert "evidence_append_only" in awaiting, (
        "the one recorded candidate bend must stay visible")
    assert "self_optimization_acceptance_criteria" in awaiting

    for entry in document["invariants"]:
        for claim in entry["claims"]:
            if entry["id"] in awaiting and claim["asserted_by"] == "STE":
                assert claim["awaiting_decision"], (
                    f"{entry['id']} is listed as awaiting a decision and the "
                    f"claim does not say WHICH -- that is a note again")


@peers_only
def test_an_open_decision_is_not_the_same_as_a_contest():
    """Zero contested and five awaiting are both true at once, and
    collapsing either into the other is the error this register exists to
    stop. A contest is two parties disagreeing about what IS. An open
    decision is nobody having chosen what SHOULD BE -- no amount of
    further measurement closes it."""
    derivation = derive(**OFFLINE)
    assert not derivation.contested
    assert derivation.awaiting_a_decision
    assert not (set(derivation.contested) & set(derivation.awaiting_a_decision))


@peers_only
def test_a_sibling_commit_is_never_excluded_from_the_comparison():
    """The exclusion is narrow on purpose, and this is the half that
    would matter if it were not.

    The deriving party's own commit is excluded because it cannot be
    stable across the act of recording it -- committing the register
    advances the very value the register carries. A SIBLING's commit has
    no such property: it is the identity of what was read, it is where
    drift would actually hide, and it must match exactly.
    """
    from architecture.derive_register import deriving_party_of, without_currency

    committed = yaml.safe_load((EXCHANGE / "invariant_register.yaml").read_text())
    party = deriving_party_of(committed)
    assert party, "the artifact must name its deriving party"

    stripped = without_currency(committed, party)
    for entry in stripped["derived_from"]:
        if entry["repository"] == party:
            assert "commit" not in entry
        else:
            assert len(entry["commit"]) == 40, (
                f"{entry['repository']} is a sibling -- its commit is not "
                f"self-referential and must survive the comparison")

    # a tampered sibling commit must still be caught
    tampered = yaml.safe_load((EXCHANGE / "invariant_register.yaml").read_text())
    sibling = next(e for e in tampered["derived_from"] if e["repository"] != party)
    sibling["commit"] = "0" * 40
    assert without_currency(tampered, party) != stripped, (
        "changing a sibling's commit must change the comparison, or the "
        "exclusion has swallowed the thing it was narrowed to protect")


# ------------------------------- a dirty sibling is not a stale one --


def _derive_over_a_dirty_sibling():
    """Build a throwaway sibling with an uncommitted edit and derive."""
    import subprocess
    import tempfile

    from architecture.derive_register import derive

    directory = tempfile.mkdtemp()
    sibling = pathlib.Path(directory) / "sibling"
    sibling.mkdir()
    for command in (["init", "-q", "-b", "main"],
                    ["config", "user.email", "t@example.invalid"],
                    ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(sibling), *command], check=True,
                       capture_output=True)
    (sibling / "architecture").mkdir()
    (sibling / "architecture" / "apparatus.yaml").write_text("name: sibling\n")
    subprocess.run(["git", "-C", str(sibling), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(sibling), "commit", "-qm", "one"],
                   check=True, capture_output=True)
    (sibling / "architecture" / "apparatus.yaml").write_text("name: edited\n")
    return derive([("STE", REPO), ("SIB", sibling)], check_remotes=True)


def test_a_dirty_sibling_clone_is_refused_and_names_the_files():
    """THE HALF THE CURRENCY CHECK WAS MISSING, and the sharper half.

    `_sibling_currency` asks whether a clone's HEAD has fallen behind
    its remote. It never asked whether the WORKING TREE matches that
    HEAD. A stale clone names an older commit honestly -- a reader can
    go and look it up. A DIRTY clone names a commit that never contained
    what was read, which is a citation to a source that does not say
    what it is quoted as saying.

    FOUND BY CAUSING IT: a patch applied to a sibling's working tree and
    left uncommitted put four register fixed-points out, and the deriver
    had nothing to say about why.
    """
    import subprocess
    import tempfile

    from architecture.derive_register import DerivationError, derive

    with tempfile.TemporaryDirectory() as directory:
        sibling = pathlib.Path(directory) / "sibling"
        sibling.mkdir()
        for command in (["init", "-q", "-b", "main"],
                        ["config", "user.email", "t@example.invalid"],
                        ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", str(sibling), *command], check=True,
                           capture_output=True)
        (sibling / "architecture").mkdir()
        (sibling / "architecture" / "apparatus.yaml").write_text("name: sibling\n")
        subprocess.run(["git", "-C", str(sibling), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(sibling), "commit", "-qm", "one"],
                       check=True, capture_output=True)

        # CLEAN: the dirtiness check must not fire. Currency is not asked
        # (no remote), so reaching any later refusal proves this one passed.
        from architecture.derive_register import _uncommitted
        assert _uncommitted(sibling) == ()

        # DIRTY: it must fire, and name the file
        (sibling / "architecture" / "apparatus.yaml").write_text("name: edited\n")
        changed = _uncommitted(sibling)
        assert changed == ("architecture/apparatus.yaml",), changed

        with pytest.raises(DerivationError) as caught:
            derive([("STE", REPO), ("SIB", sibling)], check_remotes=True)
        message = str(caught.value)
        assert "differ from its own HEAD" in message
        assert "apparatus.yaml" in message
        assert "worse than recording a stale one" in message


def test_the_dirtiness_refusal_is_distinct_from_the_staleness_one():
    """Two different failures with two different remedies. A message
    that conflated them would send a reader to fetch when the fix is to
    commit.

    Driven at RUNTIME rather than grepped from the source. The first
    version of this check read `derive_register.py` looking for the
    sentence, and failed -- because the sentence is split across two
    source lines by the formatter. A source grep tests spelling; only
    running the thing tests what it says."""
    from architecture.derive_register import DerivationError

    with pytest.raises(DerivationError) as dirty:
        _derive_over_a_dirty_sibling()
    message = str(dirty.value)

    assert "differ from its own HEAD" in message
    assert "Commit or revert the sibling" in message
    # and it must NOT send the reader to fetch, which fixes the other one
    assert "fetch first" not in message
