"""Content-locked file scopes for external agent hosts; never execute or apply code.

A passing scope check means only that a candidate changed permitted paths within
limits. It is NOT quality acceptance, a sandbox, a signature or merge permission.
"""
from __future__ import annotations
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
import os
import stat

from .control_contracts import _base, bytes_ref, content_ref, detached, keys, save_new, text
from .core.identities import content_identity
from .operations.runner import seal

MAX_FILES = 1024
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_CONTEXT = 64 * 1024
IGNORED = frozenset({".git", ".godot", "__pycache__", ".pytest_cache"})
SENSITIVE = frozenset({".env", ".ssh", ".aws", ".gnupg", "credentials.json", "id_rsa", "id_ed25519"})


def relative(name: str) -> str:
    text(name)
    if "\\" in name or ":" in name or name.startswith("/"):
        raise ValueError("Require a portable relative POSIX path")
    p = PurePosixPath(name)
    if str(p) != name or not p.parts or any(part in {".", ".."} for part in p.parts):
        raise ValueError("Noncanonical or escaping path")
    reserved = {"CON", "PRN", "AUX", "NUL", *{f"COM{i}" for i in range(1, 10)}, *{f"LPT{i}" for i in range(1, 10)}}
    for part in p.parts:
        if (part.rstrip(" .") != part or part.split(".")[0].upper() in reserved
                or any(ord(c) < 32 for c in part) or any(c in part for c in '*?[]<>|"')):
            raise ValueError("Ambiguous or nonportable path")
        if part in IGNORED or part in SENSITIVE or part.startswith(".env."):
            raise ValueError("Cache, repository internals or secret-bearing paths are not packet inputs")
    return name


def root_dir(path: Path) -> Path:
    path = Path(path).expanduser().absolute()
    # This boundary rejects linked roots and linked parents, not just linked children.
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlinked roots or parents are not admitted")
    if not path.is_dir():
        raise ValueError("Require an existing operator-selected directory")
    return path.resolve(strict=True)


def read_file(root: Path, name: str) -> bytes:
    path = root / relative(name)
    for p in (path, *path.parents):
        if p == root:
            break
        if p.is_symlink():
            raise ValueError("Symlinks are not admitted")
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Only ordinary non-hardlinked files are admitted")
    if info.st_size > MAX_FILE:
        raise ValueError("Source file exceeds byte limit")
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise ValueError("Source changed beyond byte limit")
    return raw


def inventory(path: Path) -> dict:
    root = root_dir(path)
    files, total, seen, directories = {}, 0, set(), 0
    for directory, names, leaves in os.walk(root, followlinks=False):
        directories += 1
        if directories > 4096:
            raise ValueError("Directory budget exceeded")
        names[:] = sorted(n for n in names if n not in IGNORED)
        for name in names:
            entry = Path(directory) / name
            relative(entry.relative_to(root).as_posix())
            if entry.is_symlink():
                raise ValueError("Linked source directory is not admitted")
        for name in sorted(leaves):
            if name in IGNORED:
                continue
            rel = relative((Path(directory) / name).relative_to(root).as_posix())
            if rel.casefold() in seen:
                raise ValueError("Case-colliding source paths")
            seen.add(rel.casefold())
            raw = read_file(root, rel)
            total += len(raw)
            if len(files) >= MAX_FILES or total > MAX_TOTAL:
                raise ValueError("Source inventory budget exceeded")
            files[rel] = {"sha256": bytes_ref(raw), "bytes": len(raw),
                          "executable": bool((root / rel).stat().st_mode & 0o111)}
    if not files:
        raise ValueError("Source inventory is empty")
    result = {"schema": "ciw.foundry-file-inventory.v1", "files": dict(sorted(files.items()))}
    result["inventory_id"] = content_identity(result)
    return result


