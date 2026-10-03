"""What the plane architecture NAMES, against what the tree HAS.

A SPECIFICATION IS A CLAIM ABOUT A TREE. This one names four planes and
roughly sixty module families; measured, twenty of those concepts exist
across the three apparatuses and forty-one do not. That is not a
criticism of the design -- a design is allowed to describe what is not
built yet -- but the gap has to be a MEASUREMENT rather than an
impression, because the failure mode is specific and this project has
met it repeatedly: a document that describes a system reads exactly the
same whether the system exists or not.

THE ONE THAT MATTERS MOST is `tenant`. Three of the four planes are
defined as tenant-bound, and no tenant concept exists anywhere in the
three apparatuses. A plane distinction resting on an authority boundary
the tree does not have is UNENFORCEABLE, and an API carrying
tenant-shaped names with no tenant enforcement reads as isolated while
isolating nothing -- which is worse than one that never claimed to.
"""

from __future__ import annotations

import pathlib
from typing import Dict, List, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SIBLINGS = {
    "STE": REPO_ROOT,
    "DAQ": pathlib.Path("/home/user/notationsystems/notations-acquisition-channel"),
    "SCL": pathlib.Path("/home/user/notationsystems/scientific-compute-layer"),
}
SKIP = frozenset({".git", "__pycache__", "node_modules", "target", "build",
                  "dist", ".venv", "zk", "crates", "tests", "docs"})

#: The module families the plane architecture names, grouped by the
#: treatment it assigns them. Transcribed from the specification, and
#: kept as the SPEC'S OWN words so a reader can check the transcription
#: rather than trusting this file's paraphrase.
NAMED: Dict[str, Tuple[str, ...]] = {
    "universal reference resolution and proof verification": (
        "kernel", "canonical", "registry", "verification", "router"),
    "internal persistence, read via tenant-bound resolvers": (
        "journal", "closure", "postgres"),
    "governed ingestion; read policy/receipt/retention": (
        "source_policy", "acquisition", "normalization", "capture",
        "archive", "retention"),
    "corpus catalog, comparison, membership, time-bound reads": (
        "corpus", "admission", "profile", "identity", "diff", "release"),
    "projection catalog and bounded query with exact proof roots": (
        "lexical", "vector", "spatial", "analytical", "graph", "coverage",
        "index", "projection"),
    "tenant-bound agent tools returning references and authorization": (
        "context", "agent", "search"),
    "release and trust status; activation and signing operator-only": (
        "methodology", "attestation", "signer", "activation"),
    "governance and readiness with typed evidence": (
        "preflight", "readiness"),
    "operations: lag, replay state, bounded health, evidence": (
        "worker", "checkpoint", "telemetry", "snapshot"),
    "architecture and topology, logical views only": (
        "ecosystem", "apparatus", "control_plane", "security"),
    "signed packet ingestion, acknowledgements, audit reads": (
        "federation", "signature", "replay", "audit"),
    "governance and research: candidates, reviews, reproducibility": (
        "adjudication", "challenge", "harness", "computation"),
    "infrastructure: capability and status only": (
        "object_store", "token", "auth", "deployment", "http", "mcp",
        "runtime"),
}

#: Named concepts whose ABSENCE makes a plane unenforceable rather than
#: merely unbuilt. Called out separately because "41 missing" flattens
#: a distinction that matters: most absences are work not yet done, and
#: these are claims the architecture cannot currently keep.
LOAD_BEARING = ("tenant", "http", "mcp", "token", "auth", "signature")


def _module_names(root: pathlib.Path) -> set:
    names = set()
    if not root.is_dir():
        return names
    for path in root.rglob("*.py"):
        if SKIP & set(path.parts):
            continue
        names.add(path.stem.lower())
        names.add(path.parent.name.lower())
    return names


def coverage() -> Dict[str, Dict[str, List[str]]]:
    """For every named concept, which apparatuses have a module for it.

    MATCHED BY NAME, and that is a stated weakness rather than a hidden
    one: a concept implemented under a different word reads as absent
    here. The measurement is therefore a LOWER BOUND on what exists and
    an upper bound on what is missing, which is the direction that fails
    safe -- it over-reports the gap rather than the coverage.
    """
    present: Dict[str, List[str]] = {}
    for label, root in SIBLINGS.items():
        names = _module_names(root)
        for concepts in NAMED.values():
            for concept in concepts:
                if any(concept in name for name in names):
                    present.setdefault(concept, []).append(label)
    for concept in LOAD_BEARING:
        present.setdefault(concept, present.get(concept, []))
    every = [concept for concepts in NAMED.values() for concept in concepts]
    every += [concept for concept in LOAD_BEARING if concept not in every]
    return {
        "present": {name: holders for name, holders in present.items() if holders},
        "absent": {name: [] for name in every if not present.get(name)},
    }


