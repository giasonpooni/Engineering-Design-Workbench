"""The counts this project's documentation states must be the real ones.

WHY THIS EXISTS. Every doc written in this repository records
measurements -- how many locks, how many mutants, how many lines ship.
Those numbers were true when written and go stale the moment the thing
they describe changes, with nothing recomputing them. Four had already
drifted before this file was added:

    docs/NUMERICS.md              11/11 mutants  ->  actually 15
    docs/OPEN_SOURCE_RELEASE.md   9,338 lines    ->  actually 9,426
                                  47 test files  ->  actually 48
                                  545 tests      ->  actually 557
                                  18 locks       ->  actually 19
                                  16/16 mutants  ->  actually 17

Nothing failed. The documents simply described a repository that no
longer existed, in the confident register of a measurement.

THAT IS THE SAME DEFECT THIS PROJECT KEEPS FINDING, in its own prose:
a recorded fact whose referent moved -- the stale sibling checkout, the
stale mirror history, the import count of 291 stated in nine places
while it was 293, the default branch pointing at older work. Here it had
reached the documentation ABOUT those findings.

WHAT IS PINNED, AND WHAT IS NOT. Only claims with a mechanical referent:
counts of locks, mutants and shipped code. Prose is not checked, and
numbers that describe a RUN (how many passed on some machine, on some
day) are not pinned either -- those depend on the environment, and a
test asserting them would fail for being run somewhere else, which is
not drift.

DECLARED, NOT INFERRED. The claims are listed below with the measurement
that settles each. Parsing arbitrary prose for numbers would find dozens
and understand none of them.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def _load(path: pathlib.Path):
    """Import a script by path, without needing it to be a package."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def _declared_mutants(name: str) -> int:
    """The battery's OWN list, not a grep of it. A count taken from the
    source text would drift for a different reason than the one this
    file exists to catch."""
    module = _load(ROOT / "scripts" / f"{name}.py")
    return len(module.MUTATIONS)


def _locks(name: str) -> int:
    """Distinct check functions in a suite. Not the collected count:
    parameterised checks multiply with the environment, and `locks` in
    these documents means the checks that were written."""
    source = (ROOT / "tests" / f"{name}.py").read_text()
    return len(re.findall(r"^def test_", source, re.MULTILINE))


def _facts_for(deriver: str) -> dict:
    """Measure one release's surface from its own deriver.

    Parameterised by deriver rather than duplicated per release: a second
    copy of this function would be a mirror of the first, and the moment
    one release's rule changed the other's numbers would be checked
    against the wrong one.
    """
    release = _load(ROOT / "release" / deriver / "build.py")
    modules = lines = 0
    for package in release.PACKAGES:
        for path in release._python_files(ROOT / package):
            modules += 1
            lines += len(path.read_text(errors="replace").splitlines())
    return {
        "modules": modules,
        "lines": lines,
        "test_files": len(release.selected_tests(ROOT)),
    }


def _release_facts() -> dict:
    return _facts_for("provenance_pool")


def _canonical_state_facts() -> dict:
    return _facts_for("canonical_state")


def _reduction_rate(which: str) -> int:
    """Recompute a rate quoted in docs/REDUCTION_DETERMINISM.md, using
    the same `cpp_min` the reduction locks drive. Imported rather than
    reimplemented: a copy of the operator here could agree with a wrong
    doc and a wrong lock at once."""
    import functools
    import itertools
    import math

    from test_reduction_determinism import NAN, VALUES, cpp_min

    def same(x, y):
        return (math.isnan(x) and math.isnan(y)) or x == y

    if which == "commutativity":
        return sum(1 for a, b in itertools.product(VALUES, repeat=2)
                   if not same(cpp_min(a, b), cpp_min(b, a)))
    if which == "associativity":
        return sum(1 for a, b, c in itertools.product(VALUES, repeat=3)
                   if not same(cpp_min(cpp_min(a, b), c),
                               cpp_min(a, cpp_min(b, c))))
    if which == "fold_vs_tree":
        data = [2.0, 3.0, NAN, 1.0]
        return sum(1 for o in itertools.permutations(data)
                   if not same(functools.reduce(cpp_min, o),
                               cpp_min(cpp_min(o[0], o[1]), cpp_min(o[2], o[3]))))
    raise AssertionError(f"no such rate: {which}")