def validate_inventory(value: dict) -> None:
    keys(value, {"schema", "files", "inventory_id"})
    if value["schema"] != "ciw.foundry-file-inventory.v1" or type(value["files"]) is not dict or not 1 <= len(value["files"]) <= MAX_FILES:
        raise ValueError("Invalid file inventory")
    total, seen = 0, set()
    for path, spec in value["files"].items():
        relative(path)
        if path.casefold() in seen:
            raise ValueError("Case-colliding inventory")
        seen.add(path.casefold())
        keys(spec, {"sha256", "bytes", "executable"}); content_ref(spec["sha256"])
        if type(spec["executable"]) is not bool:
            raise ValueError("Invalid executable-mode declaration")
        if type(spec["bytes"]) is not int or not 0 <= spec["bytes"] <= MAX_FILE:
            raise ValueError("Invalid source byte count")
        total += spec["bytes"]
    if total > MAX_TOTAL or value["inventory_id"] != content_identity({k: v for k, v in value.items() if k != "inventory_id"}):
        raise ValueError("Inventory integrity or size mismatch")


def changes(before: dict, after: dict) -> list[dict]:
    validate_inventory(before); validate_inventory(after)
    return [{"path": p, "change": "added" if p not in before["files"] else "removed" if p not in after["files"] else "modified"}
            for p in sorted(set(before["files"]) | set(after["files"]))
            if before["files"].get(p) != after["files"].get(p)]


def protected(path: str, baseline: dict) -> bool:
    parts = tuple(p.lower() for p in PurePosixPath(relative(path)).parts)
    return (parts[0] in {".github", "foundry"} or parts[-1] in {"project.godot", ".gitattributes", ".gitignore"}
            or parts[-1].upper().startswith(("LICENSE", "COPYING", "NOTICE"))
            or (parts[0] in {"tests", "test", "schemas"} and path in baseline["files"]))


def make_packet(project: dict, task: dict, source_root: Path, *, writable: list[str], context: list[str],
                assignee: str, max_changed_bytes: int = 131072) -> dict:
    if inventory(source_root) != project["baseline"]:
        raise ValueError("Source drift: create a new explicit project baseline before assigning work")
    text(assignee)
    if type(writable) is not list or type(context) is not list or len(writable) > 32 or len(context) > 32:
        raise ValueError("Packet paths exceed bound")
    if len(set(writable)) != len(writable) or len(set(context)) != len(context):
        raise ValueError("Duplicate packet paths")
    if type(max_changed_bytes) is not int or not 1 <= max_changed_bytes <= 512 * 1024:
        raise ValueError("Changed-byte budget must be 1..524288")
    for path in writable:
        if protected(path, project["baseline"]):
            raise ValueError("Cannot grant agent writes to original tests, runtime entrypoint, policy or license paths")
    if task["completion"] == "native_foundry" and writable:
        raise ValueError("The installed qualification task is read-only; candidate code needs separate reviewed revision")
    source_root = root_dir(source_root)
    snippets, total = {}, 0
    for path in context:
        raw = read_file(source_root, path)
        if bytes_ref(raw) != project["baseline"]["files"].get(path, {}).get("sha256"):
            raise ValueError("Context changed while assembling packet")
        if len(raw) > MAX_CONTEXT:
            raise ValueError("Context file too large; select a smaller explicit input")
        total += len(raw)
        if total > 512 * 1024:
            raise ValueError("Context exceeds packet budget")
        snippets[path] = raw.decode("utf-8")
    # Recheck the non-atomic directory read before returning a declaration.
    if inventory(source_root) != project["baseline"]:
        raise ValueError("Source changed during packet construction")
    return seal({"schema": "ciw.foundry-agent-packet.v1", "project_digest": project["record_digest"],
        "task_id": task["task_id"], "task_digest": content_identity(task), "assignee": assignee,
        "baseline": detached(project["baseline"]), "writable": sorted(writable), "context": snippets,
        "max_changed_bytes": max_changed_bytes, "acceptance": task["acceptance"],
        "rights": {"execute": False, "approve": False, "merge": False, "release": False},
        "scope": "candidate authoring in external host; no model invocation or sandbox"})


