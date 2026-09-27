"""Exact qualified worker binding for the optional interval provider."""
from copy import deepcopy
from pathlib import Path
import re

from . import native_interop_contract as nc
from .telemetry import byte_digest, canonical

FILES = tuple("runtimes/interval-requirement/" + name for name in ("Project.toml", "Manifest.toml", "worker.jl"))
HASH_KEYS = ("project_sha256", "manifest_sha256", "worker_sha256")


def qualification():
    from .native_interop import _pins
    pin = _pins().get("interval_family")
    if pin is None:
        raise ValueError("Interval provider has no qualified runtime pin")
    return pin


def runtime(bindings):
    from . import native_interop as ni
    nc.keys(bindings, {"scr", "host", "host_sha256", "provider", "executable", "runtime", "depot"})
    if bindings["provider"] != "intervals":
        raise ValueError("Unsupported interval provider")
    result, host_bytes, _ = ni._runtime({k: bindings[k] for k in ("scr", "host", "host_sha256")})
    root = Path(bindings["runtime"]).resolve(strict=True)
    artifacts = {name: (root / name).read_bytes() for name in FILES}
    if any(not 1 <= len(raw) <= 1024 * 1024 for raw in artifacts.values()):
        raise ValueError("Interval worker/environment exceeds byte budget")
    ni._depot(bindings["depot"])
    result["interval"] = {"provider": "intervals",
                          "executable_sha256": byte_digest(Path(bindings["executable"]).resolve(strict=True).read_bytes()),
                          "files": {name: byte_digest(raw) for name, raw in artifacts.items()},
                          "worker_identity": deepcopy(qualification()["worker_identity"]),
                          "environment_attestation": "not_established"}
    validate_runtime(result)
    return result, host_bytes, artifacts


def validate_runtime(runtime):
    pin, value = qualification(), runtime["interval"]
    nc.keys(value, {"provider", "executable_sha256", "files", "worker_identity", "environment_attestation"})
    if runtime["julia"] is not None or value["provider"] != "intervals" or value["environment_attestation"] != "not_established":
        raise ValueError("Interval runtime scope differs")
    if runtime["revision"] not in pin["scr_revisions"] or runtime["source_tree"] != pin["scr_trees"].get(runtime["revision"]):
        raise ValueError("Interval profile requires its qualified SCR revision/tree")
    if any(canonical(value[k]) != canonical(pin[k]) for k in ("files", "executable_sha256", "worker_identity")):
        raise ValueError("Interval runtime closure differs from qualification")


def command(source, bindings, runtime, artifacts, root, env):
    from .native_interop import _depot
    if source["provider"] != "intervals" or runtime["interval"]["provider"] != "intervals":
        raise ValueError("Interval source and bound provider differ")
    for name, raw in artifacts.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    folder = root / Path(FILES[0]).parent
    env["JULIA_DEPOT_PATH"] = _depot(bindings["depot"])
    return ["--julia", str(Path(bindings["executable"]).resolve()), "--project", str(folder), "--worker", str(folder / "worker.jl")]


def runtime_link(runtime, source, reply, response):
    validate_runtime(runtime)
    identity = reply["identity"]
    nc.keys(identity, {"provider", "host_executable_sha256", "native_source_id", "native_build", "bridge_version",
                       "julia_executable_sha256", "worker_identity", *HASH_KEYS})
    if identity != response["host"]["provider_runtime"] or identity["provider"] != source["provider"] or identity["host_executable_sha256"] != runtime["host_sha256"]:
        raise ValueError("Interval host identity differs from retained binding")
    if identity["bridge_version"] != "1.0.202" or not re.fullmatch(r"[a-f0-9]{64}", identity["native_source_id"]) or type(identity["native_build"]) is not str or not 1 <= len(identity["native_build"]) <= 32768:
        raise ValueError("Malformed interval host build identity")
    value = runtime["interval"]
    if identity["julia_executable_sha256"] != value["executable_sha256"] or canonical(identity["worker_identity"]) != canonical(value["worker_identity"]):
        raise ValueError("Interval worker executable/packages differ")
    for key, name in zip(HASH_KEYS, FILES):
        if identity[key] != value["files"][name] or identity["worker_identity"][key] != identity[key]:
            raise ValueError("Interval worker source/environment binding differs")