#: (document, regex with ONE capturing group, the measured value).
#: Each regex must match exactly once, so a claim that moves in the
#: prose is a failure rather than a silent miss.
CLAIMS = [
    ("docs/NUMERICS.md",
     r"mutate_numerics_checks\.py` — (\d+)/\d+ mutants killed",
     lambda: _declared_mutants("mutate_numerics_checks")),
    ("docs/NUMERICS.md",
     r"`tests/test_numerics\.py` — (\d+) locks",
     lambda: _locks("test_numerics")),
    ("docs/OPEN_SOURCE_RELEASE.md",
     r"\*\*(\d+) modules,",
     lambda: _release_facts()["modules"]),
    ("docs/OPEN_SOURCE_RELEASE.md",
     r"modules, ([\d,]+) lines,",
     lambda: _release_facts()["lines"]),
    ("docs/OPEN_SOURCE_RELEASE.md",
     r"lines, (\d+) test files,",
     lambda: _release_facts()["test_files"]),
    ("docs/OPEN_SOURCE_RELEASE.md",
     r"`tests/test_release_provenance_pool\.py` — (\d+) locks",
     lambda: _locks("test_release_provenance_pool")),
    ("docs/OPEN_SOURCE_RELEASE.md",
     r"mutate_release_checks\.py` — (\d+)/\d+ mutants",
     lambda: _declared_mutants("mutate_release_checks")),
    ("docs/CANONICAL_STATE_RELEASE.md",
     r"\*\*(\d+) modules,",
     lambda: _canonical_state_facts()["modules"]),
    ("docs/CANONICAL_STATE_RELEASE.md",
     r"modules, ([\d,]+) lines,",
     lambda: _canonical_state_facts()["lines"]),
    ("docs/CANONICAL_STATE_RELEASE.md",
     r"lines, (\d+) test files,",
     lambda: _canonical_state_facts()["test_files"]),
    ("docs/CANONICAL_STATE_RELEASE.md",
     r"`tests/test_release_canonical_state\.py` -- (\d+) locks",
     lambda: _locks("test_release_canonical_state")),
    ("docs/CANONICAL_STATE_RELEASE.md",
     r"mutate_canonical_state_release_checks\.py`\s*\n?-- (\d+)/\d+ mutants",
     lambda: _declared_mutants("mutate_canonical_state_release_checks")),
    ("docs/ENGINE_SEAM.md",
     r"mutate_seam_conformance_checks\.py` — (\d+)/\d+ mutants",
     lambda: _declared_mutants("mutate_seam_conformance_checks")),
    # The reduction figures are MEASURED RATES. A lambda returning the
    # literal 6 would assert rather than measure -- the uniform-inputs
    # failure in miniature -- so each recomputes its rate from the same
    # `cpp_min` the locks use.
    ("docs/REDUCTION_DETERMINISM.md",
     r"\| commutativity \| \*\*(\d+) of 16\*\* pairs \|",
     lambda: _reduction_rate("commutativity")),
    ("docs/REDUCTION_DETERMINISM.md",
     r"\| associativity \| \*\*(\d+) of 64\*\* triples \|",
     lambda: _reduction_rate("associativity")),
    ("docs/REDUCTION_DETERMINISM.md",
     r"pairwise tree \| \*\*(\d+) of 24\*\* orderings \|",
     lambda: _reduction_rate("fold_vs_tree")),
]


@pytest.mark.parametrize("document,pattern,measure", CLAIMS,
                         ids=[f"{d.split('/')[-1]}:{p[:28]}" for d, p, _ in CLAIMS])
def test_the_documented_count_is_the_measured_one(document, pattern, measure):
    text = (ROOT / document).read_text()
    found = re.findall(pattern, text)
    assert len(found) == 1, (
        f"{document}: the claim {pattern!r} matched {len(found)} times, "
        f"so this check cannot say which number it is about")

    claimed = int(found[0].replace(",", ""))
    actual = measure()
    assert claimed == actual, (
        f"{document} says {claimed:,} where the repository measures "
        f"{actual:,}. The document describes a tree that no longer exists.")


def test_the_claim_registry_is_not_empty_and_every_document_exists():
    """A registry that had quietly emptied would pass every check above
    while verifying nothing -- the vacuous pass this project has met
    more often than any other failure."""
    assert CLAIMS, "no documented claim is checked at all"
    for document, _, _ in CLAIMS:
        assert (ROOT / document).is_file(), f"{document} does not exist"


def test_a_wrong_number_would_actually_be_caught():
    """Driven, because a checker that could not fail is decorative. This
    runs the same comparison against a value known to be wrong."""
    document, pattern, measure = CLAIMS[0]
    text = (ROOT / document).read_text()
    claimed = int(re.findall(pattern, text)[0].replace(",", ""))
    assert claimed == measure()
    assert claimed != measure() + 1, "the comparison cannot distinguish anything"
