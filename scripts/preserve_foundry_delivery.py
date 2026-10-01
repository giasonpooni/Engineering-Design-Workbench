"""Recover the exact 131 original handoff entries from pinned evidence sources.

This copies bytes and derives Git patches; it never executes game/source archives.
The output ZIP is a deterministic repack, NOT the original ZIP byte identity.
No network, credentials, Git ref writes, or engine calls occur in this module.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import zipfile

REPOSITORY = "giasonpooni/Notations-Systems-Terminal"
ARTIFACTS = {
    "native": (11015799398, "3d81ff0e973d125176a731e8a346e85f4dccb3c5245bcc9cdd63cb556395b9e3"),
    "ubuntu": (11016491173, "9f584bae733cdc296c6091ecc52743c764c5bdd1c4d6e4a9f2faacac37a05fee"),
    "windows": (11015697994, "9f6bb56e28774247fda0639efa6be215e935cdb468c57b91d118ada826729c5f"),
    "initial": (11015997939, "b853dd82f2b804a4c288c137a77bcd3f141b283da0fb47c0a9d0bdc0b9acdefe"),
}
OVERLAY_SHA256 = "dff7dfe8289baa278a2e8ff1d6935d37b24d7f9f5c2a65c13e0f30251e5536d3"
CHECKSUMS_SHA256 = "eaaa9fd64dc1d80b91ea61c5a5ce696ef0b03d74769f868fae5c56b228bd3fac"
ORIGINAL_ZIP_SHA256 = "88e9ba377369e27d152d5cc1497802f56b77fb5c028c1f5331b9df209ef3c822"
ROOT_NAME = "NET_Foundry_1792_v1"
NET_FILES = (
    ".github/workflows/net-foundry.yml", "docs/NET_FOUNDRY.md",
    "scripts/check_foundry.py", "src/ciw/foundry_project.py",
    "src/ciw/foundry_water.py", "src/ciw/foundry_workflow.py",
    "src/ciw/net.py", "tests/test_foundry.py",
)
DISPATCH = ('    if argv and argv[0] == "foundry":\n'
            '        from .foundry_workflow import main as foundry_main\n'
            '        return foundry_main(argv[1:])\n')


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_name(name: str) -> str:
    parts = PurePosixPath(name)
    if not name or parts.is_absolute() or ".." in parts.parts or "\\" in name or ":" in name or str(parts) != name:
        raise ValueError("Non-canonical archive path")
    return name


def read_zip(raw: bytes) -> dict[str, bytes]:
    if len(raw) > 8_000_000:
        raise ValueError("ZIP transport budget exceeded")
    output: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 2000 or sum(item.file_size for item in entries) > 16_000_000:
            raise ValueError("ZIP expansion budget exceeded")
        for item in entries:
            if item.is_dir():
                continue
            name = safe_name(item.filename)
            if name in output or item.flag_bits & 1 or ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("Duplicate, encrypted or symlink ZIP entry")
            output[name] = archive.read(item)
    return output


def read_overlay(path: Path) -> dict[str, bytes]:
    raw = path.read_bytes()
    if digest(raw) != OVERLAY_SHA256:
        raise ValueError("Local handoff overlay digest mismatch")
    decoder = lzma.LZMADecompressor(memlimit=128 * 1024 * 1024)
    data = decoder.decompress(raw, max_length=200_001)
    if len(data) > 200_000 or not decoder.eof or decoder.unused_data:
        raise ValueError("Overlay expansion budget exceeded")
    output = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        entries = archive.getmembers()
        if len(entries) != 7:
            raise ValueError("Expected seven local-only handoff entries")
        for item in entries:
            name = safe_name(item.name)
            if not item.isfile() or name in output or not 0 < item.size <= 50000:
                raise ValueError("Invalid overlay entry")
            output[name] = archive.extractfile(item).read()
    return output


def git_patch(before: dict[str, bytes], after: dict[str, bytes]) -> bytes:
    """Reproduce the original Git diff, using raw blobs with no content filters."""
    with tempfile.TemporaryDirectory(prefix="foundry-diff-") as directory:
        def git(*args: str, data: bytes | None = None) -> bytes:
            return subprocess.run(["git", "-C", directory, *args], input=data,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=True, timeout=15).stdout
        git("init", "-q")
        trees = []
        for files in (before, after):
            git("read-tree", "--empty")
            index = bytearray()
            for name, raw in sorted(files.items()):
                sha = git("hash-object", "-w", "--stdin", data=raw).strip()
                index.extend(b"100644 " + sha + b"\t" + safe_name(name).encode() + b"\0")
            if index:
                git("update-index", "-z", "--index-info", data=bytes(index))
            trees.append(git("write-tree").decode().strip())
        return git("-c", "core.quotePath=true", "diff", "--binary", "--no-ext-diff", "--no-textconv",
                   "--no-color", "--abbrev=7", "--src-prefix=a/", "--dst-prefix=b/", *trees, "--")


def verify_entries(files: dict[str, bytes]) -> None:
    if digest(files["SHA256SUMS.txt"]) != CHECKSUMS_SHA256:
        raise ValueError("Original checksum authority changed")
    expected = {}
    for line in files["SHA256SUMS.txt"].decode("utf-8").splitlines():
        sha, name = line.split("  ", 1)
        safe_name(name)
        if name in expected or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("Malformed original checksum inventory")
        expected[name] = sha
    if len(files) != 131 or set(expected) != set(files) - {"SHA256SUMS.txt"}:
        raise ValueError("Original 131-entry inventory differs")
    for name, sha in expected.items():
        if digest(files[name]) != sha:
            raise ValueError(f"Original handoff bytes differ: {name}")


def recover(artifact_dir: Path, overlay: Path) -> dict[str, bytes]:
    inputs = {}
    for name, (artifact_id, sha) in ARTIFACTS.items():
        raw = (artifact_dir / f"{artifact_id}.zip").read_bytes()
        if digest(raw) != sha:
            raise ValueError(f"Original {name} CI artifact digest mismatch")
        inputs[name] = read_zip(raw)
    files = read_overlay(overlay)
    def add(name: str, raw: bytes) -> None:
        safe_name(name)
        if name in files:
            raise ValueError("A source attempted to replace an existing handoff entry")
        files[name] = raw
    native = inputs["native"]
    for name, raw in native.items():
        if name.startswith("results/foundry-native/"):
            add("evidence/native/" + name.removeprefix("results/foundry-native/"), raw)
        elif name in ("foundry-source.zip", "foundry-game-source.zip"):
            add("sources/" + name, raw)
        elif name.startswith("dist/") and name.endswith(".whl"):
            add(name.removeprefix("dist/"), raw)
        else:
            raise ValueError(f"Unexpected native artifact entry: {name}")
    for platform in ("ubuntu", "windows"):
        for name in ("foundry-source.xml", "foundry-wheel.xml"):
            add(f"evidence/{platform}/{name}", inputs[platform][name])
    for name, raw in inputs["initial"].items():
        if name.startswith("results/foundry-native/baseline/"):
            add("evidence/initial-failure/baseline/" + name.removeprefix("results/foundry-native/baseline/"), raw)
    source = read_zip(native["foundry-source.zip"])
    game = read_zip(native["foundry-game-source.zip"])
    add("docs/NET_FOUNDRY.md", source["docs/NET_FOUNDRY.md"])
    after = {name: source[name] for name in NET_FILES}
    dispatch = DISPATCH.encode()
    if after["src/ciw/net.py"].count(dispatch) != 1:
        raise ValueError("Original three-line CLI increment differs")
    before = {"src/ciw/net.py": after["src/ciw/net.py"].replace(dispatch, b"", 1)}
    add("patches/net-foundry-over-pr65.patch", git_patch(before, after))
    add("patches/1792-foundry-over-main.patch", git_patch({}, {"game/foundry/water_round.gd": game["game/foundry/water_round.gd"]}))
    add("SHA256SUMS.txt", "".join(f"{digest(raw)}  {name}\n" for name, raw in sorted(files.items(), key=lambda item: PurePosixPath(item[0]))).encode())
    verify_entries(files)
    return files


def publish(files: dict[str, bytes], destination: Path) -> dict:
    verify_entries(files)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(files.items()):
            entry = zipfile.ZipInfo(ROOT_NAME + "/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, raw, compresslevel=9)
    raw = stream.getvalue()
    reopened = {name.removeprefix(ROOT_NAME + "/"): value for name, value in read_zip(raw).items()}
    if reopened != files:
        raise ValueError("ZIP write/read changed original bytes")
    report = {
        "schema": "net.foundry-delivery-preservation.v1", "status": "byte_inventory_verified",
        "archive": ROOT_NAME + ".zip", "archive_sha256": digest(raw), "archive_bytes": len(raw),
        "original_bundle_sha256": ORIGINAL_ZIP_SHA256, "original_file_count": len(files),
        "all_original_file_bytes_preserved": True, "archive_encoding": "deterministic_repack_not_original_zip_bytes",
        "runtime_execution": "not_performed", "new_native_qualification": "not_performed",
        "input_artifacts": {name: {"id": item[0], "sha256": item[1]} for name, item in ARTIFACTS.items()},
        "net_runtime_head": "67225cb061560ad26218ea8473a6b70fb3ab98c1",
        "game_runtime_head": "2bb8a16e63716d54de2d4e97daabc4671d3e07f4",
        "scope": "repository retention; not ESM admission, a new runtime test or a product release",
    }
    # Construct everything before creating the destination; existing data is never overwritten.
    destination.mkdir(parents=True, exist_ok=False)
    (destination / report["archive"]).write_bytes(raw)
    (destination / "publication.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (destination / "qualification.json").write_bytes(files["evidence/native/qualification.json"])
    (destination / "HANDOFF.md").write_bytes(files["README.md"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish(recover(args.artifact_dir, args.overlay), args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
