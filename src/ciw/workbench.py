"""Shared retained sources and native instrument results for one CIW session.

This catalog does not estimate state. GSIE's retained posterior and conditional
prediction remain separate, explicitly selected contexts. Repository bindings
are trusted process configuration and never enter the saved workspace.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import RLock

from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import _json
DECLARED_KINDS = frozenset({"schematic-assessment", "numerical-heat", "proved-heat", "schematic-companions", "bim-quantity", "acquired-dataset", "residual-monitor", "measurement-chain", "geometric-circle", "identified-stability", "flat-torus-reference", "curved-path-transfer", "covariance-geometry", "mesh-path", "translation-flow", "variational-free-energy", "energy-accuracy", "instrument-exchange", "thermal-observer", "machine-manifest", "project-graph", "julia-oscillator", "native-interop"})
REPRODUCED_KINDS = DECLARED_KINDS - {"proved-heat"}
UPSTREAM_KINDS = {"identified-design": "calibrated-observable", "schematic-companions": "schematic-assessment",
                  "acquired-calibrated-window": "acquired-dataset", "identified-stability": "identified-design"}
INSTRUMENT_ROLES = frozenset({"ppda", "tbrt", "mcur", "stfe", "gsie", "cbsr", "fdir", "oit", "sra", "scr", "cse", "rci", "fsrt", "jspt", "gte", "plsr", "ftr", "csg", "cggt", "isgt", "tsde", "energy", "exchange", "thermal", "machine", "project", "julia"})

SCHEMA = "ciw.retained-workbench.v1"
SOURCE_SCHEMA = "ciw.workbench-source.v1"
OPERATIONS = {
    "calibrated-observable": "ciw.calibrated-observable.v1",
    "identified-design": "ciw.identified-design.v1",
    "telemetry": "ciw.telemetry.v1",
    "calibrated-window": "ciw.calibrated-window.v1",
    "schematic-assessment": "ciw.schematic-assessment.v1",
    "numerical-heat": "ciw.numerical-heat.v1",
    "proved-heat": "ciw.proved-heat.v1",
    "schematic-companions": "ciw.schematic-companions.v1",
    "bim-quantity": "ciw.bim-quantity.v1",
    "acquired-dataset": "ciw.acquired-dataset.v1",
    "acquired-calibrated-window": "ciw.acquired-calibrated-window.v1",
    "residual-monitor": "ciw.residual-monitor.v1",
    "measurement-chain": "ciw.measurement-chain.v1",
    "geometric-circle": "ciw.geometric-circle.v1",
    "identified-stability": "ciw.identified-stability.v1",
    "flat-torus-reference": "ciw.flat-torus-reference.v1",
    "curved-path-transfer": "ciw.curved-path-transfer.v1",
    "covariance-geometry": "ciw.covariance-geometry.v1",
    "mesh-path": "ciw.mesh-path.v1",
    "translation-flow": "ciw.translation-flow.v1",
    "variational-free-energy": "ciw.variational-free-energy.v1",
    "energy-accuracy": "ciw.energy-accuracy.v1",
    "instrument-exchange": "ciw.instrument-exchange.v1",
    "thermal-observer": "ciw.thermal-observer.v1",
    "machine-manifest": "ciw.encoder-position.v1",
    "project-graph": "ciw.project-graph.v1",
    "julia-oscillator": "ciw.julia-oscillator.v1",
    "native-interop": "ciw.native-interop.v1",
}
WORKFLOW_OPERATION_IDS = frozenset(OPERATIONS.values())
from .candidate_evidence import OPERATIONS as CANDIDATE_OPERATIONS
WORKBENCH_OPERATION_IDS = WORKFLOW_OPERATION_IDS | CANDIDATE_OPERATIONS.keys()
MAX_SOURCES = 64
MAX_BUNDLES = 128
MAX_BYTES = 64 * 1024 * 1024
_OVERHEAD = 4096


def _workflow(kind):
    if kind == "native-interop":
        from .native_interop import NativeInteropWorkflow
        return NativeInteropWorkflow()
    if kind == "machine-manifest":
        from .machine_workflow import MachineManifestWorkflow
        return MachineManifestWorkflow()
    if kind == "project-graph":
        from .project_workflow import ProjectGraphWorkflow
        return ProjectGraphWorkflow()
    if kind == "thermal-observer":
        from .thermal_workflow import ThermalWorkflow
        return ThermalWorkflow()
    if kind == "julia-oscillator":
        from .julia_oscillator import JuliaOscillatorWorkflow
        return JuliaOscillatorWorkflow()
    if kind == "instrument-exchange":
        from . import exchange_adapter
        return exchange_adapter
    if kind == "energy-accuracy":
        from .energy_workflow import EnergyAccuracyWorkflow()
        return EnergyAccuracyWorkflow()
    raise ValueError("INCOMPLETE_STUB_DO_NOT_LAND")
