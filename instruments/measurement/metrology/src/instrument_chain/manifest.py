"""Versioned instrument assembly: board, interface, instrument, installation, calibration.

These are four software responsibilities plus a calibration object. They are
not four services. A misspelled key is an error. Electrical compatibility
is declared, never inferred from the existence of a pin name.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "rci-assembly-v1"

_TOP = {"schema", "assembly_id", "version", "title", "board", "interface", "instrument", "installation", "calibration"}
_BOARD = {"id", "model", "revision", "mcu", "citation", "notes"}
_INTERFACE = {"id", "kind", "electrical", "citation", "notes"}
_INSTRUMENT = {"id", "quantity", "unit", "principle", "range_min", "range_max", "citation", "notes"}
_INSTALL = {"id", "asset", "mount", "notes"}
_CAL = {"id", "method", "raw_unit", "output_unit", "theta", "range_min", "range_max", "sigma", "sigma_unit", "sigma_reason", "citation", "notes"}
_METHODS = {"linear", "affine"}


def _str(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be a non-empty string, got {value!r}")
    return value.strip()


def _float(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number, got {value!r}")
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{what} must be finite, got {value!r}")
    return value


def _table(value, what: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be a table, got {type(value).__name__}")
    return value


def _only(table: dict, allowed: set[str], what: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ValueError(f"{what} has unknown key(s) {unknown}; allowed: {sorted(allowed)}")


@dataclass(frozen=True)
class BoardProfile:
    id: str
    model: str
    revision: str
    mcu: str
    citation: str
    notes: str


@dataclass(frozen=True)
class InterfaceProfile:
    id: str
    kind: str
    electrical: str
    citation: str
    notes: str


@dataclass(frozen=True)
class InstrumentProfile:
    id: str
    quantity: str
    unit: str
    principle: str
    range_min: float
    range_max: float
    citation: str
    notes: str


@dataclass(frozen=True)
class InstallationBinding:
    id: str
    asset: str
    mount: str
    notes: str


@dataclass(frozen=True)
class Calibration:
    id: str
    method: str
    raw_unit: str
    output_unit: str
    theta: tuple[float, ...]
    range_min: float
    range_max: float
    sigma: float
    sigma_unit: str
    sigma_reason: str
    citation: str
    notes: str


@dataclass(frozen=True)
class Assembly:
    assembly_id: str
    version: str
    title: str
    board: BoardProfile
    interface: InterfaceProfile
    instrument: InstrumentProfile
    installation: InstallationBinding
    calibration: Calibration

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "assembly_id": self.assembly_id,
            "version": self.version,
            "title": self.title,
            "board_id": self.board.id,
            "interface_id": self.interface.id,
            "instrument_id": self.instrument.id,
            "installation_id": self.installation.id,
            "calibration_id": self.calibration.id,
        }


def _parse_board(t: dict) -> BoardProfile:
    _only(t, _BOARD, "board")
    return BoardProfile(
        _str(t.get("id"), "board.id"),
        _str(t.get("model"), "board.model"),
        _str(t.get("revision"), "board.revision"),
        _str(t.get("mcu"), "board.mcu"),
        _str(t.get("citation"), "board.citation"),
        _str(t.get("notes", "-"), "board.notes"),
    )


def _parse_interface(t: dict) -> InterfaceProfile:
    _only(t, _INTERFACE, "interface")
    return InterfaceProfile(
        _str(t.get("id"), "interface.id"),
        _str(t.get("kind"), "interface.kind"),
        _str(t.get("electrical"), "interface.electrical"),
        _str(t.get("citation"), "interface.citation"),
        _str(t.get("notes", "-"), "interface.notes"),
    )


def _parse_instrument(t: dict) -> InstrumentProfile:
    _only(t, _INSTRUMENT, "instrument")
    lo = _float(t.get("range_min"), "instrument.range_min")
    hi = _float(t.get("range_max"), "instrument.range_max")
    if hi <= lo:
        raise ValueError("instrument range_max must exceed range_min")
    return InstrumentProfile(
        _str(t.get("id"), "instrument.id"),
        _str(t.get("quantity"), "instrument.quantity"),
        _str(t.get("unit"), "instrument.unit"),
        _str(t.get("principle"), "instrument.principle"),
        lo, hi,
        _str(t.get("citation"), "instrument.citation"),
        _str(t.get("notes", "-"), "instrument.notes"),
    )


def _parse_install(t: dict) -> InstallationBinding:
    _only(t, _INSTALL, "installation")
    return InstallationBinding(
        _str(t.get("id"), "installation.id"),
        _str(t.get("asset"), "installation.asset"),
        _str(t.get("mount"), "installation.mount"),
        _str(t.get("notes", "-"), "installation.notes"),
    )


def _parse_cal(t: dict) -> Calibration:
    _only(t, _CAL, "calibration")
    method = _str(t.get("method"), "calibration.method")
    if method not in _METHODS:
        raise ValueError(f"calibration.method must be one of {sorted(_METHODS)}, got {method!r}")
    theta_raw = t.get("theta")
    if not isinstance(theta_raw, list) or not theta_raw:
        raise ValueError("calibration.theta must be a non-empty array of numbers")
    theta = tuple(_float(v, f"calibration.theta[{i}]") for i, v in enumerate(theta_raw))
    if method == "linear" and len(theta) != 2:
        raise ValueError("linear calibration theta is (scale, zero_raw)")
    if method == "affine" and len(theta) != 2:
        raise ValueError("affine calibration theta is (scale, offset)")
    lo = _float(t.get("range_min"), "calibration.range_min")
    hi = _float(t.get("range_max"), "calibration.range_max")
    if hi <= lo:
        raise ValueError("calibration range_max must exceed range_min")
    sigma = _float(t.get("sigma"), "calibration.sigma")
    if sigma < 0:
        raise ValueError("calibration.sigma must be >= 0")
    return Calibration(
        _str(t.get("id"), "calibration.id"),
        method,
        _str(t.get("raw_unit"), "calibration.raw_unit"),
        _str(t.get("output_unit"), "calibration.output_unit"),
        theta, lo, hi,
        sigma,
        _str(t.get("sigma_unit"), "calibration.sigma_unit"),
        _str(t.get("sigma_reason"), "calibration.sigma_reason"),
        _str(t.get("citation"), "calibration.citation"),
        _str(t.get("notes", "-"), "calibration.notes"),
    )


def loads(text: str) -> Assembly:
    data = tomllib.loads(text)
    _only(data, _TOP, "assembly")
    schema = _str(data.get("schema"), "schema")
    if schema != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA!r}, got {schema!r}")
    return Assembly(
        _str(data.get("assembly_id"), "assembly_id"),
        _str(data.get("version"), "version"),
        _str(data.get("title"), "title"),
        _parse_board(_table(data.get("board"), "board")),
        _parse_interface(_table(data.get("interface"), "interface")),
        _parse_instrument(_table(data.get("instrument"), "instrument")),
        _parse_install(_table(data.get("installation"), "installation")),
        _parse_cal(_table(data.get("calibration"), "calibration")),
    )


def load_assembly(path: str | Path) -> Assembly:
    return loads(Path(path).read_text(encoding="utf-8"))


def default_assembly_path() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        Path.cwd() / "declarations" / "assembly_v1.toml",
        here.parents[2] / "declarations" / "assembly_v1.toml",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("declarations/assembly_v1.toml not found")
