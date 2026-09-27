#!/usr/bin/env python3
"""Run the host analog for pyramid-method-gap and print the teaching split.

Exits 0 when theta=0 is decrease-definite under the common P and theta=1 is not.
Does not import or register a CIW operation. PLSR is optional; if missing, prints
HOST_ANALOG_ONLY and does not mint runtime-status-v1 strings.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from analog_plant import (
    analog_draft_declaration,
    build_analog_render,
    certificate_on_A0,
    evaluate,
    write_draft,
    write_render,
)


def try_plsr():
    """Return (imported: bool, label: str). Never invent sealed runtime-status-v1."""
    for name in (
        "parameterized_lyapunov_stability_runtime",
        "plsr",
    ):
        try:
            __import__(name)
            return True, f"imported:{name}"
        except Exception:
            continue
    return False, "HOST_ANALOG_ONLY"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-draft",
        type=Path,
        default=None,
        help="Optional path for analog-draft JSON (local artifact; not admitted state).",
    )
    parser.add_argument(
        "--write-render",
        type=Path,
        default=None,
        help=(
            "Optional path for analog-render JSON for Godot presentation "
            "(default suggestion: results/analog_render.json)."
        ),
    )
    args = parser.parse_args(argv)

    plsr_ok, plsr_label = try_plsr()
    P = certificate_on_A0()
    r0 = evaluate(0.0, P)
    r1 = evaluate(1.0, P)
    r05 = evaluate(0.5, P)

    print("pyramid-method-gap host analog")
    print(f"PLSR: {plsr_label}")
    if not plsr_ok:
        print("HOST_ANALOG_ONLY")
    print(
        f"theta=0: alpha={r0['alpha']:.3f} maxeig(M)={r0['maxeig_M']:.3f} "
        f"hurwitz={r0['hurwitz']} decrease_definite={r0['decrease_definite']}"
    )
    print(
        f"theta=0.5: alpha={r05['alpha']:.6f} maxeig(M)={r05['maxeig_M']:.6f} "
        f"hurwitz={r05['hurwitz']} decrease_definite={r05['decrease_definite']} "
        f"(reported; not hidden)"
    )
    print(
        f"theta=1: alpha={r1['alpha']:.3f} maxeig(M)={r1['maxeig_M']:.3f} "
        f"hurwitz={r1['hurwitz']} decrease_definite={r1['decrease_definite']}"
    )

    teaching_ok = r0["decrease_definite"] and not r1["decrease_definite"]
    print(f"teaching_split_ok={teaching_ok}")

    if args.write_draft is not None:
        draft = analog_draft_declaration(P, [r0, r05, r1])
        write_draft(args.write_draft, draft)
        print(f"wrote_analog_draft={args.write_draft}")
        print("note=local artifact only; may_authorize=false; not admitted state")

    if args.write_render is not None:
        render = build_analog_render(P, plsr_label=plsr_label)
        write_render(args.write_render, render)
        print(f"wrote_analog_render={args.write_render}")
        print(
            "note=presentation artifact; meshes host-computed; "
            "Godot cards read JSON numerics; may_authorize=false"
        )

    return 0 if teaching_ok else 1


if __name__ == "__main__":
    sys.exit(main())
