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
