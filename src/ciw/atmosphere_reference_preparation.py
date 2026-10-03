"""Create and check retained data-only atmospheric measurement preparations.

The receipt binds corrected SI input to reference artifacts. It is configuration
integrity, not a scientific execution, verification or admission record.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import stat

from .atmosphere_cli import _regular_bytes
from .atmosphere_measurement_ingress import prepare, validate_preparation
from .control_contracts import MAX_BYTES, json_tree, save_new
from .operations.runner import digest
from .session import loads_json

FILES = frozenset({"measurements.csv", "declaration.json", "reference.json",
                   "policy.json", "preparation.json"})


def _json(raw: bytes) -> dict:
    value = loads_json(raw.decode("utf-8"))
    json_tree(value)
    if not isinstance(value, dict):
        raise ValueError("Preparation documents must be JSON objects")
    return value


def _summary(preparation: dict, *, status: str, fresh: bool) -> dict:
    return {
        "schema": "ciw.atmosphere-reference-preparation-inspection.v1",
        "status": status, "fresh_mapping_check": fresh,
        "reference_digest": preparation["reference"]["record_digest"],
        "policy_digest": preparation["policy"]["record_digest"],
        **{key: preparation[key] for key in (
            "reference_evidence_id", "csv_content_digest", "declaration_digest",
            "observation_count", "scalar_count")},
        "authority": deepcopy(preparation["authority"]),
    }


def prepare_files(csv_path: Path, declaration_path: Path, destination: Path) -> dict:
    """Validate all inputs before creating a new, never-overwritten bundle."""
    raw = _regular_bytes(Path(csv_path))
    declaration = _json(_regular_bytes(Path(declaration_path)))
    preparation = prepare(raw, declaration)
    documents = {
        "declaration.json": declaration, "reference.json": preparation["reference"],
        "policy.json": preparation["policy"], "preparation.json": preparation,
    }
    # Serialize and bound every output before creating any destination directory.
    for value in documents.values():
        json_tree(value)
        encoded = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")
        if len(encoded) > MAX_BYTES:
            raise ValueError("Prepared document exceeds the 8 MiB budget")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / "measurements.csv").open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    for name, value in documents.items():
        save_new(destination / name, value)
    return _summary(preparation, status="prepared", fresh=False)


def _read_preparation(directory: Path) -> tuple[bytes, dict, dict]:
    """Read one bounded snapshot; static validation does not replay CSV mapping."""
    directory = Path(directory)
    initial = directory.lstat()
    if not stat.S_ISDIR(initial.st_mode):
        raise ValueError("Preparation must be a directory without symlinks")
    if {path.name for path in directory.iterdir()} != FILES:
        raise ValueError("Preparation must contain exactly its five declared files")
    # Preflight the whole tree before reading any content, rejecting special files.
    for name in FILES:
        metadata = (directory / name).lstat()
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= MAX_BYTES:
            raise ValueError("Preparation artifacts must be bounded regular files without symlinks")
    contents = {name: _regular_bytes(directory / name) for name in sorted(FILES)}
    final = directory.lstat()
    if (not stat.S_ISDIR(final.st_mode)
            or (initial.st_dev, initial.st_ino) != (final.st_dev, final.st_ino)
            or {path.name for path in directory.iterdir()} != FILES):
        raise ValueError("Preparation directory changed during inspection")
    raw, declaration = contents["measurements.csv"], _json(contents["declaration.json"])
    preparation = validate_preparation(raw, declaration, _json(contents["preparation.json"]))
    for name, key in (("reference.json", "reference"), ("policy.json", "policy")):
        if digest(_json(contents[name])) != digest(preparation[key]):
            raise ValueError("Exported preparation artifact differs from its retained receipt")
    return raw, declaration, preparation


def inspect_preparation(directory: Path) -> dict:
    """Check retained content and declarations without remapping measurements."""
    _, _, preparation = _read_preparation(directory)
    return _summary(preparation, status="retained", fresh=False)


def verify_preparation(directory: Path) -> dict:
    """Freshly remap the retained CSV snapshot, without invoking physics providers."""
    raw, declaration, preparation = _read_preparation(directory)
    fresh = prepare(raw, declaration)
    if digest(fresh) != digest(preparation):
        raise ValueError("Retained reference preparation differs from a fresh CSV mapping")
    return _summary(preparation, status="checked", fresh=True)
