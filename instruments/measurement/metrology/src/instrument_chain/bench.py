"""Scripted displacement session. Host stand-in for the first wired prototype.

This is not firmware. It produces the same observation objects the firmware
contract must emit so replay tests can run without the board.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .manifest import Assembly, Calibration
from .observation import Observation, acquire_or_unavailable
from .receiver import receive
from .transport import Outbox, deliver


@dataclass
class Session:
    assembly: Assembly
    session_id: str
    sequence: int = 0
    ticks: int = 0
    connected: bool = True
    last_raw: float | None = None
    outbox: Outbox | None = None

    def step(self, raw: float | None, *, ticks: int = 1000) -> Observation:
        self.sequence += 1
        self.ticks += ticks
        if self.connected and raw is not None:
            self.last_raw = raw
        sample = raw if self.connected else None
        obs = acquire_or_unavailable(
            assembly=self.assembly,
            session_id=self.session_id,
            sequence=self.sequence,
            device_ticks=self.ticks,
            raw=sample,
            connected=self.connected,
        )
        return obs

    def with_calibration(self, calibration: Calibration) -> Session:
        """New measurements identify the new calibration. History is not rewritten."""
        return replace(self, assembly=replace(self.assembly, calibration=calibration, version=self.assembly.version + "+recal"))


def run_bidirectional_pass(session: Session, positions_raw: list[float], log_path) -> list[Observation]:
    records = []
    outbox = session.outbox or Outbox()
    session.outbox = outbox
    for raw in positions_raw:
        obs = session.step(raw)
        delivery = deliver(outbox, obs)
        receive(log_path, obs, delivery)
        records.append(obs)
    return records
