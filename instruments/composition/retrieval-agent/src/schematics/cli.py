"""sra --call-jspt --rci-digest DIGEST -o results"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import io
from .agent import run
from .fixtures import quadratic_drag
from .project_mermaid import mermaid
from .project_usd import usda


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sra", description="Schematics retrieval agent. Function graph + factor graph.")
    parser.add_argument("schematic", nargs="?", help="Path to plant.sch.json. Omit for quadratic-drag.")
    parser.add_argument("--fixture-A", action="store_true")
    parser.add_argument("--call-jspt", action="store_true")
    parser.add_argument("--rci-digest", default=None)
    parser.add_argument("-o", "--out", default="results")
    args = parser.parse_args(argv)
    sch = io.read(args.schematic) if args.schematic else quadratic_drag()
    report = run(sch, attach_fixture_A=args.fixture_A, call_jspt=args.call_jspt, rci_digest=args.rci_digest)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    io.write(report.schematic, out / "plant.sch.json")
    (out / "plant.mmd").write_text(mermaid(report.schematic), encoding="utf-8")
    (out / "plant.usda").write_text(usda(report.schematic), encoding="utf-8")
    print(f"nodes {len(report.schematic.nodes)} edges {len(report.schematic.edges)}")
    print(f"next {report.next_step}")
    for d in report.decisions:
        print(f"{d.status.value:14} {d.tool:32} {d.node_id:12} {d.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
