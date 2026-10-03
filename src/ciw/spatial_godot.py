"""Detached Godot inspection of retained local-frame results.

The consumer is not a USD importer, simulation, or another state owner. Package
verification rebuilds its bytes from the retained workspace and installed
trusted templates. Execution requires an operator-selected binary and digest.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import re
import subprocess
import struct
import tempfile
import uuid

from .operations.runner import check_seal, seal
from .session import loads_json
from .spatial_scene import AUTHORITY, projection, read_bounded

SCHEMA = "ciw.godot-spatial-inspection.v1"
BUNDLE_SCHEMA = "ciw.godot-spatial-bundle.v1"
BASIS = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]
TEMPLATES = ("project.godot", "main.tscn", "view.gd", "self_test.gd")
ARTIFACTS = {*TEMPLATES, "workspace.json", "display.json"}
ERROR_LINE = re.compile(r"^(?:SCRIPT ERROR|ERROR):|(?:Parse|Compile) Error:", re.M)


def digest(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def encode(value: dict) -> bytes:
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def enu_to_godot(point: list | None) -> list | None:
    if point is None:
        return None
    if (not isinstance(point, list) or len(point) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)):
        raise ValueError("Require finite ENU triples or null")
    east, north, up = point
    return [east, up, -north]


def _files(raw: bytes, result_id: str, radius: float) -> dict[str, bytes]:
    if type(radius) not in (int, float) or not math.isfinite(radius) or not 0.001 <= radius <= 100:
        raise ValueError("Marker radius must be 0.001..100 metres; it is visual only")
    if not isinstance(result_id, str) or not result_id:
        raise ValueError("Require an explicit retained result ID")
    source = projection(raw, result_id)  # Existing provider-free Session reader.
    display = {"schema": SCHEMA, "source": source, "basis_enu_to_xyz": BASIS,
               "positions_xyz_m": [enu_to_godot(p) for p in source["positions_enu_m"]],
               "marker_radius_m": float(radius), "interpolation": "none",
               "consumer": "godot-detached-inspector", "physics": "not_declared"}
    assets = files("ciw").joinpath("viewer_assets", "spatial")
    return {**{name: assets.joinpath(name).read_bytes() for name in TEMPLATES},
            "workspace.json": raw, "display.json": encode(display)}


def prepare(workspace: Path, result_id: str, output_dir: Path, *,
            marker_radius_m: float = 0.25, expected_workspace_sha256: str | None = None) -> dict:
    raw = read_bounded(workspace)
    if expected_workspace_sha256 is not None and digest(raw) != expected_workspace_sha256:
        raise ValueError("Workspace bytes do not match the operator's digest")
    artifacts = _files(raw, result_id, marker_radius_m)
    manifest = {"schema": BUNDLE_SCHEMA, "result_id": result_id,
                "marker_radius_m": float(marker_radius_m), "authority": dict(AUTHORITY),
                "godot_execution": "not_performed", "artifacts": {
                    name: digest(value) for name, value in artifacts.items()}}
    seal(manifest)
    artifacts["manifest.json"] = encode(manifest)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    # Receipt is last: an interrupted write is not a completed bundle.
    for name, value in artifacts.items():
        with (output / name).open("xb") as stream:
            stream.write(value)
    return manifest


def _snapshot(directory: Path) -> tuple[dict, dict[str, bytes]]:
    directory = Path(directory)
    manifest_raw = read_bounded(directory / "manifest.json")
    manifest = loads_json(manifest_raw.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Godot manifest must be an object")
    check_seal(manifest)
    required = {"schema", "result_id", "marker_radius_m", "authority", "godot_execution", "artifacts", "record_digest"}
    if (set(manifest) != required or manifest["schema"] != BUNDLE_SCHEMA
            or manifest["authority"] != AUTHORITY or manifest["godot_execution"] != "not_performed"
            or not isinstance(manifest["artifacts"], dict) or set(manifest["artifacts"]) != ARTIFACTS):
        raise ValueError("Unsupported or promoted Godot bundle")
    snapshot = {name: read_bounded(directory / name) for name in ARTIFACTS}
    if any(digest(value) != manifest["artifacts"][name] for name, value in snapshot.items()):
        raise ValueError("Godot bundle artifact mismatch")
    expected = _files(snapshot["workspace.json"], manifest["result_id"], manifest["marker_radius_m"])
    if snapshot != expected:
        raise ValueError("Godot bundle disagrees with retained source or trusted templates")
    snapshot["manifest.json"] = manifest_raw
    return manifest, snapshot


def verify(directory: Path) -> dict:
    manifest, snapshot = _snapshot(directory)
    display = loads_json(snapshot["display.json"].decode("utf-8"))
    return {"status": "retained_godot_bundle_checked", "result_id": manifest["result_id"],
            "source_evidence_id": display["source"]["source_evidence_id"],
            "sample_count": len(display["positions_xyz_m"]),
            "available_count": sum(p is not None for p in display["positions_xyz_m"]),
            "provider_execution": "not_performed", "godot_execution": "not_performed",
            "authority": dict(AUTHORITY)}


def check(directory: Path, executable: Path, expected_sha256: str, output_dir: Path, *, render: bool = False) -> dict:
    """Run only installed trusted test code, in a temporary copy of the bundle.

    Not an OS security sandbox. Digest is an operator assertion, not signer
    authentication. A returned engine report is checked, not trusted as a proof.
    """
    manifest, snapshot = _snapshot(directory)
    executable = Path(executable).resolve(strict=True)
    if not executable.is_file() or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_sha256):
        raise ValueError("Require an explicit Godot executable and sha256:<64 hex> pin")
    with executable.open("rb") as stream:
        from hashlib import file_digest
        actual = "sha256:" + file_digest(stream, "sha256").hexdigest()
    if actual != expected_sha256:
        raise ValueError("Godot executable digest mismatch")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": "ciw.godot-inspection-check.v1", "status": "failed",
               "inspection_id": "inspection-" + uuid.uuid4().hex,
               "bundle_digest": manifest["record_digest"], "result_id": manifest["result_id"],
               "binary_sha256": actual, "authority": dict(AUTHORITY),
               "provider_execution": "not_performed", "render_requested": render}
    try:
        with tempfile.TemporaryDirectory(prefix="ciw-godot-spatial-") as temp:
            project = Path(temp)
            for name, value in snapshot.items():
                (project / name).write_bytes(value)
            engine_report = project / "observed.json"
            args = [str(executable)]
            args += ["--rendering-method", "gl_compatibility", "--audio-driver", "Dummy"] if render else ["--headless"]
            args += ["--path", str(project), "--script", "res://self_test.gd", "--", "--report", str(engine_report)]
            if render:
                args += ["--capture", str(project / "capture.png")]
            env = os.environ.copy()
            env["GODOT_SILENCE_ROOT_WARNING"] = "1"
            with (output / "godot.log").open("wb") as log:
                completed = subprocess.run(args, cwd=project, env=env, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, timeout=90, check=False)
            log_bytes = (output / "godot.log").read_bytes()
            if completed.returncode != 0 or ERROR_LINE.search(log_bytes.decode("utf-8", errors="replace")):
                raise ValueError("Godot process failed; inspect godot.log")
            observed_raw = read_bounded(engine_report)
            # Retain native output even when host-side validation rejects it.
            (output / "observed.json").write_bytes(observed_raw)
            observed = loads_json(observed_raw.decode("utf-8"))
            display = loads_json(snapshot["display.json"].decode("utf-8"))
            count = sum(p is not None for p in display["positions_xyz_m"])
            if (observed.get("status") != "passed" or observed.get("source_unchanged") is not True
                    or observed.get("result_id") != manifest["result_id"]
                    or observed.get("available_count") != count
                    or observed.get("sample_count") != len(display["positions_xyz_m"])
                    or observed.get("selection_checks") != len(display["positions_xyz_m"])
                    or observed.get("negative_checks") != 7
                    or observed.get("display_sha256") != digest(snapshot["display.json"])
                    or observed.get("rendered") is not render
                    or not re.match(r"^4\.5\.2(?:[.\-\s]|$)", str(observed.get("godot_version", "")))):
                raise ValueError("Godot observation does not satisfy the consumer contract; inspect observed.json")
            bindings = observed.get("runtime_bindings")
            expected_points = [(i, p) for i, p in zip(display["source"]["sample_indices"], display["positions_xyz_m"]) if p is not None]
            if not isinstance(bindings, list) or len(bindings) != len(expected_points):
                raise ValueError("Godot runtime bindings are incomplete")
            instance_ids = set()
            for binding, (index, point) in zip(bindings, expected_points):
                xyz = binding.get("position_xyz_m")
                instance = binding.get("instance_id")
                if (binding.get("sample_index") != index or not isinstance(instance, str)
                        or not instance.isdigit() or instance in instance_ids
                        or not isinstance(binding.get("node_path"), str)
                        or not isinstance(xyz, list) or len(xyz) != 3):
                    raise ValueError("Invalid process-local Godot sample identity")
                instance_ids.add(instance)
                expected_point = [struct.unpack("f", struct.pack("f", x))[0] for x in point]
                if any(type(a) not in (int, float) or not math.isfinite(a)
                       or not math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-6)
                       for a, b in zip(xyz, expected_point)):
                    raise ValueError("Godot positions disagree at declared float32 display precision")
            for name, value in snapshot.items():
                if (project / name).read_bytes() != value:
                    raise ValueError("Consumer mutated retained inputs or code")
            (output / "observed.json").write_bytes(observed_raw)
            if render:
                png = (project / "capture.png").read_bytes()
                if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("Rendered capture is not PNG")
                (output / "capture.png").write_bytes(png)
            receipt.update(status="passed", godot_version=observed["godot_version"],
                           observed_sha256=digest(observed_raw), rendered=render)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        receipt["failure"] = str(exc)
        raise
    finally:
        receipt["artifacts"] = {p.name: digest(p.read_bytes()) for p in output.iterdir() if p.is_file()}
        seal(receipt)
        (output / "check.json").write_bytes(encode(receipt))
    return receipt


def register_actions(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="godot_command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("workspace", type=Path)
    p.add_argument("--result-id", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--marker-radius", type=float, default=0.25)
    p.add_argument("--expected-workspace-sha256")
    p = commands.add_parser("verify")
    p.add_argument("directory", type=Path)
    p = commands.add_parser("check")
    p.add_argument("directory", type=Path)
    p.add_argument("--godot", type=Path, required=True)
    p.add_argument("--godot-sha256", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--render", action="store_true")


def dispatch(args: argparse.Namespace) -> dict:
    if args.godot_command == "prepare":
        return prepare(args.workspace, args.result_id, args.output_dir,
                       marker_radius_m=args.marker_radius,
                       expected_workspace_sha256=args.expected_workspace_sha256)
    if args.godot_command == "verify":
        return verify(args.directory)
    return check(args.directory, args.godot, args.godot_sha256, args.output_dir, render=args.render)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    register_actions(parser)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(dispatch(args), indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "refused", "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
