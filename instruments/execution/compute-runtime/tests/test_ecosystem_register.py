"""Locks on the ecosystem register.

WHAT IT IS FOR. A company-level map of "our systems" is the kind of
claim that is true when written and false a month later, invisibly,
because nothing recomputes it. So it is derived on every run, and these
pin the three ways the derivation could flatter us:

  reading the ORG PREFIX as a provenance claim -- 12 of the 22 vendored
  repositories sit under our own org while being other parties' work

  counting PRESENCE as PARTICIPATION -- 13 are referenced by nothing

  letting the INSTRUMENT'S OWN PROSE count as evidence about what it
  measures, which is how `topopy` and `RiemannFM` first came back
  INTEGRATED when nothing anywhere references either
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "architecture"))

from architecture import ecosystem as eco

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "architecture" / "exchange" / "ecosystem_register.yaml"


def _facts(**over):
    base = dict(
        name="x", path=ROOT, remote=f"{eco.ORG}/x", branch="main",
        commit="0" * 12, commit_count=1, authors=(), copyright_holders=(),
        declares_core=(), bound_core="", declared_upstream="",
        role=eco.NOT_DECLARED, role_source="")
    base.update(over)
    return eco.RepoFacts(**base)


# ------------------------------------ org ownership is not authorship --


def test_our_org_alone_never_makes_something_an_apparatus():
    """THE FINDING. A fork under your own org is the most convincing
    mirror there is, because the URL agrees with the claim."""
    verdict = eco.classify(_facts(remote=f"{eco.ORG}/topopy",
                                  authors=("Dan Maljovec",),
                                  copyright_holders=("2018, Dan Maljovec",)))
    assert verdict.verdict == eco.VENDORED_INPUT
    assert verdict.mirrored_under_our_org is True


def test_an_outside_remote_with_our_core_declaration_is_still_ours():
    """The converse, so the rule is about EVIDENCE and not about the
    URL in either direction."""
    verdict = eco.classify(_facts(remote="someone-else/thing",
                                  authors=(eco.AUTHORED_BY,),
                                  declares_core=("architecture/core.yaml",),
                                  bound_core="core@1.0.0"))
    assert verdict.verdict == eco.APPARATUS
    assert verdict.mirrored_under_our_org is False


def test_a_repository_with_no_discriminating_evidence_is_unresolved():
    """Never rounded toward ours. Two verdicts would force a guess; the
    third is what makes refusing possible."""
    verdict = eco.classify(_facts())
    assert verdict.verdict == eco.UNRESOLVED


def test_all_three_verdicts_are_reachable_from_constructed_facts():
    """Every branch driven, so a classifier that returned a constant is
    killed. A check whose inputs are uniform tests nothing about the
    selection."""
    reached = {
        eco.classify(_facts(authors=(eco.AUTHORED_BY,),
                            declares_core=("a.yaml",))).verdict,
        # VENDORED needs a STRONG signal now; an author alone is not one
        eco.classify(_facts(copyright_holders=("2018, Someone Else",))).verdict,
        eco.classify(_facts(authors=("Someone Else",))).verdict,
    }
    assert reached == {eco.APPARATUS, eco.VENDORED_INPUT, eco.UNRESOLVED}


def test_a_core_declaration_without_our_authorship_is_not_an_apparatus():
    """Both halves are required. A vendored repo that happened to carry
    a matching declaration would otherwise be adopted.

    It is UNRESOLVED rather than VENDORED_INPUT with no strong signal --
    not adopted, and not disowned either. Both overclaims are refused
    and the test asserts the one thing the evidence supports."""
    verdict = eco.classify(_facts(declares_core=("architecture/core.yaml",),
                                  bound_core="core@1.0.0",
                                  authors=("Upstream Maintainer",)))
    assert verdict.verdict != eco.APPARATUS
    assert verdict.verdict == eco.UNRESOLVED
    # and with a strong signal it settles as vendored
    with_grant = eco.classify(_facts(declares_core=("architecture/core.yaml",),
                                     bound_core="core@1.0.0",
                                     authors=("Upstream Maintainer",),
                                     copyright_holders=("2019, Upstream Co",)))
    assert with_grant.verdict == eco.VENDORED_INPUT


# ----------------------------- the instrument is not its own evidence --


def test_the_measuring_apparatus_is_excluded_from_what_it_measures():
    """THE CONTAMINATION, PINNED. This module's docstring cites `topopy`
    and `RiemannFM` as examples of the mirror finding, and those
    citations made both come back INTEGRATED while nothing anywhere
    referenced either. An instrument that names what it classifies will
    classify its own prose."""
    assert "architecture/ecosystem.py" in eco.MEASURING_APPARATUS
    for name in ("topopy", "RiemannFM"):
        assert name in (ROOT / "architecture" / "ecosystem.py").read_text(), (
            "the citation is still there, so the exclusion is still load-bearing")


def test_every_excluded_path_exists():
    """A too-NARROW exclusion lets the contamination back in."""
    missing = [rel for rel in eco.MEASURING_APPARATUS if not (ROOT / rel).exists()]
    assert missing == []


def test_nothing_outside_the_instrument_is_excluded():
    """A too-WIDE exclusion hides a real dependency, which fails in the
    direction that makes the system look smaller and cleaner than it is.
    Every excluded path must name this measurement."""
    for rel in eco.MEASURING_APPARATUS:
        text = (ROOT / rel).read_text(errors="replace")
        assert "ecosystem" in rel or "ecosystem" in text.lower(), rel


def test_the_names_cited_in_the_instrument_are_reported_unreferenced():
    """The end-to-end proof that the exclusion works: the two names the
    docstring cites are exactly the ones that were wrong, and they must
    now come back UNREFERENCED."""
    classified = {c.facts.name: c for c in eco.scan(deriving=ROOT)}
    for name in ("topopy", "RiemannFM"):
        if name in classified:
            assert classified[name].integration == eco.UNREFERENCED


# --------------------------- presence is not participation --


def test_prose_and_load_bearing_references_are_kept_apart():
    """A repository named only in a markdown file is MENTIONED. The
    reachability distinction, applied to dependencies."""
    assert eco.MENTIONED != eco.INTEGRATED
    assert set(eco._PROSE_SUFFIXES).isdisjoint(eco._LOAD_BEARING_SUFFIXES)


def test_an_unreferenced_input_is_recorded_not_omitted():
    """Recorded rather than dropped: an input listed nowhere would read
    as a system with fewer loose parts than it has.

    DERIVED FRESH, NOT READ FROM THE COMMITTED FILE. The first version
    asserted over the emitted artifact, so a mutation that dropped
    unreferenced inputs from the DERIVER left the snapshot untouched and
    survived. A test that reads an artifact tests the artifact; to test
    what produces it, produce it."""
    document = eco.ecosystem_document(eco.scan(deriving=ROOT))
    unreferenced = [v for v in document["vendored_inputs"]
                    if v["integration"] == eco.UNREFERENCED]
    assert unreferenced
    assert document["summary"]["vendored_and_referenced_by_nothing"] == len(unreferenced)
    # and the committed artifact agrees with what the deriver just said
    assert yaml.safe_load(ARTIFACT.read_text())["vendored_inputs"] == document["vendored_inputs"]


def test_nothing_is_lost_between_the_three_verdicts():
    document = yaml.safe_load(ARTIFACT.read_text())
    summary = document["summary"]
    assert summary["repositories_in_reach"] == (
        summary["apparatuses"] + summary["vendored_inputs"] + summary["unresolved"])


# ------------------------------------------ roles are self-declared --


def test_this_apparatus_declares_its_own_role():
    classified = {c.facts.name: c for c in eco.scan(deriving=ROOT)}
    assert classified[ROOT.name].facts.role != eco.NOT_DECLARED
    assert classified[ROOT.name].facts.role_source == eco.APPARATUS_DECLARATION


def test_an_undeclared_role_is_reported_and_never_filled_in():
    """The coherence gap, made a measurement. A role written here on
    another party's behalf would be a self-declaration this party is not
    entitled to make -- so the register reports the absence and stops."""
    document = eco.ecosystem_document(eco.scan(deriving=ROOT))
    declaring = document["summary"]["apparatuses_declaring_a_role"]
    total = document["summary"]["apparatuses"]
    assert declaring < total, "if this ever passes, remove it -- the gap closed"
    undeclared = [a for a in document["apparatuses"]
                  if a["role"] == eco.NOT_DECLARED]
    assert len(undeclared) == total - declaring
    # and the register says whose job closing it is
    assert "entitled" in document["the_finding"]["no_apparatus_declares_its_role"]
    # an apparatus with no declaration file must report NOT_DECLARED and
    # never a fabricated role -- driven directly, since the artifact
    # would keep saying the right thing while the deriver invented one
    role, source = eco._declared_role(ROOT / "docs")
    assert role == eco.NOT_DECLARED and source == ""


def test_the_register_refuses_when_there_is_no_apparatus_at_all():
    """A map of nothing but vendored snapshots is not a map of a system,
    and emitting one would be the clean-looking empty result this
    project refuses everywhere else."""
    with pytest.raises(eco.EcosystemError):
        eco.scan(root=ROOT / "does-not-exist", deriving=ROOT / "docs")


# --------------------------------------------------- the artifact --


def test_the_artifact_is_a_fixed_point():
    """Emitting twice produces identical bytes, or the register is not
    derived -- it is generated.

    EXCEPT FOR THE DERIVING APPARATUS'S OWN COMMIT. The register records
    each apparatus's HEAD, and committing the register advances this
    one's -- so the artifact is permanently one commit stale about
    itself and can never equal a fresh derivation byte-for-byte. Fourth
    appearance of one class in this project: a party cannot witness a
    fact about the act it is currently performing.

    The fields stay in the artifact; they are excluded only from the
    comparison it makes with itself."""
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes

    fresh = eco.ecosystem_document(eco.scan(deriving=ROOT))
    committed = yaml.safe_load(ARTIFACT.read_text())
    assert eco.without_self_report(fresh) == eco.without_self_report(committed)


def test_only_the_deriving_apparatus_is_excused_its_own_commit():
    """Narrow by construction. A SIBLING moving is a real difference the
    fixed point must still see -- an exclusion wide enough to cover
    every apparatus would excuse exactly the drift this register exists
    to catch."""
    document = yaml.safe_load(ARTIFACT.read_text())
    trimmed = eco.without_self_report(document)
    for row in trimmed["apparatuses"]:
        if row["name"] == ROOT.name:
            assert "commit" not in row
        else:
            assert row["commit"], f"{row['name']} lost its commit"


def test_a_tampered_sibling_commit_still_breaks_the_comparison():
    """The exclusion must not be a hole. Plant a changed commit on a
    sibling row and require the comparison to notice."""
    import copy

    document = yaml.safe_load(ARTIFACT.read_text())
    tampered = copy.deepcopy(document)
    for row in tampered["apparatuses"]:
        if row["name"] != ROOT.name:
            row["commit"] = "0" * 12
            break
    assert eco.without_self_report(tampered) != eco.without_self_report(document)


def test_the_artifact_names_the_company_claim_and_which_half_is_supplied():
    document = yaml.safe_load(ARTIFACT.read_text())
    assert "provenance-bearing computational corpora" in document["company_claim"]
    declaration = yaml.safe_load(
        (ROOT / "architecture" / "apparatus.yaml").read_text())
    assert "second" in declaration["supplies_which_half_of_the_company_claim"]


def test_the_artifact_records_the_org_finding_with_its_count():
    document = yaml.safe_load(ARTIFACT.read_text())
    finding = document["the_finding"]["org_ownership_is_not_authorship"]
    assert str(document["summary"]["vendored_but_under_our_org"]) in finding
    assert eco.ORG in finding


def test_prose_alone_is_mentioned_not_integrated():
    """Drive the discriminator over CONSTRUCTED corpora rather than
    trusting the tree to contain an example of each. A repository named
    only in prose is MENTIONED; the same name in a load-bearing file is
    INTEGRATED; absent is UNREFERENCED."""
    prose = [("STE", "we evaluated widgetlib once", False)]
    code = [("STE", "import widgetlib", True)]

    assert eco.measure_integration("widgetlib", prose)[0] == eco.MENTIONED
    assert eco.measure_integration("widgetlib", code)[0] == eco.INTEGRATED
    assert eco.measure_integration("widgetlib", prose + code)[0] == eco.INTEGRATED
    assert eco.measure_integration("widgetlib", [])[0] == eco.UNREFERENCED
    # and the referencing apparatus is named, with a count
    assert eco.measure_integration("widgetlib", prose + code)[1] == (("STE", 2),)


# ---------------------------------------------------------------------
# IT HAS TO BE ABLE TO RUN. The first integration scan re-walked the
# tree once per repository name: 75 seconds. The second held every
# file's text in memory and was OOM-KILLED, because `zk/` in this
# repository is 5.6 GB of Rust build output. Both were correct. A check
# that is too slow to run and a check that cannot run are the same
# check, and neither dies by anyone deciding to remove it.
# ---------------------------------------------------------------------


def test_generated_trees_are_not_read():
    """Build output naming a dependency is evidence about the generator,
    not about what this repository depends on -- and reading it is what
    made the scan unrunnable."""
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        (root / "src").mkdir()
        (root / "src" / "real.py").write_text("import widgetlib\n")
        for skipped in ("target", "node_modules", "__pycache__", ".venv"):
            (root / skipped).mkdir()
            (root / skipped / "generated.py").write_text("import widgetlib\n")

        found = sorted(p.name for p in eco._candidate_files(root))
        assert found == ["real.py"]


def test_a_file_larger_than_the_cap_is_not_read():
    """A source file naming a dependency is a sentence; a 2 MB file that
    happens to contain the string is a haystack."""
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        (root / "small.py").write_text("widgetlib\n")
        (root / "huge.py").write_text("x" * (eco.MAX_FILE_BYTES + 1))
        assert sorted(p.name for p in eco._candidate_files(root)) == ["small.py"]


def test_the_verdict_predicate_is_driven_over_every_branch():
    """Pure, so it is tested on constructed tallies rather than on
    whatever the tree happens to contain."""
    assert eco.verdict_for({"STE": 2}, 1)[0] == eco.INTEGRATED
    assert eco.verdict_for({"STE": 2}, 0)[0] == eco.MENTIONED
    assert eco.verdict_for({}, 0)[0] == eco.UNREFERENCED
    # a load-bearing hit with no counts cannot happen, and if it ever
    # does the INTEGRATED arm must not invent an empty attribution
    assert eco.verdict_for({}, 1) == (eco.INTEGRATED, ())


def test_the_streaming_tally_keeps_prose_and_code_apart():
    """`tally` is the streaming path and needs its OWN constructed case.

    The equivalence test below compares it against `measure_integration`
    over the real tree -- and the real tree currently contains no
    prose-only reference at all, so a mutant that made `tally` count
    prose as load-bearing changed nothing observable and survived twice.
    A comparison between two implementations proves only that they agree
    on the inputs that exist."""
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        apparatus = root / "APP"
        apparatus.mkdir()
        (apparatus / "notes.md").write_text("we looked at widgetlib once\n")
        assert eco.tally(("widgetlib",), (apparatus,))["widgetlib"][0] == eco.MENTIONED

        (apparatus / "main.py").write_text("import widgetlib\n")
        assert eco.tally(("widgetlib",), (apparatus,))["widgetlib"][0] == eco.INTEGRATED
        assert eco.tally(("absent",), (apparatus,))["absent"][0] == eco.UNREFERENCED


def test_the_streaming_tally_agrees_with_the_materialised_one():
    """Two implementations of one question. `measure_integration` takes
    a corpus and is what the constructed tests drive; `tally` streams
    and is what the scan uses. They must not drift.

    EVERY NAME, NOT A CHOSEN THREE. The first version named three
    repositories and asserted they spanned all three verdicts -- which
    was true when written and false a day later, because the tree moved
    and `morphohdl` stopped being prose-only. A test whose premise is a
    fact about the corpus fails for reasons that are not the defect it
    guards. Comparing every classified name has no such premise and is
    strictly stronger; branch coverage lives in the constructed-corpus
    test above, where it cannot rot.
    """
    classified = eco.scan(deriving=ROOT)
    apparatuses = tuple(c.facts.path for c in classified
                        if c.verdict == eco.APPARATUS)
    names = tuple(c.facts.name for c in classified if c.verdict != eco.APPARATUS)

    corpus = [(a.name, p.read_text(errors="replace"),
               p.suffix in eco._LOAD_BEARING_SUFFIXES)
              for a in apparatuses for p in eco._candidate_files(a)]
    streamed = eco.tally(names, apparatuses)
    for name in names:
        assert eco.measure_integration(name, corpus) == streamed[name], name


# ---------------------------------------------------------------------
# TWO REGISTERS NOW READ ONE DIRECTORY.
#
# The invariant register derives over `architecture/**`, and the
# ecosystem register lives there and declares `extends: core@1.0.0` --
# so each is an input to the other's reading of the tree. Each being a
# fixed point ALONE does not make the pair one: two projections that
# feed each other can settle individually and still oscillate together,
# or settle to a different place depending which ran first.
#
# So the JOINT property is checked, in both orders. This is the same
# question the single-register fixed point asks -- is a projection being
# read as a source -- at the point where there are two of them.
# ---------------------------------------------------------------------

INVARIANT_REGISTER = ROOT / "architecture" / "exchange" / "invariant_register.yaml"


def test_the_two_registers_are_a_joint_fixed_point_in_both_orders():
    """Neither register moves when the other is re-emitted, whichever
    order they run in. Derived in-process and compared to the committed
    bytes rather than shelling out, so this cannot be satisfied by a
    stale file that happens to agree."""
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes

    from architecture.derive_register import (
        deriving_party_of,
        derive,
        register_document,
        without_currency,
    )

    ecosystem_first = canonical_bytes(
        eco.without_self_report(eco.ecosystem_document(eco.scan(deriving=ROOT))))
    invariant_first = register_document(derive(check_remotes=False))

    # re-derive both, in the other order
    invariant_second = register_document(derive(check_remotes=False))
    ecosystem_second = canonical_bytes(
        eco.without_self_report(eco.ecosystem_document(eco.scan(deriving=ROOT))))

    assert ecosystem_first == ecosystem_second, (
        "the ecosystem register moved when the invariant register was "
        "re-derived -- one projection is being read as a source by the other")

    party = deriving_party_of(invariant_first)
    assert without_currency(invariant_first, party) == \
        without_currency(invariant_second, party)

    # and the committed bytes are what a fresh derivation makes, modulo
    # the deriving apparatus's own commit (see the fixed-point test)
    assert ecosystem_first == canonical_bytes(
        eco.without_self_report(yaml.safe_load(ARTIFACT.read_text())))


def test_the_ecosystem_register_is_not_read_as_an_invariant_source():
    """It declares a core version, so the invariant derivation sees it.
    It must be seen as an EMITTED artifact, not as a party's claims --
    the defect that turned 26 invariants into 77."""
    document = yaml.safe_load(ARTIFACT.read_text())
    assert document["generated_by"] == "architecture/ecosystem.py"
    assert "invariants" not in document, (
        "an emitted register carrying an `invariants:` key would be read "
        "as a source of claims by the other register")


# ---------------------------------------------------------------------
# STRONG EVIDENCE ONLY.
#
# Every repository here is a single squashed commit, so its commit
# AUTHOR is whoever last touched whatever was imported -- which says
# nothing about ownership. The first classifier treated that author as
# evidence and disowned six repositories carrying the company name.
#
# It also read Apache-2.0 BOILERPLATE as a copyright grant: "Licensor
# shall mean the copyright owner or entity authorized by the copyright
# owner". That match would disown every Apache-licensed repository, on
# nothing. It was exposed by the acquisition channel's independently
# recorded census, which lists one of the disowned repositories as a
# company repository -- and the error ran in the direction that makes
# the ecosystem look SMALLER and the classifier look more DECISIVE,
# which produces no loud consequence and so is the harder direction to
# notice.
# ---------------------------------------------------------------------


def test_licence_boilerplate_is_not_read_as_a_copyright_grant():
    """A real grant carries a YEAR. That is what separates
    `Copyright (c) 2018, Dan Maljovec` from the Apache definitions
    section."""
    import tempfile

    apache = (
        '   "Licensor" shall mean the copyright owner or entity authorized by\n'
        "   the copyright owner that is granting the License.\n")
    real = "Copyright (c) 2018, Dan Maljovec\nAll rights reserved.\n"

    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        (root / "LICENSE").write_text(apache)
        assert eco._copyright_holders(root) == ()
        (root / "LICENSE").write_text(apache + real)
        holders = eco._copyright_holders(root)
        assert len(holders) == 1 and "Maljovec" in holders[0]

        # BOILERPLATE THAT CARRIES A YEAR. The year test alone rejects
        # the Apache definitions section, so on that input the phrase
        # filter is redundant and a mutant deleting it survived. This is
        # the input that separates the two guards -- a real form, from
        # licences that write a dated collective holder.
        dated = "Copyright (c) 2016 and later, the copyright holders and/or others\n"
        (root / "LICENSE").write_text(dated)
        assert eco._copyright_holders(root) == (), (
            "a dated boilerplate line still names no holder")


def test_a_squashed_commit_author_alone_does_not_disown_a_repository():
    """The correction the sibling census forced. Under our org, no core
    declaration, no declared upstream, no copyright -- UNRESOLVED, and
    rounded toward NEITHER party."""
    verdict = eco.classify(_facts(remote=f"{eco.ORG}/something",
                                  authors=("Some Upstream Person",)))
    assert verdict.verdict == eco.UNRESOLVED
    assert "NOT evidence of ownership" in verdict.because
    assert verdict.mirrored_under_our_org is False, (
        "an unsettled repository must not be flagged as a mirror either -- "
        "that would be the same overclaim in the other direction")


def test_each_strong_signal_settles_it_on_its_own():
    """Three signals, each sufficient, each driven alone so that none is
    carried by the others."""
    outside = eco.classify(_facts(remote="succinctlabs/sp1",
                                  authors=("Someone",)))
    declared = eco.classify(_facts(remote=f"{eco.ORG}/risc0-zero",
                                   declared_upstream="https://github.com/risc0/risc0/"))
    granted = eco.classify(_facts(remote=f"{eco.ORG}/topopy",
                                  copyright_holders=("2018, Dan Maljovec",)))
    for verdict in (outside, declared, granted):
        assert verdict.verdict == eco.VENDORED_INPUT
    assert "outside this org" in outside.because
    assert "declares its own upstream" in declared.because
    assert "copyright grant" in granted.because
    # and only the two UNDER our org are mirrors wearing our name
    assert (outside.mirrored_under_our_org, declared.mirrored_under_our_org,
            granted.mirrored_under_our_org) == (False, True, True)


def test_a_self_declared_upstream_inside_our_org_is_definitive():
    """The strongest evidence available: the project stating its own
    origin. SP1 and RISC Zero both do it in Cargo.toml, which is why
    neither rests on a squashed author any more."""
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        (root / "Cargo.toml").write_text(
            '[package]\nrepository = "https://github.com/succinctlabs/sp1"\n')
        assert "succinctlabs" in eco._declared_upstream(root)
        # our own org is not an upstream
        (root / "Cargo.toml").write_text(
            f'[package]\nrepository = "https://github.com/{eco.ORG}/thing"\n')
        assert eco._declared_upstream(root) == ""


# --------------------------- reconciled against an independent census --


def test_the_register_records_that_its_verdict_is_narrower_than_ownership():
    """APPARATUS means BOUND TO THE CORE, not `belongs to the company`.
    The sibling census counts 7 apparatuses to this register's 3 because
    it measures a different predicate, and a reader must not take one as
    contradicting the other."""
    document = yaml.safe_load(ARTIFACT.read_text())
    reconciliation = document["reconciled_against_an_independent_census"]
    assert "BOUND-TO-THE-CORE" in reconciliation["and_it_counts_differently"]
    assert "not derived from this artifact" in \
        reconciliation["the_sibling_measured_the_same_question"]
    assert "BOUND TO THE CORE" in document["what_this_does_not_claim"]


def test_the_register_records_what_it_structurally_cannot_see():
    """An apparatus with no repository. A register keyed on repositories
    would never have a row for it, and recording the blind spot is the
    only honest thing a repository-keyed instrument can do about it."""
    document = yaml.safe_load(ARTIFACT.read_text())
    limitation = document["reconciled_against_an_independent_census"][
        "what_this_register_structurally_cannot_see"]
    assert "NO REPOSITORY" in limitation
    assert "limitation rather than closed" in limitation


def test_the_siblings_census_is_pointed_at_and_not_transcribed():
    """Its rows are that party's to state. A copy here would drift and a
    reader could not tell which was the source."""
    document = yaml.safe_load(ARTIFACT.read_text())
    text = yaml.dump(document)
    assert "ecosystem_census.yaml" in \
        document["reconciled_against_an_independent_census"][
            "the_sibling_measured_the_same_question"]
    # the census's own apparatus rows must NOT appear here
    for row in ("data_acquisition_fabric", "notation_physical_commerce",
                "network_scout_signal_miner"):
        assert row not in text


def test_the_register_publishes_the_core_digest_beside_the_bindings():
    """Every apparatus binds core@1.0.0 BY LABEL, and the label moves
    only under bend_protocol -- so many core commits carry it. The
    digest is what makes a binding checkable rather than nominal, and it
    belongs beside the bindings so a party reading this register has
    both."""
    from architecture.core_identity import core_digest

    document = yaml.safe_load(ARTIFACT.read_text())
    bound = document["the_core_they_bind"]
    assert bound["digest"] == core_digest(ROOT)
    assert bound["digest"].startswith("sha256:")

    # BOTH steps, in order. The instruction used to be `verify(digest,
    # root)`, which checks the twin track -- not what any party measured
    # here binds. An instruction that names only the second step sends a
    # reader to check a digest without checking its referent, which is
    # exactly how the defect this field records came about.
    #
    # Read from the DERIVER, not from the emitted file: the instruction
    # is the deriver's text, and a lock reading the artifact would pass
    # unchanged while the code that writes it dropped the first step.
    how = eco.ecosystem_document(eco.scan())["the_core_they_bind"]["how_to_check"]
    assert how == bound["how_to_check"], "the artifact is stale against the deriver"
    assert "covers_what_is_bound" in how
    assert "verify(digest, root, surface_name)" in how
    assert how.index("covers_what_is_bound") < how.index("verify(digest")


def test_the_two_artifacts_agree_about_the_core():
    """Two derived artifacts naming one fact must not drift. If they
    ever disagree, one of them was emitted against a different tree.

    Now over BOTH tracks and both bindings, because the fact they have
    to agree about is no longer a single digest -- and an agreement
    check narrower than the fact would pass while they diverged on the
    part that matters to a binding party."""
    ecosystem = yaml.safe_load(ARTIFACT.read_text())
    identity = yaml.safe_load(
        (ROOT / "architecture" / "exchange" / "core_identity.yaml").read_text())

    measured = ecosystem["the_core_they_bind"]["measured"]
    assert "NOT_TAKEN" not in measured, measured
    for name, surface in identity["surfaces"].items():
        assert measured["tracks"][name] == surface["digest"], (
            f"the two artifacts disagree about {name}")
    for label, binding in identity["bindings"].items():
        assert measured["who_binds_what"][label]["binds"] == binding["binds"]
        assert measured["who_binds_what"][label]["imports"] == binding["imports"]

    assert ecosystem["the_core_they_bind"]["digest"] == (
        identity["surfaces"]["twin_compiler"]["digest"])
    assert ecosystem["summary"]["cores_bound"] == [f"core@{identity['core_version']}"]


def test_a_failure_to_take_the_digest_is_reported_not_omitted():
    """A register that silently dropped the field would look like a
    register that never had one. Driven directly, because this path
    fired for real on an import that could not resolve and said so."""
    import architecture.core_identity as identity
    import architecture.ecosystem as module

    # THE FAILURE IS FORCED, not hoped for. The first version pointed
    # REPO_ROOT at a missing directory and asserted the result was
    # EITHER a reason OR a digest -- which passes when the failure never
    # happens, so a mutant returning "" on failure survived it. An
    # assertion with an OR across the branch it is testing is not an
    # assertion about that branch.
    original = identity.core_digest

    def _raise(*_args, **_kwargs):
        raise RuntimeError("the core surface is unreadable")

    try:
        identity.core_digest = _raise
        reason = module._core_digest_or_reason()
    finally:
        identity.core_digest = original

    assert reason.startswith("NOT_TAKEN:"), reason
    assert "RuntimeError" in reason, "the reason must name the error"
    assert "unreadable" in reason, "and carry what it said"
    # and the success path still returns a digest
    assert module._core_digest_or_reason().startswith("sha256:")


def test_the_namesake_question_is_settled_as_far_as_evidence_allows():
    """The census left it open and said it must not be assumed from the
    name. It is this repository's package, so it is settled here -- and
    the finding is two-sided: the NAME is more shared than the census
    knew (both say `Morpho HDL`), and the SUBSTANCE is less shared than
    the name suggests."""
    document = yaml.safe_load(ARTIFACT.read_text())
    namesake = document["the_namesake_question"]
    assert "MORPHO HDL" in namesake["the_name_is_MORE_shared_than_the_census_knew"]
    assert "Frozen Specification" in namesake["the_artifact_that_would_settle_it"].title() \
        or "FROZEN SPECIFICATION" in namesake["the_artifact_that_would_settle_it"]
    assert namesake["verdict"].startswith("SHARED NAME, UNSHARED REFERENT")
    # and it refuses the stronger claim
    assert "Not asserted as unrelated" in namesake["verdict"]


def test_the_namesake_evidence_is_still_true_of_the_tree():
    """Derived facts, re-checked against the tree rather than trusted:
    this package really does call itself Morpho HDL and really does cite
    the Frozen Specification. If either stops being true, the recorded
    verdict is standing on nothing."""
    sources = list((ROOT / "morpho").rglob("*.py"))
    assert sources, "the package the finding is about must exist"
    text = " ".join(p.read_text(errors="replace") for p in sources)
    assert "Morpho HDL" in text
    assert "Frozen Specification" in text


def test_the_exclusion_actually_excuses_the_deriving_commit():
    """Driven over a CONSTRUCTED document, because the tree cannot show
    it: right after an emit the artifact and a fresh derivation carry the
    same commit, so removing the exclusion changes nothing observable
    until the next commit lands. A check that only works between commits
    is not a check."""
    import copy

    document = yaml.safe_load(ARTIFACT.read_text())
    moved = copy.deepcopy(document)
    for row in moved["apparatuses"]:
        if row["name"] == ROOT.name:
            row["commit"] = "0" * 12
            row["commits"] = 999_999
    assert moved != document, "the fixture must actually differ"
    assert eco.without_self_report(moved) == eco.without_self_report(document)


# ------------------------------- the core the parties actually bind --
#
# The register published one digest under the heading "the core they
# bind". Measured, no binding party imports that track: the acquisition
# channel reaches into this repository 291 times and into that track
# ZERO. The register was publishing a fingerprint of code nobody uses,
# under a heading claiming the opposite.


def test_the_register_publishes_a_digest_per_track_not_one_for_both():
    bound = eco._bound_digest_or_reason()
    assert "NOT_TAKEN" not in bound, bound
    tracks = bound["tracks"]
    assert set(tracks) == {"twin_compiler", "evidence_platform"}
    assert tracks["twin_compiler"] != tracks["evidence_platform"]
    for digest in tracks.values():
        assert digest.startswith("sha256:")


def test_the_register_says_which_track_each_party_binds_with_its_counts():
    """`binds` alone would be a declaration. The import counts are what
    let a reader check it rather than take it."""
    bound = eco._bound_digest_or_reason()
    who = bound["who_binds_what"]
    assert who, "no parties measured at all would pass this vacuously"
    for label, binding in who.items():
        track = binding["binds"]
        if track == "NEITHER":
            continue
        assert binding["imports"][track] > 0, (
            f"{label} is said to bind {track} while importing it zero times")


def test_the_kept_single_digest_field_is_named_as_the_twin_track():
    """Kept for continuity, so it must SAY what it is. An unlabelled
    leftover under a heading that used to mean something else is how the
    original defect read to anyone downstream."""
    section = eco.ecosystem_document(eco.scan())["the_core_they_bind"]
    assert section["digest"] == eco._core_digest_or_reason()
    naming = section["the_digest_field_is_the_TWIN_track"]
    assert "no binding party imports that track" in naming
    assert "`measured`" in naming
    assert section["measured"] == eco._bound_digest_or_reason()


def test_the_bound_digest_reports_why_rather_than_raising():
    """The register must still emit when the identity module cannot be
    reached -- a register that dies because one field could not be taken
    loses every field that could."""
    import architecture.core_identity as identity

    original = identity.binding_track
    identity.binding_track = lambda consumer: 1 / 0
    try:
        bound = eco._bound_digest_or_reason()
    finally:
        identity.binding_track = original
    assert "NOT_TAKEN" in bound
    assert "ZeroDivisionError" in bound["NOT_TAKEN"]
