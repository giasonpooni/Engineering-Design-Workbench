"""Installed optional tools for the existing NET MCP server; no policy from agents."""
from copy import deepcopy
from .agent_tools import STRING, OBJECT, tool, _shape
from .control_contracts import json_tree

EXPECTED = {"type": "object", "properties": {
    "owner_id": STRING, "revision": {"type": "integer", "minimum": 0, "maximum": 2**53},
    "state_revision": {"type": "integer", "minimum": 0, "maximum": 2**53}},
    "required": ["owner_id", "revision", "state_revision"], "additionalProperties": False}
TOOLS = {
    "net_sim_create": tool("create", "Attach one fresh provider from an operator-bound model preset. No path, executable or model parameters are accepted. Attachment is not a simulation execution. Use the same attempt to retry.",
        {"model": STRING, "attempt": STRING}, ("model", "attempt"), read=False, external=True),
    "net_sim_inspect": tool("inspect", "Read last captured instance metadata and the exact owner/control/state revision fence. Does not call the provider or expose snapshots. Metadata may be unknown after failure.",
        {"instance": STRING}, ("instance",)),
    "net_sim_command": tool("command", "Dispatch one lifecycle command through existing SimulationControl. Always supply the previously inspected fence. step/observe/intervene require an operator-approved preset; other actions require preset null. Same attempt and complete request retries without execution. Observation streams feed net_observe/net_compare; checkpoints return opaque handles, not native bytes.",
        {"instance": STRING, "attempt": STRING, "expected": EXPECTED,
         "action": STRING, "preset": {"anyOf": [STRING, {"type": "null"}]}},
        ("instance", "attempt", "expected", "action", "preset"), read=False, external=True),
    "net_sim_branch": tool("branch", "Restore an opaque checkpoint captured by this host into a fresh instance from the same bound factory. Never changes the parent. Same attempt retries; no snapshot, runtime or factory is selected from agent data.",
        {"checkpoint": STRING, "attempt": STRING}, ("checkpoint", "attempt"), read=False, external=True),
}
REPLAY_TOOL = "net_sim_replay"
TOOLS[REPLAY_TOOL] = tool("replay",
    "Explicitly reproduce the contiguous accepted history from a host-captured paused checkpoint to the inspected paused/stopped source boundary, on a fresh owner. Supply the source instance fence and a new attempt for new execution. Same attempt/request returns its earlier receipt. Requires an operator replay grant; no supplied commands, paths, snapshots or tolerance edits. Returns bounded original replay outcome and latest replay observation streams, not raw checkpoints or full reports. PASS applies only to these executed commands; it is not physical verification. net_replay remains the separate analysis-graph tool.",
    {"checkpoint": STRING, "instance": STRING, "expected": EXPECTED, "attempt": STRING},
    ("checkpoint", "instance", "expected", "attempt"), read=False, external=True)


CAMPAIGN_TOOL = "net_sim_campaign"
TOOLS[CAMPAIGN_TOOL] = tool("campaign",
    "Run an explicitly operator-granted intervention campaign from one host-captured paused checkpoint. "
    "Supply source instance/fence, named campaign template and attempt. Each variant gets a fresh owner; "
    "the existing campaign runner/comparator retain original outcomes and occurrences. "
    "No command list, parameters, paths or tolerance edits. Same attempt/request retries without work. "
    "Full plans/checkpoints/reports stay operator-side; responses expose outcomes and typed observation handles. "
    "Completed campaigns may contain PASS, FAIL or INDETERMINATE; there is no ranking or physical approval.",
    {"checkpoint": STRING, "instance": STRING, "expected": EXPECTED, "campaign": STRING, "attempt": STRING},
    ("checkpoint", "instance", "expected", "campaign", "attempt"), read=False, external=True)


CAPTURE_TOOL = "net_sim_capture"
TOOLS[CAPTURE_TOOL] = tool("capture",
    "Render an exact host-disclosed observation handle through the existing PNG capture operation. "
    "Select a granted camera and sample_index, or null for an explicitly empty batch. "
    "Requires recorded XYZ, never reconstructs missing axes from checkpoints. "
    "No paths, coordinates, provider choices or renderer parameters. Source simulation is not called. "
    "Same attempt/request retries without rendering. Small PNGs also return as MCP image content; "
    "larger images remain original operator-bundle artifacts with explicit metadata-only delivery.",
    {"observation": STRING, "camera": STRING, "sample_index": {"anyOf": [
        {"type": "integer", "minimum": 0, "maximum": 255}, {"type": "null"}]}, "attempt": STRING},
    ("observation", "camera", "sample_index", "attempt"), read=False, external=True)


def descriptions(*, include_replay=False, include_campaign=False, include_capture=False):
    return [{"name": name, **deepcopy({k: v for k, v in item.items() if k != "method"})}
            for name, item in TOOLS.items() if (include_replay or name != REPLAY_TOOL) and (include_campaign or name != CAMPAIGN_TOOL) and (include_capture or name != CAPTURE_TOOL)]


def validate_arguments(name, arguments, *, include_replay=False, include_campaign=False, include_capture=False):
    if type(name) is not str or name not in TOOLS:
        raise ValueError("Unknown stateful tool")
    if name == REPLAY_TOOL and not include_replay:
        raise ValueError("Simulation replay was not granted by the operator")
    if name == CAMPAIGN_TOOL and not include_campaign:
        raise ValueError("Simulation campaigns were not granted by the operator")
    if name == CAPTURE_TOOL and not include_capture:
        raise ValueError("Image capture was not granted by the operator")
    # The existing shape guard supports its original subset, without null.
    # Validate the one nullable field here and use the original guard unchanged.
    spec = deepcopy(TOOLS[name]["inputSchema"])
    data = deepcopy(arguments)
    if name == "net_sim_command":
        if type(data) is not dict or "preset" not in data:
            raise ValueError("An explicit preset or null is required")
        value = data.pop("preset")
        if value is not None:
            _shape(value, STRING)
        spec["properties"].pop("preset")
        spec["required"].remove("preset")
    if name == CAPTURE_TOOL:
        if type(data) is not dict or "sample_index" not in data:
            raise ValueError("An explicit sample index or null is required")
        value = data.pop("sample_index")
        if value is not None:
            _shape(value, {"type": "integer", "minimum": 0, "maximum": 255})
        spec["properties"].pop("sample_index")
        spec["required"].remove("sample_index")
    _shape(data, spec)
    json_tree(arguments)
