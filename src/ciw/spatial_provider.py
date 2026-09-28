"""GSC adapter on the existing pinned subprocess and operation registry seams."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
from .adapters.subprocess import PinnedSubprocessAdapter
from .operations.registry import Operation, default_registry
from .spatial_records import OPERATION, SCHEMA, request
from .core.identities import content_identity


def bind(gsc_root: Path, revision: str, *, python_executable=sys.executable):
    # Only explicit trusted operator configuration creates this binding.
    # Saved workspace fields cannot bind executable paths or providers.
    adapter = PinnedSubprocessAdapter(gsc_root, revision, "worker",
        source_root="tools/ciw-local-frame", python_executable=python_executable,
        timeout_seconds=20, max_output_bytes=2*1024*1024)

    def execute(run, parameters):
        inputs, indices = request(run, parameters)
        output = adapter.invoke(OPERATION, inputs)
        if output.get("schema") != "gsc.local-frame-output.v1":
            raise ValueError("Unexpected GSC local-frame response")
        data = deepcopy(output)
        data.update(schema=SCHEMA, source_evidence_id=run["evidence_id"], sample_indices=indices,
                    time_s=[run["time_s"][i] for i in indices],
                    entity_id=run["metadata"]["spatial"]["entity_id"],
                    frame_id="local-enu:" + content_identity(inputs["origin"]))
        return data

    def identity():
        return {**adapter.runtime_identity(), "provider": "gsc.local-frame",
                "capability": OPERATION, "pyproj_required": "3.7.2", "authority": "representation_only"}

    registry = default_registry()
    registry.register(Operation(OPERATION, "backend", execute, identity))
    return registry
