"""Operator-bound, closed-source Godot domain worker for the Foundry workload.

This is a disposable project directory, NOT an OS/container/network sandbox.
Only trusted, operator-selected source and executable bytes may be bound.
Game code stays in its own repository and retains its own licence.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import platform
import tempfile

from .control_contracts import bytes_ref, content_ref, keys, save_new
from .core.identities import content_identity
from .interactive_simulation import file_sha, run_process

PROFILE = "1792.water-round.v1"
ENTRYPOINT = "foundry/water_round.gd"
FILES = ("characters/character_names.gd", "childhood/aftermath_state.gd",
         "childhood/childhood_state.gd", "mounts/riding_rules.gd",
         "patrol/companion_rules.gd", "territory/gujranwala_state.gd",
         "territory/misl_rules.gd", "territory/water_round_rules.gd",
         "tests/aftermath_fixture.gd", "tests/gujranwala_fixture.gd", ENTRYPOINT)
PROJECT = b'config_version=5\n[application]\nconfig/name="NET Foundry isolated domain worker"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
MAX_FILE_BYTES = 128 * 1024
MAX_SOURCE_BYTES = 1024 * 1024


def validate_lock(lock: dict) -> None:
    keys(lock, {"schema", "profile", "files", "project_sha256", "source_lock_id"})
    if lock["schema"] != "ciw.foundry-source-lock.v1" or lock["profile"] != PROFILE:
        raise ValueError("Unsupported Foundry source lock")
    keys(lock["files"], set(FILES))
    for digest in lock["files"].values():
        content_ref(digest)
    if lock["project_sha256"] != bytes_ref(PROJECT):
        raise ValueError("Isolated project declaration differs")
    content_ref(lock["source_lock_id"])
    if lock["source_lock_id"] != content_identity({k: v for k, v in lock.items() if k != "source_lock_id"}):
        raise ValueError("Foundry source lock integrity mismatch")


def snapshot(game_root: Path) -> tuple[dict, dict[str, bytes]]:
    root = Path(game_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Require an operator-selected game directory")
    sources: dict[str, bytes] = {}
    for name in FILES:
        path = root / name
        # Refuse a symlink anywhere inside the supplied root, including parents.
        if any(p.is_symlink() for p in (path, *path.parents) if p != root and root in p.parents):
            raise ValueError("Source symlinks are not admitted")
        if not path.is_file():
            raise ValueError(f"Missing regular game-owned source: {name}")
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if not 0 < len(raw) <= MAX_FILE_BYTES:
            raise ValueError("Game source exceeds file byte budget")
        raw.decode("utf-8")
        sources[name] = raw
    if sum(map(len, sources.values())) > MAX_SOURCE_BYTES:
        raise ValueError("Game source exceeds total byte budget")
    lock = {"schema": "ciw.foundry-source-lock.v1", "profile": PROFILE,
            "files": {name: bytes_ref(raw) for name, raw in sources.items()},
            "project_sha256": bytes_ref(PROJECT)}
    lock["source_lock_id"] = content_identity(lock)
    validate_lock(lock)
    return lock, sources


class GodotProjectBinding:
    """Snapshot all eleven selected modules, not a moving game checkout."""
    def __init__(self, executable: Path, game_root: Path, *, expected_sha256: str, source_lock: dict):
        validate_lock(source_lock)
        content_ref(expected_sha256)
        self.executable = Path(executable).expanduser().resolve(strict=True)
        if not self.executable.is_file() or file_sha(self.executable) != expected_sha256:
            raise ValueError("Godot executable digest mismatch")
        lock, self.sources = snapshot(game_root)
        if lock != source_lock:
            raise ValueError("Game source changed since the work order was compiled")
        self.identity = {"provider": "ciw.foundry.godot-project", "execution_mode": "native_process",
                         "executable_sha256": expected_sha256, "source_lock": deepcopy(lock),
                         "host_adapter_sha256": bytes_ref(Path(__file__).read_bytes()),
                         "platform": platform.platform(),
                         "scope": "selected modules and executable; not an OS sandbox or library attestation"}

    def runtime_identity(self) -> dict:
        if file_sha(self.executable) != self.identity["executable_sha256"]:
            raise ValueError("Godot executable changed after binding")
        if {k: bytes_ref(v) for k, v in self.sources.items()} != self.identity["source_lock"]["files"]:
            raise ValueError("Bound game source snapshot changed")
        return deepcopy(self.identity)

    def invoke(self, objective: dict, parameters: dict) -> dict:
        from .adapters.protocol import AdapterRefusal
        from .foundry_water import validate_objective, validate_parameters, validate_capture
        validate_objective(objective)
        validate_parameters(parameters)
        self.runtime_identity()
        if objective["source_lock"] != self.identity["source_lock"]:
            raise ValueError("Operation source differs from the declared objective")
        request = {"schema": "ciw.foundry-water-request.v1", **deepcopy(parameters),
                   "source_lock_id": objective["source_lock"]["source_lock_id"]}
        try:
            with tempfile.TemporaryDirectory(prefix="net-foundry-") as directory:
                root = Path(directory)
                for name, raw in self.sources.items():
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                (root / "project.godot").write_bytes(PROJECT)
                save_new(root / "request.json", request)
                output = root / "observations.json"
                diagnostic = run_process([str(self.executable), "--headless", "--path", str(root),
                    "--script", "res://" + ENTRYPOINT, "--", str(root / "request.json"), str(output),
                    str(root / "checkpoint.json")], root, [output, root / "checkpoint.json"], timeout=30)
                logs = {}
                for name in ("stdout.log", "stderr.log"):
                    raw = (root / name).read_bytes()
                    if len(raw) > 65536 or b"ERROR:" in raw:
                        raise ValueError("Godot error or oversized log despite successful exit")
                    logs[name] = {"utf8": raw.decode("utf-8"), "sha256": bytes_ref(raw)}
                for name, raw in self.sources.items():
                    if (root / name).read_bytes() != raw:
                        raise ValueError("Engine changed a bound source module")
                if (root / "project.godot").read_bytes() != PROJECT:
                    raise ValueError("Engine changed the isolated project declaration")
                with output.open("rb") as stream:
                    raw = stream.read(65537)
                if not 0 < len(raw) <= 65536:
                    raise ValueError("Native response exceeds byte budget")
                result = {"schema": "ciw.foundry-water-capture.v1", "request": request,
                          "source_utf8": raw.decode("utf-8"), "source_sha256": bytes_ref(raw),
                          "logs": logs, "elapsed_wall_s": diagnostic["elapsed_wall_s"]}
                validate_capture(result, objective, parameters)
                self.runtime_identity()
                return result
        except (OSError, ValueError, RuntimeError) as exc:
            raise AdapterRefusal("foundry_game_runtime_failed", str(exc)[:4096]) from exc
