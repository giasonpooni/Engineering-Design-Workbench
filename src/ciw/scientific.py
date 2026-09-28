"""Thin NET entry points for the scientific workflows already owned by Session.

No provider algorithms, new operation identities, runtime pins, or second DAG.
Host bindings are explicit arguments; sources and saved workspaces cannot bind code.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import tempfile
import uuid

from .adapters.protocol import AdapterRefusal
from .control_contracts import detached, load, save_new, text
from .workbench import OPERATIONS, Workbench, _source

# Navigation only. Executable roles, pins, requests, links, verification and replay
# remain in the existing Workbench and workflow modules. This table loads no engine.
_ROUTES = {
    "measurement-chain": (("measure", "calibrate", "estimate", "covariance"), ("RCI", "FSRT", "JSPT")),
    "calibrated-observable": (("time", "calibrate", "observe", "estimate", "diagnose"), ("TBRT", "MCUR", "OIT", "FSRT", "GSIE", "CBSR", "FDIR", "SET")),
    "identified-design": (("identify", "design", "budget"), ("SIDT", "EDSPT", "YWIR")),
    "telemetry": (("acquire", "features", "estimate", "evaluate"), ("PPDA", "STFE", "GSIE", "SET", "CBSR")),
    "calibrated-window": (("time", "calibrate", "features", "estimate"), ("TBRT", "MCUR", "STFE", "GSIE", "SET")),
    "acquired-calibrated-window": (("acquire", "calibrate", "features", "estimate"), ("PPDA", "TBRT", "MCUR", "STFE", "GSIE", "SET")),
    "acquired-dataset": (("acquire",), ("PPDA",)),
    "residual-monitor": (("diagnose",), ("FDIR",)),
    "schematic-assessment": (("retrieve", "eligibility"), ("SRA",)),
    "schematic-companions": (("sensitivity", "certificate"), ("SRA", "JSPT", "PLSR")),
    "bim-quantity": (("bim", "estimate"), ("CSE",)),
    "identified-stability": (("certificate", "stability"), ("PLSR",)),
    "geometric-circle": (("geometry", "covariance"), ("GTE",)),
    "flat-torus-reference": (("geometry", "reference"), ("FTR",)),
    "curved-path-transfer": (("geometry", "sensitivity", "covariance"), ("CSR",)),
    "covariance-geometry": (("geometry", "covariance"), ("CGGT",)),
    "mesh-path": (("geometry", "path"), ("ISGT",)),
    "translation-flow": (("geometry", "dynamics"), ("TSDE",)),
    "numerical-heat": (("compute",), ("SCR",)),
    "native-interop": (("compute", "reference"), ("SCR",)),
    "instrument-exchange": (("conformance", "replay"), ("SET",)),
    "julia-oscillator": (("simulate", "reference"), ("Julia",)),
    "thermal-observer": (("estimate", "reference"), ("NET thermal reference",)),
}


def catalog(capability: str | None = None, *, session=None) -> dict:
    """Index existing dispatch, not discovery/qualification of installed providers."""
    workbench = Workbench() if session is None else session.workbench
    operations = {row["source_kind"]: row for row in workbench.describe_operations()
                  if "source_kind" in row}
    if not set(_ROUTES) <= operations.keys():
        raise RuntimeError("Scientific navigation references a missing Workbench operation")
    entries = []
    for kind, (capabilities, instruments) in _ROUTES.items():
        if capability is None or capability in capabilities:
            entries.append({**operations[kind], "capabilities": list(capabilities),
                            "instrument_highlights": list(instruments), "qualification": "not_performed_by_catalog"})
    return {"schema": "ciw.scientific-navigation.v1", "operations": deepcopy(entries),
            "authorizes_execution": False, "binding_source": "explicit_host_configuration_only",
            "other_boundaries": {
                "GSC": "Read-only representation consumer; no browser integration is executed by this facade",
                "ESM": "Existing candidate/admission boundary; not automatically invoked",
                "ICRH": "Independent conformance/replay qualification; not the SET instrument-exchange validator",
                "Atelier-MCP/CNC-Machine-MCP": "No machine connection or motion authorization in this facade",
                "STAQNET": "No new corpus pipeline adapter claimed"}}


def _kind(value: str) -> str:
    if value not in _ROUTES:
        raise AdapterRefusal("scientific_workflow_unavailable", "Select an indexed scientific workflow")
    return value


def request(session, kind: str, payload: dict) -> dict:
    response = session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex,
                               "type": kind, "payload": deepcopy(payload)})
    if response["type"] == "error":
        raise AdapterRefusal(response["payload"]["code"], response["payload"]["message"])
    return response["payload"]


def source_payload(kind: str, raw: bytes, label: str) -> dict:
    _kind(kind)
    if type(raw) is not bytes or not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError("Scientific source requires 1..2097152 exact bytes")
    payload = {"kind": kind, "label": text(label), "bytes_b64": base64.b64encode(raw).decode("ascii")}
    _source(payload)  # Existing source-specific validation, before any provider probe.
    return payload


def bind(session, kind: str, repositories: dict[str, Path | str]) -> None:
    """Explicit operator paths only; retain the existing pin/closure validation."""
    _kind(kind)
    if type(repositories) is not dict:
        raise ValueError("Bindings must be an explicit role-to-path map")
    for role, path in repositories.items():
        text(role)
        if not isinstance(path, (str, Path)) or not str(path).strip() or not Path(path).is_absolute():
            raise ValueError("Use absolute paths for every explicit scientific binding")
    session.workbench.bind_workflow(kind, repositories)


def execute(session, kind: str, raw: bytes, *, label: str,
            repositories: dict | None = None, upstream_bundle_id: str | None = None,
            configuration: dict | None = None) -> dict:
    """Use existing source.add / operation.execute. No provider code copied here."""
    payload = source_payload(kind, raw, label)
    if repositories is not None:
        bind(session, kind, repositories)
    source = request(session, "source.add", payload)
    parameters = {"source_id": source["source_id"]}
    if upstream_bundle_id is not None:
        parameters["upstream_bundle_id"] = text(upstream_bundle_id)
    if configuration is not None:
        parameters["configuration"] = detached(configuration)
    return request(session, "operation.execute", {"operation_id": OPERATIONS[kind], "parameters": parameters})


def selected_bundle(session, bundle_id: str) -> dict:
    text(bundle_id)
    selected = [row for row in session.workbench.list_bundles() if row["bundle_id"] == bundle_id]
    if len(selected) != 1:
        raise ValueError("Select one exact retained bundle identity; no latest-result fallback")
    return selected[0]


def replay(session, bundle_id: str, *, repositories: dict | None = None) -> dict:
    selected = selected_bundle(session, bundle_id)
    _kind(selected["kind"])
    if repositories is not None:
        bind(session, selected["kind"], repositories)
    return request(session, "bundle.replay", {"bundle_id": bundle_id})


def inspect(session, *, bundle_id: str | None = None, instrument: str | None = None) -> dict:
    if bundle_id is None:
        if instrument is not None:
            raise ValueError("Instrument inspection requires an exact bundle identity")
        return {"schema": "ciw.scientific-inspection.v1", "bundles": session.workbench.list_bundles(),
                "instruments": session.workbench.instrument_views(),
                "failed_executions": session.workbench.failed_execution_summaries(),
                "runtime_launched": False, "state_admission": "not_performed"}
    selected_bundle(session, bundle_id)
    return request(session, "instrument.inspect" if instrument else "experiment.inspect",
                   {"bundle_id": bundle_id, **({"instrument": instrument} if instrument else {})})


@contextmanager
def open_workspace(path: Path, output_dir: Path | None = None, *, expected_sha256: str | None = None):
    """Freeze one bounded source read, validate offline, optionally copy for execution.

    A caller can inspect in scratch or extend a new output directory. The original
    is never written. Execution failures still save the existing Session's history.
    """
    from .session import Session
    value = load(path, expected_sha256=expected_sha256)
    with tempfile.TemporaryDirectory(prefix="net-science-") as temporary:
        root = Path(temporary)
        frozen = root / "workspace.json"
        save_new(frozen, value)
        checked = Session.from_workspace(frozen, root / "checked")
        if output_dir is None:
            yield checked
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=False)
            session = Session.from_workspace(frozen, output_dir)
            try:
                yield session
            finally:
                session.save_workspace(output_dir / "workspace.json")


def read_source(path: Path) -> bytes:
    with Path(path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError("Scientific source exceeds the facade's 2 MiB byte limit")
    return raw


def parse_bindings(values: list[str]) -> dict[str, Path]:
    result = {}
    for declaration in values:
        role, separator, raw = declaration.partition("=")
        if not separator or not role or not raw or role in result:
            raise ValueError("Each binding must be a unique ROLE=ABSOLUTE_PATH")
        path = Path(raw)
        if not path.is_absolute():
            raise ValueError("Each scientific binding must use an absolute path")
        result[role] = path
    return result


def heading_request(baseline_bundle_id: str, space, headings: list[float], *,
                    sample_index: int, limits: dict, study_id: str) -> dict:
    """Connect NET's parameter domain to the existing heading-only CSR study.

    This is not a new sweep/optimizer. Source physics, validity preflight,
    derivative comparison, covariance accounting and replay stay in that study.
    """
    from .control_plane import ParameterSpace
    from .curved_path_study import make_request
    if not isinstance(space, ParameterSpace):
        raise ValueError("Require an explicit NET ParameterSpace")
    specification = space.to_dict()["parameters"]
    if set(specification) != {"initial_heading_radian"} or specification["initial_heading_radian"]["unit"] != "radian":
        raise ValueError("This study accepts only initial_heading_radian with radian units")
    if type(headings) is not list or not 1 <= len(headings) <= 8:
        raise ValueError("Declare one to eight explicit headings")
    from .core.identities import content_identity
    if len({content_identity(value) for value in headings}) != len(headings):
        raise ValueError("Repeated headings require distinct explicit experiments, not duplicate study cases")
    candidates = [{"candidate_id": f"case-{i + 1:03d}",
                   **space.validate({"initial_heading_radian": value})} for i, value in enumerate(headings)]
    return make_request(baseline_bundle_id, candidates, sample_index=sample_index,
                        limits=limits, study_id=study_id)


def heading_study(session, study_request: dict, *, repositories: dict | None = None) -> dict:
    from .curved_path_study import _preflight, run_study
    # The existing provider-free study preflight checks every candidate before bind.
    _preflight(session.workbench, study_request)
    if repositories is not None:
        bind(session, "curved-path-transfer", repositories)
    return run_study(session.workbench, study_request)
