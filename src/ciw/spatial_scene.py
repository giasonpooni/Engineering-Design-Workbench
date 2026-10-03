"""Detached local-frame scene exports; source results remain authoritative."""
from __future__ import annotations
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import struct
import tempfile
from .session import Session
from .spatial_records import OPERATION, MAX_BYTES

PROFILE = "ciw.local-frame-scene.v1"
AUTHORITY = {"representation": "detached_copy", "scientific_verification": "not_performed",
             "state_admission": "not_performed", "physical_validation": "not_performed"}


def read_bounded(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Use a regular retained file, not a symbolic link")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Retained workspace exceeds the byte limit")
    return raw


def projection(raw, result_id):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("Invalid workspace bytes")
    with tempfile.TemporaryDirectory(prefix="ciw-spatial-read-") as temp:
        p = Path(temp)/"workspace.json"
        p.write_bytes(raw)
        session = Session.from_workspace(p, Path(temp)/"restored")
        result = session.results.get(result_id)
        if result is None or result["operation_id"] != OPERATION:
            raise ValueError("Select a retained local-frame result")
        data = result["data"]
        return {"schema": PROFILE, "authority": dict(AUTHORITY),
            "workspace_sha256": "sha256:"+sha256(raw).hexdigest(),
            "result_id": result_id, "execution_id": result["execution_id"],
            "operation_id": OPERATION, "source_evidence_id": result["evidence_id"],
            "run_id": result["run_id"], "entity_id": data["entity_id"],
            "prim_path": "/Notations/Entity_"+sha256(data["entity_id"].encode()).hexdigest()[:16],
            "frame_id": data["frame_id"], "origin_lon_lat_height": data["origin"],
            "axes": data["axes"], "unit": data["unit"], "up_axis": "Z",
            "positions_enu_m": data["positions_enu_m"], "time_s": data["time_s"],
            "sample_indices": data["sample_indices"], "uncertainty": data["uncertainty"],
            "runtime_entity_id": None, "interpolation": "none", "physics": "not_declared"}


def _sdk():
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom, Vt
    except ImportError as exc:
        raise RuntimeError("OpenUSD is unavailable; install the existing openusd extra") from exc
    return Gf, Sdf, Usd, UsdGeom, Vt


def usd_bytes(view):
    Gf, Sdf, Usd, UsdGeom, Vt = _sdk()
    stage = Usd.Stage.CreateInMemory()
    root = UsdGeom.Xform.Define(stage, "/Notations")
    stage.SetDefaultPrim(root.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    entity = UsdGeom.Xform.Define(stage, view["prim_path"])
    for key in ("entity_id", "frame_id", "result_id", "execution_id", "source_evidence_id"):
        entity.GetPrim().CreateAttribute("notations:"+key, Sdf.ValueTypeNames.String).Set(view[key])
    entity.GetPrim().CreateAttribute("notations:authority", Sdf.ValueTypeNames.String).Set("representation_only")
    valid = [(i,t,p) for i,t,p in zip(view["sample_indices"], view["time_s"], view["positions_enu_m"]) if p is not None]
    missing = [i for i,p in zip(view["sample_indices"], view["positions_enu_m"]) if p is None]
    points = UsdGeom.Points.Define(stage, view["prim_path"]+"/Samples")
    points.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for _,_,p in valid]))
    points.CreateIdsAttr(Vt.Int64Array([i for i,_,_ in valid]))
    points.GetPrim().CreateAttribute("notations:time_s", Sdf.ValueTypeNames.DoubleArray).Set([t for _,t,_ in valid])
    entity.GetPrim().CreateAttribute("notations:missing_sample_indices", Sdf.ValueTypeNames.IntArray).Set(missing)
    entity.GetPrim().CreateAttribute("notations:interpolation", Sdf.ValueTypeNames.String).Set("none")
    raw = stage.GetRootLayer().ExportToString().encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("Scene exceeds byte budget")
    # Reopen only our freshly generated, self-contained layer, never arbitrary assets.
    layer = Sdf.Layer.CreateAnonymous(".usda")
    if not layer.ImportFromString(raw.decode()) or layer.subLayerPaths or layer.GetExternalReferences():
        raise ValueError("Generated scene is not self-contained")
    reopened = Usd.Stage.Open(layer, load=Usd.Stage.LoadNone)
    actual = UsdGeom.Points(reopened.GetPrimAtPath(view["prim_path"]+"/Samples"))
    f32 = lambda x: struct.unpack("f", struct.pack("f", x))[0]
    if ([list(p) for p in actual.GetPointsAttr().Get()] != [[f32(v) for v in p] for _,_,p in valid]
            or list(actual.GetIdsAttr().Get()) != [i for i,_,_ in valid]
            or UsdGeom.GetStageMetersPerUnit(reopened) != 1.0
            or UsdGeom.GetStageUpAxis(reopened) != "Z"):
        raise ValueError("Native USD roundtrip mismatch")
    return raw, {"status": "sdk_roundtrip_matched", "sdk_version": ".".join(map(str, Usd.GetVersion())),
                 "points_checked": len(valid), "coordinate_storage": "float32_display_copy"}


