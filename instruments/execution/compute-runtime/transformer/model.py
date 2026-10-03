"""AttentionModel: the model-computation layer, lowered into the
unchanged STE execution boundary.

IDENTITY SEPARATION, exactly as the unified directive requires:

    model identity          commit over (d, Wq, Wk, Wv) -- the weights
    representation identity the typed tokens (representation.py)
    spec identity           program + configuration + input (STE, unchanged)
    computation identity    program + input + output + exit (STE, unchanged)
    operation identity      trace occurrences (STE, unchanged)
    verification identity   proof/warrant machinery (STE, unchanged)

The model's parameters travel INSIDE the specification's input payload
(the kernel consumes [X | Wq | Wk | Wv]), so the spec identity covers
model+data jointly -- which is exactly right: a different model IS a
different computation. The model identity exists BESIDE that, at this
layer, so campaigns can ask "same model, different inputs" without a
transformer-specific identity namespace leaking downward.

There is no proving path for this kernel yet: the stage-5 registry gate
refuses attributably (no guest is registered), which is the honest
state, locked by test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from execution.commitments import commit_hex
from execution.engine import ExecutionResult, run_specification, run_specifications
from execution.specification import (
    HARDMAX_ATTENTION_DESCRIPTOR,
    ExecutionSpecification,
    encode_attention_input,
)
from transformer.prediction import Prediction
from transformer.representation import TransformerRepresentation

MODEL_TAG = "ste.transformer.model.v1"

_VALUE_BOUND = 1 << 20


@dataclass(frozen=True)
class AttentionModel:
    """Single-head hardmax attention: three d*d integer projection
    matrices. Frozen; content-addressed."""

    wq: Tuple[Tuple[int, ...], ...]
    wk: Tuple[Tuple[int, ...], ...]
    wv: Tuple[Tuple[int, ...], ...]

    def __post_init__(self):
        d = len(self.wq)
        for name, w in (("wq", self.wq), ("wk", self.wk), ("wv", self.wv)):
            if len(w) != d or any(len(row) != d for row in w):
                raise ValueError(f"{name} is not a {d}x{d} matrix")
            if any(abs(v) > _VALUE_BOUND for row in w for v in row):
                raise ValueError(f"{name} exceeds the kernel's |v| <= 2^20 bound")

    @property
    def d(self) -> int:
        return len(self.wq)

    def model_identity(self) -> str:
        canonical = f"d={self.d}|" + "|".join(
            ",".join(str(v) for row in w for v in row)
            for w in (self.wq, self.wk, self.wv))
        return commit_hex(MODEL_TAG, [canonical.encode()])

    def forward_spec(self, representation: TransformerRepresentation) -> ExecutionSpecification:
        """The lowering: representation + model -> the execution request
        the unchanged engine runs."""
        if representation.d != self.d:
            raise ValueError(
                f"representation dimension {representation.d} does not match "
                f"model dimension {self.d}"
            )
        payload = encode_attention_input(
            self.d, [list(row) for row in representation.tensor()],
            [list(r) for r in self.wq], [list(r) for r in self.wk],
            [list(r) for r in self.wv])
        return ExecutionSpecification(HARDMAX_ATTENTION_DESCRIPTOR, b"", payload)

    def forward(self, representation: TransformerRepresentation) -> Prediction:
        """One model computation through the STE boundary. A halted
        execution raises -- a fault is a refusal, never a prediction."""
        spec = self.forward_spec(representation)
        result: ExecutionResult = run_specification(spec)
        return self._prediction_from(representation, spec, result)

    def forward_batch(self, representations) -> "tuple[Prediction, ...]":
        """B independent forwards through ONE engine process -- the
        batched execution contract. Each representation lowers to its
        own specification; the engine answers B blocks in request order;
        every constituent keeps its own spec/computation identity and
        occurrence. Semantics per item are IDENTICAL to `forward` --
        including refusal: any halted item raises, naming its index (a
        fault is never a prediction), after the whole batch's results
        are attributable."""
        representations = tuple(representations)
        if not representations:
            raise ValueError("an empty batch is refused")
        specs = [self.forward_spec(rep) for rep in representations]
        results = run_specifications(specs)
        for at, result in enumerate(results):
            if result.status != "completed":
                raise RuntimeError(
                    f"batch item {at}: model computation halted "
                    f"(exit {result.exit_code}); no prediction exists"
                )
        return tuple(
            self._prediction_from(rep, spec, result)
            for rep, spec, result in zip(representations, specs, results)
        )

    def _prediction_from(
        self,
        representation: TransformerRepresentation,
        spec: ExecutionSpecification,
        result: ExecutionResult,
    ) -> Prediction:
        if result.status != "completed":
            raise RuntimeError(
                f"model computation halted (exit {result.exit_code}); "
                f"no prediction exists"
            )
        n, d = len(representation.tokens), self.d
        values = tuple(
            tuple(int.from_bytes(result.output[8 * (i * d + k):8 * (i * d + k) + 8],
                                 "little", signed=True) for k in range(d))
            for i in range(n))
        return Prediction(
            model_identity=self.model_identity(),
            representation_identity=representation.identity(),
            specification_identity=spec.identity(),
            values=values,
            uncertainty_kind="absent",
        )


def reference_attention(tokens, wq, wk, wv):
    """The pure-Python reference implementation for numerical-agreement
    tests: the descriptor's semantics, independently."""
    d = len(wq)

    def project(row, w):
        return [sum(row[j] * w[j][k] for j in range(d)) for k in range(d)]

    q = [project(t, wq) for t in tokens]
    k = [project(t, wk) for t in tokens]
    v = [project(t, wv) for t in tokens]
    out = []
    for i in range(len(tokens)):
        scores = [sum(q[i][a] * k[j][a] for a in range(d)) for j in range(len(tokens))]
        best = max(range(len(tokens)), key=lambda j: (scores[j], -j))
        out.append(tuple(v[best]))
    return tuple(out)
