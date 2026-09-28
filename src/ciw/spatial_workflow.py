"""Local-frame provider workflow through the existing CIW Session."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import uuid
from .session import Session, envelope
from .spatial_records import OPERATION, demo_run, source
from .spatial_scene import read_bounded


def create(run, origin, output_dir, *, gsc_root, revision, python_executable=sys.executable):
    source(run)
    output = Path(output_dir)
    # A fresh directory is an explicit execution; never replace prior evidence.
    output.mkdir(parents=True, exist_ok=False)
    session = Session(run, output)
    try:
        from .spatial_provider import bind
        session.operations = bind(gsc_root, revision, python_executable=python_executable)
    except (ValueError, OSError) as exc:
        # Retain provisioning failure separately; do not invent a provider execution.
        session.save_workspace(output/"workspace.json")
        from .session import write_json
        write_json(output/"provisioning-refusal.json", {"status": "refused_before_execution", "message": str(exc)})
        raise
    result = session.handle(envelope("operation.execute", {"operation_id": OPERATION,
        "parameters": {"origin": origin, "channel": session.selection["channel"],
                       "interval_s": session.selection["interval_s"]}}, uuid.uuid4().hex))
    session.save_workspace(output/"workspace.json")
    if result["type"] == "error":
        raise ValueError(result["payload"]["message"])
    return result["payload"]


def _snapshot(raw):
    """Read one exact byte snapshot; never re-read a source during replay."""
    with tempfile.TemporaryDirectory(prefix="ciw-spatial-inspect-") as directory:
        p=Path(directory)/"workspace.json";p.write_bytes(raw)
        session=Session.from_workspace(p, Path(directory)/"restored")
        report = {"status": "retained_records_checked", "source_evidence_id": session.run["evidence_id"],
                "results": list(session.results.values()), "executions": list(session.executions.values()),
                "provider_execution": "not_performed", "scientific_verification": "not_performed"}
        return session.run, report


def inspect(workspace):
    return _snapshot(read_bounded(workspace))[1]


def register_commands(commands):
    spatial=commands.add_parser("spatial", help="Bounded GSC local-frame integration and detached scene export")
    _register_actions(spatial)


def _register_actions(spatial):
    actions=spatial.add_subparsers(dest="spatial_command", required=True)
    actions.add_parser("catalog", help="Read-only provider roadmap; never installs or executes")
    for name in ("demo", "run", "replay"):
        p=actions.add_parser(name)
        p.add_argument("--gsc-root", type=Path, required=True)
        p.add_argument("--gsc-revision", required=True, help="Exact full GSC checkout commit")
        p.add_argument("--python", type=Path, default=Path(sys.executable), help="Interpreter with pyproj 3.7.2")
        p.add_argument("--output-dir", type=Path, required=True)
        if name == "run":
            p.add_argument("--source", type=Path, required=True)
            p.add_argument("--origin", nargs=3, type=float, required=True, metavar=("LON", "LAT", "HEIGHT"))
        elif name == "replay":
            p.add_argument("workspace", type=Path)
            p.add_argument("--result-id", required=True)
    p=actions.add_parser("inspect");p.add_argument("workspace", type=Path)
    p=actions.add_parser("verify-export");p.add_argument("directory", type=Path)
    p=actions.add_parser("export");p.add_argument("workspace", type=Path)
    p.add_argument("--result-id", required=True);p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--with-usd", action="store_true", help="Require actual OpenUSD SDK; no fallback")


def dispatch(args):
    command=args.spatial_command
    if command == "catalog":
        from .provider_catalog import catalog
        return catalog()
    if command == "inspect":
        return inspect(args.workspace)
    if command == "verify-export":
        from .spatial_scene import verify_export
        return verify_export(args.directory)
    if command == "export":
        from .spatial_scene import export
        return export(args.workspace,args.result_id,args.output_dir,with_usd=args.with_usd)
    if command == "demo":
        run,origin=demo_run()
    elif command == "run":
        from .session import loads_json
        run=loads_json(read_bounded(args.source).decode("utf-8"));origin=args.origin
    elif command == "replay":
        run,retained=_snapshot(read_bounded(args.workspace))
        matches=[r for r in retained["results"] if r["result_id"] == args.result_id and r["operation_id"] == OPERATION]
        if not matches:
            raise ValueError("Select a retained local-frame result")
        # Full-source replay only. Do not silently widen a saved interval.
        chosen=matches[0]
        if chosen["interval_s"] != [0.0,run["metadata"]["duration_s"]] or chosen["channel"] != next(iter(run["channels"])):
            raise ValueError("This CLI supports full-source replay only")
        origin=chosen["parameters"]["origin"]
    else:
        raise ValueError("Unknown spatial command")
    return create(run,origin,args.output_dir,gsc_root=args.gsc_root,revision=args.gsc_revision,python_executable=args.python)


def main(argv=None):
    """Optional CLI surface on the existing Session, not a second controller."""
    import argparse
    import json
    parser=argparse.ArgumentParser(prog="python -m ciw.spatial_workflow",
        description="Pinned GSC local-frame workflow through CIW Session")
    _register_actions(parser)
    args=parser.parse_args(argv)
    try:
        result=dispatch(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status":"refused", "message":str(exc)},allow_nan=False))
        return 2
    print(json.dumps(result,indent=2,allow_nan=False))
    return 2 if result.get("status")=="refused" else 0


if __name__ == "__main__":
    raise SystemExit(main())
