"""Build an explicitly simulated calibration request for the CIW transport.

The default fixture uses the existing displacement assembly. ``--reservoirs``
emits two requests for separate simulated mass assemblies, one reading each.
They are fixture declarations, not calibrated physical weighing instruments.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from instrument_chain.ciw_adapter import OPERATION_ID, REQUEST_SCHEMA
from instrument_chain.manifest import default_assembly_path, loads
from instrument_chain.observation import acquire_or_unavailable


def request(assembly_toml: str, readings: list[float], session: str) -> dict:
    assembly = loads(assembly_toml)
    records = []
    for sequence, raw in enumerate(readings):
        observation = acquire_or_unavailable(
            assembly=assembly, session_id=session, sequence=sequence,
            device_ticks=sequence, raw=raw,
        )
        raw_bytes = (json.dumps(observation.as_dict(), indent=2) + "\n").encode("utf-8")
        records.append({
            "raw_record_b64": base64.b64encode(raw_bytes).decode("ascii"),
            "observed_at": "2026-01-15T12:00:00Z",
        })
    return {
        "schema": REQUEST_SCHEMA, "operation_id": OPERATION_ID,
        "inputs": {
            "assembly_toml": assembly_toml,
            "calibration": {
                "schema": "rci-calibration-binding.v1", "calibration_id": assembly.calibration.id,
                "assembly_id": assembly.assembly_id, "assembly_version": assembly.version,
                "installation_id": assembly.installation.id,
                "assembly_digest": hashlib.sha256(assembly_toml.encode("utf-8")).hexdigest(),
                "valid_from": "2026-01-01T00:00:00Z", "valid_until": "2026-02-01T00:00:00Z",
                "parameter_order": ["scale", "zero_raw"],
                "parameter_covariance": [[1e-10, 1e-7], [1e-7, 0.04]],
                "residual_correlation": "independent", "raw_parameter_independent": True,
            },
            "records": records,
            "raw_covariance": [[0.25 if i == j else 0.0 for j in range(len(readings))] for i in range(len(readings))],
        },
    }


def reservoir_requests() -> list[dict]:
    requests = []
    for name, raw in (("reservoir-1", 7000.0), ("reservoir-2", 3000.0)):
        declaration = f'''schema = "rci-assembly-v1"
assembly_id = "simulated-{name}-mass"
version = "1"
title = "Simulated reservoir mass fixture; no physical device or traceability claim"
[board]
id = "simulated-{name}-board"
model = "host-fixture"
revision = "1"
mcu = "none"
citation = "Declared synthetic CIW fixture"
[interface]
id = "simulated-{name}-interface"
kind = "simulated-counts"
electrical = "none; software fixture"
citation = "Declared synthetic CIW fixture"
[instrument]
id = "simulated-{name}-mass-sensor"
quantity = "mass"
unit = "kg"
principle = "simulated-linear-indication"
range_min = 0.0
range_max = 100.0
citation = "Declared synthetic CIW fixture"
[installation]
id = "simulated-{name}-installation"
asset = "{name}"
mount = "none; software fixture"
[calibration]
id = "simulated-{name}-calibration-v1"
method = "linear"
raw_unit = "count"
output_unit = "kg"
theta = [0.01, 0.0]
range_min = 0.0
range_max = 10000.0
sigma = 0.02
sigma_unit = "kg"
sigma_reason = "Declared independent synthetic residual standard uncertainty; not a physical calibration certificate"
citation = "Synthetic scale and zero with declared parameter covariance"
'''
        requests.append(request(declaration, [raw], f"simulated-{name}-acquisition"))
    return requests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reservoirs", action="store_true")
    args = parser.parse_args()
    result = reservoir_requests() if args.reservoirs else request(
        Path(default_assembly_path()).read_text(encoding="utf-8"), [100.0, 200.0], "ciw-simulated-displacement",
    )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
