"""Batched-forward execution contract locks: B independent requests,
one engine process, B attributable results -- the same contract, not a
second one. Proof-free and fast."""

from __future__ import annotations

import subprocess

import pytest

from execution.engine import (
    EngineProtocolError,
    ExecutionRefused,
    _encode_request,
    default_cli_path,
    run_specification,
    run_specifications,
)
from execution.specification import (
    HARDMAX_ATTENTION_DESCRIPTOR,
    HEAT_DIFFUSION_DESCRIPTOR,
    ExecutionSpecification,
    encode_attention_input,
    encode_heat_input,
)
from structures.library import METHANE, WATER
from transformer.model import AttentionModel, reference_attention
from transformer.representation import molecule_representation

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine not built; environment gap",
)

EYE4 = tuple(tuple(1 if i == j else 0 for j in range(4)) for i in range(4))
MIXER = tuple(tuple((i * 7 + j * 3 + 1) % 5 - 2 for j in range(4)) for i in range(4))
MODEL = AttentionModel(EYE4, MIXER, EYE4)


def _heat(seed: int) -> ExecutionSpecification:
    return ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"",
        encode_heat_input(10, [0, 500 + seed, 900, 500, 0]))


def test_batch_of_one_is_the_single_contract():
    """Backward compatibility, exactly: a batch of one and a single run
    agree on every field including identities and occurrence 0."""
    spec = _heat(1)
    single = run_specification(spec)
    (batched,) = run_specifications([spec])
    assert batched == single


@pytest.mark.parametrize("size", [1, 2, 4, 8, 16])
def test_batched_equals_independent_singles_in_order(size):
    """The central invariant: batched[i] == single(input[i]) for every
    i, in request order, at every tested batch size -- same outputs,
    same computation identities, engine-minted."""
    specs = [_heat(seed) for seed in range(size)]
    batch = run_specifications(specs)
    for at, (spec, result) in enumerate(zip(specs, batch)):
        single = run_specification(spec)
        assert result.output == single.output, f"item {at}"
        assert result.computation_identity == single.computation_identity
        assert result.specification_identity == spec.identity()
        assert result.engine_occurrence == at, "occurrences record batch order"


def test_constituent_identities_never_collapse():
    """A batch containing DUPLICATE specs: same computation identity for
    the duplicates (content!), distinct occurrences (operations!), and
    distinct identities for the distinct member."""
    a, b = _heat(1), _heat(2)
    batch = run_specifications([a, a, b])
    assert batch[0].computation_identity == batch[1].computation_identity
    assert batch[0].engine_occurrence != batch[1].engine_occurrence
    assert batch[2].computation_identity != batch[0].computation_identity
    # retention: every constituent keeps the full identity set
    for result in batch:
        assert result.specification_identity and result.program_identity
        assert result.input_identity and result.output_identity
        assert result.computation_identity is not None


def test_per_item_failure_is_attributable_and_never_a_prediction():
    """A halted member (kernel fault) is an ordinary per-item result;
    the other members complete -- per-item failure semantics, exactly
    the single-run semantics per item."""
    good, bad = _heat(1), ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"", b"xx")
    batch = run_specifications([good, bad, good])
    assert [r.status for r in batch] == ["completed", "halted", "completed"]
    assert batch[1].exit_code == 2 and batch[1].output is None
    assert batch[0].output == batch[2].output


def test_unrunnable_item_refuses_naming_its_index():
    unknown = ExecutionSpecification(b"no.such.program", b"", b"")
    with pytest.raises(ExecutionRefused, match="batch item 1"):
        run_specifications([_heat(1), unknown])


def test_malformed_stream_executes_nothing():
    """A truncated batch stream is a protocol error: exit 2, no result
    blocks, nothing executed -- parse-all-before-execute, verified at
    the process level."""
    raw = _encode_request(_heat(1)) + b"\x07\x00"  # truncated second request
    proc = subprocess.run([str(default_cli_path())], input=raw, capture_output=True)
    assert proc.returncode == 2
    assert b"ste-execution-result" not in proc.stdout, "nothing ran"
    with pytest.raises(ValueError, match="empty batch"):
        run_specifications([])


