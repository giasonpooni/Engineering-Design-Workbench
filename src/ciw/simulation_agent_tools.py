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


def descriptions():
    return [{"name": name, **deepcopy({k: v for k, v in item.items() if k != "method"})}
            for name, item in TOOLS.items()]


def validate_arguments(name, arguments):
    if type(name) is not str or name not in TOOLS:
        raise ValueError("Unknown stateful tool")
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
    _shape(data, spec)
    json_tree(arguments)
