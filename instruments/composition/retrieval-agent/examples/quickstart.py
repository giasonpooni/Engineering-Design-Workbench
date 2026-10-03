from pathlib import Path
from schematics import quadratic_drag, run
from schematics import io
from schematics.project_mermaid import mermaid
from schematics.project_usd import usda

OUT = Path(__file__).resolve().parents[1] / "results"
OUT.mkdir(exist_ok=True)


def main() -> None:
    report = run(quadratic_drag(), attach_fixture_A=True)
    io.write(report.schematic, OUT / "quadratic_drag.sch.json")
    (OUT / "quadratic_drag.mmd").write_text(mermaid(report.schematic), encoding="utf-8")
    (OUT / "quadratic_drag.usda").write_text(usda(report.schematic), encoding="utf-8")
    lines = ["# quadratic-drag first slice", "", f"- nodes: {len(report.schematic.nodes)}", f"- next: {report.next_step}", ""]
    for d in report.decisions:
        lines.append(f"- {d.status.value} {d.tool} {d.node_id}")
    lines.append("")
    lines.append("Fixture A does not open PLSR. Use --call-jspt after installing pinned sensitivity.")
    (OUT / "quickstart.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((OUT / "quickstart.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
