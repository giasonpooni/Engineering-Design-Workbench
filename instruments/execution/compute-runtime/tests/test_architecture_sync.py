"""Architecture-sync locks: the acquisition-first loop's write barriers
and gates, all executable, all fail-closed. Proof-free and fast."""

from __future__ import annotations

import pathlib

import pytest
import yaml

from architecture.conformance import (
    ConformanceError,
    check_core_closure,
    check_doctrine_current,
    check_vertical_contract,
    core_version,
    lint_doctrine_vendor_free,
)
from architecture.doctrine_generator import generate_doctrine
from architecture.retention import AgentExecutionRecord, RetentionError, fingerprint
from architecture.snapshot_verification import (
    CanaryCalibration,
    CanaryFixture,
    SnapshotVerificationError,
    behavioral_canary,
    measure_noise_floor,
    pin_accepted,
)
from evidence.classes import EvidenceClassError, class_of
from evidence.quarantine import Quarantine
from evidence.types import make_observation
from materials.candidates import ActionCandidate
from structures.method_blocks import MethodBlockError, assert_applicability, assert_method_block
from structures.quantity import QuantityError, assert_property_context, assert_quantity_type
from structures.substance import (
    DistributionIdentity,
    IdentityPolicyError,
    ResolutionPolicy,
    SubstanceIdentity,
    assert_distribution_identity,
    assert_identity_policy,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


# -- class_assigned_at_ingest ------------------------------------------------------------------------


def test_evidence_class_is_total_over_production_methods_and_fails_closed():
    """Every extraction method production code declares has a class;
    an undeclared method is refused, never guessed."""
    assert class_of("simulation:deterministic_native_execution") == "computed"
    assert class_of("human_transcription") == "asserted"
    assert class_of("regex:fixture_lines") == "asserted"
    assert class_of("model:someday") == "asserted", (
        "a model-extracted claim is still the document's claim")
    assert class_of("fit:linear") == "derived"
    assert class_of("measurement:instrument") == "measured"
    with pytest.raises(EvidenceClassError):
        class_of("vibes")


def test_computation_never_classes_as_measurement():
    """COMPUTATION != MEASUREMENT, executable: no simulation-declared
    method can reach the measured class."""
    for method in ("simulation:deterministic_native_execution",
                   "simulation:gromacs", "simulation:anything"):
        assert class_of(method) == "computed"


def test_class_is_immutable_because_identity_covers_the_declaration():
    """No promotion path exists structurally: a different declaration is
    a DIFFERENT observation (content-addressed id), and the type is
    frozen."""
    kwargs = dict(record_ids=("r1",), content={"v": 1}, confidence=1.0,
                  extracted_at="t")
    computed = make_observation(extraction_method="simulation:x", **kwargs)
    claimed_measured = make_observation(extraction_method="measurement:x", **kwargs)
    assert computed.id != claimed_measured.id, "promotion = a different fact"
    with pytest.raises(Exception):
        computed.extraction_method = "measurement:x"  # frozen


# -- proposals_are_not_evidence ----------------------------------------------------------------------


def test_optimizer_output_has_no_write_path_into_the_pool():
    """An ActionCandidate is not an admissible evidence type, and no
    optimizer-side module holds a pool write. A proposal becomes
    evidence only via its execution's own result entering the admission
    seam as computed evidence."""
    from evidence.admission import admit_observation
    from evidence.pool import EvidencePool

    candidate = ActionCandidate.__new__(ActionCandidate)  # no admissible form exists
    pool = EvidencePool()
    with pytest.raises(Exception):
        admit_observation(pool, candidate)  # type: ignore[arg-type]

    for module in ("candidates", "selection", "optimization", "decision",
                   "evaluation", "utility"):
        source = (REPO / "materials" / f"{module}.py").read_text()
        assert ".put_" not in source and "admit_" not in source, (
            f"materials/{module}.py holds a pool write path")


def test_return_edge_only_declared_seams_mint_observations():
    """The loop's return edge: derived state re-enters through
    acquisition only. The set of production modules that mint or write
    observations is closed and named -- a new seam must be added HERE,
    consciously."""
    minters = set()
    for path in REPO.rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith(("tests/", ".", "workbench")) or "__pycache__" in rel:
            continue
        text = path.read_text()
        if "make_observation(" in text or "put_observation(" in text:
            minters.add(rel)
    allowed = {
        "evidence/types.py",       # the constructor itself
        "evidence/pool.py",        # the store
        "evidence/admission.py",   # the gate
        "materials/results.py",    # execution results -> admission seam
        "experiment/step.py",      # the dispatch seam
        "scout/pipeline.py",       # document acquisition seam
        "campaign/driver.py",      # docstring mention only (no call)
    }
    assert minters <= allowed, f"undeclared observation seam(s): {minters - allowed}"


# -- vocabulary and registries -----------------------------------------------------------------------


def test_vocabulary_maps_onto_the_four_classes_and_validated_is_not_one():
    data = yaml.safe_load((REPO / "architecture" / "vocabulary_map.yaml").read_text())
    from evidence.classes import EVIDENCE_CLASSES

    for term, entry in data["vocabulary_map"].items():
        assert entry["class"] in EVIDENCE_CLASSES, (term, entry)
    assert "validated" not in data["vocabulary_map"]
    assert data["not_a_class"]["validated"]["kind"] == "status_on_claim"


def test_conformance_gates_pass_on_the_committed_repository():
    check_doctrine_current()
    assert core_version() == "core@1.0.0"
    assert len(check_core_closure()) >= 5
    contract = check_vertical_contract(
        REPO / "architecture" / "verticals" / "chemistry" / "vertical.yaml")
    assert contract["admissibility_class"] == "reproducible_on_demand"
    assert contract["instrument_adapters"] == []


def test_unconformant_vertical_is_refused(tmp_path):
    bad = tmp_path / "vertical.yaml"
    bad.write_text("extends: core@1.0.0\nvertical: incomplete\n")
    with pytest.raises(ConformanceError, match="missing"):
        check_vertical_contract(bad)
    stale = tmp_path / "stale.yaml"
    stale.write_text(
        "extends: core@0.0\nvertical: stale\nextensions: []\n"
        "observation_types: []\nadmissibility_class: x\n"
        "instrument_adapters: []\nretraction_policy: none\n")
    with pytest.raises(ConformanceError, match="core"):
        check_vertical_contract(stale)


def test_doctrine_is_deterministic_vendor_free_and_budgeted():
    first, second = generate_doctrine(), generate_doctrine()
    assert first == second, "regeneration is deterministic"
    for name, content in first.items():
        lint_doctrine_vendor_free(content, where=name)
    with pytest.raises(ConformanceError, match="vendor token"):
        lint_doctrine_vendor_free("the openai validator", where="bad.md")


# -- hosted-binding boundary -------------------------------------------------------------------------


def test_canary_boundary_measured_against_the_deterministic_extractor():
    """The canary is exercised against the repository's real
    deterministic extractor: measured noise floor exactly 0.0, and a
    behavioral change (a broken field) halts with the diff surfaced."""
    from scout.extraction import DeterministicExtractor
    from evidence.types import make_record

    record = make_record(document_id="d", locator="l",
                         raw_content="ENTITY: FEP :: material\nFACT: mp=260 unit=C\n")
    extractor = DeterministicExtractor()

    def run(fixture: CanaryFixture):
        (candidate,) = extractor.extract(record)
        entities = {e.label: e.kind for e in candidate.entities}
        return {"entity_count": len(candidate.entities),
                "fep_kind": entities.get("FEP")}

    fixtures = [CanaryFixture("f1", "ENTITY: FEP", {"entity_count": 1, "fep_kind": "material"})]
    floor, runs = measure_noise_floor(fixtures, run, runs=3)
    assert floor == 0.0 and len(runs) == 3, "deterministic binding: exact zero"

    calibration = CanaryCalibration("rule-based-extractor", "fixtures-v1",
                                    runs=3, noise_floor=floor, threshold=floor)
    assert behavioral_canary(fixtures, run, calibration) == 1.0

    def drifted(fixture: CanaryFixture):
        return {"entity_count": 2, "fep_kind": "material"}
    with pytest.raises(SnapshotVerificationError, match="HALT INGEST"):
        behavioral_canary(fixtures, drifted, calibration)

    with pytest.raises(SnapshotVerificationError, match="pinned identifier"):
        pin_accepted("retired-snapshot", lambda _: False)
    with pytest.raises(SnapshotVerificationError, match="noise floor"):
        CanaryCalibration("b", "v", runs=3, noise_floor=0.2, threshold=0.1)


def test_agent_execution_retention_is_mandatory_and_self_consistent():
    output = "ACCEPT"
    record = AgentExecutionRecord(
        binding_id="validator", snapshot_identity="unavailable",
        adapter_version="a1", doctrine_hash="d" * 64,
        effective_prompt="p", input_fingerprint="i" * 64,
        raw_output=output, output_fingerprint=fingerprint(output.encode()),
        executed_at="2026-08-25T00:00:00Z", lineage="scout->resolver->validator")
    assert record.snapshot_identity == "unavailable", "explicit, never blank"
    with pytest.raises(RetentionError, match="missing"):
        AgentExecutionRecord("", "s", "a", "d", "p", "i", "o",
                             fingerprint(b"o"), "t", "l")
    with pytest.raises(RetentionError, match="does not match"):
        AgentExecutionRecord("b", "s", "a", "d", "p", "i", "o", "0" * 64, "t", "l")


def test_quarantine_retains_counts_and_has_no_force_path():
    quarantine = Quarantine()
    quarantine.hold({"raw": "bad row"}, ("class_assigned_at_ingest",), "run-1")
    quarantine.hold({"raw": "bare scalar"},
                    ("no_context_free_property", "quantity_is_typed"), "run-1")
    assert quarantine.by_invariant() == {
        "class_assigned_at_ingest": 1, "no_context_free_property": 1,
        "quantity_is_typed": 1}
    assert quarantine.rejection_rate(attempted=10) == 0.2
    assert not hasattr(quarantine, "force"), "no force path exists"
    assert not any("force" in name for name in dir(Quarantine) if not name.startswith("_"))


# -- chemistry identity, quantities, method blocks ---------------------------------------------------


def test_substance_identity_policy_is_declared_versioned_and_blocks_mismatched_merges():
    policy = ResolutionPolicy(tautomer="normalized(inchi-15)", stereo="distinct",
                              salt_solvate="parent_only", isotope="ignored")
    a = SubstanceIdentity("InChI=1S/H2O/h1H2", "standard-inchi 1.06", policy)
    b = SubstanceIdentity("InChI=1S/H2O/h1H2", "standard-inchi 1.06", policy)
    assert a.identity() == b.identity()
    assert_identity_policy(a, b)  # compatible: merge may proceed

    other = SubstanceIdentity("InChI=1S/H2O/h1H2", "standard-inchi 1.06",
                              ResolutionPolicy(salt_solvate="distinct"))
    assert a.identity() != other.identity(), "the policy is part of the identity"
    with pytest.raises(IdentityPolicyError, match="mismatch blocks the merge"):
        assert_identity_policy(a, other)
    with pytest.raises(IdentityPolicyError, match="rule id"):
        ResolutionPolicy(tautomer="normalized")
    with pytest.raises(IdentityPolicyError):
        ResolutionPolicy(stereo="whatever")


def test_distributions_have_no_point_identity():
    with pytest.raises(IdentityPolicyError, match="structure string"):
        assert_distribution_identity("polymer", {"structure": "C2F4"})
    with pytest.raises(IdentityPolicyError, match="missing"):
        DistributionIdentity("polymer", {"repeat_units": ("C2F4",)})
    polymer = assert_distribution_identity("polymer", {
        "repeat_units": ("C2F4",), "composition": {"C2F4": 1.0},
        "molar_mass": {"Mn": 50_000, "Mw": 120_000}, "dispersity": 2.4,
        "end_groups": ("CF3",), "architecture": "linear"})
    batch = assert_distribution_identity("batch", {
        "material_ref": polymer.identity(), "process_ref": "extrusion-7",
        "timestamp": "2026-08-25", "facility": "plant-2"})
    assert polymer.identity() != batch.identity()


def test_properties_are_never_context_free_and_quantities_are_typed():
    good = {"property": "melt_viscosity", "value": 1250.0, "unit": "Pa.s",
            "uncertainty_kind": "stated", "uncertainty": 25.0,
            "method": "capillary_rheometry",
            "conditions": {"temperature_K": 653, "rate_s-1": 100}}
    quantity = assert_property_context(good)
    assert quantity.uncertainty == 25.0
    with pytest.raises(QuantityError, match="method"):
        assert_property_context({"property": "x", "value": 1, "unit": "u",
                                 "uncertainty_kind": "absent",
                                 "conditions": {"T": 300}})
    with pytest.raises(QuantityError, match="bare scalars"):
        assert_quantity_type({"value": 1250.0})
    with pytest.raises(QuantityError, match="absent"):
        assert_quantity_type({"value": 1.0, "unit": "u",
                              "uncertainty_kind": "absent", "uncertainty": 0.1})
    absent = assert_quantity_type({"value": 1.0, "unit": "u",
                                   "uncertainty_kind": "absent"})
    assert absent.uncertainty is None, (
        "'source reported none' is explicit, distinct from 'lost during ingest'")


def test_computed_method_blocks_gate_canonical_assertion_on_the_real_workload():
    """The MD block built from the ACTUAL argon GROMACS inputs passes;
    removing a field refuses; an out-of-domain ML prediction refuses."""
    md_block = {"force_field": "LJ argon (inline topology: sigma 0.3401, eps 0.978638)",
                "force_field_version": "stage-1 fixture",
                "ensemble": "single-point (nsteps 0)", "timestep": "n/a",
                "equilibration": "none", "sampling_time": "single point",
                "thermostat": "none", "barostat": "none"}
    assert_method_block("md", md_block)
    with pytest.raises(MethodBlockError, match="missing"):
        assert_method_block("md", {k: v for k, v in md_block.items()
                                   if k != "force_field"})
    with pytest.raises(MethodBlockError, match="unknown"):
        assert_method_block("dft-ish", {})

    ml = {"model_id": "m", "snapshot": "s",
          "training_evidence_classes": ("measured", "computed"),
          "applicability_domain": {"temperature_K": (250, 400)}}
    assert_method_block("ml", ml)
    assert_applicability(ml, {"temperature_K": 300})
    with pytest.raises(MethodBlockError, match="outside the declared domain"):
        assert_applicability(ml, {"temperature_K": 500})
    with pytest.raises(MethodBlockError, match="never declared"):
        assert_applicability(ml, {"pressure_bar": 1})
