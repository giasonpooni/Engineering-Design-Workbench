"""Can the party READING a record recompute the value it carries?

THIS APPARATUS DECLARES THAT IT CAN. architecture/apparatus.yaml says
this repository supplies the second half of "provenance-bearing
computational corpora" because "a computed result carries what it was
computed from and can be recomputed by the party reading it".

That is a claim about the records, so it is measurable, and a claim a
repository makes about itself is exactly the kind that should be
measured rather than restated. This probe attempts the recomputation
instead of describing it.

THE GRADES, and the distinction that matters is between the first two:

  SELF_CONTAINED     the record carries the PROGRAM. A reader with the
                     record and nothing else can run it again.
  NAMES_ITS_METHOD   the record carries a method IDENTIFIER. A reader
                     can say WHAT was done and can recompute only if it
                     already possesses that method -- which is a real
                     precondition and not a detail.
  UNGROUNDED         neither.

A record that names its method is still provenance-bearing: it says
what produced the value, and two records naming different methods are
different facts. What it is not is SELF-SUFFICIENT, and the declaration
did not distinguish those.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Callable, Dict, List, Optional, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Run as a script from anywhere, and as a module from the suite.
if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REPO_ROOT))

SELF_CONTAINED = "SELF_CONTAINED"
NAMES_ITS_METHOD = "NAMES_ITS_METHOD"
UNGROUNDED = "UNGROUNDED"

#: A demonstration that ran and produced the value again, or the reason
#: it could not. `attempted` separates "tried and failed" from "not
#: tried" -- an untried recomputation reported as a failure would be the
#: silence-as-cleanliness error inverted.
@dataclasses.dataclass(frozen=True)
class Recomputation:
    record_kind: str
    grade: str
    carries: Tuple[str, ...]
    attempted: bool
    succeeded: Optional[bool]
    detail: str


def demonstrate_execution(program: bytes) -> bool:
    """Can a reader holding the SERIALISED record arrive at the same
    computation? Parameterised on the program so it can be driven over a
    record that must FAIL.

    WITHOUT A FAILING INPUT THIS PROVES NOTHING. The demonstration
    returned True for the only record it was ever given, so a test could
    assert no more than `True`, and three separate mutants that
    hardcoded True survived. A check with one input cannot distinguish a
    working mechanism from a constant.

    An EMPTY program is the discriminating case: the record still
    rebuilds, but removing the program no longer changes the identity,
    so nothing in the record is carrying the computation.
    """
    from execution.specification import ExecutionSpecification

    original = ExecutionSpecification(
        program=program, configuration=b"cfg", input_payload=b"input")

    # ACROSS AN ENCODING BOUNDARY, which is what a reader actually
    # crosses. Handing the constructor the very attributes it was built
    # from cannot fail -- that version was still a tautology, and a
    # mutant replacing the comparison with True was EQUIVALENT to it,
    # which is the clearest possible statement that the step tested
    # nothing. A record reaches a reader as bytes in a document, so the
    # round trip goes through one.
    transmitted = {name: getattr(original, name).hex()
                   for name in ("program", "configuration", "input_payload")}
    decoded = {name: bytes.fromhex(value) for name, value in transmitted.items()}
    rebuilt = ExecutionSpecification(**decoded)
    same = rebuilt.identity() == original.identity()

    without_program = dict(decoded, program=b"")
    program_is_load_bearing = (
        ExecutionSpecification(**without_program).identity() != original.identity())
    return same and program_is_load_bearing


def _execution_specification() -> Recomputation:
    """The proof-bearing path. The record carries `program: bytes`, so
    the demonstration is: rebuild the specification from ITS OWN FIELDS
    and check the identity is the same one."""
    from execution.specification import ExecutionSpecification

    same = demonstrate_execution(b"\x00asm-stand-in-program-bytes")

    carries = tuple(f.name for f in dataclasses.fields(ExecutionSpecification))
    return Recomputation(
        record_kind="execution.specification.ExecutionSpecification",
        grade=SELF_CONTAINED,
        carries=carries,
        attempted=True,
        succeeded=same,
        detail=(
            "the record carries the PROGRAM ITSELF, not a name for it, and "
            "its identity is a commitment over (program, configuration, "
            "input). A reader holding the record holds everything the "
            "computation consumed, which is why this path can be proved at "
            "all: a proof about a program nobody can exhibit proves nothing "
            "a reader can check. Demonstrated through a SERIALISED record "
            "rather than from the live object, and with the negative half: "
            "removing the program changes the identity, so the field is "
            "load-bearing rather than merely present"),
    )


def _derived_value() -> Recomputation:
    """The generic derivation path. The record carries a method NAME.
    The demonstration is the honest one: try to resolve that name to
    something callable using only the record, and report the failure."""
    from evidence.types import make_derived_value

    record = make_derived_value(
        derived_from=("obs-a", "obs-b"),
        method="mean_of_replicates",
        content={"property": "Mn", "value": 3300.0},
        confidence=1.0,
        derived_at="2026-09-03T00:00:00Z",
    )
    carries = tuple(f.name for f in dataclasses.fields(type(record)))

    # A reader holds only the record. Can it obtain the method?
    resolved: Optional[Callable] = None
    detail_extra = ""
    try:
        module_name, _, attribute = record.method.rpartition(".")
        if module_name:
            import importlib
            resolved = getattr(importlib.import_module(module_name), attribute)
    except Exception as error:  # noqa: BLE001 -- the failure is the finding
        detail_extra = f" (resolution raised {type(error).__name__})"

    return Recomputation(
        record_kind="evidence.types.DerivedValue",
        grade=NAMES_ITS_METHOD,
        carries=carries,
        attempted=True,
        succeeded=resolved is not None,
        detail=(
            f"`method` is {record.method!r} -- a STRING. It says what was "
            f"done and is part of the record's identity, so two derivations "
            f"by different methods are different facts. It is not a "
            f"definition: a reader holding this record cannot obtain the "
            f"method from it, and recomputation requires the reader to "
            f"already possess it" + detail_extra),
    )


PROBES: Tuple[Callable[[], Recomputation], ...] = (
    _execution_specification,
    _derived_value,
)


def probe() -> List[Recomputation]:
    return [make() for make in PROBES]


def document() -> dict:
    results = probe()
    by_grade: Dict[str, List[str]] = {}
    for result in results:
        by_grade.setdefault(result.grade, []).append(result.record_kind)

    self_contained = by_grade.get(SELF_CONTAINED, [])
    named = by_grade.get(NAMES_ITS_METHOD, [])

    return {
        "extends": "core@1.0.0",
        "generated_by": "architecture/recomputability.py",
        "artifact": "recomputability",
        "owner": "STE",
        "the_claim_being_measured": (
            "architecture/apparatus.yaml: 'a computed result carries what it "
            "was computed from and can be recomputed by the party reading "
            "it'"),
        "the_verdict": (
            "TRUE OF ONE PATH AND WEAKER ON THE OTHER, and the declaration "
            "did not distinguish them. The proof-bearing execution path "
            "carries the PROGRAM and a reader can rerun it. The generic "
            "derivation path carries a method NAME and a reader can rerun it "
            "only if it already has that method"),
        "summary": {
            "record_kinds_probed": len(results),
            "self_contained": len(self_contained),
            "names_its_method": len(named),
            "ungrounded": len(by_grade.get(UNGROUNDED, [])),
            "demonstrations_attempted": sum(1 for r in results if r.attempted),
        },
        "records": [
            {
                "kind": r.record_kind,
                "grade": r.grade,
                "carries": list(r.carries),
                "demonstration_attempted": r.attempted,
                "demonstration_succeeded": r.succeeded,
                "detail": r.detail,
            }
            for r in sorted(results, key=lambda r: r.record_kind)
        ],
        "what_naming_a_method_still_buys": (
            "the method is part of the record's IDENTITY, so two derivations "
            "by different methods are different facts and cannot be confused "
            "downstream. That is provenance-bearing. It is not "
            "self-sufficient, and the gap between those is exactly what this "
            "artifact exists to state"),
        "what_would_close_it": (
            "carrying a DIGEST of the method's definition, the way the "
            "execution path carries the program -- so a reader could at "
            "least check that the method it possesses is the method that "
            "was run. NOT DONE HERE: it changes what a DerivedValue is, "
            "which is a core-schema change under bend_protocol, and it is a "
            "decision rather than a measurement"),
        "what_this_does_not_claim": (
            "that a self-contained record is CORRECT. It says a reader can "
            "run the computation again, not that the computation was the "
            "right one to run -- an identity, not a warrant"),
    }


def emit(root: pathlib.Path = REPO_ROOT) -> pathlib.Path:
    import sys as _sys
    _sys.path.insert(0, str(root / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes, canonical_sha256

    payload = document()
    out = root / "architecture" / "exchange" / "recomputability.yaml"
    out.write_bytes(canonical_bytes(payload))
    (root / "architecture" / "exchange" / "recomputability.sha256").write_text(
        canonical_sha256(payload) + "\n")
    return out


def main() -> int:
    import sys

    payload = document()
    print("=== CAN A READER RECOMPUTE WHAT THE RECORD CARRIES? ===")
    for record in payload["records"]:
        print(f"\n  {record['kind']}")
        print(f"    grade      : {record['grade']}")
        print(f"    carries    : {', '.join(record['carries'])}")
        print(f"    demonstrated: attempted={record['demonstration_attempted']} "
              f"succeeded={record['demonstration_succeeded']}")
    print(f"\n=== THE VERDICT ===\n  {payload['the_verdict']}")
    if "--emit" in sys.argv:
        out = emit()
        print(f"\n  wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