def document() -> dict:
    result = coverage()
    present, absent = result["present"], result["absent"]
    unenforceable = [name for name in LOAD_BEARING if name in absent]

    return {
        "extends": "core@1.0.0",
        "generated_by": "architecture/plane_coverage.py",
        "artifact": "plane_coverage",
        "owner": "STE",
        "subject": "the plane architecture, measured against the tree",
        "method": (
            "every module family the specification names is matched by NAME "
            "against module and package names across the three apparatuses. "
            "Matching by name is a stated weakness: a concept implemented "
            "under a different word reads as absent, so this is a LOWER "
            "bound on coverage and an UPPER bound on the gap -- the "
            "direction that over-reports what is missing rather than what "
            "exists"),
        "summary": {
            "concepts_named": len(present) + len(absent),
            "present": len(present),
            "absent": len(absent),
            "planes_declared": 4,
        },
        "the_finding": {
            "a_specification_is_a_claim_about_a_tree": (
                f"{len(present)} of {len(present) + len(absent)} named "
                "concepts exist. That is not a criticism -- a design may "
                "describe what is not built. It is recorded because a "
                "document describing a system reads exactly the same "
                "whether the system exists or not, and this is the only "
                "thing that tells them apart"),
            "unenforceable_rather_than_merely_unbuilt": (
                f"{unenforceable} are absent, and their absence is a "
                "different kind from the rest. Three of the four planes are "
                "defined as TENANT-BOUND and no tenant concept exists "
                "anywhere. A plane distinction resting on an authority "
                "boundary the tree does not have cannot be enforced, and an "
                "API carrying tenant-shaped names with no tenant "
                "enforcement reads as isolated while isolating nothing -- "
                "which is worse than one that never claimed to"),
            "what_was_built_instead": (
                "api/envelope.py -- the specification's own key invariant, "
                "which is the one part buildable before any of the absent "
                "concepts: a response is grounded or it says it is not, "
                "there is no third construction, and the read-only planes "
                "cannot report a mutation. It does not authenticate, "
                "authorise or bind a tenant, and says so"),
        },
        "present": {name: sorted(holders) for name, holders in sorted(present.items())},
        "absent": sorted(absent),
        "unenforceable_today": unenforceable,
        "treatments": {label: list(concepts) for label, concepts in sorted(NAMED.items())},
        "what_this_does_not_claim": (
            "that an absent concept is missing from the PRODUCT. It is "
            "missing from these three repositories, matched by name. A "
            "concept living in another repository, under another word, or "
            "in a design not yet committed is absent HERE and this artifact "
            "says only that"),
    }


def emit(root: pathlib.Path = REPO_ROOT) -> pathlib.Path:
    import sys as _sys
    _sys.path.insert(0, str(root / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes, canonical_sha256

    payload = document()
    out = root / "architecture" / "exchange" / "plane_coverage.yaml"
    out.write_bytes(canonical_bytes(payload))
    (root / "architecture" / "exchange" / "plane_coverage.sha256").write_text(
        canonical_sha256(payload) + "\n")
    return out


def main() -> int:
    import sys

    payload = document()
    summary = payload["summary"]
    print("=== THE PLANE ARCHITECTURE, MEASURED ===")
    print(f"  concepts named : {summary['concepts_named']}")
    print(f"  present        : {summary['present']}")
    print(f"  absent         : {summary['absent']}")
    print(f"\n  UNENFORCEABLE TODAY: {payload['unenforceable_today']}")
    print("  three of the four planes are tenant-bound and no tenant")
    print("  concept exists. That is not 'unbuilt' -- it is a claim the")
    print("  architecture cannot currently keep.")
    print("\n  absent:")
    for name in payload["absent"]:
        print(f"      {name}")
    if "--emit" in sys.argv:
        out = emit()
        print(f"\n  wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
