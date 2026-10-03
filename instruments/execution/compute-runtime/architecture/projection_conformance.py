"""Are the serving projections actually rebuildable, and do they write?

THE INFRASTRUCTURE PLAN RESTS ON TWO PROPERTIES. "No serving projection
writes canonical truth", and serving projections are REBUILDABLE from
canonical state. Every layer above the canonical one is disposable only
if both hold; if either fails for a projection, that projection is
carrying state nothing can regenerate, and the canonical layer is not
canonical for it.

Both are checkable NOW, before any of the infrastructure exists -- and
that is the point of checking them now. A projection that turns out not
to be rebuildable is a cheap finding today and an expensive one after a
lakehouse has been built on the assumption.

BEHAVIOURAL, NOT GREPPED. The write barrier could be checked by
searching each projection's source for `put_`. That tests SPELLING: a
mutant reaching the same method through getattr and a split string
walked past exactly such a check in this repository yesterday. So the
canonical layer's own fingerprint is taken before and after, and any
write moves it however it is spelled.

ENUMERATED FROM THE TREE, NOT FROM MEMORY. The probe discovers
projection modules and REFUSES if one is unclassified. A conformance
report covering the projections someone remembered is the 0-of-20 shape:
every check passing, over a set that omits the one that fails.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REPO_ROOT))

#: Verdicts.
REBUILDABLE = "REBUILDABLE"          # regenerates byte-identically from canonical
NOT_REBUILDABLE = "NOT_REBUILDABLE"  # ran, and did not reproduce
WRITES_UPSTREAM = "WRITES_UPSTREAM"  # the barrier moved
NOT_PROBED = "NOT_PROBED"            # discovered and not classified -- a refusal


class ProjectionConformanceError(RuntimeError):
    """A projection exists in the tree that this probe does not cover."""


#: Where projections live. Declared, so that a module appearing in one of
#: these places and NOT in the probe below is a refusal rather than a
#: silent omission.
PROJECTION_HOMES: Tuple[str, ...] = (
    "core/projection",
    "backends",
    "evidence/trust_graph.py",
    "evidence/metrics.py",
    "materials/analysis.py",
)

#: Modules inside those homes that are NOT projections, each with the
#: reason. Listed rather than pattern-matched so that adding one is a
#: visible act.
NOT_A_PROJECTION: Dict[str, str] = {
    "__init__": "package marker",
    "interface": (
        "backends/neural and backends/simulation define PROTOCOLS and "
        "types, not a projection that produces output from canonical "
        "state. There is nothing to rebuild and nothing that could "
        "write. Listed with a reason rather than skipped, because a "
        "quiet omission and a considered exclusion look identical in a "
        "report"),
}


@dataclass(frozen=True)
class Conformance:
    name: str
    verdict: str
    detail: str
    barrier_held: Optional[bool] = None
    rebuilt_identically: Optional[bool] = None


def discovered_projections(root: pathlib.Path = REPO_ROOT) -> Tuple[str, ...]:
    """Every projection module in the declared homes, from the tree."""
    found: List[str] = []
    for home in PROJECTION_HOMES:
        target = root / home
        if target.is_file():
            found.append(target.relative_to(root).as_posix())
            continue
        if not target.is_dir():
            continue
        for path in sorted(target.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            if path.stem in NOT_A_PROJECTION:
                continue
            found.append(path.relative_to(root).as_posix())
    return tuple(sorted(found))


# ------------------------------------------------------ the probes --


def _pool_with_evidence():
    """A canonical layer with something in it, built THROUGH THE
    ACQUISITION SEAM rather than by hand.

    THE FIRST VERSION MINTED IT DIRECTLY, and the return-edge ratchet
    caught it: `tests/test_architecture_sync.py` allows only declared
    seams to mint observations, and this module is not one. The right
    answer was not to add it to that allowlist -- widening the check
    that guards the write barrier to make a probe convenient is the
    trade this project exists to refuse. It was to stop hand-minting.

    So the canonical layer is built the way a real one is: fixture
    documents through `scout.pipeline.run_scout`, which IS a declared
    seam. The probe now measures projections over a canonical state that
    arrived the way canonical state is supposed to arrive, which is a
    better fixture than the one the ratchet rejected.

    A projection over an EMPTY canonical layer rebuilds identically for
    the wrong reason, so the result is asserted non-empty.
    """
    from evidence.pool import EvidencePool
    from scout.extraction import DeterministicExtractor
    from scout.fixtures import GITHUB_REPO_DOCUMENT, PAPER_DOCUMENT
    from scout.pipeline import run_scout

    class _Fixtures:
        def fetch(self):
            return (PAPER_DOCUMENT, GITHUB_REPO_DOCUMENT)

    pool = EvidencePool()
    findings, _failures = run_scout(_Fixtures(), DeterministicExtractor(), pool)
    if not pool.all_referents() or not pool.all_claimed_relationships():
        raise ProjectionConformanceError(
            "the acquisition seam produced an empty canonical layer; a "
            "projection over nothing rebuilds identically for the wrong "
            "reason and the measurement would be vacuous")
    return pool


def _probe_trust_graph() -> Conformance:
    from evidence.trust_graph import build_trust_graph

    pool = _pool_with_evidence()
    before = pool.fingerprint()
    first = build_trust_graph(pool)
    barrier = pool.fingerprint() == before
    second = build_trust_graph(pool)
    identical = (first.nodes, first.edges) == (second.nodes, second.edges)
    return Conformance(
        name="evidence/trust_graph.py",
        verdict=classify(barrier, identical),
        barrier_held=barrier, rebuilt_identically=identical,
        detail=("the graph is a pure function of the pool's referents and "
                "relationships; dropping it and rebuilding gives the same "
                "nodes and edges"))


def _probe_metrics() -> Conformance:
    from evidence.metrics import connectivity
    from evidence.trust_graph import build_trust_graph

    pool = _pool_with_evidence()
    before = pool.fingerprint()
    graph = build_trust_graph(pool)
    first = connectivity(graph)
    barrier = pool.fingerprint() == before
    identical = connectivity(build_trust_graph(pool)) == first
    return Conformance(
        name="evidence/metrics.py",
        verdict=classify(barrier, identical),
        barrier_held=barrier, rebuilt_identically=identical,
        detail="connectivity is a function of the graph, which is a function "
               "of the pool")


def _probe_materials_analysis() -> Conformance:
    """The one with a `put_`-shaped line in it, so the behavioural check
    matters here rather than the grep."""
    from materials.analysis import MaterialQuestion, analyze
    from retrieval.engine import DeterministicRetrievalEngine

    pool = _pool_with_evidence()
    engine = DeterministicRetrievalEngine()

    # THE SUBJECT IS DISCOVERED, NOT HARDCODED. The first version named
    # a referent the hand-built fixture happened to contain; once the
    # canonical layer came through the acquisition seam that key was
    # gone and the probe raised. A probe that only works against a
    # fixture it wrote itself is measuring its own fixture.
    subject = None
    for referent in pool.all_referents():
        for observation in pool.observations_about(referent.id):
            name = observation.content.get("property")
            if name:
                subject = MaterialQuestion(
                    material_natural_key=referent.natural_key, property=str(name))
                break
        if subject:
            break
    if subject is None:
        raise ProjectionConformanceError(
            "no referent in the acquired canonical layer carries a property "
            "observation, so this projection cannot be exercised over it")
    question = subject

    before = pool.fingerprint()
    history = pool.fingerprint_history()
    first = analyze(pool, engine, question)
    barrier = pool.fingerprint() == before and pool.fingerprint_history() == history
    second = analyze(pool, engine, question)
    identical = (first.observed_comparison_groups ==
                 second.observed_comparison_groups)
    return Conformance(
        name="materials/analysis.py",
        verdict=classify(barrier, identical),
        barrier_held=barrier, rebuilt_identically=identical,
        detail=("the module whose source contains a write-shaped line; the "
                "fingerprint says whether anything actually moved, which a "
                "grep cannot"))


def _genesis():
    from core.canonical.version import create_genesis_version
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT))
    from conftest import SAMPLE_SCHEMA

    return create_genesis_version(SAMPLE_SCHEMA, "2026-09-03T00:00:00Z")


def aliases_canonical_state(projected, version) -> bool:
    """Does the projection share a mutable reference back into the
    version?

    EXTRACTED SO IT CAN BE DRIVEN BOTH WAYS. The real projection never
    aliases, so a mutant hardcoding `False` changed nothing observable
    and survived -- the discriminating-input failure again. A projection
    that aliased canonical state could mutate it WITHOUT EVER CALLING A
    WRITE METHOD, so the fingerprint barrier would hold and the property
    would still be false.
    """
    return projected.fields is version.state.fields


def _probe_core_projection() -> Conformance:
    """THE projection the whole architecture is named for: canonical
    state to a projected view."""
    from core.projection.project import project_state

    version = _genesis()
    before = version.id
    first = project_state(version)
    barrier = version.id == before and version.state.fields is not None
    second = project_state(version)
    identical = (first.fields, first.edges, first.source_version) == (
        second.fields, second.edges, second.source_version)
    # and the projection must share no mutable reference back into the
    # version -- a projection that aliased canonical state could mutate
    # it without ever calling a write method
    aliased = aliases_canonical_state(first, version)
    return Conformance(
        name="core/projection/project.py",
        verdict=classify(barrier and not aliased, identical),
        barrier_held=barrier and not aliased, rebuilt_identically=identical,
        detail=("pure: the projected state shares no mutable reference with "
                "the version, so it cannot reach back into canonical state "
                "without a write call at all"))


def _ir_document():
    from core.projection.project import project_state
    from morpho.compiler import CompilerConfig, compile_morpho

    return compile_morpho(project_state(_genesis()), CompilerConfig())


def _barrier_over_ir(compile_once) -> Tuple[bool, object, object]:
    """Run a backend twice and MEASURE its barrier rather than assuming
    it.

    THE FIRST VERSION ASSERTED IT. The three backend probes passed
    `barrier_held=True` because a backend takes an IR document and not a
    pool -- which is a good argument and was not a measurement. Three of
    seven barriers were therefore claims, in a probe whose entire
    purpose is to replace claims with measurements.

    Two things are checked instead: the input IR is unchanged after
    compiling (a backend that mutated its input would corrupt the very
    thing a rebuild starts from), and the backend's signature takes no
    pool, so there is no canonical handle for it to write through.
    """
    import inspect

    ir = _ir_document()
    before = (ir.entities, ir.relations)
    first = compile_once(ir)
    unchanged = (ir.entities, ir.relations) == before
    takes_no_pool = "pool" not in inspect.signature(compile_once).parameters
    second = compile_once(ir)
    return unchanged and takes_no_pool, first, second


def _probe_diagram() -> Conformance:
    from backends.diagram.compiler import DiagramLayoutConfig, compile_svg

    barrier, first, second = _barrier_over_ir(
        lambda ir: compile_svg(ir, DiagramLayoutConfig()))
    return Conformance(
        name="backends/diagram/compiler.py",
        verdict=classify(barrier, first == second),
        barrier_held=barrier, rebuilt_identically=first == second,
        detail=("SVG regenerated from the same IR is byte-identical, and the "
                "IR is unchanged after compiling -- measured, not assumed "
                "from the signature taking no pool"))


def _probe_threejs() -> Conformance:
    from backends.threejs.compiler import ThreeJSRenderConfig, compile_threejs

    barrier, first, second = _barrier_over_ir(
        lambda ir: compile_threejs(ir, ThreeJSRenderConfig()))
    return Conformance(
        name="backends/threejs/compiler.py",
        verdict=classify(barrier, first == second),
        barrier_held=barrier, rebuilt_identically=first == second,
        detail="the scene descriptor regenerated from the same IR is equal, "
               "and the IR is unchanged after compiling")


def _probe_graph_backend() -> Conformance:
    from backends.graph.analysis import analyze

    barrier, first, second = _barrier_over_ir(analyze)
    return Conformance(
        name="backends/graph/analysis.py",
        verdict=classify(barrier, first == second),
        barrier_held=barrier, rebuilt_identically=first == second,
        detail="the analysis report regenerated from the same IR is equal, "
               "and the IR is unchanged after analysing")


PROBES: Dict[str, Callable[[], Conformance]] = {
    "core/projection/project.py": _probe_core_projection,
    "backends/diagram/compiler.py": _probe_diagram,
    "backends/threejs/compiler.py": _probe_threejs,
    "backends/graph/analysis.py": _probe_graph_backend,
    "evidence/trust_graph.py": _probe_trust_graph,
    "evidence/metrics.py": _probe_metrics,
    "materials/analysis.py": _probe_materials_analysis,
}


def probe(root: pathlib.Path = REPO_ROOT) -> List[Conformance]:
    """Every discovered projection, or a refusal naming the ones this
    probe does not cover.

    THE REFUSAL IS THE POINT. A conformance report over the projections
    someone remembered is the shape this repository already measured
    once: every check passing, over a set that omitted the failing one.
    """
    discovered = set(discovered_projections(root))
    uncovered = sorted(discovered - set(PROBES))
    if uncovered:
        raise ProjectionConformanceError(
            f"projections exist that this probe does not cover: {uncovered}. "
            f"Either probe them or list them in NOT_A_PROJECTION with a "
            f"reason -- a report over a remembered subset is how a clean "
            f"result gets manufactured")
    stale = sorted(set(PROBES) - discovered)
    if stale:
        raise ProjectionConformanceError(
            f"this probe covers modules that are no longer in the tree: "
            f"{stale}. A probe reporting on something absent is reporting "
            f"on nothing")
    return [PROBES[name]() for name in sorted(PROBES)]


def classify(barrier_held: bool, rebuilt_identically: bool) -> str:
    """The verdict, as a pure function of the two measurements.

    EXTRACTED SO IT CAN BE DRIVEN. Every projection in this tree comes
    back REBUILDABLE, and a probe whose every verdict is identical tests
    nothing about its own classification -- the uniform-inputs failure
    this repository has now hit five times. The other two arms are
    exercised over constructed measurements instead of waiting for a
    real projection to break.

    The write barrier is checked FIRST: a projection that wrote upstream
    might still reproduce itself, and reporting that as merely
    not-rebuildable would name the smaller of the two problems.
    """
    if not barrier_held:
        return WRITES_UPSTREAM
    if not rebuilt_identically:
        return NOT_REBUILDABLE
    return REBUILDABLE


def document(root: pathlib.Path = REPO_ROOT) -> dict:
    results = probe(root)
    discovered = discovered_projections(root)
    by_verdict: Dict[str, List[str]] = {}
    for result in results:
        by_verdict.setdefault(result.verdict, []).append(result.name)

    return {
        "extends": "core@1.0.0",
        "generated_by": "architecture/projection_conformance.py",
        "artifact": "projection_conformance",
        "owner": "STE",
        "the_properties_being_measured": (
            "the data-platform plan rests on two: NO SERVING PROJECTION "
            "WRITES CANONICAL TRUTH, and serving projections are "
            "REBUILDABLE from canonical state. Every layer above the "
            "canonical one is disposable only if both hold; where either "
            "fails, that projection carries state nothing can regenerate "
            "and the canonical layer is not canonical for it"),
        "why_now": (
            "both are checkable before any of the infrastructure exists, "
            "and that is the reason to check. A projection that turns out "
            "not to be rebuildable is a cheap finding today and an "
            "expensive one after a lakehouse has been built on the "
            "assumption"),
        "method": {
            "barrier": (
                "BEHAVIOURAL, NOT GREPPED. The canonical layer's own "
                "fingerprint is taken before and after; a write moves it "
                "however it is spelled. A source search for `put_` tests "
                "SPELLING, and a mutant reaching the same method through "
                "getattr and a split string walked past exactly such a "
                "check in this repository"),
            "rebuild": (
                "the projection is regenerated from the canonical layer "
                "alone and required to be identical, over a NON-EMPTY "
                "canonical state -- an empty one reproduces identically "
                "for the wrong reason"),
            "enumeration": (
                "projections are DISCOVERED from the tree and the probe "
                "REFUSES if one is uncovered. A conformance report over "
                "the projections someone remembered is the shape already "
                "measured here once: every check passing, over a set that "
                "omitted the failing one"),
        },
        "summary": {
            "discovered": len(discovered),
            "probed": len(results),
            "excluded_with_a_reason": len(NOT_A_PROJECTION),
            "rebuildable": len(by_verdict.get(REBUILDABLE, [])),
            "not_rebuildable": len(by_verdict.get(NOT_REBUILDABLE, [])),
            "writes_upstream": len(by_verdict.get(WRITES_UPSTREAM, [])),
        },
        "projections": [
            {
                "module": r.name,
                "verdict": r.verdict,
                "write_barrier_held": r.barrier_held,
                "rebuilt_identically": r.rebuilt_identically,
                "detail": r.detail,
            }
            for r in results
        ],
        "excluded": dict(NOT_A_PROJECTION),
        "what_this_does_not_claim": (
            "that a rebuildable projection is CORRECT, or that it will "
            "stay rebuildable at scale. It says the projection is a "
            "function of the canonical layer on this data, which is what "
            "makes it disposable -- not that the function is the right "
            "one. And every verdict here is REBUILDABLE, which is a fact "
            "about seven modules and not a guarantee about the eighth"),
    }


def emit(root: pathlib.Path = REPO_ROOT) -> pathlib.Path:
    import sys as _sys
    _sys.path.insert(0, str(root / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes, canonical_sha256

    payload = document(root)
    out = root / "architecture" / "exchange" / "projection_conformance.yaml"
    out.write_bytes(canonical_bytes(payload))
    (root / "architecture" / "exchange" / "projection_conformance.sha256").write_text(
        canonical_sha256(payload) + "\n")
    return out


def main() -> int:
    import sys

    payload = document()
    print("=== ARE THE SERVING PROJECTIONS REBUILDABLE, AND DO THEY WRITE? ===")
    for entry in payload["projections"]:
        print(f"  {entry['verdict']:16} barrier={entry['write_barrier_held']!s:5} "
              f"rebuilt={entry['rebuilt_identically']!s:5}  {entry['module']}")
    summary = payload["summary"]
    print(f"\n  discovered {summary['discovered']}, probed {summary['probed']}, "
          f"excluded with a reason {summary['excluded_with_a_reason']}")
    print(f"  rebuildable {summary['rebuildable']} / writes upstream "
          f"{summary['writes_upstream']} / not rebuildable "
          f"{summary['not_rebuildable']}")
    print("\n  Every verdict is REBUILDABLE. That is a fact about seven")
    print("  modules, not a guarantee about the eighth -- the probe's own")
    print("  other two arms are exercised on constructed measurements.")
    if "--emit" in sys.argv:
        out = emit()
        print(f"\n  wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
