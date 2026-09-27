"""Read-only ASCII USDA copies of retained inspect geometry.

This writes `#usda 1.0` text. It does not load OpenUSD, interpolate samples,
or admit scene files as observations.
"""
from copy import deepcopy
from json import dumps

SCHEMA = "ciw.usda-export.v1"
AUTHORITY = "inspection_copy_not_observation"


def _finite(value, name):
    if type(value) not in (int, float) or value != value or abs(value) == float("inf"):
        raise ValueError(name + " requires finite coordinates")
    return float(value)


def _quote(value):
    return dumps(str(value), ensure_ascii=True)


def _point(values):
    coords = list(values) + [0.0, 0.0, 0.0]
    return "(%s, %s, %s)" % (
        repr(_finite(coords[0], "USDA point")),
        repr(_finite(coords[1], "USDA point")),
        repr(_finite(coords[2], "USDA point")),
    )


def _layer(kind, identity, frame, extra=""):
    return """#usda 1.0
(
    defaultPrim = "NotationsInspect"
    metersPerUnit = 1
    upAxis = "Y"
    customLayerData = {
        string ciw_schema = %s
        string source_kind = %s
        string canvas_id = %s
        string frame = %s
        string authority = %s
    }
)

def Xform "NotationsInspect" (
    kind = "component"
)
{
%s
}
""" % (_quote(SCHEMA), _quote(kind), _quote(identity or ""), _quote(frame or ""),
       _quote(AUTHORITY), extra.rstrip())


def export_recording(run):
    """Copy a retained oscillator recording to unconnected USDA points."""
    if not isinstance(run, dict) or "time_s" not in run or "render" not in run:
        raise ValueError("USDA export requires a retained oscillator recording")
    render = run.get("render") or {}
    trajectory = render.get("trajectory")
    if not isinstance(trajectory, list) or not trajectory:
        raise ValueError("USDA export requires a retained trajectory")
    points = ",\n            ".join(_point(item) for item in trajectory)
    frame = render.get("coordinate_frame") or (run.get("metadata") or {}).get("coordinate_frame")
    times = run.get("time_s") or []
    if len(times) != len(trajectory):
        raise ValueError("USDA export requires time samples that match the trajectory")
    for item in times:
        _finite(item, "USDA time")
    extra = """    def Points "samples"
    {
        point3f[] points = [
            %s
        ]
        custom string note = "Declared-order samples; not a trajectory interpolation"
        custom string unit = "m"
    }
""" % points
    return _layer("oscillator-recording", run.get("run_id"), frame, extra)


def export_render(render, *, canvas_id=None, title=None):
    """Copy a detached panel-render descriptor to unconnected USDA geometry."""
    if not isinstance(render, dict):
        raise ValueError("USDA export requires a detached panel-render descriptor")
    kind = render.get("kind")
    if kind in ("plane2d", "strip") and render.get("connect") is True:
        raise ValueError("Plane and strip copies stay unconnected")
    frame = render.get("frame")
    if isinstance(frame, dict):
        frame = frame.get("id") or frame.get("frame_id")
    identity = render.get("canvas_id") or canvas_id or ""
    if identity and frame and identity == frame and kind in ("plane2d", "strip"):
        raise ValueError("Stamped canvas id equals the declared frame")
    if kind == "plane2d":
        points = render.get("points") or []
        if not points:
            raise ValueError("USDA export requires declared plane points")
        body = ",\n            ".join(
            _point((item.get("x"), item.get("y"), 0.0)) for item in points)
        extra = """    def Points "samples"
    {
        point3f[] points = [
            %s
        ]
        custom string canvas_title = %s
        custom string note = "Declared-order points; not a trajectory interpolation"
    }
""" % (body, _quote(title or render.get("canvas_title") or ""))
        return _layer("plane2d", identity, frame, extra)
    if kind == "strip":
        samples = render.get("samples") or []
        if not samples:
            raise ValueError("USDA export requires declared strip samples")
        body = ",\n            ".join(
            _point((item.get("parameter"), item.get("value"), 0.0)) for item in samples)
        extra = """    def Points "samples"
    {
        point3f[] points = [
            %s
        ]
        custom string parameter_name = %s
        custom string note = "Declared parameter samples; not event time"
    }
""" % (body, _quote(render.get("parameter_name") or ""))
        return _layer("strip", identity, frame, extra)
    if kind == "mesh":
        vertices = render.get("vertices") or []
        triangles = render.get("triangles") or []
        if not vertices or not triangles:
            raise ValueError("USDA export requires declared mesh faces")
        points = ",\n            ".join(_point(item) for item in vertices)
        counts = ", ".join("3" for _ in triangles)
        indices = ", ".join(str(int(index)) for face in triangles for index in face)
        extra = """    def Mesh "declared"
    {
        point3f[] points = [
            %s
        ]
        int[] faceVertexCounts = [%s]
        int[] faceVertexIndices = [%s]
        custom string canvas_title = %s
        custom string note = "Declared faces; not a surveyed mesh"
    }
""" % (points, counts, indices, _quote(title or render.get("canvas_title") or ""))
        return _layer("mesh", identity, frame, extra)
    raise ValueError("USDA export requires a plane, strip, mesh or oscillator recording")


