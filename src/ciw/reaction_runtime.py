"""Additive trusted bindings for the two bounded reaction providers.

The native execution envelope is unchanged. Qualification is by a complete
worker/environment closure; arbitrary payloads never select a program or path.
"""
from copy import deepcopy
from pathlib import Path
import re

from . import native_interop_contract as nc
from .telemetry import byte_digest

FILES = {
    "catalyst": ("runtimes/reaction-kinetics/Project.toml", "runtimes/reaction-kinetics/Manifest.toml", "runtimes/reaction-kinetics/worker.jl"),
    "cantera": ("runtimes/cantera-reaction/requirements.txt", "runtimes/cantera-reaction/worker.py"),
}
HASH_KEYS = {"catalyst": ("project_sha256", "manifest_sha256", "worker_sha256"),
             "cantera": ("requirements_sha256", "worker_sha256")}


def qualification(provider):
    from .native_interop import _pins
    row = _pins().get("reaction_families", {}).get(provider)
    if row is None:
        raise ValueError("Reaction provider has no qualified runtime pin")
    return row


def runtime(bindings):
    from . import native_interop as ni
    provider = bindings.get("provider")
    if provider not in FILES:
        raise ValueError("Unsupported bound worker family")
    required = {"scr", "host", "host_sha256", "provider", "executable", "runtime"}
    if provider == "catalyst": required.add("depot")
    nc.keys(bindings, required)
    result, host_bytes, _ = ni._runtime({k:bindings[k] for k in ("scr", "host", "host_sha256")})
    pin = qualification(provider)
    root = Path(bindings["runtime"]).resolve(strict=True)
    artifacts = {name:(root/name).read_bytes() for name in FILES[provider]}
    if any(not 1 <= len(raw) <= 1024*1024 for raw in artifacts.values()):
        raise ValueError("Reaction worker/environment exceeds byte budget")
    files = {name:byte_digest(raw) for name,raw in artifacts.items()}
    exe = Path(bindings["executable"]).resolve(strict=True)
    digest = byte_digest(exe.read_bytes())
    if provider == "catalyst": ni._depot(bindings["depot"])
    result["reaction"] = {"provider":provider, "executable_sha256":digest, "files":files,
                          "worker_identity":deepcopy(pin["worker_identity"]),
                          "environment_attestation":"not_established"}
    validate_runtime(result, provider)
    return result, host_bytes, artifacts


def validate_runtime(runtime, provider):
    """Validate retained qualification, without consulting a live installation."""
    pin = qualification(provider)
    r = runtime["reaction"]
    nc.keys(r, {"provider", "executable_sha256", "files", "worker_identity", "environment_attestation"})
    if runtime["julia"] is not None or r["provider"] != provider or r["environment_attestation"] != "not_established":
        raise ValueError("Retained reaction runtime scope differs")
    if runtime["revision"] not in pin["scr_revisions"] or runtime.get("source_tree") != pin["scr_trees"].get(runtime["revision"]):
        raise ValueError("Reaction profile requires its qualified SCR revision")
    if r["files"] != pin["files"] or r["executable_sha256"] != pin["executable_sha256"] or r["worker_identity"] != pin["worker_identity"]:
        raise ValueError("Reaction runtime closure differs from qualification")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", r["executable_sha256"]):
        raise ValueError("Malformed reaction executable identity")


def command(source, bindings, runtime, artifacts, root, env):
    from .native_interop import _depot
    provider = source["provider"]
    if bindings.get("provider") != provider or runtime.get("reaction", {}).get("provider") != provider:
        raise ValueError("Reaction source and bound provider family differ")
    for name,raw in artifacts.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    folder = root/Path(FILES[provider][0]).parent
    exe = str(Path(bindings["executable"]).resolve())
    if provider == "catalyst":
        env["JULIA_DEPOT_PATH"] = _depot(bindings["depot"])
        return ["--julia", exe, "--project", str(folder), "--worker", str(folder/"worker.jl")]
    return ["--python", exe, "--project", str(folder), "--worker", str(folder/"worker.py")]


def runtime_link(runtime, source, reply, response):
    provider = source["provider"]
    validate_runtime(runtime, provider)
    identity = reply["identity"]
    exe_key = "julia_executable_sha256" if provider == "catalyst" else "python_executable_sha256"
    nc.keys(identity, {"provider", "host_executable_sha256", "native_source_id", "native_build", "bridge_version", exe_key, "worker_identity", *HASH_KEYS[provider]})
    if identity != response["host"]["provider_runtime"] or identity["provider"] != provider or identity["host_executable_sha256"] != runtime["host_sha256"]:
        raise ValueError("Reaction host identity differs from retained binding")
    if identity["bridge_version"] != "1.0.202" or not re.fullmatch(r"[a-f0-9]{64}", identity["native_source_id"]) or type(identity["native_build"]) is not str or not 1 <= len(identity["native_build"]) <= 32768:
        raise ValueError("Malformed reaction host build identity")
    r = runtime["reaction"]
    if provider == "catalyst" and response["data"]["mechanism"]["sha256"] != identity["worker_sha256"]:
        raise ValueError("Catalyst mechanism is not the retained code-owned worker")
    if identity[exe_key] != r["executable_sha256"] or identity["worker_identity"] != r["worker_identity"]:
        raise ValueError("Reaction worker executable/packages differ")
    for key,path in zip(HASH_KEYS[provider], FILES[provider]):
        if identity[key] != r["files"][path] or identity["worker_identity"][key] != identity[key]:
            raise ValueError("Reaction worker environment/source binding differs")
