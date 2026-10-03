"""Laptop receiver: durable log keyed by observation identity."""

from __future__ import annotations

import json
from pathlib import Path

from .digest import observation_digest
from .observation import Observation
from .transport import Delivery


def receive(path: str | Path, observation: Observation, delivery: Delivery | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = observation.as_dict()
    record["digest"] = observation_digest(observation)
    if delivery is not None:
        record["delivery"] = {
            "packet_id": delivery.packet_id,
            "attempt": delivery.attempt,
            "acknowledged": delivery.acknowledged,
            "admitted": delivery.admitted,
        }
    existing = replay(path)
    by_id = {item["observation_id"]: item for item in existing}
    # A retry updates delivery history; it does not append a second physical sample.
    if observation.observation_id in by_id:
        prior = by_id[observation.observation_id]
        prior_attempts = list(prior.get("delivery_history", []))
        if "delivery" in prior and prior["delivery"] not in prior_attempts:
            prior_attempts.append(prior["delivery"])
        if delivery is not None:
            prior_attempts.append(record["delivery"])
        prior["delivery_history"] = prior_attempts
        if delivery is not None:
            prior["delivery"] = record["delivery"]
        _rewrite(path, list(by_id.values()))
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def replay(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _rewrite(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
