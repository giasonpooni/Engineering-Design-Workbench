"""Bounded oscillator-displacement projection through the real OpenUSD SDK.

No arbitrary scene import, scientific solver, provider or equipment is executed.
Source workspaces remain authoritative. Export/reload checks are not SP1 proofs.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile

from .adapters.subprocess import _json
from .session import Session
from .telemetry import canonical, digest

PROFILE = "ciw.oscillator-displacement-usd.v1"
WORKSPACE_LIMIT = 8 * 1024**2
SCENE_LIMIT = 4 * 1024**2
MAX_SAMPLES = 4096
AUTHORITY = {"scientific_verification": "not_performed", "physical_validation": "not_performed",
             "cryptographic_verification": "not_performed", "state_admission": "not_performed"}


def _read(path: Path, limit: int) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Use a regular retained file, not a symbolic link")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Retained file exceeds this profile's byte limit")
    return raw


def _hash(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def _sdk():
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom
    except ImportError as exc:
        raise RuntimeError("OpenUSD is unavailable; install the optional openusd extra") from exc
    return Gf, Sdf, Usd, UsdGeom


def _project(raw: bytes, result_id: str) -> dict:
    # Load precisely the captured bytes; reopening only writes into scratch.
    if not isinstance(raw, bytes) or len(raw) > WORKSPACE_LIMIT:
        raise ValueError("Invalid bounded workspace")
    if not isinstance(result_id, str):
        raise ValueError("Select a retained result identity")
    with tempfile.TemporaryDirectory(prefix="ciw-usd-source-") as temp:
        path = Path(temp) / "workspace.json"
        path.write_bytes(raw)
        session = Session.from_workspace(path, Path(temp) / "restored")
        run = session.run
        result = session.results.get(result_id)
        if (run["instrument"] != "analytic-damped-oscillator.v1" or result is None
                or result["channel"] != "q" or run["channels"]["q"]["unit"] != "m"):
            raise ValueError("This profile requires a retained oscillator displacement result in metres")
        start, end = result["interval_s"]
        indices = [i for i, t in enumerate(run["time_s"]) if start <= t < end]
        if not 1 <= len(indices) <= MAX_SAMPLES:
            raise ValueError("Scene sample count is outside the qualified profile")
        return {
            "profile": PROFILE, "workspace_sha256": _hash(raw),
            "run_id": run["run_id"], "evidence_id": run["evidence_id"],
            "result_id": result["result_id"], "execution_id": result["execution_id"],
            "result_sha256": digest(result), "source_frame": run["metadata"]["coordinate_frame"],
            "mapping": "q_metres_to_local_x.v1", "unit": "m",
            "time_reference": "seconds_since_run_start", "interval_s": result["interval_s"],
            "sample_indices": indices, "times": [run["time_s"][i] for i in indices],
            "q": [run["channels"]["q"]["values"][i] for i in indices],
            "interpolation": "client_display_only_not_new_observations",
        }


def _scene(projection: dict) -> tuple[bytes, str]:
    Gf, Sdf, Usd, UsdGeom = _sdk()
    stage = Usd.Stage.CreateInMemory()
    root = UsdGeom.Xform.Define(stage, "/Notations")
    stage.SetDefaultPrim(root.GetPrim())
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    stage.SetTimeCodesPerSecond(1.0)
    stage.SetFramesPerSecond(1.0)
    stage.SetStartTimeCode(projection["times"][0])
    stage.SetEndTimeCode(projection["times"][-1])
    # Metadata has no asset paths, executable names or device commands.
    root.GetPrim().CreateAttribute("notations:binding", Sdf.ValueTypeNames.String).Set(
        canonical({k: v for k, v in projection.items() if k not in {"times", "q"}}).decode())
    motion = UsdGeom.Xform.Define(stage, "/Notations/Displacement")
    translate = motion.AddTranslateOp(precision=UsdGeom.XformOp.PrecisionDouble)
    for time, q in zip(projection["times"], projection["q"]):
        translate.Set(Gf.Vec3d(q, 0.0, 0.0), Usd.TimeCode(time))
    marker = UsdGeom.Sphere.Define(stage, "/Notations/Displacement/Marker")
    marker.CreateRadiusAttr(0.025)  # Display glyph only; not a specimen dimension.
    raw = stage.GetRootLayer().ExportToString().encode("utf-8")
    if len(raw) > SCENE_LIMIT:
        raise ValueError("Export exceeds the bounded scene size")
    return raw, ".".join(map(str, Usd.GetVersion()))


def _reload(raw: bytes, projection: dict) -> str:
    """Read captured USDA without resolving external layers, then compare values.

    Only the exact self-contained authored schema subset below is accepted.
    This is not a general sandbox for arbitrary OpenUSD files or plugins.
    """
    Gf, Sdf, Usd, UsdGeom = _sdk()
    layer = Sdf.Layer.CreateAnonymous(".usda")
    if not layer.ImportFromString(raw.decode("utf-8")):
        raise ValueError("Invalid USDA")
    if set(layer.pseudoRoot.ListInfoKeys()) - {"defaultPrim", "metersPerUnit", "upAxis",
            "timeCodesPerSecond", "framesPerSecond", "startTimeCode", "endTimeCode"}:
        raise ValueError("Unqualified layer metadata is unsupported")
    if layer.subLayerPaths or layer.GetExternalReferences():
        raise ValueError("External layers, references and payloads are unsupported")
    expected = {
        "/Notations": ("Xform", {"notations:binding"}),
        "/Notations/Displacement": ("Xform", {"xformOpOrder", "xformOp:translate"}),
        "/Notations/Displacement/Marker": ("Sphere", {"radius"}),
    }
    found = set()
    def inspect(spec):
        path = str(spec.path)
        if path not in expected or spec.typeName != expected[path][0]:
            raise ValueError("Unsupported authored prim")
        if set(spec.ListInfoKeys()) - {"specifier", "typeName"}:
            raise ValueError("Composition arcs or unqualified prim metadata are unsupported")
        if {p.name for p in spec.properties} != expected[path][1]:
            raise ValueError("Unsupported authored properties")
        for prop in spec.properties:
            if set(prop.ListInfoKeys()) - {"custom", "typeName", "variability", "default", "timeSamples"}:
                raise ValueError("Connections or unqualified property metadata are unsupported")
        found.add(path)
        for child in spec.nameChildren:
            inspect(child)
    for spec in layer.rootPrims:
        inspect(spec)
    if found != set(expected):
        raise ValueError("Scene is missing required prims")
    # No external arcs exist when the composition engine is invoked.
    stage = Usd.Stage.Open(layer, load=Usd.Stage.LoadNone)
    if (stage.GetDefaultPrim().GetPath() != Sdf.Path("/Notations")
            or UsdGeom.GetStageMetersPerUnit(stage) != 1.0
            or UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z
            or stage.GetTimeCodesPerSecond() != 1.0 or stage.GetFramesPerSecond() != 1.0
            or stage.GetStartTimeCode() != projection["times"][0]
            or stage.GetEndTimeCode() != projection["times"][-1]):
        raise ValueError("Scene units, axes or time support differ from the profile")
    prim = stage.GetPrimAtPath("/Notations")
    binding = prim.GetAttribute("notations:binding").Get()
    required = canonical({k: v for k, v in projection.items() if k not in {"times", "q"}}).decode()
    if binding != required:
        raise ValueError("Scene identity binding differs from retained evidence")
    motion = UsdGeom.Xformable(stage.GetPrimAtPath("/Notations/Displacement"))
    ops = motion.GetOrderedXformOps()
    if (motion.GetResetXformStack() or len(ops) != 1
            or ops[0].GetOpType() != UsdGeom.XformOp.TypeTranslate
            or ops[0].GetPrecision() != UsdGeom.XformOp.PrecisionDouble
            or ops[0].IsInverseOp()):
        raise ValueError("Scene transform stack differs from the projection")
    attr = ops[0].GetAttr()
    if attr.GetTimeSamples() != projection["times"]:
        raise ValueError("Scene sample times differ from retained sample support")
    for time, q in zip(projection["times"], projection["q"]):
        if tuple(attr.Get(Usd.TimeCode(time))) != (q, 0.0, 0.0):
            raise ValueError("Scene displacement differs from retained numerical values")
    radius = UsdGeom.Sphere(stage.GetPrimAtPath("/Notations/Displacement/Marker")).GetRadiusAttr()
    if radius.Get() != 0.025 or radius.GetNumTimeSamples():
        raise ValueError("Display glyph differs from the supported projection")
    return ".".join(map(str, Usd.GetVersion()))


def export_workspace(workspace: Path, result_id: str, output_dir: Path) -> dict:
    """Export one selected result context into a new, self-contained directory."""
    raw = _read(workspace, WORKSPACE_LIMIT)
    projection = _project(raw, result_id)
    scene, version = _scene(projection)
    _reload(scene, projection)  # Actual SDK export/reload before publication.
    report = {"schema": "ciw.oscillator-usd-export.v1", "projection": projection,
              "scene_sha256": _hash(scene), "exporter": "ciw.usd_export.v1",
              "usd_version": version, "scene_file": "scene.usda", "workspace_file": "workspace.json",
              "validation": "sdk_roundtrip_matched", "authority": dict(AUTHORITY)}
    report["export_id"] = digest(report)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    # A manifest exists only after both dependencies are fully written.
    # No multi-file crash transaction or concurrent hostile-host protection claimed.
    with (output / "workspace.json").open("xb") as stream:
        stream.write(raw)
    with (output / "scene.usda").open("xb") as stream:
        stream.write(scene)
    with (output / "export.json").open("xb") as stream:
        stream.write(canonical(report))
    return report


def verify_export(output_dir: Path) -> dict:
    """Recheck saved projection without executing scientific providers."""
    output = Path(output_dir)
    report = _json(_read(output / "export.json", 512 * 1024))
    if not isinstance(report, dict) or set(report) != {
            "schema", "projection", "scene_sha256", "exporter", "usd_version", "scene_file",
            "workspace_file", "validation", "authority", "export_id"}:
        raise ValueError("Invalid export manifest")
    if (report["schema"] != "ciw.oscillator-usd-export.v1"
            or report["exporter"] != "ciw.usd_export.v1"
            or report["workspace_file"] != "workspace.json" or report["scene_file"] != "scene.usda"
            or report["validation"] != "sdk_roundtrip_matched" or report["authority"] != AUTHORITY
            or report["export_id"] != digest({k: v for k, v in report.items() if k != "export_id"})):
        raise ValueError("Export identity, scope or filenames changed")
    raw = _read(output / "workspace.json", WORKSPACE_LIMIT)
    scene = _read(output / "scene.usda", SCENE_LIMIT)
    if not isinstance(report["projection"], dict):
        raise ValueError("Invalid projection")
    projection = _project(raw, report["projection"].get("result_id"))
    if canonical(projection) != canonical(report["projection"]) or _hash(scene) != report["scene_sha256"]:
        raise ValueError("Export dependencies changed")
    version = _reload(scene, projection)
    return {"export_id": report["export_id"], "validation": "sdk_roundtrip_matched",
            "samples_checked": len(projection["times"]), "checker_usd_version": version,
            "authority": dict(AUTHORITY)}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("workspace", type=Path)
    export.add_argument("--result-id", required=True)
    export.add_argument("--output-dir", required=True, type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        value = (export_workspace(args.workspace, args.result_id, args.output_dir)
                 if args.command == "export" else verify_export(args.directory))
        print(json.dumps(value, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        import sys
        print("ciw usd: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
