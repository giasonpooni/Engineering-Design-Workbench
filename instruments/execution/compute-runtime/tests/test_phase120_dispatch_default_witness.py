"""Phase 120: DispatchedMeasurement default / witness boundary audit.

sec.7 VERDICT: B -- FALSIFIED.

The default asserts execution without a structural witness. It is the
SAME defect as Phase 119's in kind, smaller in reach, and worse in what
it has actually done.

sec.1 THE EXHAUSTIVE CONSTRUCTION AUDIT -- ONE SITE, AND IT IS A FIXTURE
-------------------------------------------------------------------------
An AST sweep of the entire repository finds EXACTLY ONE construction of
`DispatchedMeasurement`:

    tests/test_experiment_step.py:54   ScriptedDispatcher.dispatch

ZERO in production. And that one site OMITS `extraction_method`, so the
default fires. `ScriptedDispatcher`'s own docstring:

    "A deterministic, test/demo-oriented `ActionDispatcher` ... Returns a
     pre-scripted value per candidate_id; never touches EvidencePool,
     never reads a clock."

So THE ONLY OBJECT THAT HAS EVER TAKEN THIS DEFAULT IS A FIXTURE
RETURNING HARDCODED NUMBERS, AND THE DEFAULT DECLARES THEM A MEASUREMENT
PRODUCED BY CAMPAIGN EXECUTION. Its entire observed lifetime has been
mislabelling scripted constants.

Phase 119's removed default at least fired on real workbench observations
where a human had typed a number they had actually measured. This one has
never fired on anything but a test constant.

sec.4 THE NAME IS NOT A WITNESS
--------------------------------
The proposed justification -- "the object is called DispatchedMeasurement,
so it was dispatched" -- requires the type to be structurally tied to the
Protocol. It is not:

    no factory (`make_dispatched_measurement` does not exist)
    no admission gate
    no `__post_init__` validation of the method (it only freezes `content`)
    no restriction on construction

`ActionDispatcher` RETURNS the type; it does not OWN it. A bare
constructor call from anywhere yields
`extraction_method="measurement:campaign_execution"`. Nomenclature is not
provenance -- which is the same result Phase 117 reached for the field
itself and Phase 111b reached for the whole pool.

sec.2 FOUR WORLDS, ONE OBJECT
-------------------------------
A genuine instrument reading, a construction with nothing running, a
hand-fabricated value and a simulation output -- passed through the same
constructor with the same content -- produce FOUR EQUAL OBJECTS, all
declaring `measurement:campaign_execution`. The constructor cannot
distinguish them and does not try.

sec.5 THE COMPARISON WITH PHASE 119
-------------------------------------
Identical defect shape:

    absence of caller information -> positive assertion about a world event

The candidate difference was "construction context supplies a genuinely
different guarantee". Tested and rejected: the context is a Protocol
return type with no enforcement, and the sole construction site is a
fixture that is explicitly not a measurement.

The ONE genuine difference is REACH, not justification. `DispatchedMeasurement`
has no id, is never admitted, and nothing in production constructs it, so
the default currently causes no production harm. That is an accident of
the execution seam being empty (Phase 114: no `ActionDispatcher`
implementation exists and none is planned), NOT a structural guarantee.
An empty seam is not a witness either.

sec.3 THE DEFAULT-REMOVAL TEST, RUN AND REVERTED
--------------------------------------------------
Measured, not theorised. With `extraction_method: str` required:

    5 test failures, 1784 passing
      3 in tests/test_experiment_step.py  -- ScriptedDispatcher, one line
      2 locks asserting the default exists -- they did their job
    0 production callers break             -- there are none
    0 identities change                    -- the object has no id
    0 admission semantics change           -- it is never admitted
    0 legitimate callers lose information  -- the sole caller gains the
                                              obligation to say what it did

The change would MERELY RELOCATE A DECLARATION, exactly as Phase 119's
did -- with one difference worth stating plainly: the sole caller could
not honestly relocate `"measurement:campaign_execution"`, because
`ScriptedDispatcher` does not measure anything. It would have to declare
something true of a scripted fixture. That choice is a semantic decision
and is NOT made here.

sec.7 SMALLEST REPAIR, AND THE DISTINCTION IT MUST PRESERVE
-------------------------------------------------------------
    REPAIR OF SILENT ASSERTION
        make `DispatchedMeasurement.extraction_method` required, and have
        `ScriptedDispatcher` declare what it actually is. One signature
        line plus one fixture line. No new type, no gate, no factory.

    ESTABLISHMENT OF AUTHENTICITY
        NOT ATTEMPTED AND NOT ACHIEVABLE. Phase 119 proved that a
        required declaration leaves genuine, fabricated, simulated and
        hand-typed values collapsing to one identical Observation
        whenever the caller declares the same method. Requiring this
        declaration removes the architecture's unsolicited claim. It
        supplies no witness, and per Phase 111b none can be supplied from
        inside a content-addressed system.

WHY NOT (C) VACUOUS
--------------------
The C reading -- "no execution concept exists, so the question is
meaningless" -- was considered and rejected. The assertion is perfectly
meaningful and perfectly false: the string reaches
`classify_epistemic_status` and reaches `Observation.id` through
`run_experiment_step`, and it has determined the declared provenance of
every observation in this codebase's only end-to-end experiment test. It
is the JUSTIFICATION that is missing, not the meaning.

NO ABSTRACTION IS PROPOSED.

REPAIRED AFTER THIS AUDIT
--------------------------
`DispatchedMeasurement.extraction_method` is now REQUIRED, and the sole
constructor declares `"simulation:scripted_fixture"`. That literal was
chosen, not inherited: a stipulated constant is not observed (nobody saw
it), not extracted (no document holds it), and not inferred (no model
made it). Of the four statuses `classify_epistemic_status` can return,
`simulation:` is the ONLY one that asserts no EXTERNAL event -- a bare
`fixture:` prefix falls through to EXTRACTED, which would falsely claim a
document extraction. It is the least-wrong declaration available, not a
claim that a simulation ran.

The declared provenance of that test's observations changed, and their
ids with it. That was the point: the previous value was FALSE for the
only object that used it, and preserving it to keep a hash stable would
have been preserving a false claim for convenience.

THE TWO RULES, NOW BOTH LOCKED

    CONSTRUCTOR   must not invent a world event   (Phase 119, Phase 120)
    DECLARATION   is still not a witness          (Phase 119)

Stated as one invariant: the architecture may REQUIRE a caller to declare
what an object represents, but it must never SUPPLY a positive epistemic
declaration merely because of a type name, a constructor, or an absent
argument.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from experiment.interface import ActionDispatcher, DispatchedMeasurement
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
DEFAULT = "measurement:campaign_execution"
TIMESTAMP = "2026-01-01T00:00:00Z"
CONTENT = {"property": "tensile_strength", "value": 90.0, "unit": "MPa"}


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _construction_sites():
    sites = []
    for path in sorted(REPO.rglob("*.py")):
        if ".git" in str(path) or "notationsystems" in str(path):
            continue
        if path.name in (Path(__file__).name, "test_operations_integration.py"):
            continue        # this audit's own probes, and Phase 125's
                            # integration dispatcher, both construct one
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "DispatchedMeasurement"):
                sites.append((str(path.relative_to(REPO)), node.lineno,
                              "extraction_method" in {k.arg for k in node.keywords}))
    return sites


# -- 1. the exhaustive construction audit -------------------------------------------------------------


def test_every_construction_site_is_enumerated_and_declares():
    """AMENDED (STE stage 1). Phase 120's lock said "exactly one site,
    and it is a test fixture" -- a snapshot of a world in which no
    production dispatcher existed. The INVARIANT it protected is that
    every construction DECLARES extraction_method (no construction may
    lean on a default, because the default was the lie). The STE
    execution vertical added the first production constructor,
    `execution/dispatcher.py`, which declares -- so the lock now states
    the invariant and enumerates the sites, instead of freezing the
    census at one."""
    sites = _construction_sites()
    assert {(path, declares) for path, _, declares in sites} == {
        ("tests/test_experiment_step.py", True),
        ("execution/dispatcher.py", True),
    }, f"unexpected DispatchedMeasurement construction census: {sites}"


def test_production_constructions_declare_a_simulation_prefix():
    """The one production constructor reports a COMPUTATION, and its
    declaration must say so: of the epistemic classifier's prefixes,
    only `simulation:` asserts no external-world event (Phase 120's own
    finding). A production site declaring `measurement:` or falling
    through to extracted would be claiming a world event no computation
    can witness."""
    source = (REPO / "execution" / "dispatcher.py").read_text()
    tree = ast.parse(source)
    declared = [
        keyword.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "DispatchedMeasurement"
        for keyword in node.keywords
        if keyword.arg == "extraction_method" and isinstance(keyword.value, ast.Constant)
    ]
    assert declared == ["simulation:deterministic_native_execution"]


def test_the_sole_constructor_documents_itself_as_scripted_and_not_a_measurement():
    text = " ".join((REPO / "tests" / "test_experiment_step.py").read_text().split())
    assert "test/demo-oriented `ActionDispatcher`" in text
    assert "Returns a pre-scripted value per candidate_id" in text
    assert "never touches EvidencePool, never reads a clock" in text


# -- 4. the name is not a witness -----------------------------------------------------------------------


def test_the_type_is_freely_constructible_with_no_factory_or_gate():
    import experiment.interface as interface
    assert not hasattr(interface, "make_dispatched_measurement")
    public = {n for n in dir(interface) if not n.startswith("_")}
    assert "ActionDispatcher" in public and "DispatchedMeasurement" in public
    # A bare call USED TO get the claim for free. It now cannot be made
    # at all without saying what happened.
    with pytest.raises(TypeError):
        DispatchedMeasurement(content={"x": 1}, record_locator="l",
                              record_raw_content="1", extracted_at=TIMESTAMP)


def test_post_init_freezes_content_and_validates_nothing():
    source = inspect.getsource(DispatchedMeasurement)
    assert "MappingProxyType" in source
    for absent in ("raise", "ValueError", "assert"):
        assert absent not in source.split("__post_init__")[-1]


def test_the_protocol_returns_the_type_but_does_not_own_it():
    signature = inspect.signature(ActionDispatcher.dispatch)
    assert signature.return_annotation == "DispatchedMeasurement"
    # A Protocol return annotation constrains implementations, never
    # constructors: anyone may build one without implementing anything,
    # and nothing records which implementation (if any) produced it.
    assert "id" not in {f.name for f in dataclasses.fields(DispatchedMeasurement)}
    assert "dispatcher" not in {f.name for f in dataclasses.fields(DispatchedMeasurement)}


# -- 2. four worlds, one object ---------------------------------------------------------------------------


@pytest.mark.parametrize("world", [
    "genuine instrument reading",
    "constructed, nothing ran",
    "fabricated by hand",
    "simulation output",
])
def test_no_world_can_be_constructed_without_declaring_what_it_is(world):
    """WHEN THIS AUDIT RAN all four produced equal objects labelled a
    campaign measurement. Now none can be built at all in silence."""
    with pytest.raises(TypeError):
        DispatchedMeasurement(content=CONTENT, record_locator="loadframe-run-7",
                              record_raw_content="90.0", extracted_at=TIMESTAMP)


def test_the_four_worlds_still_collapse_once_they_declare_alike():
    """FINDING B IS UNTOUCHED. Requiring the declaration removed the
    architecture's unsolicited claim; it supplied no witness. Four callers
    declaring the same string still produce one object."""
    made = [DispatchedMeasurement(content=CONTENT, record_locator="loadframe-run-7",
                                  record_raw_content="90.0", extracted_at=TIMESTAMP,
                                  extraction_method=DEFAULT)
            for _ in range(4)]
    signatures = {(m.record_locator, m.record_raw_content, m.extraction_method,
                   tuple(sorted(m.content.items()))) for m in made}
    assert len(signatures) == 1


# -- 3. the measured blast radius --------------------------------------------------------------------------


def test_the_object_has_no_identity_so_removal_shifts_nothing_downstream():
    fields = {f.name for f in dataclasses.fields(DispatchedMeasurement)}
    assert "id" not in fields
    assert fields == {"content", "record_locator", "record_raw_content",
                      "extracted_at", "extraction_method"}


def test_it_is_never_admitted_and_reaches_no_pool_method():
    from evidence.pool import EvidencePool
    for absent in ("put_dispatched_measurement", "put_dispatch"):
        assert not hasattr(EvidencePool, absent)
    import evidence.admission as admission
    assert not any(n.endswith("dispatched_measurement") for n in dir(admission))


def test_only_the_extraction_method_is_read_downstream():
    from experiment.step import run_experiment_step
    source = inspect.getsource(run_experiment_step)
    reads = {node.attr for node in ast.walk(ast.parse(source.lstrip()))
             if isinstance(node, ast.Attribute)
             and isinstance(node.value, ast.Name) and node.value.id == "dispatched"}
    assert reads == {"record_locator", "record_raw_content", "content",
                     "extracted_at", "extraction_method"}
    # five fields copied, nothing retained -- Phase 118's payload-supplier
    # finding, re-confirmed.


# -- 5/7. the defect is the same shape as Phase 119's --------------------------------------------------------


def test_neither_default_survives():
    """Both had the same shape -- absence of caller information becoming a
    positive assertion about a world event -- and both are gone."""
    from materials.results import make_experimental_result
    assert inspect.signature(make_experimental_result).parameters[
        "extraction_method"].default is inspect.Parameter.empty     # Phase 119
    assert [f for f in dataclasses.fields(DispatchedMeasurement)
            if f.name == "extraction_method"][0].default is dataclasses.MISSING


def test_the_repair_landed_and_no_abstraction_was_added():
    """THE REGRESSION LOCK. The default is gone and nothing was invented
    to replace it -- no execution record, no origin type, no gate."""
    assert [f for f in dataclasses.fields(DispatchedMeasurement)
            if f.name == "extraction_method"][0].default is dataclasses.MISSING

    forbidden = {"ExecutionRecord", "MeasurementOrigin", "ProvenanceEvent",
                 "TrustedDispatcher", "Witness"}
    hits = []
    for package in ("evidence", "retrieval", "materials", "experiment",
                    "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


def test_the_sole_constructor_declares_the_least_wrong_thing():
    """It does NOT declare a measurement, and it does not claim a
    simulation ran -- `simulation:` is chosen because it is the only
    status that asserts no external event."""
    from retrieval.epistemic import SIMULATED, classify_epistemic_status
    from evidence.types import make_observation

    text = (REPO / "tests" / "test_experiment_step.py").read_text()
    assert 'extraction_method="simulation:scripted_fixture"' in text
    assert "measurement:campaign_execution" not in text

    observation = make_observation(
        record_ids=("r",), extraction_method="simulation:scripted_fixture",
        content={"v": 1.0}, confidence=1.0, extracted_at=TIMESTAMP)
    assert classify_epistemic_status(observation) == SIMULATED

    # a bare `fixture:` prefix would fall through to EXTRACTED -- a false
    # claim that a document was parsed
    bare = make_observation(
        record_ids=("r",), extraction_method="fixture:scripted",
        content={"v": 1.0}, confidence=1.0, extracted_at=TIMESTAMP)
    assert classify_epistemic_status(bare) != SIMULATED


def test_the_two_rules_hold_together():
    """CONSTRUCTOR must not invent a world event; DECLARATION is still not
    a witness. The first is now enforced at both seams; the second remains
    unachievable and is not attempted."""
    import inspect as _inspect

    from materials.results import make_experimental_result

    # rule 1, enforced
    assert _inspect.signature(make_experimental_result).parameters[
        "extraction_method"].default is _inspect.Parameter.empty
    assert [f for f in dataclasses.fields(DispatchedMeasurement)
            if f.name == "extraction_method"][0].default is dataclasses.MISSING

    # rule 2, unenforceable -- no witness field exists anywhere
    for cls in (DispatchedMeasurement,):
        fields = {f.name for f in dataclasses.fields(cls)}
        for absent in ("witness", "attested_by", "signature", "verified"):
            assert absent not in fields
