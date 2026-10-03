"""Finite directed edge gluing and exact affine segments, with explicit stops.

Each segment is derived from p(t) = p0 + direction * (t-t0), and edge times
are rational solutions of x=0/1 or y=0/1. There is no floating-point solver,
epsilon ordering, corner continuation, or asymptotic dynamics claim.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import re

MAX_REQUEST_BYTES = 32768
MAX_TILES = 32
MAX_EVENTS = 1024
INPUT_BITS = 64
ARITHMETIC_BITS = 256
REQUEST_SCHEMA = "tsde.square-tiled-flow-request.v1"
RESULT_SCHEMA = "tsde.square-tiled-flow-result.v1"
OPERATION = "tsde.square-tiled-flow.v1"
CLAIM_SCOPE = "exact_rational_translation_flow_prefix_on_declared_square_tiled_surface"
_RATIONAL = re.compile(r"(?:0|-?[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z")
_EDGE_DATA = {
    "right": (0, Fraction(-1)), "left": (0, Fraction(1)),
    "up": (1, Fraction(-1)), "down": (1, Fraction(1)),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return "sha256:" + sha256(canonical(value)).hexdigest()


def _keys(value, required, name):
    if type(value) is not dict or set(value) != set(required):
        raise ValueError(f"{name} requires exactly {sorted(required)}")


def _bounded(value):
    if abs(value.numerator).bit_length() > ARITHMETIC_BITS or value.denominator.bit_length() > ARITHMETIC_BITS:
        raise ValueError("Arithmetic rational bit budget exceeded; no complete result produced")
    return value


def _text(value):
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _fraction(value, name):
    if type(value) is not str or len(value) > 43 or not _RATIONAL.fullmatch(value):
        raise ValueError(f"{name} must be a canonical reduced rational string")
    result = Fraction(value)
    if (_text(result) != value or abs(result.numerator).bit_length() > INPUT_BITS or
            result.denominator.bit_length() > INPUT_BITS):
        raise ValueError(f"{name} must be reduced and within the {INPUT_BITS}-bit input budget")
    return result


def _pair(value, name):
    if type(value) is not list or len(value) != 2:
        raise ValueError(f"{name} must contain exactly two rational strings")
    return [_fraction(item, name) for item in value]


def _inverse(permutation):
    result = [0] * len(permutation)
    for before, after in enumerate(permutation):
        result[after] = before
    return result


def _connected(right, up):
    reached, pending = {0}, [0]
    while pending:
        tile = pending.pop()
        for neighbor in (right[tile], up[tile]):
            if neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    return len(reached) == len(right)


def validate_request(request: dict) -> dict:
    """Validate the complete fixed profile and return an independent copy.

    Noncanonical rationals and permutations are rejected, never normalized.
    """
    _keys(request, {"schema", "gluing", "start", "direction", "duration", "max_events"}, "request")
    if request["schema"] != REQUEST_SCHEMA:
        raise ValueError("Unsupported translation-flow request schema")
    gluing = request["gluing"]
    _keys(gluing, {"right", "up"}, "gluing")
    right, up = gluing["right"], gluing["up"]
    if type(right) is not list or not 1 <= len(right) <= MAX_TILES:
        raise ValueError("Require 1..32 square tiles")
    count = len(right)
    for permutation in (right, up):
        if (type(permutation) is not list or len(permutation) != count or
                any(type(tile) is not int for tile in permutation) or sorted(permutation) != list(range(count))):
            raise ValueError("Right and up gluing must be permutations of every tile index")
    if not _connected(right, up):
        raise ValueError("The declared square-tiled surface must be connected")
    start = request["start"]
    _keys(start, {"tile", "position"}, "start")
    if type(start["tile"]) is not int or not 0 <= start["tile"] < count:
        raise ValueError("Start tile is outside the declared surface")
    if not all(0 < value < 1 for value in _pair(start["position"], "start.position")):
        raise ValueError("Start must lie strictly inside its square; boundary starts are unsupported")
    direction = _pair(request["direction"], "direction")
    if not any(direction) or any(abs(value) > 1024 for value in direction):
        raise ValueError("Direction must be nonzero with component magnitudes at most 1024")
    duration = _fraction(request["duration"], "duration")
    if not 0 <= duration <= 1024:
        raise ValueError("Duration must lie in [0,1024]")
    if type(request["max_events"]) is not int or not 0 <= request["max_events"] <= MAX_EVENTS:
        raise ValueError("max_events must be an integer from 0 to 1024")
    if len(canonical(request)) > MAX_REQUEST_BYTES:
        raise ValueError("Request exceeds the byte budget")
    return deepcopy(request)


def _topology(gluing):
    """Identify corners under translations, then derive Euler characteristic.

    Local corner order is bottom-left, bottom-right, top-right, top-left.
    Each tile contributes one face, two paired edges, and four quarter angles.
    """
    right, up = gluing["right"], gluing["up"]
    parent = list(range(4 * len(right)))

    def find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(first, second):
        first, second = find(first), find(second)
        parent[max(first, second)] = min(first, second)

    for tile in range(len(right)):
        union(4 * tile + 1, 4 * right[tile])
        union(4 * tile + 2, 4 * right[tile] + 3)
        union(4 * tile + 3, 4 * up[tile])
        union(4 * tile + 2, 4 * up[tile] + 1)
    classes = {}
    for corner in range(len(parent)):
        classes.setdefault(find(corner), []).append([corner // 4, corner % 4])
    vertices, vertex_lookup = [], {}
    for index, corners in enumerate(classes.values()):
        if len(corners) % 4:
            raise ValueError("Gluing does not give integral translation-surface cone angles")
        vertices.append({"vertex_id": index, "corners": corners,
                         "cone_angle_multiple_of_2pi": len(corners) // 4,
                         "singular": len(corners) != 4})
        for tile, corner in corners:
            vertex_lookup[tile, corner] = index
    chi = len(vertices) - len(right)
    if chi > 0 or chi % 2:
        raise ValueError("Invalid orientable square-tiled surface topology")
    return {"permutations_bijective": True, "connected": True,
            "tile_count": len(right), "edge_count": 2 * len(right),
            "vertex_count": len(vertices), "euler_characteristic": chi,
            "genus": 1 - chi // 2, "right": right[:], "left": _inverse(right),
            "up": up[:], "down": _inverse(up), "vertices": vertices}, vertex_lookup


def _vector(values):
    return [_text(value) for value in values]


def _invariants(request, topology, segments, events, final, elapsed, status):
    """Recheck each retained affine segment and its intervening gluing map."""
    direction = [Fraction(value) for value in request["direction"]]
    position = [Fraction(value) for value in request["start"]["position"]]
    initial = position[:]
    tile, time, applied = request["start"]["tile"], Fraction(0), 0
    translations = [Fraction(0), Fraction(0)]
    affine, continuity, gluing, inside = True, True, True, True
    last_event_time = Fraction(-1)
    increasing = True
    for segment in segments:
        start, end = [[Fraction(value) for value in segment[key]] for key in ("start", "end")]
        before, after = Fraction(segment["t_start"]), Fraction(segment["t_end"])
        continuity &= segment["tile"] == tile and start == position and before == time and after > before
        affine &= end == [_bounded(start[i] + direction[i] * (after - before)) for i in range(2)]
        inside &= all(0 <= value <= 1 for value in start + end)
        position, time = end, after
        if applied < len(events) and Fraction(events[applied]["time"]) == time:
            event = events[applied]
            axis, amount = _EDGE_DATA[event["edge"]]
            expected_translation = [Fraction(0), Fraction(0)]
            expected_translation[axis] = amount
            target = [position[i] + expected_translation[i] for i in range(2)]
            gluing &= (event["index"] == applied and event["from_tile"] == tile and
                       event["to_tile"] == topology[event["edge"]][tile] and
                       event["from_position"] == _vector(position) and
                       event["to_position"] == _vector(target) and
                       event["translation"] == _vector(expected_translation))
            increasing &= time > last_event_time
            last_event_time = time
            tile, position = event["to_tile"], target
            translations[axis] += amount
            applied += 1
    continuity &= applied == len(events) and tile == final["tile"] and _vector(position) == final["position"] and time == elapsed
    unfolded = position == [_bounded(initial[i] + direction[i] * elapsed + translations[i]) for i in range(2)]
    result = {"affine_segments_match_direction": bool(affine),
              "segment_continuity_via_gluing": bool(continuity),
              "directed_edge_maps_match_permutations": bool(gluing),
              "positions_in_closed_unit_square": bool(inside),
              "event_times_strictly_increasing": bool(increasing),
              "unfolded_displacement_matches": bool(unfolded),
              "elapsed_within_requested_duration": 0 <= elapsed <= Fraction(request["duration"]),
              "requested_duration_completed": status == "completed"}
    if not all(value for key, value in result.items() if key != "requested_duration_completed"):
        raise RuntimeError("Internal translation-flow invariant failed")
    return result


def run(request: dict) -> dict:
    """Return a complete bounded trajectory or an explicitly stopped prefix."""
    request = validate_request(request)
    topology, vertices = _topology(request["gluing"])
    position = [Fraction(value) for value in request["start"]["position"]]
    direction = [Fraction(value) for value in request["direction"]]
    duration, elapsed, tile = Fraction(request["duration"]), Fraction(0), request["start"]["tile"]
    segments, events, pending = [], [], []
    vertex_id, status = None, "completed"
    while elapsed < duration:
        candidates = []
        for axis, speed in enumerate(direction):
            if speed:
                boundary = Fraction(1) if speed > 0 else Fraction(0)
                distance = _bounded((boundary - position[axis]) / speed)
                if distance <= 0:
                    raise RuntimeError("An unprocessed boundary cannot be silently continued")
                edge = ("right" if speed > 0 else "left") if axis == 0 else ("up" if speed > 0 else "down")
                candidates.append((distance, edge))
        crossing = min(value for value, _ in candidates)
        remaining = _bounded(duration - elapsed)
        step = min(crossing, remaining)
        end = [_bounded(position[i] + direction[i] * step) for i in range(2)]
        after = _bounded(elapsed + step)
        segments.append({"tile": tile, "t_start": _text(elapsed), "t_end": _text(after),
                         "start": _vector(position), "end": _vector(end)})
        elapsed, position = after, end
        if crossing > remaining:
            break
        pending = [edge for time, edge in candidates if time == crossing]
        if len(pending) == 2:
            status = "stopped_at_vertex"
            corner = (2 if position[0] == 1 else 3) if position[1] == 1 else (1 if position[0] == 1 else 0)
            vertex_id = vertices[tile, corner]
            break
        if len(events) >= request["max_events"]:
            status = "event_budget_exhausted"
            break
        edge, old_tile, before = pending[0], tile, position[:]
        axis, amount = _EDGE_DATA[edge]
        translation = [Fraction(0), Fraction(0)]
        translation[axis] = amount
        position[axis] += amount
        tile = topology[edge][tile]
        events.append({"index": len(events), "time": _text(elapsed), "edge": edge,
                       "from_tile": old_tile, "to_tile": tile,
                       "from_position": _vector(before), "to_position": _vector(position),
                       "translation": _vector(translation)})
        pending = []
    final = {"tile": tile, "position": _vector(position), "pending_edges": pending, "vertex_id": vertex_id}
    result = {"schema": RESULT_SCHEMA, "operation_id": OPERATION, "request": request,
              "request_digest": digest(request), "claim_scope": CLAIM_SCOPE,
              "arithmetic": {"kind": "exact_rational", "coordinate_unit": "unit_square_side",
                  "time_parameter": "declared_flow_parameter", "tolerance": "0",
                  "derivation": "affine_position_and_rational_boundary_intersection",
                  "input_bits": INPUT_BITS, "arithmetic_bits": ARITHMETIC_BITS,
                  "vertex_policy": "stop_before_any_vertex_continuation",
                  "endpoint_policy": "process_single_edge_crossing_at_duration",
                  "event_budget_policy": "stop_at_next_boundary_before_omitted_gluing"},
              "gluing_validation": topology, "status": status, "elapsed": _text(elapsed),
              "remaining": _text(_bounded(duration - elapsed)), "final_state": final,
              "segments": segments, "events": events,
              "invariants": _invariants(request, topology, segments, events, final, elapsed, status)}
    result["artifact_digest"] = digest(result)
    return result
