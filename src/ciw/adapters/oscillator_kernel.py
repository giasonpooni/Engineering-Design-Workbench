"""Explicit binding to a Julia-authored oscillator RHS; no import-time native load.

This module does not own an integrator, session, engine state or verification
identity. The existing operation runner retains execution and result records.
Only the host supplies executable bindings; saved payload validation is offline.
"""
from __future__ import annotations

import ctypes
from hashlib import sha256
import math
from pathlib import Path
import platform
import re

OPERATION = "oscillator.rhs-native.v1"
PAYLOAD = "ciw.oscillator-rhs-native-result.v1"
PROFILE = "oscillator-f64-rhs-v1"
MAX_SAMPLES = 4096
PARAMETERS = {"gamma_s_inv", "omega_0_rad_s", "channel", "interval_s"}
STATUS = {1: "null pointer", 2: "buffer length", 3: "nonfinite input",
          4: "profile bounds", 5: "nonfinite output", 6: "rounding mode"}


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        h = sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def checked_digest(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ValueError("expected an explicit sha256 digest")
    return value


def finite_number(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("expected a finite real scalar, not a coerced value")
    try:
        converted = float(value)
    except OverflowError as error:
        raise ValueError("scalar is not representable in binary64") from error
    if not math.isfinite(converted):
        raise ValueError("expected a finite real scalar")
    return converted


def check_state_parameters(state, parameters):
    if not isinstance(state, (list, tuple)) or len(state) != 2:
        raise ValueError("state order must be [q, v]")
    if not isinstance(parameters, (list, tuple)) or len(parameters) != 2:
        raise ValueError("parameter order must be [gamma, omega]")
    q, v = map(finite_number, state)
    gamma, omega = map(finite_number, parameters)
    if (abs(q) > 1e6 or abs(v) > 1e6 or not math.ulp(1.0) <= omega <= 20.0
            or not 0.0 <= gamma <= 0.5 * omega):
        raise ValueError("input exceeds the oscillator RHS profile")
    return [q, v], [gamma, omega]


class OscillatorKernel:
    """Host-owned binding to an explicitly trusted native artifact.

    Hashes detect artifact drift, not malicious libraries. A caller must trust
    the build/toolchain before loading native code. Native pointers stay private.
    """
    def __init__(self, library: Path, *, library_sha256: str, source_sha256: str):
        self._path = Path(library).expanduser().resolve(strict=True)
        self._library_sha256 = checked_digest(library_sha256)
        self._source_sha256 = checked_digest(source_sha256)
        self._check_file()
        self._library = ctypes.CDLL(str(self._path))
        abi = self._library.ciw_oscillator_abi_v1
        abi.argtypes, abi.restype = [], ctypes.c_uint32
        source = self._library.ciw_oscillator_source_sha256_v1
        source.argtypes, source.restype = [], ctypes.c_char_p
        if abi() != 1 or source() != self.source_sha256[7:].encode("ascii"):
            raise ValueError("native ABI or source identity mismatch")
        self._rhs = self._library.ciw_oscillator_rhs_v1
        ptr = ctypes.POINTER(ctypes.c_double)
        self._rhs.argtypes = [ptr, ctypes.c_size_t, ptr, ctypes.c_size_t, ptr, ctypes.c_size_t]
        self._rhs.restype = ctypes.c_int32

    @property
    def library_sha256(self) -> str:
        return self._library_sha256

    @property
    def source_sha256(self) -> str:
        return self._source_sha256

    def _check_file(self) -> None:
        if file_digest(self._path) != self.library_sha256:
            raise ValueError("native artifact digest mismatch")

    def runtime_identity(self) -> dict:
        self._check_file()
        return {"provider": OPERATION, "profile": PROFILE, "abi": 1,
                "library_sha256": self.library_sha256, "source_sha256": self.source_sha256,
                "platform": platform.system(), "machine": platform.machine(),
                "required_arithmetic_policy": "binary64; nearest; no fast-math; fp-contract=off"}

    def rhs(self, state, parameters) -> list[float]:
        state, parameters = check_state_parameters(state, parameters)
        array = ctypes.c_double * 2
        out = array()
        code = self._rhs(array(*state), 2, array(*parameters), 2, out, 2)
        if code != 0:
            raise ValueError("native RHS refused: " + STATUS.get(code, f"unknown status {code}"))
        result = list(out)
        if not all(math.isfinite(value) for value in result):
            raise ValueError("native RHS returned nonfinite output")
        return result


def selected_samples(run: dict, parameters: dict):
    from ..core.records import validate_run_structure
    validate_run_structure(run)
    if run["metadata"]["coordinate_frame"] != "oscillator-state":
        raise ValueError("expected the oscillator-state frame")
    if not isinstance(parameters, dict) or set(parameters) != PARAMETERS:
        raise ValueError("RHS parameters must declare model, channel and interval only")
    if parameters["channel"] != "q":
        raise ValueError("RHS selection channel must be q")
    interval = parameters["interval_s"]
    if not isinstance(interval, list) or len(interval) != 2:
        raise ValueError("expected a half-open interval")
    start, stop = map(finite_number, interval)
    duration = finite_number(run["metadata"]["duration_s"])
    if not 0 <= start < stop <= duration:
        raise ValueError("selection outside run")
    if run["channels"]["q"]["unit"] != "m" or run["channels"]["v"]["unit"] != "m/s":
        raise ValueError("expected q in metres and v in metres/second")
    times = run["time_s"]
    if not isinstance(times, list) or not 1 <= len(times) <= MAX_SAMPLES:
        raise ValueError("run exceeds bounded sample count")
    times = [finite_number(t) for t in times]
    if times[0] < 0 or times[-1] >= duration or any(b <= a for a,b in zip(times, times[1:])):
        raise ValueError("run time grid must be ordered within duration")
    q, v = run["channels"]["q"]["values"], run["channels"]["v"]["values"]
    if len(q) != len(times) or len(v) != len(times):
        raise ValueError("state channels do not match the time grid")
    p = [parameters["gamma_s_inv"], parameters["omega_0_rad_s"]]
    indices = [i for i,t in enumerate(times) if start <= t < stop]
    if not indices:
        raise ValueError("selection has no samples")
    states = [check_state_parameters([q[i],v[i]], p)[0] for i in indices]
    _, p = check_state_parameters(states[0], p)
    return indices, [times[i] for i in indices], states, p


def evaluate_run(kernel: OscillatorKernel, run: dict, parameters: dict) -> dict:
    indices, times, states, p = selected_samples(run, parameters)
    values = [kernel.rhs(state, p) for state in states]
    return {"schema": PAYLOAD, "source_evidence_id": run["evidence_id"],
            "sample_indices": indices, "time_s": times,
            "dq_m_s": [row[0] for row in values], "dv_m_s2": [row[1] for row in values],
            "model": {"gamma_s_inv": p[0], "omega_0_rad_s": p[1]},
            "library_sha256": kernel.library_sha256, "source_sha256": kernel.source_sha256,
            "origin": "computed_model_output", "verification": "not_verified"}


def validate_payload(operation_id, data, run, parameters, selection):
    """Structural/binding checks only: no CDLL, provider execution or verification."""
    expected = {"schema", "source_evidence_id", "sample_indices", "time_s", "dq_m_s",
                "dv_m_s2", "model", "library_sha256", "source_sha256", "origin", "verification"}
    if operation_id != OPERATION or not isinstance(data, dict) or set(data) != expected:
        raise ValueError("unsupported RHS payload")
    if data["schema"] != PAYLOAD or data["source_evidence_id"] != run["evidence_id"]:
        raise ValueError("RHS evidence binding mismatch")
    if any(parameters[k] != selection[k] for k in ("channel", "interval_s")):
        raise ValueError("RHS selection mismatch")
    indices, times, _, p = selected_samples(run, parameters)
    if (data["sample_indices"] != indices or any(type(i) is not int for i in data["sample_indices"])
            or data["time_s"] != times or data["model"] != {"gamma_s_inv":p[0], "omega_0_rad_s":p[1]}):
        raise ValueError("RHS sampling or model mismatch")
    for value in data["model"].values():
        finite_number(value)
    for name in ("dq_m_s", "dv_m_s2", "time_s"):
        values = data[name]
        if not isinstance(values, list) or len(values) != len(indices):
            raise ValueError("RHS output length mismatch")
        for value in values:
            finite_number(value)
    checked_digest(data["library_sha256"])
    checked_digest(data["source_sha256"])
    if data["origin"] != "computed_model_output" or data["verification"] != "not_verified":
        raise ValueError("RHS payload cannot confer measurement or verification")


def operation(kernel: OscillatorKernel):
    """Construct a binding for an existing OperationRegistry; never auto-register."""
    from ..operations.registry import Operation
    return Operation(OPERATION, "backend", lambda run,p: evaluate_run(kernel,run,p), kernel.runtime_identity)
