from pathlib import Path
from schematics import EdgeKind, Node, NodeKind, Schematic, run
from schematics import io

OUT = Path(__file__).resolve().parents[1] / "results"
OUT.mkdir(exist_ok=True)


def main() -> None:
    sch = Schematic(meta={"id": "unknown_box"})
    sch.add(Node(id="x", kind=NodeKind.VARIABLE, attrs={"role": "state"}))
    sch.add(Node(id="f", kind=NodeKind.FUNCTION, attrs={"class": "unknown"}))
    sch.add(Node(id="observer", kind=NodeKind.OBSERVER, attrs={}))
    sch.connect(EdgeKind.INPUT, "x", "f")
    sch.connect(EdgeKind.OBSERVES, "observer", "f")
    report = run(sch)
    io.write(report.schematic, OUT / "unknown_box.sch.json")
    for d in report.decisions:
        print(d.status.value, d.tool, d.reason)


if __name__ == "__main__":
    main()
