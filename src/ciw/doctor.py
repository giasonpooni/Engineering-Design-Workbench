"""Read-only, profile-scoped provisioning diagnostics; never qualification.

Requirements are projected from the runtime's existing authorities. Only local
Git metadata, installed distribution metadata, and explicit file bindings are
inspected. No provider, package manager, compiler, or credential is invoked.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from importlib import metadata
import json
import os
from pathlib import Path
import re
import sys

from .provider_checkouts import ProviderCheckoutError, _git, validate_checkout


PROFILES = ("core", "legibility", "declared-workloads", "native-interop", "interval-requirement",
            "reaction-catalyst", "reaction-cantera")
_FAMILIES = {"interval-requirement": "intervals", "reaction-catalyst": "catalyst",
             "reaction-cantera": "cantera"}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class _Issue(ValueError):
    def __init__(self, classification, message):
        super().__init__(message)
        self.classification = classification


def _check(report, name, expected, inspect):
    row = {"check": name, "expected": deepcopy(expected), "observed": None}
    report["checks"].append(row)
    try:
        observed, matches = inspect()
        row["observed"] = observed
        if not matches:
            raise _Issue("identity_mismatch", "Observed identity differs from the selected requirement")
        row.update(status="passed", classification=None)
    except (ProviderCheckoutError, _Issue) as exc:
        row.update(status="failed", classification=exc.classification, reason=str(exc))
    except (FileNotFoundError, NotADirectoryError) as exc:
        row.update(status="failed", classification="dependency_unavailable", reason=str(exc))
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        row.update(status="failed", classification="setup_failure", reason=str(exc))
    return row


def _path(value):
    if value is None:
        raise _Issue("dependency_unavailable", "No explicit local binding was supplied")
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise _Issue("setup_failure", "A nonempty local path is required")
    return Path(value).expanduser().resolve(strict=True)


def _file(value, limit=None):
    path = _path(value)
    if not path.is_file():
        raise _Issue("setup_failure", "Bound path must be a regular file")
    size = 0
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if limit is not None and size > limit:
                raise _Issue("setup_failure", "Bound file exceeds the runtime byte limit")
            digest.update(chunk)
    if not size:
        raise _Issue("setup_failure", "Bound file is empty")
    return {"path": str(path), "sha256": "sha256:" + digest.hexdigest(), "byte_count": size}


def _checkout(value, revisions, trees=None):
    path = _path(value)
    observed = {"path": str(path), "revision": _git(path, "rev-parse", "HEAD").decode().strip(),
                "source_tree": _git(path, "rev-parse", "HEAD^{tree}").decode().strip()}
    if observed["revision"] not in revisions:
        return observed, False
    validate_checkout(path, observed["revision"])
    return observed, trees is None or trees.get(observed["revision"]) == observed["source_tree"]


def _installed(name):
    try:
        return metadata.distribution(name)
    except metadata.PackageNotFoundError as exc:
        raise _Issue("dependency_unavailable", "Installed distribution is unavailable: " + name) from exc


def _core(report):
    def installed():
        dist = _installed("computational-instrumentation-workbench")
        return {"version": dist.version, "requires_python": dist.metadata.get("Requires-Python"),
                "requirements": list(dist.requires or [])}, True
    package = _check(report, "ciw_distribution", {"authority": "installed CIW distribution metadata"}, installed)
    if package["status"] != "passed":
        return
    info = package["observed"]
    required_python = info["requires_python"]
    def python_version():
        match = re.fullmatch(r">=(\d+)\.(\d+)(?:\.(\d+))?", required_python or "")
        if match is None:
            raise _Issue("setup_failure", "Cannot interpret the installed Requires-Python constraint")
        minimum = tuple(int(part or 0) for part in match.groups())
        return {"version": ".".join(map(str, sys.version_info[:3])), "executable": sys.executable}, sys.version_info[:3] >= minimum
    _check(report, "python_version", required_python, python_version)
    for requirement in info["requirements"]:
        # The wheel's optional extras are deliberately outside the core profile.
        parts = requirement.split(";", 1)
        if len(parts) == 2 and re.fullmatch(r"\s*extra\s*==\s*['\"][^'\"]+['\"]\s*", parts[1]):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9_.+!-]+)", parts[0].strip()) if len(parts) == 1 else None
        def dependency(match=match):
            if match is None:
                raise _Issue("setup_failure", "Cannot interpret a required distribution constraint")
            version = _installed(match[1]).version
            return {"distribution": match[1], "version": version}, version == match[2]
        _check(report, "core_dependency:" + (match[1] if match else requirement), requirement, dependency)


def _legibility(report):
    _core(report)
    package = next(row for row in report["checks"] if row["check"] == "ciw_distribution")
    if package["status"] != "passed":
        return
    requirements = package["observed"]["requirements"]
    authority = {"authority": "installed CIW distribution metadata", "extra": "legibility",
                 "constraint": "exact version", "required_distribution": "cryptography"}

    def selected_requirements():
        selected, names = [], set()
        for requirement in requirements:
            parts = requirement.split(";", 1)
            if len(parts) != 2 or not re.search(r"\blegibility\b", parts[1]):
                continue
            marker = re.fullmatch(r"\s*extra\s*==\s*(['\"])legibility\1\s*", parts[1])
            pin = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)\s*==\s*"
                               r"((?:\d+!)?\d+(?:\.\d+)*(?:(?:a|b|rc)\d+)?"
                               r"(?:\.post\d+)?(?:\.dev\d+)?"
                               r"(?:\+[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)?)", parts[0].strip())
            if marker is None or pin is None:
                raise _Issue("setup_failure", "Cannot interpret a Legibility optional distribution constraint")
            name = re.sub(r"[_.-]+", "-", pin[1]).lower()
            if name in names:
                raise _Issue("setup_failure", "Duplicate Legibility distribution requirement: " + name)
            names.add(name)
            selected.append({"distribution": name, "version": pin[2], "requirement": requirement})
        if "cryptography" not in names:
            raise _Issue("setup_failure", "Installed CIW metadata does not declare exact Legibility cryptography requirements")
        return selected, True

    row = _check(report, "legibility_requirements", authority, selected_requirements)
    report["not_checked"].extend(["cryptographic backend import and loadability",
                                  "key generation, signing, signature verification or issuer trust"])
    if row["status"] != "passed":
        return
    report["requirements"] = {**authority, "distributions": deepcopy(row["observed"])}
    for requirement in row["observed"]:
        def dependency(requirement=requirement):
            version = _installed(requirement["distribution"]).version
            return {"distribution": requirement["distribution"], "version": version}, version == requirement["version"]
        _check(report, "legibility_dependency:" + requirement["distribution"],
               requirement["requirement"], dependency)


def _declared(report, stack_root, engine):
    from .declared_workload import PINS
    for kind, pin in sorted(PINS.items()):
        root = Path(stack_root).expanduser() / pin["role"] if stack_root is not None else None
        _check(report, "checkout:" + pin["role"], {"authority": "ciw.declared_workload.PINS", "kind": kind, **pin},
               lambda root=root, pin=pin: _checkout(root, [pin["revision"]]))
    _check(report, "execution_engine", {"binding": "operator_asserted_not_attested", "nonempty_file": True},
           lambda: (_file(engine, 32 * 1024 * 1024), True))
    report["not_checked"].extend(["Python provider import and dependency identity", "engine loadability and source-to-binary relationship"])


def _binding(value):
    path = _path(value)
    if not path.is_file():
        raise _Issue("setup_failure", "Runtime binding must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise _Issue("setup_failure", "Host binding exceeds byte budget")
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate binding field: " + key)
            result[key] = item
        return result
    def reject(value):
        raise ValueError("Non-finite binding value: " + value)
    binding = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    if type(binding) is not dict:
        raise _Issue("setup_failure", "Runtime binding must be an object")
    for key in ("scr", "host", "executable", "runtime", "julia", "julia_runtime"):
        if key in binding:
            if type(binding[key]) is not str or not binding[key].strip():
                raise _Issue("setup_failure", "Runtime path must be a nonempty string: " + key)
            binding[key] = str((path.parent / binding[key]).resolve())
    return binding


def _depot(value):
    if type(value) is not str or not value.strip():
        raise _Issue("setup_failure", "An explicit Julia depot path is required")
    # Match native_interop._depot exactly: a literal '~' is a relative path,
    # not a request for shell/user-home expansion.
    paths = [Path(part).resolve(strict=True) for part in value.split(os.pathsep) if part]
    if not paths or not all(path.is_dir() for path in paths):
        raise _Issue("dependency_unavailable", "Julia depot directory is unavailable")
    return {"paths": [str(path) for path in paths], "packages": "not_checked"}, True


def _native(report, profile, binding_path):
    from .native_interop import _julia_closures, _pins
    pins = _pins()
    provider = _FAMILIES.get(profile)
    pin = pins["interval_family"] if provider == "intervals" else pins["reaction_families"][provider] if provider else pins
    requirements = {"authority": "ciw/native-interop-runtimes.json", "scr_revisions": pin["scr_revisions"]}
    if provider:
        requirements.update({key: deepcopy(pin[key]) for key in ("scr_trees", "files", "executable_sha256", "worker_identity")})
    else:
        requirements["julia_file_closures"] = _julia_closures(pins)
    report["requirements"] = requirements
    def inspect_binding():
        binding = _binding(binding_path)
        required = {"scr", "host", "host_sha256"}
        if provider:
            required |= {"provider", "executable", "runtime"}
            if provider != "cantera":
                required.add("depot")
            if binding.get("provider") != provider:
                raise _Issue("identity_mismatch", "Binding provider differs from the selected profile")
            if binding.keys() != required:
                raise _Issue("setup_failure", "Binding fields differ from the selected runtime contract")
        else:
            julia = {"julia", "julia_runtime", "julia_depot"}
            if not required <= binding.keys() <= required | julia or (binding.keys() & julia and not julia <= binding.keys()):
                raise _Issue("setup_failure", "Native binding requires SCR/host and an optional complete Julia binding")
        if type(binding["host_sha256"]) is not str or not _DIGEST.fullmatch(binding["host_sha256"]):
            raise _Issue("setup_failure", "Host digest must be a full sha256 identity")
        return binding, True
    row = _check(report, "runtime_binding", {"profile": profile, "provider": provider}, inspect_binding)
    if row["status"] != "passed":
        return
    binding = row["observed"]
    _check(report, "checkout:scr", {"revisions": pin["scr_revisions"], "trees": pin.get("scr_trees")},
           lambda: _checkout(binding["scr"], pin["scr_revisions"], pin.get("scr_trees")))
    def host():
        observed = _file(binding["host"], 64 * 1024 * 1024)
        return observed, observed["sha256"] == binding["host_sha256"]
    _check(report, "host_binary", {"sha256": binding["host_sha256"], "authority": "operator_asserted_not_attested"}, host)
    if provider:
        closures, root = [pin["files"]], binding["runtime"]
    elif "julia_runtime" in binding:
        closures, root = _julia_closures(pins), binding["julia_runtime"]
    else:
        closures, root = [], None
    if closures:
        def files():
            directory = _path(root)
            observed = {name: _file(directory / name, 1024 * 1024 if provider else 256 * 1024)["sha256"] for name in closures[0]}
            return observed, observed in closures
        _check(report, "worker_files", {"complete_accepted_closures": closures}, files)
        def executable():
            observed = _file(binding["executable"] if provider else binding["julia"])
            return observed, not provider or observed["sha256"] == pin["executable_sha256"]
        _check(report, "worker_executable", {"sha256": pin["executable_sha256"]} if provider else {"identity": "reported_only"}, executable)
        if provider != "cantera":
            _check(report, "julia_depot", {"existing_directories": True, "contents": "not_attested"},
                   lambda: _depot(binding["depot"] if provider else binding["julia_depot"]))


def diagnose(profile="core", *, stack_root=None, engine=None, binding=None):
    """Return explicit expected/observed checks; passing never means qualified."""
    if profile not in PROFILES:
        raise ValueError("Unknown doctor profile")
    report = {"schema": "ciw.doctor.v1", "profile": profile, "read_only": True,
              "qualification": "not_performed", "checks": [],
              "not_checked": ["credential or network access", "worker loadability", "scientific execution", "numerical/proof qualification", "source-to-binary attestation"]}
    try:
        if profile == "core":
            if any(value is not None for value in (stack_root, engine, binding)):
                raise _Issue("setup_failure", "Core doctor does not accept provider bindings")
            _core(report)
        elif profile == "legibility":
            if any(value is not None for value in (stack_root, engine, binding)):
                raise _Issue("setup_failure", "Legibility doctor does not accept provider bindings")
            _legibility(report)
        elif profile == "declared-workloads":
            if binding is not None:
                raise _Issue("setup_failure", "Declared workloads use stack-root and engine bindings")
            _declared(report, stack_root, engine)
        else:
            if stack_root is not None or engine is not None:
                raise _Issue("setup_failure", "Native profiles use the existing runtime binding JSON")
            _native(report, profile, binding)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        report["checks"].append({"check": "profile_configuration", "expected": profile, "observed": None,
                                 "status": "failed", "classification": getattr(exc, "classification", "setup_failure"), "reason": str(exc)})
    failures = [row for row in report["checks"] if row["status"] == "failed"]
    report["status"] = "blocked" if failures else "preflight_passed"
    report["classifications"] = sorted({row["classification"] for row in failures})
    return report
