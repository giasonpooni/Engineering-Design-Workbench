"""Bounded temperature processing on NET's retained evidence and MCP path.

Copyright (c) 2026 Giason Pooni. SPDX-License-Identifier: AGPL-3.0-or-later
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import platform

import numpy as np

from .adapters.protocol import InstrumentManifest
from .control_contracts import keys
from .core.identities import evidence_id, validate_evidence_identity
from .core.records import validate_run_structure
from .operations.registry import Operation
from .operations.runner import digest
from .temperature_contract import validate_request

PROCESS = "metrology.temperature.process.v1"


def runtime_identity() -> dict:
    from . import temperature_contract, temperature_processing, control_contracts
    from .core import covariance, identities
    from .operations import runner
    modules = [temperature_contract, temperature_processing, control_contracts, covariance, identities,
               runner, __import__(__name__, fromlist=["*"])]
    raw = b"\0".join(Path(module.__file__).name.encode() + b"\0" +
                     Path(module.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                     for module in modules)
    return {"provider": "ciw.temperature", "version": "1", "code_sha256": sha256(raw).hexdigest(),
            "source_normalization": "utf8_lf", "scope": "declared_temperature_processing_only",
            "environment": {"python": platform.python_version(), "numpy": np.__version__,
                            "floating_point": "binary64"}}


def make_source(request: dict) -> dict:
    request = validate_request(request)
    manifest = InstrumentManifest(
        instrument_id="temperature-measurement-evidence.v1", role="retained_measurement_declaration",
        units={"measurement_declaration": "1"}, frames=("measurement-declaration",),
        sampling={"kind": "one_measurement_declaration", "time_semantics": "selection_envelope_only"},
        supported_operations=(PROCESS,),
        calibration_requirements={"temperature": "explicit affine calibration and declared covariance; physical qualification separate"})
    source = {"run_schema": "run.v1", "run_id": "run-temperature-" + digest(request)[7:23],
              "instrument": manifest.instrument_id,
              "metadata": {"duration_s": 1.0, "sample_count": 1, "sample_rate_hz": None,
                           "coordinate_frame": "measurement-declaration", "manifest": manifest.to_dict(),
                           "temperature_request": request,
                           "provenance": {"source": request["source_kind"],
                                          "generator": "ciw.temperature_workflow.make_source", "generator_version": 1}},
              "time_s": [0.0], "channels": {"measurement_declaration": {"unit": "1", "values": [1.0]}},
              "render": {}}
    source["evidence_id"] = evidence_id(source)
    return source


def source_request(source: dict) -> dict:
    validate_run_structure(source)
    validate_evidence_identity(source)
    request = validate_request(source["metadata"]["temperature_request"])
    if source != make_source(request):
        raise ValueError("Temperature source differs from its exact retained measurement declaration")
    return request


def _process(source: dict, parameters: dict) -> dict:
    from .temperature_processing import process_request
    keys(parameters, set())
    return process_request(source_request(source))


def operation() -> Operation:
    return Operation(PROCESS, "backend", _process, runtime_identity)


def capability_registry(*, bind: bool = False):
    from .control_plane import CapabilityRegistry
    value = CapabilityRegistry()
    manifest = InstrumentManifest(instrument_id=PROCESS, role="backend", units={}, frames=(),
        sampling={"kind": "retained_measurement_declaration"}, supported_operations=(PROCESS,),
        calibration_requirements={"authority": "conditional calculation; no physical qualification or proof"})
    value.advertise(manifest, runtime=runtime_identity(),
                    capabilities={PROCESS: ["metrology.temperature.process"]}, inputs={PROCESS: {}})
    if bind:
        value.bind(operation())
    return value


def validate_payload(operation_id: str, data: dict, run: dict, parameters: dict, selection: dict) -> None:
    from .temperature_processing import validate_report
    if operation_id != PROCESS:
        raise ValueError("Unsupported temperature operation")
    keys(parameters, set())
    if selection["channel"] != "measurement_declaration" or selection["interval_s"] != [0.0, 1.0]:
        raise ValueError("Temperature processing requires the complete measurement declaration")
    validate_report(source_request(run), data)
