"""Prediction: a computational result -- never evidence.

The prediction names everything it depends on (model, representation,
specification identities) and carries an EXPLICIT uncertainty posture
(`prediction_carries_uncertainty`: "absent" is a declared fact, and a
prediction without calibrated uncertainty is inadmissible for canonical
assertion under the architecture's evidence-class invariants). There is
no conversion from this type to an Observation anywhere in this
package: re-entering evidence goes through validation, admissibility,
and acquisition -- the loop's return edge -- exactly like every other
derived result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

UNCERTAINTY_KINDS = ("stated", "estimated", "propagated", "absent")


@dataclass(frozen=True)
class Prediction:
    model_identity: str
    representation_identity: str
    specification_identity: str
    values: Tuple[Tuple[int, ...], ...]
    uncertainty_kind: str

    def __post_init__(self):
        if self.uncertainty_kind not in UNCERTAINTY_KINDS:
            raise ValueError(
                f"uncertainty_kind {self.uncertainty_kind!r} must be one of "
                f"{UNCERTAINTY_KINDS} -- explicit, never implied"
            )
        if not (self.model_identity and self.representation_identity
                and self.specification_identity):
            raise ValueError("a prediction names everything it depends on")
