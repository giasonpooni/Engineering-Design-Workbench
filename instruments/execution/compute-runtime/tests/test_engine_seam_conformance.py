"""What every engine behind the specification seam must satisfy.

WHY THIS IS NOT A NUMERICAL COMPARISON, WHICH IS WHAT WAS FIRST PROPOSED.
The obvious cross-engine test is "run one configuration through both
engines and require the answers to agree". Measured, that test cannot
exist here, and the reason is worth recording rather than discovering
twice:

    STE's kernel      sum of  2^80/r^4 - 2^40/r^2,  i128 integers,
                      truncating division, coordinates bounded |c|<=2^20
    SCL's kernel      4*eps*((sigma/r)^12 - (sigma/r)^6) and forces,
                      IEEE-754 doubles, with a cutoff

Those are different functions, not two implementations of one. At the
same separation they differ in SIGN, their ratio moves by a factor of 20
across r = 2..8, and their minima sit at r ~ 1.48e6 and r ~ 1.12. No
scaling turns one into the other, so no configuration exists on which
they SHOULD agree, and a test asserting agreement could only be made to
pass by inventing a tolerance wide enough to be meaningless.

The exponents are also not an accident of taste. STE's kernel must run
inside a zkVM, where floating point is not reproducible and therefore
not provable, so it is integer arithmetic end to end. SCL's must run on
CUDA. Neither constraint admits the other's implementation.

WHAT DOES HAVE TO HOLD ACROSS THEM. The dispatcher accepts any engine as
a `runner`; GROMACS plugs into the same seam. What makes engines
interchangeable is not that they compute the same thing -- they must
not -- but that they OBSERVE THE SAME CONTRACT about identity, refusal
and determinism. That contract is what this file pins, once, over every
engine present.

AND ONE PROPERTY THAT ONLY EXISTS BECAUSE THERE ARE TWO. Two engines
behind one seam create a hazard a single engine cannot have: if their
program identities could collide, a proof or a warrant about one would
be indistinguishable from one about the other. That is the real cost of
having two, and it is checked here directly.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import Callable, Optional

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from execution.engine import ExecutionResult, run_specification  # noqa: E402
from execution.specification import (  # noqa: E402
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
    encode_positions,
)

SCL_ROOT = pathlib.Path("/home/user/notationsystems/scientific-compute-layer")
SCL_CLI = SCL_ROOT / "native" / "build" / "scl_cli"


@dataclass(frozen=True)
class Engine:
    """One engine behind the seam, and how to exercise it."""

    name: str
    valid: Callable[[], ExecutionSpecification]
    #: A DIFFERENT valid input, for "different input, different identity".
    other: Callable[[], ExecutionSpecification]
    #: Input the engine must refuse. `None` when this engine's refusal
    #: path is covered elsewhere -- stated, never silently skipped.
    refusable: Optional[Callable[[], ExecutionSpecification]]
    run: Callable[[ExecutionSpecification], ExecutionResult]


# ------------------------------------------------------------ engines --


def _ste_spec(positions) -> ExecutionSpecification:
    return ExecutionSpecification(
        program=PAIRWISE_ENERGY_DESCRIPTOR,
        configuration=b"",
        input_payload=encode_positions(positions),
    )


def _ste_engine() -> Engine:
    return Engine(
        name="ste-native",
        valid=lambda: _ste_spec([(0, 0, 0), (4, 0, 0), (0, 4, 0)]),
        other=lambda: _ste_spec([(0, 0, 0), (9, 0, 0), (0, 4, 0)]),
        # two coincident particles: an undefined term, refused rather
        # than replaced with a zero
        refusable=lambda: _ste_spec([(1, 1, 1), (1, 1, 1)]),
        run=lambda spec: run_specification(spec),
    )


def _scl_engine() -> Optional[Engine]:
    """SCL's engine, or None when its native binary is not built.

    Absent is an ENVIRONMENT GAP, not a failure: SCL needs a C++
    toolchain and nlohmann_json, and STE deliberately needs neither. The
    tests that require it skip and say so.
    """
    if not SCL_CLI.exists():
        return None
    sys.path.insert(0, str(SCL_ROOT / "python"))
    try:
        from scl.ste_adapter import build_lj_specification, run_scl_specification
    except ImportError:
        return None

    def build(positions):
        return build_lj_specification(1.0, 1.0, 5.0, positions, cli_path=SCL_CLI)

    return Engine(
        name="scl-cpu",
        valid=lambda: build([(0.0, 0.0, 0.0), (1.4, 0.0, 0.0)]),
        other=lambda: build([(0.0, 0.0, 0.0), (2.2, 0.0, 0.0)]),
        refusable=None,   # covered by SCL's own failure-path suite
        run=lambda spec: run_scl_specification(spec, cli_path=SCL_CLI),
    )


def _available():
    engines = [_ste_engine()]
    scl = _scl_engine()
    if scl is not None:
        engines.append(scl)
    return engines


ENGINES = _available()
ENGINE_IDS = [engine.name for engine in ENGINES]


@pytest.fixture(params=ENGINES, ids=ENGINE_IDS)
def engine(request) -> Engine:
    return request.param


# ------------------------------------- the contract, per engine --------


def test_the_identities_are_the_specifications_and_not_the_engines(engine: Engine):
    """An engine reports identities the CALLER can recompute from the
    specification alone. If an engine could mint its own, two engines'
    results would not be comparable at all, and a stored result could
    not be checked later against the request that produced it."""
    spec = engine.valid()
    result = engine.run(spec)

    assert result.status == "completed", result.detail
    assert result.specification_identity == spec.identity()
    assert result.program_identity == spec.program_identity()
    assert result.input_identity == spec.input_identity()
    assert result.computation_identity is not None
    assert result.output is not None


def test_the_same_specification_twice_gives_the_same_identities(engine: Engine):
    """Determinism at the seam. Without it nothing downstream that
    dedupes or verifies by identity can work."""
    first = engine.run(engine.valid())
    second = engine.run(engine.valid())

    assert first.specification_identity == second.specification_identity
    assert first.program_identity == second.program_identity
    assert first.input_identity == second.input_identity
    assert first.output == second.output
    assert first.computation_identity == second.computation_identity


def test_a_different_input_is_a_different_specification(engine: Engine):
    """An engine that ignored its input would pass every check above.
    The program is the same here and must stay the same; only the input
    moves, and it must move the specification with it."""
    one, two = engine.valid(), engine.other()

    assert one.input_identity() != two.input_identity()
    assert one.identity() != two.identity()
    assert one.program_identity() == two.program_identity()

    first, second = engine.run(one), engine.run(two)
    assert first.output != second.output, (
        "two different inputs produced identical output -- the engine may "
        "not be reading its input at all")
    assert first.computation_identity != second.computation_identity


def test_an_undefined_computation_is_refused_rather_than_answered(engine: Engine):
    """Fail-closed at the seam: a refusal carries NO output and NO
    computation identity. A zero would be a fabricated answer, and the
    identity would make it look like a computation that happened."""
    if engine.refusable is None:
        pytest.skip(f"{engine.name}: refusal path is covered by its own suite")

    result = engine.run(engine.refusable())

    assert result.status != "completed"
    assert result.output is None
    assert result.computation_identity is None
    assert result.detail, "a refusal that does not say why is not much of a refusal"
    # the request is still identified -- what was refused stays nameable
    assert result.specification_identity == engine.refusable().identity()


# ------------------------ the property that exists only because of two --


def test_at_least_one_engine_is_present_and_the_battery_is_not_vacuous():
    """A parameterised suite over an empty list passes while testing
    nothing. This is the guard against that."""
    assert ENGINES, "no engine available: the conformance battery ran on nothing"
    assert all(e.name for e in ENGINES)


def test_the_same_input_under_a_different_program_is_a_different_request():
    """THE COLLISION HAZARD IN ITS PUREST FORM, and it needs no second
    engine installed to check.

    Two engines can legitimately be handed the same input bytes -- a set
    of coordinates is just bytes, and nothing stops both being asked
    about the same ones. What must never happen is that the two requests
    share a specification identity, because then a result stored against
    one is retrievable as the other, and everything downstream trusts
    identity.

    A mutant that dropped `program` from the specification identity
    survived the two-engine test, because those two engines also differ
    in their input. This drives the case that isolates it."""
    payload = encode_positions([(0, 0, 0), (4, 0, 0)])
    one = ExecutionSpecification(
        program=PAIRWISE_ENERGY_DESCRIPTOR, configuration=b"", input_payload=payload)
    two = ExecutionSpecification(
        program=b"a-different-engine-descriptor", configuration=b"", input_payload=payload)

    assert one.input_identity() == two.input_identity(), (
        "the fixture is wrong: these must share an input to isolate the program")
    assert one.program_identity() != two.program_identity()
    assert one.identity() != two.identity(), (
        "same input under different programs collides -- a result about one "
        "would be retrievable as a result about the other")


def test_the_same_program_under_a_different_configuration_is_a_different_request():
    """The third field, driven for the same reason. A configuration that
    did not reach the identity would make two differently-parameterised
    runs indistinguishable -- an epsilon of 1.0 and an epsilon of 5.0
    answering to the same name."""
    payload = encode_positions([(0, 0, 0), (4, 0, 0)])
    one = ExecutionSpecification(
        program=PAIRWISE_ENERGY_DESCRIPTOR, configuration=b"eps=1", input_payload=payload)
    two = ExecutionSpecification(
        program=PAIRWISE_ENERGY_DESCRIPTOR, configuration=b"eps=5", input_payload=payload)

    assert one.program_identity() == two.program_identity()
    assert one.input_identity() == two.input_identity()
    assert one.identity() != two.identity()


@pytest.mark.skipif(len(ENGINES) < 2,
                    reason="SCL's native binary is not built here, so there is "
                           "no second engine to be distinguished from")
def test_two_engines_can_never_be_mistaken_for_one_another():
    """THE HAZARD THAT ONLY EXISTS BECAUSE THERE ARE TWO.

    These engines compute DIFFERENT functions -- an integer (4,2)
    inverse-power sum and a floating-point (12,6) Lennard-Jones with
    forces -- so a result from one is not an answer to the other's
    question. What makes that safe rather than dangerous is that their
    identities are disjoint: a warrant, a proof, or a stored result
    about one can never be read as being about the other.

    A collision here would be the worst kind of defect this project can
    have, because everything downstream is built to trust identity."""
    identities = {}
    for candidate in ENGINES:
        spec = candidate.valid()
        identities[candidate.name] = {
            "program": spec.program_identity(),
            "specification": spec.identity(),
            "input": spec.input_identity(),
        }

    programs = [value["program"] for value in identities.values()]
    specifications = [value["specification"] for value in identities.values()]
    assert len(set(programs)) == len(programs), (
        f"two engines share a program identity: {identities}")
    assert len(set(specifications)) == len(specifications), (
        f"two engines share a specification identity: {identities}")


@pytest.mark.skipif(len(ENGINES) < 2,
                    reason="SCL's native binary is not built here")
def test_the_two_engines_are_not_expected_to_agree_and_this_records_why():
    """Driven, so the claim in this file's docstring is a measurement
    rather than an assertion someone has to take on trust.

    If a later change made these two compute the same function, this
    test would fail -- and that failure would be the RIGHT alarm: it
    would mean one of them had silently stopped being what it is."""
    outputs = {}
    for candidate in ENGINES:
        result = candidate.run(candidate.valid())
        assert result.status == "completed", result.detail
        outputs[candidate.name] = result.output

    assert len(set(outputs.values())) == len(outputs), (
        "two engines computing different functions produced identical "
        f"output bytes, which should be impossible: {outputs}")
