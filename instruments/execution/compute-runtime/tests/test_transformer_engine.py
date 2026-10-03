"""Transformer Engine locks: the smallest real scientific transformer
workload, end-to-end through the unchanged STE boundary. Proof-free
and fast (the attention kernel runs in milliseconds)."""

from __future__ import annotations

import pathlib

import pytest

from execution.engine import default_cli_path, run_specification
from execution.specification import (
    HARDMAX_ATTENTION_DESCRIPTOR,
    ExecutionSpecification,
    encode_attention_input,
)
from structures.library import METHANE, WATER
from structures.molecule import Atom, Molecule
from transformer.model import AttentionModel, reference_attention
from transformer.prediction import Prediction
from transformer.representation import molecule_representation

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine not built; environment gap",
)

REPO = pathlib.Path(__file__).resolve().parent.parent

EYE4 = tuple(tuple(1 if i == j else 0 for j in range(4)) for i in range(4))
MIXER = tuple(tuple((i * 7 + j * 3 + 1) % 5 - 2 for j in range(4)) for i in range(4))
MODEL = AttentionModel(EYE4, MIXER, EYE4)


# -- representation -> tensor correctness ------------------------------------------------------------


def test_molecular_state_projects_to_typed_tokens():
    rep = molecule_representation(WATER)
    assert rep.feature_semantics == ("mass_amu", "x_pm", "y_pm", "z_pm")
    assert rep.tokens == ((16, 0, 0, 0), (1, 76, 0, 59), (1, -76, 0, 59))
    assert rep.tensor() == rep.tokens, "the tensor is a projection, not a mutation"
    # identity: content and only content
    assert rep.identity() == molecule_representation(Molecule(WATER.atoms)).identity()
    moved = Molecule((WATER.atoms[0], Atom("H", 77, 0, 59), WATER.atoms[2]))
    relabeled = Molecule((Atom("S", 0, 0, 0),) + WATER.atoms[1:])
    assert rep.identity() != molecule_representation(moved).identity()
    assert rep.identity() != molecule_representation(relabeled).identity(), (
        "unlike the pairwise lowering, the mass feature SEES the element")


# -- transformer -> STE contract, reference agreement, repeatability ---------------------------------


def test_forward_agrees_with_the_independent_reference_and_repeats():
    for molecule in (WATER, METHANE):
        rep = molecule_representation(molecule)
        first = MODEL.forward(rep)
        second = MODEL.forward(rep)
        assert first == second, "repeat computation: identical prediction"
        expected = reference_attention(
            [list(r) for r in rep.tokens], [list(r) for r in MODEL.wq],
            [list(r) for r in MODEL.wk], [list(r) for r in MODEL.wv])
        assert first.values == expected, "native/reference agreement, exactly"


def test_identity_separation_and_tamper_sensitivity():
    rep = molecule_representation(WATER)
    spec = MODEL.forward_spec(rep)
    identities = {MODEL.model_identity(), rep.identity(), spec.identity()}
    assert len(identities) == 3, "model != representation != specification"

    tampered_weights = AttentionModel(EYE4, MIXER, MIXER)
    assert tampered_weights.model_identity() != MODEL.model_identity()
    assert tampered_weights.forward_spec(rep).identity() != spec.identity(), (
        "a changed model is a changed computation")
    moved = molecule_representation(
        Molecule((WATER.atoms[0], Atom("H", 77, 0, 59), WATER.atoms[2])))
    assert MODEL.forward_spec(moved).identity() != spec.identity(), (
        "a changed input is a changed computation")
    # two runs of one spec: one computation identity (engine recomputes
    # and compares; equal results imply equal computation identity)
    assert run_specification(spec).output == run_specification(spec).output


def test_failure_semantics_are_refusals_never_predictions():
    with pytest.raises(ValueError, match="2\\^20"):
        AttentionModel(((1 << 21,),), ((0,),), ((0,),))
    with pytest.raises(ValueError, match="matrix"):
        AttentionModel(EYE4, MIXER, (EYE4[0],))
    rep3 = molecule_representation(WATER)
    wrong_d = AttentionModel(((1,),), ((1,),), ((1,),))
    with pytest.raises(ValueError, match="dimension"):
        wrong_d.forward_spec(rep3)
    # malformed payload halts in the kernel with the descriptor's code
    bad = ExecutionSpecification(HARDMAX_ATTENTION_DESCRIPTOR, b"", b"xxx")
    result = run_specification(bad)
    assert result.status == "halted" and result.exit_code == 2
    # value bound is the kernel's refusal, not a wrapped prediction
    over = encode_attention_input(1, [[1 << 21]], [[1]], [[1]], [[1]])
    bound = run_specification(ExecutionSpecification(HARDMAX_ATTENTION_DESCRIPTOR, b"", over))
    assert bound.status == "halted" and bound.exit_code == 4


def test_prediction_is_not_evidence_and_declares_uncertainty():
    """No conversion to Observation exists; the pool refuses the type;
    the transformer package holds no pool writes (and the
    architecture-sync minting ratchet scans it too); uncertainty is
    explicit or the prediction cannot exist."""
    from evidence.admission import admit_observation
    from evidence.pool import EvidencePool

    prediction = MODEL.forward(molecule_representation(WATER))
    assert prediction.uncertainty_kind == "absent", "declared, never implied"
    with pytest.raises(Exception):
        admit_observation(EvidencePool(), prediction)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="uncertainty_kind"):
        Prediction("m", "r", "s", ((1,),), "vibes")
    for path in (REPO / "transformer").glob("*.py"):
        text = path.read_text()
        assert ".put_" not in text and "admit_" not in text and \
            "make_observation" not in text, f"{path.name} touches the pool"


def test_proving_the_attention_kernel_is_refused_attributably(tmp_path):
    """No guest is registered for the attention program: the stage-5
    gate refuses with the attributable message -- never a silent skip,
    never a false warrant."""
    from execution.proving import (
        ProvedRunError,
        default_nexus_host_path,
        prove_and_verify_result,
    )

    nexus = default_nexus_host_path()
    elf = REPO / "zk" / "artifacts" / "nexus-heat.elf"
    if not (nexus.exists() and elf.exists()):
        pytest.skip("nexus not built; environment gap")
    spec = MODEL.forward_spec(molecule_representation(WATER))
    native = run_specification(spec)
    with pytest.raises(ProvedRunError, match="no built guest is registered"):
        prove_and_verify_result(native, spec, tmp_path / "p.bin", nexus, elf)
