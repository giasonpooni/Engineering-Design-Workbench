"""Protocol-only synthetic child, deliberately NOT a Cantera implementation."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

MODE = "ok"
assert sys.flags.isolated == 1 and sys.flags.ignore_environment == 1
assert {p.name for p in Path(__file__).parent.iterdir()} == {"worker.py", "requirements.txt"}


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def read():
    header = sys.stdin.buffer.read(4)
    if not header:
        return None
    length = struct.unpack(">I", header)[0]
    return json.loads(sys.stdin.buffer.read(length))


def write(value):
    raw = json.dumps(value, separators=(",", ":")).encode()
    sys.stdout.buffer.write(struct.pack(">I", len(raw)) + raw)
    sys.stdout.buffer.flush()


while (request := read()) is not None:
    if request["schema"] == "ciw.native-interop-handshake-request.v1":
        identity = {"schema": "ciw.reaction-cantera-identity.v1", "python_version": sys.version.split()[0],
                    "platform": "PROTOCOL-ONLY-FIXTURE", "packages": {"fixture-not-cantera": "1"},
                    "worker_sha256": digest(Path(__file__).read_bytes()),
                    "requirements_sha256": digest(Path(__file__).with_name("requirements.txt").read_bytes()),
                    "extension_sha256": digest(b"not-a-real-extension"),
                    "package_files_sha256": digest(b"not-a-real-distribution")}
        if MODE == "identity":
            identity["worker_sha256"] = digest(b"wrong-worker")
        write({"schema": "ciw.native-interop-handshake-response.v1", "request_id": request["request_id"],
               "status": "ok", "identity": identity, "profiles": ["reaction-a-to-b.v1"]})
        continue
    if MODE == "timeout":
        time.sleep(60)
    if MODE == "stderr":
        sys.stderr.buffer.write(b"x" * 70000)
        sys.stderr.buffer.flush()
        time.sleep(60)
    if MODE == "crash":
        sys.exit(9)
    if MODE == "truncated":
        sys.stdout.buffer.write(struct.pack(">I", 100) + b"a")
        sys.stdout.buffer.flush()
        sys.exit(0)
    source = request["payload"]
    # Synthetic constant values exercise only transport/shape acceptance.
    data = {"model": source["model"], "species_order": source["species_order"], "time_s": source["time_s"],
            "concentration_mol_m3": [source["initial_concentration_mol_m3"] for _ in source["time_s"]],
            "production_rate_mol_m3_s": [[0, 0] for _ in source["time_s"]],
            "mechanism": {"format": "cantera-yaml-v1", "bytes_hex": b"synthetic".hex(), "sha256": digest(b"synthetic")},
            "solver": {"algorithm": "Cantera.CVODES", "retcode": "Success", **source["solver"]}}
    if MODE == "grid":
        data["time_s"] = [0, 2]
    if MODE == "solver":
        data["solver"]["max_steps"] += 1
    if MODE == "digest":
        data["mechanism"]["sha256"] = digest(b"wrong")
    if MODE == "nonfinite":
        data["concentration_mol_m3"][0][0] = float("nan")
    response = {"schema": "ciw.native-interop-response.v1", "request_id": request["request_id"],
                "parent_execution_id": request["parent_execution_id"], "profile": request["profile"],
                "status": "ok", "data": data}
    if MODE == "stale":
        response["request_id"] = "wrong-id"
    if MODE == "refused":
        del response["data"]
        response.update(status="refused", refusal={"code": "fixture-refusal", "detail": "deliberate refusal"})
    write(response)
