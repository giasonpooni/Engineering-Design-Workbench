"""Run, inspect or replay a bounded native curved-path candidate study.

Install CIW first. This script deliberately does not prepend checkout code, so
an isolated installed-wheel invocation exercises the installed implementation.
"""
from __future__ import annotations

import argparse
import base64
from pathlib import Path
import sys

from ciw import curved_path_study as study
from ciw.adapters.subprocess import _json
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw.telemetry import canonical


def _read(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Input exceeds its byte budget")
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run", help="Execute baseline and heading candidates with the pinned native provider")
    run.add_argument("--source", required=True, type=Path)
    run.add_argument("--spec", required=True, type=Path, help="Study ID, candidates, sample_index and limits")
    for name in ("inspect", "replay"):
        command = sub.add_parser(name)
        command.add_argument("--workspace", required=True, type=Path)
        command.add_argument("--study", required=True, type=Path)
    for name in ("run", "replay"):
        command = sub.choices[name]
        command.add_argument("--csg-repo", required=True, type=Path)
        command.add_argument("--output", required=True, type=Path, help="New directory; never overwrite a prior run")
    args = parser.parse_args(argv)
    session = None
    created_output = False
    try:
        if args.action == "inspect":
            session = Session.from_workspace(args.workspace)
            record = study.load_study(args.study, session.workbench)
        else:
            args.output.mkdir(parents=True, exist_ok=False)
            created_output = True
            if args.action == "run":
                spec = _json(_read(args.spec, study.MAX_BYTES))
                study._keys(spec, {"study_id", "candidates", "sample_index", "limits"})
                # Shape/domain errors need no provider execution, even baseline.
                study.make_request("pending-baseline", **spec)
                raw = _read(args.source, 32768)
                session = Session(make_demo_run(), args.output)
                session.workbench.bind_workflow(study.KIND, {"csg": str(args.csg_repo.resolve())})
                source = session.workbench.add_source({"kind": study.KIND, "label": spec["study_id"] + "/baseline",
                    "bytes_b64": base64.b64encode(raw).decode("ascii")})
                baseline = session.workbench.execute({"operation_id": study.OPERATION, "source_id": source["source_id"]})
                record = study.run_study(session.workbench, study.make_request(baseline["bundle_id"], **spec))
            else:
                session = Session.from_workspace(args.workspace, args.output)
                original = study.load_study(args.study, session.workbench)
                session.workbench.bind_workflow(study.KIND, {"csg": str(args.csg_repo.resolve())})
                record = study.replay_study(session.workbench, original)
            session.save_workspace(args.output / "workspace.json")
            study.save_study(args.output / "study.json", session.workbench, record)
        print(canonical({"action": args.action, "study_digest": record["study_digest"],
            "authority": record["authority"], "baseline": record["baseline"]["summary"],
            "candidates": [{"candidate_id": row["candidate_id"], "summary": row["summary"],
                            "response": row["response"]} for row in record["candidates"]]}).decode("utf-8"))
        return 0
    except (OSError, ValueError) as exc:
        # Completed occurrences remain recoverable after a later candidate fails.
        if session is not None and created_output:
            session.save_workspace(args.output / "partial-workspace.json")
        print("Curved-path study refused: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