def export_payload(payload):
    """Dispatch a recording or experiment-view copy to USDA text."""
    if not isinstance(payload, dict):
        raise ValueError("USDA export requires a retained JSON object")
    if payload.get("schema") == "ciw.experiment-view.v1":
        render = payload.get("system_render")
        if not isinstance(render, dict):
            for panel in payload.get("panels") or []:
                if isinstance(panel, dict) and isinstance(panel.get("render"), dict):
                    render = panel["render"]
                    break
        if not isinstance(render, dict):
            raise ValueError("USDA export requires a detached canvas on the inspect view")
        return export_render(
            deepcopy(render),
            canvas_id=payload.get("system_canvas_id") or render.get("canvas_id"),
            title=render.get("canvas_title"),
        )
    if "render" in payload and "time_s" in payload:
        return export_recording(payload)
    if payload.get("kind") in ("plane2d", "strip", "mesh"):
        return export_render(payload)
    raise ValueError("USDA export requires a retained recording or inspect view")


def write_usda(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def parse_points(text):
    """Read point3f[] values from a CIW USDA copy. Not a general OpenUSD loader."""
    if not isinstance(text, str) or not text.startswith("#usda 1.0"):
        raise ValueError("USDA compare requires a CIW ASCII USDA copy")
    if SCHEMA not in text:
        raise ValueError("USDA compare requires schema " + SCHEMA)
    start = text.find("point3f[] points = [")
    if start < 0:
        raise ValueError("USDA compare requires declared points")
    block = text[start + len("point3f[] points = ["):]
    end = block.find("]")
    if end < 0:
        raise ValueError("USDA compare requires a closed point array")
    points = []
    for raw in block[:end].split(")"):
        raw = raw.replace("(", " ").replace(",", " ")
        parts = raw.split()
        if len(parts) < 3:
            continue
        points.append([_finite(float(parts[0]), "USDA point"),
                       _finite(float(parts[1]), "USDA point"),
                       _finite(float(parts[2]), "USDA point")])
    if not points:
        raise ValueError("USDA compare found no declared points")
    return points


def compare_export(payload, text):
    """Compare a USDA copy to its retained source. Display interpolation is refused."""
    if "BasisCurves" in text:
        raise ValueError("USDA compare refuses interpolated curves")
    exported = parse_points(text)
    expected = []
    if isinstance(payload, dict) and "time_s" in payload:
        for item in payload["render"]["trajectory"]:
            coords = list(item) + [0.0, 0.0, 0.0]
            expected.append([float(coords[0]), float(coords[1]), float(coords[2])])
    else:
        render = payload.get("system_render", payload)
        if render.get("kind") == "plane2d":
            expected = [[float(item["x"]), float(item["y"]), 0.0] for item in render["points"]]
        elif render.get("kind") == "strip":
            expected = [[float(item["parameter"]), float(item["value"]), 0.0] for item in render["samples"]]
        elif render.get("kind") == "mesh":
            expected = [list(item) + [0.0] * (3 - len(item)) for item in render["vertices"]]
            expected = [[float(row[0]), float(row[1]), float(row[2])] for row in expected]
        else:
            raise ValueError("USDA compare requires a retained recording or inspect canvas")
    if exported != expected:
        raise ValueError("USDA copy does not match the retained source points")
    return {"status": "matched", "schema": SCHEMA, "point_count": len(exported),
            "authority": AUTHORITY, "openusd_runtime": "not_loaded"}

