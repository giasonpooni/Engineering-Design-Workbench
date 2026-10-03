"""Locks on the two properties the data-platform plan rests on.

NO SERVING PROJECTION WRITES CANONICAL TRUTH, and serving projections
are REBUILDABLE from canonical state. Every layer above the canonical
one is disposable only if both hold.

Both are checkable before any of the infrastructure exists, and that is
the reason to check them now: a projection that turns out not to be
rebuildable is a cheap finding today and an expensive one after a
lakehouse has been built on the assumption.
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "architecture"))

from architecture import projection_conformance as conf

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "architecture" / "exchange" / "projection_conformance.yaml"


# ------------------------------------------- the probe refuses gaps --


def test_a_projection_the_probe_does_not_cover_is_a_refusal():
    """THE POINT OF THE PROBE. A conformance report over the projections
    someone remembered is the shape already measured here once: every
    check passing, over a set that omitted the failing one."""
    original = dict(conf.PROBES)
    try:
        conf.PROBES.pop("evidence/metrics.py")
        with pytest.raises(conf.ProjectionConformanceError) as caught:
            conf.probe(ROOT)
        assert "evidence/metrics.py" in str(caught.value)
    finally:
        conf.PROBES.clear()
        conf.PROBES.update(original)


def test_a_probe_for_a_module_no_longer_in_the_tree_is_a_refusal():
    """Reporting on something absent is reporting on nothing."""
    original = dict(conf.PROBES)
    try:
        conf.PROBES["evidence/deleted_projection.py"] = lambda: None
        with pytest.raises(conf.ProjectionConformanceError) as caught:
            conf.probe(ROOT)
        assert "no longer in the tree" in str(caught.value)
    finally:
        conf.PROBES.clear()
        conf.PROBES.update(original)


def test_every_discovered_projection_is_probed_or_excluded_with_a_reason():
    discovered = set(conf.discovered_projections(ROOT))
    assert discovered == set(conf.PROBES), (
        "discovery and coverage must agree, or the report is over a subset")
    for module, reason in conf.NOT_A_PROJECTION.items():
        assert len(reason) > 10, f"{module} is excluded without a reason"


# -------------------------------- the classifier's other two arms --


def test_all_three_verdicts_are_reachable_from_constructed_measurements():
    """Every projection in this tree comes back REBUILDABLE. A probe
    whose every verdict is identical tests nothing about its own
    classification -- the uniform-inputs failure, in its fifth
    appearance here. So the other arms are driven directly."""
    assert conf.classify(True, True) == conf.REBUILDABLE
    assert conf.classify(True, False) == conf.NOT_REBUILDABLE
    assert conf.classify(False, True) == conf.WRITES_UPSTREAM
    assert conf.classify(False, False) == conf.WRITES_UPSTREAM


def test_a_write_outranks_a_failed_rebuild():
    """A projection that wrote upstream might still reproduce itself,
    and calling that merely not-rebuildable names the smaller of the two
    problems."""
    assert conf.classify(False, True) == conf.WRITES_UPSTREAM
    assert conf.classify(False, False) == conf.WRITES_UPSTREAM


# ------------------------------------- the barrier is behavioural --


def test_no_barrier_is_asserted_rather_than_measured():
    """THE DEFECT THIS REPLACES. The three backend probes originally
    passed `barrier_held=True` because a backend takes an IR and not a
    pool. That is a good argument and it was not a measurement -- three
    of seven barriers were claims, inside a probe whose whole purpose is
    to replace claims with measurements.

    Every barrier value must now come from something that was run: a
    pool fingerprint, or an IR compared before and after."""
    import inspect

    for name, probe in conf.PROBES.items():
        body = inspect.getsource(probe)
        measured = ("fingerprint()" in body or "_barrier_over_ir" in body
                    or "aliased" in body)
        assert measured, f"{name} decides its barrier without measuring it"
        assert "barrier_held=True," not in body, (
            f"{name} asserts its barrier as a literal")


def test_the_ir_barrier_fails_when_a_backend_mutates_its_input():
    """Driven, so the IR half is not a constant either. A backend that
    rewrote its input would corrupt the very thing a rebuild starts
    from."""
    def mutating(ir):
        object.__setattr__(ir, "entities", ())
        return "output"

    barrier, _first, _second = conf._barrier_over_ir(mutating)
    assert barrier is False


def test_the_ir_barrier_holds_for_a_backend_that_only_reads():
    barrier, first, second = conf._barrier_over_ir(lambda ir: len(ir.entities))
    assert barrier is True
    assert first == second


def test_a_write_to_the_pool_actually_moves_the_fingerprint():
    """The barrier rests on this. If a write did not move the
    fingerprint, every projection would pass the barrier for free."""
    from evidence.types import make_referent

    pool = conf._pool_with_evidence()
    before = pool.fingerprint()
    pool.put_referent(make_referent(natural_key="delta", kind="substance"))
    assert pool.fingerprint() != before


def test_the_canonical_state_the_probe_uses_is_not_empty():
    """A projection over an empty canonical layer rebuilds identically
    for the wrong reason -- the vacuous-plant shape."""
    pool = conf._pool_with_evidence()
    assert len(pool.all_referents()) >= 2
    assert len(pool.all_claimed_relationships()) >= 1


def test_the_canonical_layer_arrives_through_the_acquisition_seam():
    """NOT HAND-MINTED. The first version built the pool directly and
    the return-edge ratchet caught it: only declared seams mint
    observations, and this module is not one. Adding it to that
    allowlist would have widened the check guarding the write barrier to
    make a probe convenient. It builds through run_scout instead --
    which is a better fixture than the one the ratchet rejected, because
    the canonical state now arrives the way canonical state is supposed
    to."""
    import inspect

    body = inspect.getsource(conf._pool_with_evidence)
    assert "run_scout" in body
    assert "put_observation" not in body and "make_observation" not in body


def test_the_analysis_subject_is_discovered_not_hardcoded():
    """A probe that only works against a fixture it wrote itself is
    measuring its own fixture. When the canonical layer changed source,
    a hardcoded key raised."""
    import inspect

    body = inspect.getsource(conf._probe_materials_analysis)
    assert "all_referents()" in body
    assert '"alpha"' not in body


def test_the_core_projection_shares_no_mutable_reference_with_the_version():
    """A projection that aliased canonical state could mutate it without
    ever calling a write method -- the barrier would hold and the
    property would still be false."""
    result = conf._probe_core_projection()
    assert result.verdict == conf.REBUILDABLE
    assert result.barrier_held is True
    assert "shares no mutable reference" in result.detail

    # DRIVEN BOTH WAYS. The real projection never aliases, so asserting
    # only that it passes cannot tell the check from a constant -- a
    # mutant hardcoding False survived exactly that.
    from core.projection.project import project_state

    version = conf._genesis()

    honest = project_state(version)
    assert conf.aliases_canonical_state(honest, version) is False

    class _Aliasing:
        fields = version.state.fields

    assert conf.aliases_canonical_state(_Aliasing(), version) is True


# --------------------------------------------------- the artifact --


def test_the_artifact_is_a_fixed_point():
    sys.path.insert(0, str(ROOT / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes

    assert canonical_bytes(conf.document(ROOT)) == ARTIFACT.read_bytes()


def test_the_artifact_states_that_a_uniform_result_is_not_a_guarantee():
    """Seven of seven rebuildable is a fact about seven modules."""
    document = yaml.safe_load(ARTIFACT.read_text())
    assert document["summary"]["rebuildable"] == document["summary"]["probed"]
    assert "not a guarantee about the eighth" in document["what_this_does_not_claim"]
    assert "not that the function is the right one" in \
        document["what_this_does_not_claim"]


def test_the_artifact_says_why_this_is_measured_before_the_infrastructure():
    document = yaml.safe_load(ARTIFACT.read_text())
    assert "cheap finding today" in document["why_now"]
    assert "lakehouse" in document["why_now"]


def test_an_empty_canonical_layer_is_refused_rather_than_measured():
    """FORCED, because the real fixtures are never empty and the
    refusal therefore never fires on its own -- so asserting only that
    the layer is non-empty cannot tell the guard from a constant, and a
    mutant deleting it survived exactly that.

    A projection over nothing rebuilds identically for the wrong reason.
    The probe must refuse rather than report seven clean verdicts over
    an empty layer."""
    import scout.fixtures as fixtures

    paper, repo = fixtures.PAPER_DOCUMENT, fixtures.GITHUB_REPO_DOCUMENT
    try:
        # a document the extractor yields nothing from leaves the
        # canonical layer empty without breaking acquisition
        empty = dataclasses.replace(paper, content="")
        fixtures.PAPER_DOCUMENT = empty
        fixtures.GITHUB_REPO_DOCUMENT = dataclasses.replace(repo, content="")
        with pytest.raises(conf.ProjectionConformanceError) as caught:
            conf._pool_with_evidence()
        assert "vacuous" in str(caught.value)
    finally:
        fixtures.PAPER_DOCUMENT, fixtures.GITHUB_REPO_DOCUMENT = paper, repo
