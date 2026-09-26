"""Bounded Cantera provider for the code-owned reaction benchmark.

The request contains only the fixed model parameters.  The worker constructs
the retained YAML mechanism itself; it never evaluates mechanism or Python
source supplied by a caller.  Cantera's native concentrations and production
rates are converted from kmol-based SI quantities to the CIW mol/m^3 wire
units explicitly.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform as _platform
import re
import struct
import sysconfig
import sys
from typing import Any


PROFILE = "reaction-a-to-b.v1"
MODEL = "closed-isothermal-a-to-b.v1"
REQUEST_SCHEMA = "ciw.native-interop-request.v1"
RESPONSE_SCHEMA = "ciw.native-interop-response.v1"
HANDSHAKE_REQUEST_SCHEMA = "ciw.native-interop-handshake-request.v1"
HANDSHAKE_RESPONSE_SCHEMA = "ciw.native-interop-handshake-response.v1"
MAX_FRAME = 4 * 1024 * 1024
MAX_REQUEST_FRAME = 1 * 1024 * 1024
MAX_REQUESTS = 256
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,160}$")

SEMANTICS = {
    "layout": "time-major",
    "concentration_unit": "mol/m^3",
    "production_rate_unit": "mol/m^3/s",
    "time_unit": "s",
    "temperature_unit": "K",
    "volume_unit": "m^3",
    "frame": "homogeneous-control-volume",
    "clock": "declared-simulation-time",
}

_PAYLOAD_FIELDS = {
    "model",
    "species_order",
    "initial_concentration_mol_m3",
    "rate_constant_s_inv",
    "temperature_k",
    "volume_m3",
    "time_s",
    "solver",
}
_SOLVER_FIELDS = {"reltol", "abstol_mol_m3", "max_steps"}
_REQUEST_FIELDS = {
    "schema",
    "request_id",
    "parent_execution_id",
    "profile",
    "arithmetic",
    "semantics",
    "payload",
}


class InvalidRequest(ValueError):
    """The caller supplied a value outside the fixed provider contract."""


class NumericalFailure(RuntimeError):
    """Cantera did not produce a finite, bounded successful trajectory."""


def _keys_exact(value: Any, expected: set[str], label: str) -> None:
    if type(value) is not dict or set(value) != expected:
        raise InvalidRequest(f"{label} fields differ from the fixed contract")


def _number(value: Any, lower: float, upper: float, label: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise InvalidRequest(f"{label} is not a binary64 number")
    converted = float(value)
    if not math.isfinite(converted) or not lower <= converted <= upper:
        raise InvalidRequest(f"{label} is outside its finite declared bounds")
    return converted


def _identifier(value: Any, label: str) -> str:
    if type(value) is not str or IDENTIFIER_RE.fullmatch(value) is None:
        raise InvalidRequest(f"{label} is not a valid bounded identifier")
    return value


def _validate_payload(payload: Any) -> dict[str, Any]:
    _keys_exact(payload, _PAYLOAD_FIELDS, "reaction payload")
    if payload["model"] != MODEL:
        raise InvalidRequest("unsupported chemical model")
    if payload["species_order"] not in (["A", "B"], ["B", "A"]):
        raise InvalidRequest("species order must name A and B exactly once")

    initial = payload["initial_concentration_mol_m3"]
    if type(initial) is not list or len(initial) != 2:
        raise InvalidRequest("exactly two initial concentrations are required")
    for value in initial:
        _number(value, 0.0, 1000.0, "initial concentration")
    total = math.fsum(float(value) for value in initial)
    if not 1e-6 <= total <= 1000.0:
        raise InvalidRequest("total initial concentration is outside the profile")

    rate = _number(payload["rate_constant_s_inv"], 0.0, 10.0, "rate constant")
    _number(payload["temperature_k"], 250.0, 500.0, "temperature")
    _number(payload["volume_m3"], 1e-6, 1.0, "volume")

    times = payload["time_s"]
    if type(times) is not list or not 2 <= len(times) <= 128:
        raise InvalidRequest("time grid length is outside the profile")
    times_as_float = [_number(value, 0.0, 100.0, "time") for value in times]
    if times_as_float[0] != 0.0 or any(
        later <= earlier for earlier, later in zip(times_as_float, times_as_float[1:])
    ):
        raise InvalidRequest("time grid must increase strictly from zero")
    if rate * times_as_float[-1] > 30.0:
        raise InvalidRequest("reaction exposure exceeds the qualified profile")

    solver = payload["solver"]
    _keys_exact(solver, _SOLVER_FIELDS, "reaction solver")
    if _number(solver["reltol"], 1e-9, 1e-9, "solver relative tolerance") != 1e-9:
        raise InvalidRequest("solver relative tolerance differs from the profile")
    if _number(solver["abstol_mol_m3"], 1e-11, 1e-11, "solver absolute tolerance") != 1e-11:
        raise InvalidRequest("solver absolute tolerance differs from the profile")
    max_steps = solver["max_steps"]
    if type(max_steps) is not int or isinstance(max_steps, bool) or not 1 <= max_steps <= 100000:
        raise InvalidRequest("solver max_steps must be an integer in 1..100000")
    return payload


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_digest(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _distribution_file_hashes(distribution_name: str) -> dict[str, str]:
    """Return path-independent hashes for runtime files in one distribution.

    Distribution metadata is deliberately omitted.  It includes installation
    paths and RECORD self-references on some installers.  Runtime package
    sources, data files and native libraries remain included.
    """

    distribution = importlib.metadata.distribution(distribution_name)
    files = distribution.files
    if files is None:
        raise RuntimeError(f"distribution has no file inventory: {distribution_name}")
    result: dict[str, str] = {}
    for package_path in files:
        relative = PurePosixPath(str(package_path).replace("\\", "/"))
        if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
            continue
        parts = set(relative.parts)
        if any(part.endswith((".dist-info", ".egg-info")) for part in relative.parts):
            continue
        if any(part in {"Scripts", "bin", ".data"} for part in relative.parts):
            continue
        if "__pycache__" in parts or relative.name.endswith(".pyc"):
            continue
        if relative.name in {"RECORD", "INSTALLER", "REQUESTED", "direct_url.json"}:
            continue
        absolute = Path(distribution.locate_file(str(package_path)))
        if not absolute.is_file():
            continue
        result[str(relative)] = hashlib.sha256(absolute.read_bytes()).hexdigest()
    if not result:
        raise RuntimeError(f"distribution has no runtime files: {distribution_name}")
    return dict(sorted(result.items()))


def _package_files_digest() -> str:
    # Prefixing each path with its distribution keeps the canonical mapping
    # unambiguous while retaining distribution-relative paths.
    mapping = {
        name: _distribution_file_hashes(name)
        for name in ("cantera", "numpy", "ruamel.yaml", "typing-extensions")
    }
    canonical = json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(canonical)


def _extension_digest() -> str:
    spec = importlib.util.find_spec("cantera._cantera")
    origin = None if spec is None else spec.origin
    if not origin or origin in {"built-in", "frozen"}:
        raise RuntimeError("Cantera native extension origin is unavailable")
    return _file_digest(Path(origin))


def identity() -> dict[str, Any]:
    """Return the qualified provider closure identity without absolute paths."""

    here = Path(__file__).resolve()
    requirements = here.with_name("requirements.txt")
    packages = {
        name: importlib.metadata.version(name)
        for name in ("cantera", "numpy", "ruamel.yaml", "typing-extensions")
    }
    return {
        "schema": "ciw.reaction-cantera-identity.v1",
        "python_version": platform_python_version(),
        "platform": sysconfig.get_platform(),
        "packages": packages,
        "worker_sha256": _file_digest(here),
        "requirements_sha256": _file_digest(requirements),
        "extension_sha256": _extension_digest(),
        "package_files_sha256": _package_files_digest(),
    }


def platform_python_version() -> str:
    return _platform.python_version()


def _mechanism_bytes(rate_constant: float) -> bytes:
    """Build the fixed abstract A=>B mechanism with exact retained bytes."""

    rate_text = format(float(rate_constant), ".17g")
    mechanism = f"""units:
  length: m
  quantity: kmol
  time: s
  activation-energy: J/kmol
