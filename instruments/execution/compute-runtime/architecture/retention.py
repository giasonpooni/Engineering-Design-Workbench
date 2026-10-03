"""Agent-execution retention: the mitigation for
`no_reproducible_agent_execution`.

Hosted agent executions cannot be re-executed after a vendor retires a
snapshot -- but AUDITABILITY is not re-executability, and the record
below preserves the auditable half completely: which binding ran, under
which doctrine, on which input, producing which output, when, in which
lineage. Every field is mandatory at construction (fail closed);
`snapshot_identity` alone admits the explicit "unavailable" the hosted
world forces, and admits it VISIBLY.

No live agent-execution path exists in this repository (inspected); the
record is the boundary that path must construct when it exists, and the
tests exercise it with synthetic executions so the contract is
executable now, not aspirational.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


class RetentionError(ValueError):
    """An agent execution missing its audit record is refused."""


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class AgentExecutionRecord:
    """The complete audit record for one hosted agent execution."""

    binding_id: str
    snapshot_identity: str       # vendor snapshot id, or "unavailable"
    adapter_version: str
    doctrine_hash: str           # sha256 of the generated doctrine served
    effective_prompt: str
    input_fingerprint: str       # sha256 of the input payload
    raw_output: str
    output_fingerprint: str      # sha256 of raw_output
    executed_at: str             # RFC3339; audit metadata, not identity
    lineage: str                 # which chain of proposals/roles produced this

    def __post_init__(self):
        required = {
            "binding_id": self.binding_id,
            "snapshot_identity": self.snapshot_identity,
            "adapter_version": self.adapter_version,
            "doctrine_hash": self.doctrine_hash,
            "effective_prompt": self.effective_prompt,
            "input_fingerprint": self.input_fingerprint,
            "executed_at": self.executed_at,
            "lineage": self.lineage,
        }
        empty = [name for name, value in required.items() if not value]
        if empty:
            raise RetentionError(
                f"agent execution record is missing {empty}; an execution "
                f"without its audit record is refused"
            )
        if self.output_fingerprint != fingerprint(self.raw_output.encode()):
            raise RetentionError(
                "output_fingerprint does not match raw_output; the record "
                "does not describe the execution it claims to"
            )