def test_forward_batch_matches_singles_and_reference():
    reps = [molecule_representation(m) for m in (WATER, METHANE, WATER, METHANE)]
    batch = MODEL.forward_batch(reps)
    singles = tuple(MODEL.forward(rep) for rep in reps)
    assert tuple(batch) == singles, "identical predictions, identity for identity"
    for rep, prediction in zip(reps, batch):
        expected = reference_attention(
            [list(r) for r in rep.tokens], [list(r) for r in MODEL.wq],
            [list(r) for r in MODEL.wk], [list(r) for r in MODEL.wv])
        assert prediction.values == expected


def test_forward_batch_refuses_faulted_items_by_index():
    """A fault inside a batched forward names its index and yields no
    prediction -- the model layer's refusal, on top of the execution
    layer's attributable per-item results."""
    good = molecule_representation(WATER)
    over = encode_attention_input(4, [[1 << 21, 0, 0, 0]],
                                  [list(r) for r in EYE4],
                                  [list(r) for r in EYE4],
                                  [list(r) for r in EYE4])
    # drive the failure through the execution layer with a hand-built
    # faulting spec beside a good one, then assert the model layer's
    # index-naming refusal using its own specs
    faulting = ExecutionSpecification(HARDMAX_ATTENTION_DESCRIPTOR, b"", over)
    results = run_specifications([MODEL.forward_spec(good), faulting])
    assert [r.status for r in results] == ["completed", "halted"]

    class Sneaky(AttentionModel):
        def forward_spec(self, representation):
            spec = super().forward_spec(representation)
            return faulting if representation is good else spec

    with pytest.raises(RuntimeError, match="batch item 0"):
        Sneaky(EYE4, MIXER, EYE4).forward_batch([good])


# -- checker-cost phase: optimized checking, identical verification ----------------------------------


def test_optimized_and_reference_checkers_agree_on_valid_and_tampered_corpus():
    """The reference checker (`_check_result` with no precomputed
    identities) and the batch path's digest-reuse checker must agree
    EXACTLY -- acceptance for acceptance, rejection for rejection, on
    valid blocks and on every class of tampered identity. Digest reuse
    shares computation over byte-identical inputs; it must never share
    a verdict."""
    from execution.engine import EngineIdentityMismatch, _check_result, _parse_lines, _split_blocks
    import subprocess as sp

    specs = [_heat(seed) for seed in (1, 1, 2)]  # duplicates included
    raw = b"".join(_encode_request(s) for s in specs)
    proc = sp.run([str(default_cli_path())], input=raw, capture_output=True)
    blocks = _split_blocks(proc.stdout.decode())
    fields = [_parse_lines(b) for b in blocks]

    # valid corpus: reference vs batch path agree field-for-field
    reference = [_check_result(s, f) for s, f in zip(specs, fields)]
    batch = run_specifications(specs)
    for ref, opt in zip(reference, batch):
        assert ref.computation_identity == opt.computation_identity
        assert ref.output == opt.output and ref.status == opt.status

    # tampered corpus: every identity field, both checkers reject
    for key in ("spec", "program", "input", "output_id", "computation"):
        tampered = dict(fields[0])
        tampered[key] = "ab" * 32
        with pytest.raises(EngineIdentityMismatch):
            _check_result(specs[0], tampered)
        with pytest.raises(EngineIdentityMismatch):
            _check_result(specs[0], tampered, precomputed=(
                specs[0].identity(), specs[0].program_identity(),
                specs[0].input_identity()))
    # tampered output BYTES (identity fields left alone): both reject --
    # a flipped byte, because integer truncation can make two nearby
    # heat inputs converge to IDENTICAL outputs (observed: seeds 1 and 2
    # do), and swapping equal outputs would be no tamper at all
    flipped = dict(fields[0])
    first = "0" if flipped["output"][0] != "0" else "f"
    flipped["output"] = first + flipped["output"][1:]
    with pytest.raises(EngineIdentityMismatch):
        _check_result(specs[0], flipped)
    with pytest.raises(EngineIdentityMismatch):
        _check_result(specs[0], flipped, precomputed=(
            specs[0].identity(), specs[0].program_identity(),
            specs[0].input_identity()))


def test_digest_reuse_never_collapses_operations():
    """[A, A, A, B]: the duplicates share digest COMPUTATION and
    therefore computation identity (content), while remaining three
    executed operations with distinct occurrences -- reuse of work,
    never of operations."""
    a, b = _heat(1), _heat(2)
    batch = run_specifications([a, a, a, b])
    assert len({r.computation_identity for r in batch[:3]}) == 1
    assert [r.engine_occurrence for r in batch] == [0, 1, 2, 3]
    assert batch[3].computation_identity != batch[0].computation_identity