phases:
- name: gas
  thermo: ideal-gas
  kinetics: gas
  elements: [H]
  species: [A, B]
  state: {{T: 300 K, P: 101325 Pa}}
species:
- name: A
  composition: {{H: 1}}
  thermo:
    model: constant-cp
    T0: 300 K
    h0: 0 J/kmol
    s0: 0 J/kmol/K
    cp0: 20786.156545383 J/kmol/K
    T-min: 200 K
    T-max: 1000 K
- name: B
  composition: {{H: 1}}
  thermo:
    model: constant-cp
    T0: 300 K
    h0: 0 J/kmol
    s0: 0 J/kmol/K
    cp0: 20786.156545383 J/kmol/K
    T-min: 200 K
    T-max: 1000 K
reactions:
- equation: A => B
  rate-constant: {{A: {rate_text} 1/s, b: 0, Ea: 0 J/kmol}}
"""
    return mechanism.encode("utf-8")


def _solver_step_count(network: Any) -> int | None:
    try:
        stats = network.solver_stats
        if callable(stats):
            stats = stats()
        if isinstance(stats, dict):
            value = stats.get("steps")
        else:
            try:
                value = stats["steps"]
            except (KeyError, IndexError, TypeError):
                value = None
        if type(value) is int and value >= 0:
            return value
    except Exception:
        pass
    return None


def _execute(payload: dict[str, Any]) -> dict[str, Any]:
    # Importing lazily keeps handshake/startup diagnostics separate from the
    # actual engine execution while identity() still fingerprints the closure.
    import cantera as ct

    _validate_payload(payload)
    order = [str(value) for value in payload["species_order"]]
    initial_by_species = dict(zip(order, payload["initial_concentration_mol_m3"]))
    total_mol_m3 = math.fsum(float(value) for value in payload["initial_concentration_mol_m3"])
    total_kmol_m3 = total_mol_m3 / 1000.0
    composition = {
        "A": float(initial_by_species["A"]) / total_mol_m3,
        "B": float(initial_by_species["B"]) / total_mol_m3,
    }
    temperature = float(payload["temperature_k"])
    volume = float(payload["volume_m3"])
    mechanism = _mechanism_bytes(float(payload["rate_constant_s_inv"]))
    gas = ct.Solution(yaml=mechanism.decode("utf-8"), name="gas")
    # Pressure is a derived initialization quantity.  The benchmark exposes
    # concentration and volume, so choose pressure to realize that density.
    pressure = total_kmol_m3 * float(ct.gas_constant) * temperature
    gas.TPX = temperature, pressure, composition
    reactor = ct.IdealGasMoleReactor(gas, energy="off", volume=volume, clone=True)
    network = ct.ReactorNet([reactor])
    relative_tolerance = float(payload["solver"]["reltol"])
    concentration_tolerance = float(payload["solver"]["abstol_mol_m3"])
    # ReactorNet's mole state uses kmol.  Convert the requested concentration
    # tolerance by multiplying by m^3 and dividing by 1000 mol/kmol.
    state_absolute_tolerance = concentration_tolerance * volume / 1000.0
    network.rtol = relative_tolerance
    network.atol = state_absolute_tolerance
    max_steps = int(payload["solver"]["max_steps"])
    network.max_steps = max_steps

    concentrations: list[list[float]] = []
    production_rates: list[list[float]] = []
    times = [float(value) for value in payload["time_s"]]
    for time in times:
        try:
            network.advance(time)
        except Exception as error:
            raise NumericalFailure(f"Cantera.CVODES advance failed: {error}") from error
        total_steps = _solver_step_count(network)
        if total_steps is None:
            raise NumericalFailure("Cantera.CVODES aggregate step count unavailable")
        if total_steps > max_steps:
            raise NumericalFailure("Cantera.CVODES aggregate max_steps exceeded")
        phase = reactor.phase
        native_concentrations = [float(value) for value in phase.concentrations]
        native_rates = [float(value) for value in phase.net_production_rates]
        by_name_concentration = dict(zip(phase.species_names, native_concentrations))
        by_name_rates = dict(zip(phase.species_names, native_rates))
        # Cantera uses kmol/m^3 and kmol/m^3/s here; CIW uses mol units.
        concentration_row = [1000.0 * by_name_concentration[name] for name in order]
        rate_row = [1000.0 * by_name_rates[name] for name in order]
        if not all(math.isfinite(value) for value in concentration_row + rate_row):
            raise NumericalFailure("Cantera returned a nonfinite reaction sample")
        concentrations.append(concentration_row)
        production_rates.append(rate_row)

    return {
        "model": MODEL,
        "species_order": order,
        "time_s": list(payload["time_s"]),
        "concentration_mol_m3": concentrations,
        "production_rate_mol_m3_s": production_rates,
        "mechanism": {
            "format": "cantera-yaml-v1",
            "bytes_hex": mechanism.hex(),
            "sha256": _sha256_bytes(mechanism),
        },
        "solver": {
            "algorithm": "Cantera.CVODES",
            "retcode": "Success",
            "reltol": 1e-9,
            "abstol_mol_m3": 1e-11,
            "max_steps": max_steps,
        },
    }


def _load_json(raw: bytes) -> Any:
    def reject_constant(value: str) -> Any:
        raise ValueError(f"nonfinite JSON constant {value}")

    return json.loads(
        raw.decode("utf-8"),
        parse_constant=reject_constant,
        object_pairs_hook=_reject_duplicate_keys,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_frame(stream: Any) -> Any | None:
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError("truncated frame header")
    count = struct.unpack(">I", header)[0]
    if not 1 <= count <= MAX_REQUEST_FRAME:
        raise ValueError("empty or oversized frame")
    raw = stream.read(count)
    if len(raw) != count:
        raise ValueError("truncated frame payload")
    return _load_json(raw)


def _write_frame(stream: Any, value: dict[str, Any]) -> None:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if not 1 <= len(raw) <= MAX_FRAME:
        raise ValueError("oversized response")
    stream.write(struct.pack(">I", len(raw)))
    stream.write(raw)
    stream.flush()


def _refusal(request_id: str, parent: str, profile: str, code: str, message: str) -> dict[str, Any]:
    return {
        "schema": RESPONSE_SCHEMA,
        "request_id": request_id,
        "parent_execution_id": parent,
        "profile": profile,
        "status": "refused",
        "refusal": {"code": code, "message": message[:2048]},
    }


def _validate_request(request: Any) -> dict[str, Any]:
    _keys_exact(request, _REQUEST_FIELDS, "native reaction request")
    if request["schema"] != REQUEST_SCHEMA or request["profile"] != PROFILE:
        raise InvalidRequest("unsupported native reaction profile")
    if request["arithmetic"] != "binary64" or request["semantics"] != SEMANTICS:
        raise InvalidRequest("reaction arithmetic, units, frame or clock differ")
    _identifier(request["request_id"], "request_id")
    _identifier(request["parent_execution_id"], "parent_execution_id")
    _validate_payload(request["payload"])
    return request


def _main() -> None:
    first = _read_frame(sys.stdin.buffer)
    if first is None:
        return
    _keys_exact(first, {"schema", "request_id"}, "handshake")
    if first["schema"] != HANDSHAKE_REQUEST_SCHEMA:
        raise InvalidRequest("invalid native handshake")
    _identifier(first["request_id"], "handshake request_id")
    initial_identity = identity()
    _write_frame(
        sys.stdout.buffer,
        {
            "schema": HANDSHAKE_RESPONSE_SCHEMA,
            "status": "ok",
            "request_id": first["request_id"],
            "identity": initial_identity,
            "profiles": [PROFILE],
        },
    )
    seen: set[str] = set()
    while True:
        raw_request = _read_frame(sys.stdin.buffer)
        if raw_request is None:
            return
        request_id = raw_request.get("request_id", "unknown") if isinstance(raw_request, dict) else "unknown"
        parent = raw_request.get("parent_execution_id", "unknown") if isinstance(raw_request, dict) else "unknown"
        profile = raw_request.get("profile", "unsupported") if isinstance(raw_request, dict) else "unsupported"
        if not isinstance(request_id, str):
            request_id = "unknown"
        if not isinstance(parent, str):
            parent = "unknown"
        if not isinstance(profile, str):
            profile = "unsupported"
        try:
            _identifier(request_id, "request_id")
            _identifier(parent, "parent_execution_id")
            if request_id in seen:
                raise InvalidRequest("duplicate or stale request occurrence")
            if len(seen) >= MAX_REQUESTS:
                raise InvalidRequest("worker occurrence limit reached")
            seen.add(request_id)
            request = _validate_request(raw_request)
            before = identity()
            if before != initial_identity:
                raise NumericalFailure("provider closure changed since handshake")
            data = _execute(request["payload"])
            after = identity()
            if before != after or after != initial_identity:
                raise NumericalFailure("provider closure changed during request")
            response = {
                "schema": RESPONSE_SCHEMA,
                "request_id": request_id,
                "parent_execution_id": parent,
                "profile": profile,
                "status": "ok",
                "data": data,
            }
        except InvalidRequest as error:
            response = _refusal(request_id, parent, profile, "INVALID_REQUEST", str(error))
        except Exception as error:
            response = _refusal(request_id, parent, profile, "NUMERICAL_FAILURE", str(error))
        _write_frame(sys.stdout.buffer, response)


if __name__ == "__main__":
    try:
        _main()
    except Exception as error:
        print(f"reaction-cantera transport failure: {str(error)[:2048]}", file=sys.stderr)
        raise SystemExit(2)
