"""Ephemeral, repository-allowlisted Git credentials for private CI providers.

Never writes a token to Git configuration, GITHUB_ENV, URLs, or artifacts.
The operator supplies a read-only selected-repository credential through the
CIW_PROVIDER_READ_TOKEN Actions secret. This does not grant permissions.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import sys

PROVIDERS = frozenset(name.lower() for name in (
    "Constraint-Based-State-Reconciliation", "Construction-State-Estimator-for-BIM",
    "Covariance-Geometry-and-Geodesic-Testbed", "Curved-Surface-Geodesic-Sensitivity-Runtime",
    "Evidence-and-State-Management", "Experiment-Design-Sensor-Placement-Testbed",
    "Fault-Detection-Isolation-Runtime", "Flat-Torus-Geodesic-Reference",
    "Fluid-State-Reconstruction-Testbed", "Geometric-State-Inference-Engine",
    "Geometric-Telemetry-Engine", "Geospatial-State-Visualization",
    "Instrument-Conformance-and-Replay-Harness", "Intrinsic-Surface-Geodesics-Testbed",
    "Jacobian-Sensitivity-Propagation-Testbed", "Metrological-Calibration-Uncertainty-Runtime",
    "Observability-Identifiability-Testbed", "Parameterized-Lyapunov-Stability-Runtime",
    "Provenance-Preserving-Data-Acquisition", "Retrofitted-Computational-Instrumentation",
    "Schematics-Retrieval-Agent", "Scientific-Computation-Runtime",
    "State-Estimation-Evaluation-Testbed", "Streaming-Telemetry-Feature-Extraction",
    "System-Identification-Dynamics-Testbed", "Time-Base-Reconciliation-Runtime",
    "Translation-Surface-Dynamics-Explorer", "Yield-Weighted-Inference-Runtime",
    # Verified current names for the same providers; legacy slugs remain aliases.
    "Conformance-and-Replay-Retainer", "Notations-Calibration-Runtime",
    "Notations-ClockSync", "Notations-Compute-Runtime",
    "Notations-Data-Intake", "Notations-Estimator-Bench",
    "Notations-Estimator-for-BIM", "Notations-FaultSense-RunTime",
    "Notations-FlowState", "Notations-Linear-Dynamics-Testbed",
    "Notations-Metrology-Adapter", "Notations-Observability-Testbed",
    "Notations-Periodic-Space", "Notations-Real-Time-Globe",
    "Notations-Retrieval-Agent", "Notations-Sensitivity-Testbed",
    "Notations-SensorDesign-RunTime", "Notations-Signal-Processing-RunTime",
    "Notations-State-Inference-Engine", "Notations-State-Ledger",
    "Notations-State-Recompiler", "Notations-Surface-RunTime",
    "Notations-Telemetry-Engine", "Notations-Yield-Weighted-Runtime",
    "Polygon-Trajectory-Experiments",
))
TOKEN_ENV = "CIW_PROVIDER_READ_TOKEN"


def read_token() -> str:
    token = os.environ.get(TOKEN_ENV, "")
    if not token or len(token) > 4096 or any(c.isspace() for c in token):
        raise ValueError("Private provider qualification requires the read-only CIW_PROVIDER_READ_TOKEN secret; no credentials were configured and no tests were qualified")
    return token


def credential(request: str, token: str) -> str:
    """Answer only Git's HTTPS credential protocol for declared provider repos."""
    if len(request) > 8192:
        return ""
    fields = {}
    for line in request.splitlines():
        if not line:
            break
        key, sep, value = line.partition("=")
        if not sep or key in fields:
            return ""
        fields[key] = value
    if fields.get("protocol") != "https" or fields.get("host") != "github.com":
        return ""
    path = fields.get("path", "")
    if not re.fullmatch(r"atomtrapping/[A-Za-z0-9_.-]+", path, re.IGNORECASE):
        return ""
    owner, name = path.lower().split("/", 1)
    if name.removesuffix(".git") not in PROVIDERS:
        return ""
    if fields.get("username", "x-access-token") != "x-access-token":
        return ""
    if not token or len(token) > 4096 or any(c.isspace() for c in token):
        return ""
    return "username=x-access-token\npassword=" + token + "\n\n"


def configuration(helper: Path) -> dict[str, str]:
    path = helper.resolve().as_posix()
    if any(c in path for c in "\r\n"):
        raise ValueError("Invalid credential-helper path")
    return {
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_KEY_0": "credential.helper", "GIT_CONFIG_VALUE_0": "",
        "GIT_CONFIG_KEY_1": "credential.helper",
        "GIT_CONFIG_VALUE_1": "!python " + shlex.quote(path) + " credential",
        "GIT_CONFIG_KEY_2": "credential.useHttpPath", "GIT_CONFIG_VALUE_2": "true",
        "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never",
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if args and args[0] == "credential":
            # Git adds get/store/erase. Never retain credentials on store/erase.
            if args != ["credential", "get"]:
                return 0
            request = sys.stdin.read(8193)
            sys.stdout.write(credential(request, read_token()))
            return 0
        if args != ["configure"]:
            raise ValueError("Use configure or the Git credential protocol")
        read_token()
        if os.environ.get("GITHUB_ACTIONS") != "true":
            raise ValueError("CI credential configuration is restricted to GitHub Actions")
        event, ref = os.environ.get("GITHUB_EVENT_NAME"), os.environ.get("GITHUB_REF")
        if event != "workflow_dispatch" and not (event == "push" and (ref == "refs/heads/main" or (ref or "").startswith("refs/tags/"))):
            raise ValueError("Private credentials are not enabled for pull-request or unreviewed push jobs")
        if os.environ.get("GIT_CONFIG_COUNT") not in (None, "", "0"):
            raise ValueError("Refuse to overwrite existing process Git configuration")
        destination = os.environ.get("GITHUB_ENV")
        if not destination:
            raise ValueError("Missing Actions environment file")
        values = configuration(Path(__file__))
        with Path(destination).open("a", encoding="utf-8", newline="\n") as stream:
            for key, value in values.items():
                stream.write(key + "=" + value + "\n")
        print("Configured ephemeral read-only provider credential transport; actual checkout and qualification still required")
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