def html_bytes(view):
    """No scripts, network, live engine, interpolation or mutable controls."""
    present = [p for p in view["positions_enu_m"] if p is not None]
    if present:
        xs, ys = [p[0] for p in present], [p[1] for p in present]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        span = max(xmax-xmin, ymax-ymin, 1.0)
        cx, cy = (xmin+xmax)/2, (ymin+ymax)/2
        dots = "".join(f'<circle cx="{300+480*(p[0]-cx)/span:.5f}" cy="{275-480*(p[1]-cy)/span:.5f}" r="5"><title>sample {i}; t={t:g} s; ENU={escape(str(p))} m</title></circle>'
            for i,t,p in zip(view["sample_indices"],view["time_s"],view["positions_enu_m"]) if p is not None)
        caption = f"Equal horizontal and vertical scale; plotted span {span:g} m. Unconnected samples, not an interpolated path."
    else:
        dots, caption = "", "No complete position samples are available."
    rows = "".join(f'<tr><td>{i}</td><td>{t:g}</td><td>{"unavailable" if p is None else escape(", ".join(format(v,".9g") for v in p))}</td></tr>'
        for i,t,p in zip(view["sample_indices"],view["time_s"],view["positions_enu_m"]))
    style = "body{font:16px system-ui;max-width:960px;margin:2rem auto;padding:0 1rem;line-height:1.5}svg{width:100%;max-height:560px;border:1px solid}table{border-collapse:collapse;width:100%}td,th{padding:.5rem;border-bottom:1px solid;text-align:left}code{overflow-wrap:anywhere}"
    import base64
    csp_hash = base64.b64encode(sha256(style.encode()).digest()).decode()
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'sha256-{csp_hash}'; base-uri 'none'; form-action 'none'">
<title>NET local-frame inspection</title><style>{style}</style>
<h1>Local-frame inspection</h1><p>Detached representation. No acquisition, estimation, physics or state admission.</p>
<p>Entity: <code>{escape(view['entity_id'])}</code><br>Result: <code>{escape(view['result_id'])}</code><br>Frame: <code>{escape(view['frame_id'])}</code></p>
<h2>East / north plan</h2><svg viewBox="0 0 600 550" role="img" aria-label="Unconnected local east/north position samples">{dots}<text x="260" y="535">East (metres)</text><text x="8" y="20">North (metres), upward</text></svg>
<p>{caption}</p><p>Height is WGS84 ellipsoidal. Missing coordinates stay unavailable. Covariance was not propagated.</p>
<h2>Retained samples</h2><table><thead><tr><th>Index</th><th>Time (s)</th><th>East, north, up (m)</th></tr></thead><tbody>{rows}</tbody></table>
<p>Scientific source: <code>{escape(view['source_evidence_id'])}</code></p></html>'''
    return html.encode()


def export(workspace, result_id, output_dir, *, with_usd=False):
    raw = read_bounded(workspace)
    view = projection(raw, result_id)
    outputs = {"workspace.json": raw,
               "scene-binding.json": (json.dumps(view, indent=2, allow_nan=False)+"\n").encode(),
               "inspector.html": html_bytes(view)}
    native = {"status": "not_requested"}
    if with_usd:
        outputs["scene.usda"], native = usd_bytes(view)
    report = {"schema": "ciw.local-frame-export.v1", "authority": dict(AUTHORITY),
              "result_id": result_id, "usd": native,
              "artifacts": {name: "sha256:"+sha256(b).hexdigest() for name,b in outputs.items()}}
    from .operations.runner import seal
    seal(report)
    outputs["export.json"] = (json.dumps(report, indent=2, allow_nan=False)+"\n").encode()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in outputs.items():
        with (output/name).open("xb") as f:
            f.write(data)
    return report


def verify_export(directory):
    """Recheck retained bytes/bindings without invoking PROJ or the USD SDK.

    Producer SDK-roundtrip claims are retained, not independently rerun here.
    Seals detect mismatches but cannot authenticate a malicious resealing author.
    """
    from .session import loads_json
    from .operations.runner import check_seal
    directory = Path(directory)
    report = loads_json(read_bounded(directory / "export.json").decode())
    check_seal(report)
    if (set(report) != {"schema", "authority", "result_id", "usd", "artifacts", "record_digest"}
            or report["schema"] != "ciw.local-frame-export.v1" or report["authority"] != AUTHORITY
            or not isinstance(report["artifacts"], dict) or not isinstance(report["usd"], dict)):
        raise ValueError("Invalid export receipt")
    expected = {"workspace.json", "scene-binding.json", "inspector.html"}
    native = report["usd"]
    if native.get("status") == "sdk_roundtrip_matched":
        if (set(native) != {"status", "sdk_version", "points_checked", "coordinate_storage"}
                or native["coordinate_storage"] != "float32_display_copy"
                or not isinstance(native["sdk_version"], str)):
            raise ValueError("Invalid producer SDK report")
        expected.add("scene.usda")
    elif native != {"status": "not_requested"}:
        raise ValueError("Invalid USD export disposition")
    if set(report["artifacts"]) != expected:
        raise ValueError("Unknown or missing export artifact")
    files = {name: read_bounded(directory/name) for name in expected}
    if any(report["artifacts"][name] != "sha256:"+sha256(raw).hexdigest() for name,raw in files.items()):
        raise ValueError("Export artifact integrity mismatch")
    view = projection(files["workspace.json"], report["result_id"])
    expected_binding = (json.dumps(view, indent=2, allow_nan=False)+"\n").encode()
    if files["scene-binding.json"] != expected_binding or files["inspector.html"] != html_bytes(view):
        raise ValueError("Export semantics contradict retained source")
    count=sum(p is not None for p in view["positions_enu_m"])
    if "scene.usda" in expected and (type(native["points_checked"]) is not int or native["points_checked"] != count):
        raise ValueError("Producer SDK sample-count mismatch")
    return {"status": "retained_export_integrity_checked", "result_id": report["result_id"],
            "artifacts_checked": len(files), "provider_execution": "not_performed",
            "usd_sdk": "not_invoked", "producer_usd_claim": native, "authority": dict(AUTHORITY)}
