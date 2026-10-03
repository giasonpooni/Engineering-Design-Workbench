"""Read-only integration roadmap; not an executable plugin loader.

Disposition is scoped to this slice, not a claim about upstream capability.
Code, observations, evidence, verification and scene identities remain separate.
"""
from copy import deepcopy

# Operator intent and repository ownership, not automatic discovery or installation.
_TARGETS = (
    ("gsc.local-frame", "world", "GSC", "binding_required", "gsc.local-frame.v1", "tools/ciw-local-frame/worker.py"),
    ("ciw.oscillator", "science", "NET", "builtin", "statistics.v1", "ciw.adapters.oscillator"),
    ("openusd", "representation", "NET/GSC", "optional_export", None, "ciw.spatial_scene"),
    ("blender", "authoring", "Blender", "planned", None, None),
    ("godot.spatial-inspector", "inspection", "Godot/NET", "optional_inspection", None, "ciw.spatial_godot"),
    ("godot", "runtime", "Godot", "planned", None, None),
    ("bevy", "runtime", "Bevy", "planned", None, None),
    ("gdal", "world", "GSC", "planned", None, None),
    ("pdal", "world", "GSC", "planned", None, None),
    ("postgis", "world", "GSC", "planned", None, None),
    ("routing", "world", "GSC", "planned", None, None),
    ("sciml", "science", "SCR/provider", "planned", None, None),
    ("networkx", "science", "provider", "planned", None, None),
    ("pymc", "science", "provider", "planned", None, None),
    ("lammps", "science", "provider", "planned", None, None),
    ("hoomd-blue", "science", "provider", "planned", None, None),
    ("veros", "science", "provider", "planned", None, None),
    ("lotusim", "science", "provider", "planned", None, None),
    ("mesa", "science", "provider", "planned", None, None),
    ("qwen-code", "agent", "agent worker", "planned", None, None),
    ("kimi-code", "agent", "agent worker", "planned", None, None),
    ("openllmetry", "observability", "telemetry", "planned", None, None),
    ("graphiti", "context", "context provider", "planned", None, None),
    ("shinkaevolve", "research", "experiment worker", "research", None, None),
)


def catalog():
    return {"schema": "ciw.provider-roadmap.v1", "scope": "local-frame-first-slice",
            "authorizes_execution": False, "qualification": "not_performed_by_listing",
            "note": "Read alongside ciw capabilities and existing profile docs; not a replacement registry.",
            "providers": [dict(zip(("provider_id", "kind", "owner", "disposition", "operation_id", "adapter"), row),
                              authorizes_execution=False) for row in deepcopy(_TARGETS)]}