def validate_packet(packet: dict, project: dict, task: dict) -> None:
    _base(packet, "foundry-agent-packet", {"project_digest", "task_id", "task_digest", "assignee", "baseline", "writable", "context", "max_changed_bytes", "acceptance", "rights", "scope"})
    validate_inventory(packet["baseline"])
    if (packet["project_digest"] != project["record_digest"] or packet["baseline"] != project["baseline"]
        or packet["task_id"] != task["task_id"] or packet["task_digest"] != content_identity(task)
        or packet["acceptance"] != task["acceptance"]
        or packet["rights"] != {"execute": False, "approve": False, "merge": False, "release": False}):
        raise ValueError("Packet changed project, acceptance or authority")
    text(packet["assignee"])
    if type(packet["max_changed_bytes"]) is not int or not 1 <= packet["max_changed_bytes"] <= 524288:
        raise ValueError("Invalid packet budget")
    allow = packet["writable"]
    if type(allow) is not list or len(allow) > 32 or len(set(allow)) != len(allow):
        raise ValueError("Invalid write allowlist")
    for path in allow:
        if protected(path, packet["baseline"]):
            raise ValueError("Packet grants a protected write")
    if task["completion"] == "native_foundry" and allow:
        raise ValueError("Native qualification packet must be read-only")
    if type(packet["context"]) is not dict or len(packet["context"]) > 32:
        raise ValueError("Invalid packet context")
    total = 0
    for path, value in packet["context"].items():
        relative(path)
        if type(value) is not str:
            raise ValueError("Context must be text")
        raw = value.encode("utf-8"); total += len(raw)
        if len(raw) > MAX_CONTEXT or bytes_ref(raw) != packet["baseline"]["files"].get(path, {}).get("sha256"):
            raise ValueError("Context does not match locked bytes")
    if total > 512 * 1024:
        raise ValueError("Context budget exceeded")


def check_candidate(packet: dict, project: dict, task: dict, candidate_root: Path, *, expected_packet_id: str) -> dict:
    content_ref(expected_packet_id)
    if packet.get("record_digest") != expected_packet_id:
        raise ValueError("Packet differs from the operator-retained packet identity")
    validate_packet(packet, project, task)
    actual = inventory(candidate_root)
    diff = changes(packet["baseline"], actual)
    forbidden = [d["path"] for d in diff if d["path"] not in packet["writable"]]
    byte_count = sum(actual["files"].get(d["path"], {}).get("bytes", 0) for d in diff)
    return seal({"schema": "ciw.foundry-candidate-scope.v1", "packet_digest": packet["record_digest"],
        "candidate_inventory_id": actual["inventory_id"], "changes": diff, "out_of_scope": forbidden,
        "changed_bytes": byte_count, "status": "scope_passed" if not forbidden and byte_count <= packet["max_changed_bytes"] else "scope_refused",
        "quality_acceptance": "not_performed", "executed": False, "publication": "not_performed"})


def compatible_wave(packets: list[dict]) -> dict:
    """Report conflicts only; this is not a parallel executor or a lock/lease service."""
    if not 1 <= len(packets) <= 16:
        raise ValueError("Require 1..16 validated packets")
    conflicts = []
    for i, left in enumerate(packets):
        for right in packets[i+1:]:
            writes = set(left["writable"]) & set(right["writable"])
            # Any write to a baseline input invalidates another packet's locked snapshot.
            reads = (set(left["writable"]) & set(right["baseline"]["files"])) | (set(right["writable"]) & set(left["baseline"]["files"]))
            if writes or reads:
                conflicts.append({"left": left["task_id"], "right": right["task_id"],
                                  "write_write": sorted(writes), "write_read": sorted(reads)})
    return {"schema": "ciw.foundry-packet-conflicts.v1", "conflicts": conflicts,
            "parallel_execution": "not_performed", "scope": "isolated candidate generation possible; integration must rebase and requalify conflicts"}
