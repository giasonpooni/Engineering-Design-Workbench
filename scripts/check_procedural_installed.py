"""Qualify real wheel-installed graphics commands outside the source checkout."""
from __future__ import annotations

import argparse
from hashlib import sha256
import base64
import json
import os
from pathlib import Path
import subprocess
import struct
import zlib


def reopen_png(raw, width, height):
    """An independent parser for the qualified RGBA8, filter-zero export."""
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    cursor, chunks = 8, []
    while cursor < len(raw):
        length = struct.unpack(">I", raw[cursor:cursor + 4])[0]
        kind = raw[cursor + 4:cursor + 8]
        payload = raw[cursor + 8:cursor + 8 + length]
        crc = struct.unpack(">I", raw[cursor + 8 + length:cursor + 12 + length])[0]
        assert crc == zlib.crc32(kind + payload) & 0xffffffff
        chunks.append((kind, payload))
        cursor += length + 12
    assert cursor == len(raw) and [kind for kind, _ in chunks] == [b"IHDR", b"IDAT", b"IEND"]
    assert struct.unpack(">IIBBBBB", chunks[0][1]) == (width, height, 8, 6, 0, 0, 0)
    assert chunks[2][1] == b""
    decoded = zlib.decompress(chunks[1][1])
    stride = width * 4 + 1
    assert len(decoded) == height * stride
    assert all(decoded[row * stride] == 0 for row in range(height))
    return b"".join(decoded[row * stride + 1:(row + 1) * stride] for row in range(height))


def snapshot(path):
    return {str(p.relative_to(path)): sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


def qualify(executable, destination):
    executable = Path(executable).resolve(strict=True)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    invocations = []

    def command(*args, expected=0):
        reply = subprocess.run([str(executable), "graphics", *map(str, args)], cwd=destination,
                               env=environment, capture_output=True, text=True, timeout=90)
        assert reply.returncode == expected, (args, reply.returncode, reply.stderr or reply.stdout)
        invocations.append({"command": args[0], "expected_exit": expected})
        return json.loads(reply.stderr if expected == 1 else reply.stdout)

    profiles = {}
    for profile in ("sphere", "wave", "gyroid", "parametric", "texture"):
        command("example", "--profile", profile, "--output", profile + ".json")
        created = command("run", profile + ".json", "--output-dir", profile)
        assert created["status"] == "LOCAL" and created["verification_status"] == "PASS"
        before = snapshot(destination / profile)
        retained = command("inspect", profile)
        checked = command("verify", profile)
        assert retained["fresh_execution"] is False and retained["fresh_numerical_verification"] is False
        assert checked["fresh_numerical_verification"] is True and checked["fresh_execution"] is False
        repeated = command("replay", profile, "--output-dir", profile + "-replay")
        assert repeated["evidence_id"] == created["evidence_id"]
        assert repeated["mesh_digest"] == created["mesh_digest"]
        assert repeated["output_digest"] == created["output_digest"]
        for name in ("result_id", "execution_id", "verification_id", "verification_execution_id"):
            assert repeated[name] != created[name]
        receipt = json.loads((destination / (profile + "-replay") / "replay.json").read_text())
        assert receipt["status"] == "PASS" and receipt["fresh_occurrences"] is True
        assert receipt["authority"]["source_archive_authenticity"] == "not_established"
        formats = ("png", "json") if profile == "texture" else ("obj", "json")
        for fmt in formats:
            command("export", profile, "--format", fmt, "--output", f"{profile}-artifact.{fmt}")
        fmt = formats[0]
        manifest = json.loads((destination / f"{profile}-artifact.{fmt}.json").read_text())
        exported = (destination / f"{profile}-artifact.{fmt}").read_bytes()
        assert manifest["output_sha256"] == "sha256:" + sha256(exported).hexdigest()
        if profile == "texture":
            artifact = json.loads((destination / "texture-artifact.json").read_text())["artifact"]
            image = artifact["image"]
            assert reopen_png(exported, image["width"], image["height"]) == base64.b64decode(image["rgba_base64"], validate=True)
            assert artifact["shader"]["compilation"] == "not_performed"
            assert manifest["frame"] == "procedural.texture_uv.v1"
            command("export", profile, "--format", "obj", "--output", "wrong.obj", expected=1)
        else:
            assert manifest["units"] == "normalized_length"
            assert manifest["frame"] == "procedural.local_xyz.v1"
            vertices = [list(map(float, line.split()[1:])) for line in exported.decode().splitlines() if line.startswith("v ")]
            faces = [list(map(int, line.split()[1:])) for line in exported.decode().splitlines() if line.startswith("f ")]
            assert len(vertices) == created["metrics"]["vertex_count"]
            assert len(faces) == created["metrics"]["triangle_count"]
            assert all(len(face) == 3 and all(1 <= index <= len(vertices) for index in face) for face in faces)
            command("export", profile, "--format", "png", "--output", f"wrong-{profile}.png", expected=1)
        assert snapshot(destination / profile) == before
        assert checked["authority"]["physical_material_validation"] == "not_established"
        profiles[profile] = {"verification": "PASS", "replay": "PASS", "exports": list(formats),
                             "metrics": created["metrics"], "original_unchanged": True}
    for profile in ("sphere", "parametric", "texture"):
        excessive = json.loads((destination / (profile + ".json")).read_text())
        excessive["domain"]["resolution"] = 25 if profile == "sphere" else [49, 16] if profile == "parametric" else [257, 128]
        path = profile + "-excessive.json"
        (destination / path).write_text(json.dumps(excessive))
        assert command("run", path, "--output-dir", profile + "-excessive", expected=1)["status"] == "REFUSE"
        assert not (destination / (profile + "-excessive")).exists()
    request = json.loads((destination / "sphere.json").read_text())
    request["definition"]["expression"] = "__import__('os').getcwd()"
    (destination / "unsafe.json").write_text(json.dumps(request))
    assert command("run", "unsafe.json", "--output-dir", "unsafe", expected=1)["status"] == "REFUSE"
    assert not (destination / "unsafe").exists()
    request["definition"]["expression"] = "1"
    (destination / "empty.json").write_text(json.dumps(request))
    refused = command("run", "empty.json", "--output-dir", "empty", expected=2)
    assert refused["status"] == "REFUSE" and refused["verification_status"] == "not_verified"
    assert command("inspect", "empty", expected=2)["status"] == "REFUSE"
    command("export", "empty", "--output", "empty.obj", expected=1)
    assert not (destination / "empty.obj").exists()
    report = {"status": "PASS", "profiles": profiles, "unsafe_notation_refused": True,
              "excessive_resources_refused": True, "command_count": len(invocations),
              "empty_surface_retained_as_refusal": True, "physical_material_validation": "not_established"}
    (destination / "installed-qualification.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.net, args.output_dir), indent=2))
