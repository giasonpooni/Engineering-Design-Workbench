"""One observation. Identity is assigned at acquisition, not at MQTT publish.

Quality is four questions, not one GOOD flag.
A missing sample is unavailable. It is never the last value again.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .calibration import CalibrationError, apply_calibration
from .manifest import Assembly


class AcquisitionStatus(str, Enum):
    RECEIVED = "received"
    UNAVAILABLE = "unavailable"
    OVERRANGE = "overrange"
    CORRUPT = "corrupt"


class TimingStatus(str, Enum):
    DEVICE_CLOCK = "device_clock"
    READOUT_ONLY = "readout_only"
    UNKNOWN = "unknown"


class CalibrationStatus(str, Enum):
    APPLICABLE = "applicable"
    UNSUPPORTED_RANGE = "unsupported_range"
    CHANGED_INSTALLATION = "changed_installation"
    NONE = "none"


class InferenceStatus(str, Enum):
    NOT_RUN = "not_run"
    UPDATED = "updated"
    PREDICTION_ONLY = "prediction_only"
    OUTSIDE_MODEL = "outside_model"


@dataclass(frozen=True)
class Quality:
    acquisition: AcquisitionStatus
    timing: TimingStatus
    calibration: CalibrationStatus
    inference: InferenceStatus = InferenceStatus.NOT_RUN

    def as_dict(self) -> dict[str, str]:
        return {
            "acquisition": self.acquisition.value,
            "timing": self.timing.value,
            "calibration": self.calibration.value,
            "inference": self.inference.value,
        }


@dataclass(frozen=True)
class Observation:
    """A bounded record produced by the acquisition path."""

    observation_id: str
    session_id: str
    sequence: int
    device_ticks: int
    timestamp_meaning: str
    assembly_id: str
    assembly_version: str
    calibration_id: str
    raw: float | None
    raw_unit: str
    indicated: float | None
    indicated_unit: str
    sigma: float | None
    sigma_unit: str
    sigma_reason: str
    quality: Quality

    def as_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "device_ticks": self.device_ticks,
            "timestamp_meaning": self.timestamp_meaning,
            "assembly_id": self.assembly_id,
            "assembly_version": self.assembly_version,
            "calibration_id": self.calibration_id,
            "raw": self.raw,
            "raw_unit": self.raw_unit,
            "indicated": self.indicated,
            "indicated_unit": self.indicated_unit,
            "sigma": self.sigma,
            "sigma_unit": self.sigma_unit,
            "sigma_reason": self.sigma_reason,
            "quality": self.quality.as_dict(),
        }


def observation_id(session_id: str, sequence: int) -> str:
    return f"{session_id}:{sequence}"


def acquire_or_unavailable(
    *,
    assembly: Assembly,
    session_id: str,
    sequence: int,
    device_ticks: int,
    raw: float | None,
    connected: bool = True,
    timestamp_meaning: str = "device_clock_at_readout",
) -> Observation:
    """Produce one record. Never invent a raw value."""
    if not connected or raw is None:
        return Observation(
            observation_id=observation_id(session_id, sequence),
            session_id=session_id,
            sequence=sequence,
            device_ticks=device_ticks,
            timestamp_meaning=timestamp_meaning,
            assembly_id=assembly.assembly_id,
            assembly_version=assembly.version,
            calibration_id=assembly.calibration.id,
            raw=None,
            raw_unit=assembly.calibration.raw_unit,
            indicated=None,
            indicated_unit=assembly.calibration.output_unit,
            sigma=None,
            sigma_unit=assembly.calibration.sigma_unit,
            sigma_reason=assembly.calibration.sigma_reason,
            quality=Quality(
                AcquisitionStatus.UNAVAILABLE,
                TimingStatus.DEVICE_CLOCK if timestamp_meaning.startswith("device_clock") else TimingStatus.READOUT_ONLY,
                CalibrationStatus.NONE,
            ),
        )
    try:
        indicated = apply_calibration(raw, assembly.calibration)
        cal_status = CalibrationStatus.APPLICABLE
        acq = AcquisitionStatus.RECEIVED
    except CalibrationError:
        indicated = None
        cal_status = CalibrationStatus.UNSUPPORTED_RANGE
        acq = AcquisitionStatus.OVERRANGE
    return Observation(
        observation_id=observation_id(session_id, sequence),
        session_id=session_id,
        sequence=sequence,
        device_ticks=device_ticks,
        timestamp_meaning=timestamp_meaning,
        assembly_id=assembly.assembly_id,
        assembly_version=assembly.version,
        calibration_id=assembly.calibration.id,
        raw=float(raw),
        raw_unit=assembly.calibration.raw_unit,
        indicated=indicated,
        indicated_unit=assembly.calibration.output_unit,
        sigma=assembly.calibration.sigma if indicated is not None else None,
        sigma_unit=assembly.calibration.sigma_unit,
        sigma_reason=assembly.calibration.sigma_reason,
        quality=Quality(
            acq,
            TimingStatus.DEVICE_CLOCK if timestamp_meaning.startswith("device_clock") else TimingStatus.READOUT_ONLY,
            cal_status,
        ),
    )
