from pathlib import Path
from schematics import quadratic_drag, run
from schematics import io

OUT = Path(__file__).resolve().parents[1] / "results"
OUT.mkdir(exist_ok=True)
RECORD = {
    "board": "LILYGO-T-Display-S3",
    "interface": "i2c-displacement",
    "instrument": "lvdt-12mm",
    "installation": "bench-fixture-A",
    "quality": {"acquisition": "sample received", "timing": "device clock at readout", "calibration": "applicable", "inference": "not run"},
    "rci_digest": "sha256-field-fixture",
}


def main() -> None:
    report = run(quadratic_drag(), rci_record=RECORD)
    io.write(report.schematic, OUT / "field_record.sch.json")
    print("next", report.next_step)


if __name__ == "__main__":
    main()
