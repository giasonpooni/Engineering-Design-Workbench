"""Bounded projectile experiment payloads; no engine imports or execution on read.

These payloads extend CIW operation results, not its execution/verification model.
This profile is a point mass in constant gravity with tick-addressed delta-v
inputs. It is not contact physics, a scene ontology, or a general game protocol.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
import re
import struct

MAX_BYTES = 8 * 1024 * 1024
SCENARIO = "ciw.projectile-scenario.v1"
AUTHOR = "ciw.projectile-asset.v1"
TRACE = "ciw.projectile-trace.v1"
COMPARE = "ciw.projectile-comparison.v1"
LANDMARKS = {"origin": [0, 0, 0], "axis_x": [1, 0, 0],
             "axis_y": [0, 2, 0], "axis_z": [0, 0, 3]}
POLICY = {"position_m": 0.1, "velocity_m_s": 0.0001}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def keys(value, expected, name):
    require(isinstance(value, dict) and set(value) == set(expected.split()),
            name + ": unexpected or missing fields")


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "finite number required")
    return float(value)


def vector(value):
    require(isinstance(value, list) and len(value) == 3, "three coordinates required")
    require(all(abs(number(x)) <= 1e6 for x in value), "coordinate budget exceeded")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def identity(value):
    require(isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value),
            "invalid content identity")
    return value


def parse(raw):
    require(len(raw) <= MAX_BYTES, "JSON exceeds byte budget")
    def pairs(items):
        obj = {}
        for key, value in items:
            require(key not in obj, "duplicate JSON key")
            obj[key] = value
        return obj
    def constant(value):
        raise ValueError("nonfinite JSON constant: " + value)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    # Also rejects exponent overflow (1e999) and non-JSON values.
    canonical(value)
    return value


def read(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    return parse(raw)


def validate_scenario(s):
    keys(s, "schema name model entity frame p0_m v0_m_s gravity_m_s2 mass_kg step_hz ticks inputs", "scenario")
    require(s["schema"] == SCENARIO and s["model"] == "point-projectile-no-contact.v1", "unsupported model")
    require(s["entity"] == "projectile" and s["frame"] == "local-y-up-m", "unsupported entity/frame")
    require(isinstance(s["name"], str) and 1 <= len(s["name"]) <= 120, "invalid scenario name")
    for key in ("p0_m", "v0_m_s", "gravity_m_s2"):
        vector(s[key])
        require(max(abs(x) for x in s[key]) <= 100, "initial-state budget exceeded")
    require(0 < number(s["mass_kg"]) <= 1e4, "invalid mass")
    require(type(s["step_hz"]) is int and 30 <= s["step_hz"] <= 1000, "invalid tick frequency")
    require(type(s["ticks"]) is int and 1 <= s["ticks"] <= 2000, "invalid tick count")
    require(s["ticks"] / s["step_hz"] <= 5, "duration exceeds five seconds")
    require(isinstance(s["inputs"], list) and len(s["inputs"]) <= 128, "input budget exceeded")
    ids, order = set(), []
    for event in s["inputs"]:
        keys(event, "id tick delta_v_m_s", "input")
        require(isinstance(event["id"], str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", event["id"]), "invalid input id")
        require(event["id"] not in ids, "duplicate input id")
        ids.add(event["id"])
        require(type(event["tick"]) is int and 1 <= event["tick"] <= s["ticks"], "invalid input tick")
        vector(event["delta_v_m_s"])
        require(max(abs(x) for x in event["delta_v_m_s"]) <= 100, "input budget exceeded")
        order.append((event["tick"], event["id"]))
    require(order == sorted(order), "inputs must be ordered by tick and id")
    return s


def validate_glb(raw):
    require(20 <= len(raw) <= 2 * 1024 * 1024, "GLB size budget")
    magic, version, length = struct.unpack_from("<4sII", raw)
    require(magic == b"glTF" and version == 2 and length == len(raw), "invalid GLB header")
    offset, chunks = 12, []
    while offset < len(raw):
        require(offset + 8 <= len(raw), "truncated GLB chunk")
        size, kind = struct.unpack_from("<II", raw, offset)
        offset += 8
        require(size % 4 == 0 and offset + size <= len(raw), "invalid GLB chunk size")
        chunks.append((kind, raw[offset:offset + size]))
        offset += size
    require(len(chunks) == 2 and [x[0] for x in chunks] == [0x4E4F534A, 0x004E4942], "require embedded JSON and BIN")
    doc = parse(chunks[0][1])
    require(doc.get("asset", {}).get("version") == "2.0", "unsupported glTF version")
    require(not doc.get("extensionsRequired"), "required glTF extensions unsupported")
    require(not doc.get("animations") and not doc.get("skins"), "animated/skinned assets unsupported")
    buffers = doc.get("buffers", [])
    require(len(buffers) == 1 and "uri" not in buffers[0], "external buffers unsupported")
    require(0 <= len(chunks[1][1]) - buffers[0]["byteLength"] <= 3, "BIN size mismatch")
    require(not doc.get("images"), "images/textures outside this asset profile")
    nodes = doc.get("nodes", [])
    require(5 <= len(nodes) <= 32, "node budget")
    roots = doc.get("scenes", [{}])[doc.get("scene", 0)].get("nodes", [])
    require(sorted(roots) == list(range(len(nodes))), "only flat root-node assets supported")
    for node in nodes:
        require(not node.get("children") and "matrix" not in node, "node hierarchy/matrix unsupported")
        require(node.get("rotation", [0,0,0,1]) == [0,0,0,1] and node.get("scale", [1,1,1]) == [1,1,1], "node rotation/scale unsupported")
    names = [node.get("name") for node in nodes]
    require(len(names) == len(set(names)), "duplicate node names")
    for name, expected in LANDMARKS.items():
        require(name in names, "missing landmark")
        node = nodes[names.index(name)]
        require(not node.get("children") and "matrix" not in node, "landmark hierarchy unsupported")
        actual = node.get("translation", [0, 0, 0])
        vector(actual)
        require(all(abs(a-b) < 1e-6 for a, b in zip(actual, expected)), "landmark frame/scale mismatch")
    require("projectile" in names, "missing projectile mesh")
    projectile = nodes[names.index("projectile")]
    require(projectile.get("translation", [0,0,0]) == [0,0,0], "projectile mesh must be origin-centred")
    require(type(projectile.get("mesh")) is int and 0 <= projectile["mesh"] < len(doc.get("meshes", [])), "projectile is not a mesh")
    return doc


def validate_asset(data):
    keys(data, "schema format asset_sha256 asset_b64 generator_sha256 report", "asset")
    require(data["schema"] == AUTHOR and data["format"] == "glb", "asset schema")
    identity(data["generator_sha256"])
    require(isinstance(data["asset_b64"], str) and len(data["asset_b64"]) <= 3 * 1024 * 1024, "asset encoding budget")
    raw = base64.b64decode(data["asset_b64"], validate=True)
    require(sha(raw) == identity(data["asset_sha256"]), "asset digest mismatch")
    validate_glb(raw)
    keys(data["report"], "blender_version export_y_up radius_m", "author report")
    require(isinstance(data["report"]["blender_version"], str) and data["report"]["blender_version"], "author version")
    require(data["report"]["export_y_up"] is True and data["report"]["radius_m"] == .25, "author configuration")
    return raw


def validate_request(request):
    keys(request, "schema scenario asset_sha256 nonce fault", "runtime request")
    require(request["schema"] == "ciw.projectile-request.v1", "runtime request schema")
    validate_scenario(request["scenario"])
    identity(request["asset_sha256"])
    require(re.fullmatch(r"[0-9a-f]{32}", str(request["nonce"])), "invalid request nonce")
    require(request["fault"] in ("none", "double-gravity"), "unsupported diagnostic fault")


def validate_trace(data):
    keys(data, "schema request trace", "trace result")
    require(data["schema"] == TRACE, "trace result schema")
    request, trace = data["request"], data["trace"]
    validate_request(request)
    s = request["scenario"]
    keys(trace, "engine engine_version state_owner clock phase request_sha256 asset_sha256 precision import_report observations events complete", "trace")
    require(trace["engine"] in ("godot", "bevy") and trace["state_owner"] == trace["engine"], "runtime state ownership")
    require(isinstance(trace["engine_version"], str) and trace["engine_version"], "missing engine version")
    require(trace["clock"] == "integer-ticks" and trace["phase"] == "initial_then_post_step", "clock/phase mismatch")
    require(trace["request_sha256"] == sha(canonical(request)), "request byte binding mismatch")
    require(trace["asset_sha256"] == request["asset_sha256"], "trace asset mismatch")
    require(trace["precision"] == {"godot": "Vector3-float32", "bevy": "f64"}[trace["engine"]], "precision mismatch")
    report = trace["import_report"]
    keys(report, "landmarks_m vertex_count bounds_min_m bounds_max_m", "import report")
    require(set(report["landmarks_m"]) == set(LANDMARKS), "landmark coverage mismatch")
    for name, expected in LANDMARKS.items():
        actual = vector(report["landmarks_m"][name])
        require(all(abs(a-b) < 1e-5 for a,b in zip(actual, expected)), "runtime frame/scale mismatch")
    require(type(report["vertex_count"]) is int and 20 <= report["vertex_count"] <= 10000, "invalid imported vertex count")
    for field, sign in (("bounds_min_m", -1), ("bounds_max_m", 1)):
        require(all(abs(x - sign*.25) < 1e-5 for x in vector(report[field])), "runtime mesh size mismatch")
    rows = trace["observations"]
    require(isinstance(rows, list) and 1 <= len(rows) <= s["ticks"] + 1, "trace length mismatch")
    for n, row in enumerate(rows):
        keys(row, "tick time_s entity p_m v_m_s", "observation")
        require(type(row["tick"]) is int and row["tick"] == n, "tick order/gap")
        require(abs(number(row["time_s"]) - n/s["step_hz"]) < 1e-9, "observation time mismatch")
        require(row["entity"] == s["entity"], "entity correspondence mismatch")
        require((row["p_m"] is None) == (row["v_m_s"] is None), "partial state missingness")
        if row["p_m"] is not None:
            vector(row["p_m"]); vector(row["v_m_s"])
    for field, initial in (("p_m", "p0_m"), ("v_m_s", "v0_m_s")):
        require(rows[0][field] is not None and all(abs(a-b) < 1e-5 for a,b in zip(rows[0][field], s[initial])), "initial state mismatch")
    expected_events = [{"id": event["id"], "requested_tick": event["tick"], "applied_tick": event["tick"],
                        "delta_v_m_s": event["delta_v_m_s"]} for event in s["inputs"] if event["tick"] < len(rows)]
    require(trace["events"] == expected_events, "input application history mismatch")
    complete = len(rows) == s["ticks"]+1 and all(r["p_m"] is not None for r in rows)
    require(type(trace["complete"]) is bool and trace["complete"] == complete, "trace completeness mismatch")
    return data


def reference(s, tick):
    """Analytic constant-acceleration solution, with inputs before their transition.

    Input tick k is applied at (k-1)/Hz before evolving to the post-step sample k.
    Tick zero is the original state before any input; it is never extrapolated.
    """
    t = tick/s["step_hz"]
    p = [p+v*t+.5*g*t*t for p,v,g in zip(s["p0_m"], s["v0_m_s"], s["gravity_m_s2"])]
    v = [v+g*t for v,g in zip(s["v0_m_s"], s["gravity_m_s2"])]
    for event in s["inputs"]:
        if event["tick"] <= tick:
            elapsed = t-(event["tick"]-1)/s["step_hz"]
            p = [x+dv*elapsed for x,dv in zip(p, event["delta_v_m_s"])]
            v = [x+dv for x,dv in zip(v, event["delta_v_m_s"])]
    return p, v


def norm_difference(a, b):
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def metrics(data):
    validate_trace(data)
    trace, s = data["trace"], data["request"]["scenario"]
    if not trace["complete"]:
        return {"status": "INCOMPLETE", "max_position_error_m": None,
                "max_velocity_error_m_s": None, "first_out_of_policy_tick": None}
    max_p = max_v = 0.0
    first = None
    for row in trace["observations"]:
        p, v = reference(s, row["tick"])
        pe, ve = norm_difference(p, row["p_m"]), norm_difference(v, row["v_m_s"])
        max_p, max_v = max(max_p, pe), max(max_v, ve)
        if first is None and (pe > POLICY["position_m"] or ve > POLICY["velocity_m_s"]):
            first = row["tick"]
    return {"status": "PASS" if first is None else "FAIL", "max_position_error_m": max_p,
            "max_velocity_error_m_s": max_v, "first_out_of_policy_tick": first}


def comparison(left, right):
    validate_trace(left); validate_trace(right)
    require(left["request"]["scenario"] == right["request"]["scenario"], "incomparable scenario/grid; refinement uses independent reference metrics")
    a, b = left["trace"], right["trace"]
    complete = a["complete"] and b["complete"]
    return {"schema": COMPARE, "policy": dict(POLICY), "left": metrics(left), "right": metrics(right),
            "cross_runtime_max_position_m": max(norm_difference(x["p_m"], y["p_m"]) for x,y in zip(a["observations"],b["observations"])) if complete else None,
            "claim": "numerical comparison only; not physical validation or verification"}
