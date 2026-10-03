"""Bind an RCI digest or field record. Do not interpret the sample."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from ..ir import Node, NodeKind, Schematic, Status
from ..kernels import KernelEvent
from ..pins import RCI

CHAIN = ("board", "interface", "instrument", "installation")
QUALITY = ("acquisition", "timing", "calibration", "inference")
FORBIDDEN_QUALITY = {"GOOD", "good", "ok", "OK"}
QUALITY_ALIASES = {
    "sample received": "received", "received": "received", "unavailable": "unavailable",
    "overrange": "overrange", "corrupt": "corrupt",
    "device clock at readout": "device_clock", "device_clock": "device_clock",
    "readout only": "readout_only", "readout_only": "readout_only", "unknown": "unknown",
    "applicable": "applicable", "unsupported range": "unsupported_range", "unsupported_range": "unsupported_range",
    "changed installation": "changed_installation", "none": "none",
    "not run": "not_run", "not_run": "not_run", "observer updated": "updated", "updated": "updated",
    "predicted": "prediction_only", "prediction_only": "prediction_only",
}


class RciUnavailable(RuntimeError):
    pass


def load_instrument_chain() -> Any:
    try:
        return import_module(str(RCI["import"]))
    except ImportError as exc:
        raise RciUnavailable(f"{RCI['import']} is not installed; pin {RCI['repo']}@{RCI['sha']}") from exc


def bind_digest(schematic: Schematic, measurement_id: str, digest: str) -> KernelEvent:
    node = schematic.node(measurement_id)
    if node.kind is not NodeKind.MEASUREMENT:
        return KernelEvent(tool="rci.bind", owner="rci", node_id=measurement_id, result=Status.REFUSED, detail={"reason": f"{measurement_id} is not a measurement"})
    if not digest or digest.startswith("interpret:"):
        return KernelEvent(tool="rci.bind", owner="rci", node_id=measurement_id, result=Status.REFUSED, detail={"reason": "digest empty or trying to smuggle an interpretation"})
    attrs = dict(node.attrs)
    attrs["rci_digest"] = digest
    if attrs.get("quality") == "undeclared":
        attrs["quality"] = "bound"
    schematic.replace(Node(id=node.id, kind=node.kind, attrs=attrs))
    return KernelEvent(tool="rci.bind", owner="rci", node_id=measurement_id, result=Status.SAMPLED, detail={"rci_digest": digest, "interpreted": False, "pin": RCI})


def _canonical_quality(quality: dict[str, Any]) -> dict[str, str] | str:
    out: dict[str, str] = {}
    for key in QUALITY:
        raw = str(quality.get(key, "")).strip().lower()
        canon = QUALITY_ALIASES.get(raw)
        if canon is None:
            return f"unknown {key} status {quality.get(key)!r}"
        out[key] = canon
    if out["inference"] in {"updated", "prediction_only"}:
        return "inference does not belong on the measurement record"
    return out


def bind_record(schematic: Schematic, measurement_id: str, record: dict[str, Any]) -> KernelEvent:
    node = schematic.node(measurement_id)
    if node.kind is not NodeKind.MEASUREMENT:
        return KernelEvent(tool="rci.bind_record", owner="rci", node_id=measurement_id, result=Status.REFUSED, detail={"reason": "not a measurement", "pin": RCI})
    if record.get("as_state") or record.get("promote_to_state"):
        return KernelEvent(tool="rci.bind_record", owner="rci", node_id=measurement_id, result=Status.REFUSED, detail={"reason": "refused promotion of a sample to a state", "pin": RCI})
    missing = [key for key in CHAIN if not str(record.get(key) or "").strip()]
    if missing:
        return KernelEvent(tool="rci.bind_record", owner="rci", node_id=measurement_id, result=Status.REFUSED, detail={"reason": f"incomplete chain: {missing}", "pin": RCI})
    quality = record.get("quality")
    if isinstance(quality, str) and quality in FORBIDDEN_QUALITY:
        return KernelEvent(tool="rci.bind_record", owner="rci", node_id=measurement_id, result=Status.REFUSED, detail={"reason": "one GOOD flag is forbidden", "pin": RCI})
    if not isinstance(quality, dict) or any(k not in quality for k in QUALITY):
        return KernelEvent(tool="rci.bind_record", owner="rci", node_id=measurement_id, result=Status.REFUSED, detail={"reason": f"quality must declare {list(QUALITY)}", "pin": RCI})
    canon = _canonical_quality(quality)
    if isinstance(canon, str):
        return KernelEvent(tool="rci.bind_record", owner="rci", node_id=measurement_id, result=Status.REFUSED, detail={"reason": canon, "pin": RCI})
    contract = "local"
    try:
        chain = load_instrument_chain()
        contract = f"{RCI['repo']}@{RCI['sha']}"
        _ = chain.Quality
    except RciUnavailable:
        pass
    attrs = dict(node.attrs)
    for key in CHAIN:
        attrs[key] = record[key]
    attrs["quality"] = canon
    if record.get("rci_digest"):
        attrs["rci_digest"] = record["rci_digest"]
    attrs["record_kind"] = "rci.field"
    attrs["rci_contract"] = contract
    schematic.replace(Node(id=node.id, kind=node.kind, attrs=attrs))
    return KernelEvent(tool="rci.bind_record", owner="rci", node_id=measurement_id, result=Status.SAMPLED, detail={"chain": list(CHAIN), "interpreted": False, "contract": contract, "pin": RCI})
