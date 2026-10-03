"""Opaque provider-owned checkpoint seam. No new engine or simulation Session."""
from __future__ import annotations

from typing import Protocol

from .control_contracts import _base, bytes_ref, content_ref, detached, keys, number, record, text


class CheckpointProvider(Protocol):
    def identity(self) -> dict: ...
    def snapshot(self) -> bytes: ...
    def restore(self, snapshot: bytes) -> None: ...
    def step(self, dt: float) -> None: ...
    def observe(self) -> dict: ...


def _identity(value: dict) -> None:
    keys(value, {"runtime", "model_id", "simulation_id", "owner_id", "state_revision", "clock"})
    if type(value["runtime"]) is not dict or not value["runtime"]:
        raise ValueError("Provider must declare runtime identity")
    for key in ("model_id", "simulation_id", "owner_id"):
        text(value[key])
    if type(value["state_revision"]) is not int or value["state_revision"] < 0:
        raise ValueError("Provider must expose a nonnegative state revision")
    keys(value["clock"], {"id", "time_s"})
    text(value["clock"]["id"])
    number(value["clock"]["time_s"])
    detached(value)


def capture_checkpoint(provider: CheckpointProvider, *, experiment_id: str) -> tuple[dict, bytes]:
    """Explicitly invoke snapshot; the provider remains responsible for atomic state capture."""
    before = detached(provider.identity())
    _identity(before)
    payload = provider.snapshot()
    if type(payload) is not bytes or len(payload) > 64 * 1024 * 1024:
        raise ValueError("Provider snapshot must be bounded exact bytes")
    if before != provider.identity():
        raise ValueError("Provider changed while snapshot was being captured")
    checkpoint = record("checkpoint", experiment_id=text(experiment_id), provider=before,
                        sha256=bytes_ref(payload), size_bytes=len(payload))
    return checkpoint, payload


def validate_checkpoint(value: dict, payload: bytes | None = None) -> None:
    _base(value, "checkpoint", {"experiment_id", "provider", "sha256", "size_bytes"})
    text(value["experiment_id"])
    _identity(value["provider"])
    content_ref(value["sha256"])
    if type(value["size_bytes"]) is not int or not 0 <= value["size_bytes"] <= 64 * 1024 * 1024:
        raise ValueError("Checkpoint size exceeds budget")
    if payload is not None and (bytes_ref(payload) != value["sha256"] or len(payload) != value["size_bytes"]):
        raise ValueError("Checkpoint payload digest/size mismatch")


def restore_checkpoint(provider: CheckpointProvider, checkpoint: dict, payload: bytes) -> dict:
    """Only an explicitly supplied fresh owner can restore matching opaque bytes.

    This is a provider hook, not a CLI loader, distributed lease or transactional
    engine rollback. A failed provider restore must be discarded by its owner.
    """
    checkpoint = detached(checkpoint)
    validate_checkpoint(checkpoint, payload)
    target = detached(provider.identity())
    _identity(target)
    source = checkpoint["provider"]
    for key in ("runtime", "model_id", "simulation_id"):
        if target[key] != source[key]:
            raise ValueError(f"Checkpoint {key} differs from explicitly supplied provider")
    if (target["clock"]["id"] != source["clock"]["id"] or target["owner_id"] == source["owner_id"]
            or target["state_revision"] != 0):
        raise ValueError("Checkpoint restore requires a fresh owner on the declared clock")
    provider.restore(payload)
    restored = detached(provider.identity())
    _identity(restored)
    for key in ("runtime", "model_id", "simulation_id", "owner_id"):
        if restored[key] != target[key]:
            raise ValueError("Provider changed identity during restore; discard this target")
    if restored["clock"] != source["clock"]:
        raise ValueError("Provider did not restore the checkpoint clock; discard this target")
    return restored
