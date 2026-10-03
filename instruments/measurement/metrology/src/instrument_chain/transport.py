"""Delivery is not a new observation. A retry keeps the same observation_id."""

from __future__ import annotations

from dataclasses import dataclass, field

from .observation import Observation


@dataclass
class Delivery:
    observation_id: str
    packet_id: int
    attempt: int
    acknowledged: bool
    admitted: bool


@dataclass
class Outbox:
    next_packet: int = 1
    history: list[Delivery] = field(default_factory=list)
    by_observation: dict[str, list[Delivery]] = field(default_factory=dict)

    def send(self, observation: Observation, *, acknowledged: bool = True, admitted: bool = True) -> Delivery:
        delivery = Delivery(
            observation_id=observation.observation_id,
            packet_id=self.next_packet,
            attempt=len(self.by_observation.get(observation.observation_id, [])) + 1,
            acknowledged=acknowledged,
            admitted=admitted,
        )
        self.next_packet += 1
        self.history.append(delivery)
        self.by_observation.setdefault(observation.observation_id, []).append(delivery)
        return delivery

    def retransmit(self, observation: Observation, *, acknowledged: bool = True, admitted: bool = True) -> Delivery:
        """Same observation, new packet. Broker ACK is not PayloadOS admission."""
        return self.send(observation, acknowledged=acknowledged, admitted=admitted)


def deliver(outbox: Outbox, observation: Observation, *, retry: bool = False) -> Delivery:
    if retry:
        return outbox.retransmit(observation)
    return outbox.send(observation)
