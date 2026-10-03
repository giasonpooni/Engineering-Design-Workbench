#!/usr/bin/env python3
"""Emit the derived invariant register, canonicalized and digested.

The register is a PROJECTION of every bound repository's canonical
sources. It is emitted, never hand-authored -- hand-authored YAML has
nothing but agreement between it and a digest the two readers disagree
on, and this artifact's whole purpose is to be quotable outside the
project.

TWO PROPERTIES, DELIBERATELY SEPARATED. Conflating them made this
repository's test suite fail because a SIBLING pushed -- which is not a
defect here, and which puts pressure on the staleness check in exactly
the wrong direction: the way to get green becomes weakening the gate.

  FAITHFULNESS  the committed artifact is exactly what the derivation
                produces from the commits it NAMES. This repository's
                responsibility, deterministic, offline, and a hard gate.
  CURRENCY      the commits it names are still the siblings' remote
                heads. A fact about the world that changes when someone
                else pushes, with nobody doing anything wrong.

Currency is enforced at EMISSION (the artifact is always current at the
moment it is written) and REPORTED afterwards. It is not a test failure,
because a test that fails when a counterparty is productive is measuring
the counterparty.

Usage:  python3 build_invariant_register.py [--check | --currency]
  (no flag)  writes invariant_register.yaml and .sha256, requiring
             currency against every remote
  --check    FAITHFULNESS: re-derives from the local clones and fails if
             the committed artifact does not reproduce. Asks no remote.
  --currency CURRENCY: asks every remote and reports drift. Exit 0 when
             current, 2 when a sibling has moved -- distinct from 1 so a
             caller can tell "someone pushed" from "the artifact is
             wrong".
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from architecture.derive_register import (  # noqa: E402
    derive,
    deriving_party_of,
    register_document,
    without_currency,
)
from architecture.exchange.canonical_yaml import (  # noqa: E402
    canonical_bytes,
    canonical_sha256,
)

ARTIFACT = HERE / "invariant_register.yaml"
DIGEST = HERE / "invariant_register.sha256"


def build(check_remotes: bool = True) -> tuple[bytes, str]:
    document = register_document(derive(check_remotes=check_remotes))
    return canonical_bytes(document), canonical_sha256(document)


def report_currency() -> int:
    """Ask every remote and say what has moved. Never rewrites anything."""
    from architecture.derive_register import (
        BOUND_REPOSITORIES, _commit_of, _git, _remote_head,
    )

    drifted = []
    for label, root in BOUND_REPOSITORIES:
        if not root.is_dir():
            print(f"  {label:5} UNREACHABLE at {root}")
            drifted.append(label)
            continue
        branch = _git(root, "branch", "--show-current").stdout.strip()
        local = _commit_of(root)
        remote = _remote_head(root, branch)
        if remote is None:
            print(f"  {label:5} remote unreachable ({branch})")
            drifted.append(label)
        elif remote == local:
            print(f"  {label:5} in sync      {local[:12]}  {branch}")
        elif _git(root, "merge-base", "--is-ancestor", remote, local).returncode == 0:
            print(f"  {label:5} local ahead  {local[:12]} > {remote[:12]}  {branch}")
        else:
            print(f"  {label:5} BEHIND       {local[:12]} < {remote[:12]}  {branch}")
            drifted.append(label)
    if drifted:
        print(f"\nnot current against: {', '.join(drifted)} -- fetch and re-emit")
        return 2
    print("\nevery bound repository is current")
    return 0


def main(argv) -> int:
    if "--currency" in argv:
        return report_currency()
    # --check is FAITHFULNESS and asks no remote: a sibling pushing must
    # not turn this repository's suite red.
    payload, digest = build(check_remotes="--check" not in argv)
    if "--check" in argv:
        if not ARTIFACT.exists() or not DIGEST.exists():
            print("register artifact is not committed", file=sys.stderr)
            return 1
        import yaml as _yaml
        committed = _yaml.safe_load(ARTIFACT.read_text())
        fresh = register_document(derive(check_remotes=False))
        party = deriving_party_of(committed)
        if without_currency(committed, party) != without_currency(fresh, party):
            print(
                "UNFAITHFUL REGISTER: re-deriving from the local clones does "
                "not reproduce the committed artifact. Either the artifact "
                "was edited by hand, or a clone moved since it was emitted -- "
                "run --currency to tell which.",
                file=sys.stderr,
            )
            return 1
        if DIGEST.read_text().strip() != canonical_sha256(committed):
            print("register digest does not match its content", file=sys.stderr)
            return 1
        print(f"register faithful to its recorded commits: {digest}")
        return 0
    ARTIFACT.write_bytes(payload)
    DIGEST.write_text(digest + "\n")
    print(f"wrote {ARTIFACT.name} ({len(payload)} bytes)\n{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
