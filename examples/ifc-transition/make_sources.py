"""Create example declarations; neither observation is a field measurement.

The public-model observation is only a synthetic negative-path stimulus. The
whole original public IFC must remain unchanged even though it cannot lower.
Run from a checkout: python examples/ifc-transition/make_sources.py OUTPUT_DIR.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path

from ciw.control_contracts import save_new

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SHA256 = "73b0e45d931d5dc13bfee5fdc7bd80f796526445458b2de74c4168d209097832"
PUBLIC_REVISION = "e6f1c1d80ac216e1c1d6f88d4650f13d8c8277b7"
PUBLIC_PATH = "IFC 4.0.2.1 (IFC 4)/ISO Spec - ReferenceView_V1.2/wall-with-opening-and-window.ifc"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    examples = (
        ("room", ROOT / "examples/bim-quantity/room.ifc", "CIWSTOREY00000000000015",
         {"kind": "SYNTHETIC_FIXTURE", "source_uri": "repository:examples/bim-quantity/room.ifc",
          "revision": "ciw.bim-quantity-source.v1", "source_path": "examples/bim-quantity/room.ifc",
          "license": "AGPL-3.0-or-later"}),
        ("public-wall", ROOT / "examples/ifc-transition/buildingSMART-wall-opening-window.ifc",
         "2GNgSHJ5j9BRUjqT$7tE8w",
         {"kind": "PUBLIC_REFERENCE", "source_uri": "https://github.com/buildingSMART/Sample-Test-Files",
          "revision": PUBLIC_REVISION, "source_path": PUBLIC_PATH, "license": "CC-BY-4.0"}),
    )
    declarations = []
    for name, path, global_id, provenance in examples:
        raw = path.read_bytes()
        artifact_ref = "sha256:" + sha256(raw).hexdigest()
        if name == "public-wall" and (len(raw) != 12492 or artifact_ref != "sha256:" + PUBLIC_SHA256):
            raise ValueError("Public fixture differs from pinned original bytes")
        target = {"ifc_class": "IfcBuildingStorey", "global_id": global_id, "quantity": "ClearHeight"}
        frame = "synthetic-declared-model-frame"
        spec = {"run_id": "experiment.ifc-" + name + ".v1", "canonical_entity_id": "candidate:ifc-" + name,
                "required_admission_authority": "authority.external-review.v1",
                "target": target, "model_frame": frame, "source_provenance": provenance | {"sha256": artifact_ref}}
        observation = {"schema": "ciw.bim-scalar-observation.v1", "value": 2.99, "variance": 0.000025,
                       "unit": "m", "frame": frame, "ifc_sha256": artifact_ref,
                       "cross_covariance_policy": "independent", **target}
        declarations.extend(((args.output_dir / (name + "-spec.json"), spec),
                             (args.output_dir / (name + "-observation.json"), observation)))
    if any(path.exists() or path.is_symlink() for path, _ in declarations):
        raise FileExistsError("Use a fresh output directory; declarations are create-only")
    for path, value in declarations:
        save_new(path, value)
    print("Created room and public-wall declarations; both observations are synthetic.")


if __name__ == "__main__":
    main()
