"""Doctrine generator: canonical architecture in, role doctrine out.

Doctrine is a GENERATED PROJECTION of the structured sources
(invariants.yaml, evidence_class.yaml, vocabulary_map.yaml, the binding
CONSTRAINTS -- never the binding table itself). The generator is not
another source of truth:

    doctrine_source_is_canonical        content below derives only from
                                        the YAML sources
    doctrine_regeneration_is_deterministic
                                        pure function of file contents;
                                        sorted iteration; no timestamps,
                                        hostnames, or environment
    generated_doctrine_matches_source   conformance.check_doctrine_current
                                        regenerates and diffs; non-zero
                                        diff fails closed
    manual_generated_doctrine_changes_fail
                                        same check -- a hand edit to the
                                        projection cannot survive it

BUDGET: each doctrine file is capped (DOCTRINE_BUDGET_CHARS). Overflow
FAILS CLOSED with the overflowing sections named -- structural material
belongs in schemas/invariants/enforcement, not in more prose.

VENDOR-FREE: the generator lints its own output; a vendor identity in
doctrine is a generation failure, not a warning.
"""

from __future__ import annotations

import pathlib
from typing import Dict

import yaml

from architecture.conformance import lint_doctrine_vendor_free

ROOT = pathlib.Path(__file__).resolve().parent

DOCTRINE_BUDGET_CHARS = 4000


class DoctrineBudgetError(ValueError):
    """Generated doctrine exceeded its budget: move structure into
    schemas or enforcement, never into more prose."""


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text())


def _epistemic_doctrine() -> str:
    classes = _load("evidence_class.yaml")
    vocabulary = _load("vocabulary_map.yaml")
    lines = [
        "# Epistemic doctrine (generated -- do not edit; see doctrine_generator.py)",
        "",
        "Evidence classes are assigned at ingest and are immutable; the class",
        "is a total, fail-closed function of the declared extraction method.",
        "",
        "Classes:",
    ]
    for name in sorted(classes["classes"]):
        lines.append(f"- {name}: {classes['classes'][name]['meaning']}")
    lines += ["", "Presentation vocabulary maps onto these classes; it never mints:"]
    for term in sorted(vocabulary["vocabulary_map"]):
        entry = vocabulary["vocabulary_map"][term]
        lines.append(f"- {term} -> {entry['class']}")
    for term in sorted(vocabulary.get("not_a_class", {})):
        lines.append(f"- {term}: NOT a class ({vocabulary['not_a_class'][term]['kind']})")
    lines += [
        "",
        "Write barriers: proposals are not evidence (optimizer output has no",
        "write path into the pool); derived state re-enters only through",
        "acquisition; no operation promotes a class after ingest.",
        "",
    ]
    return "\n".join(lines)


def _role_doctrine(role: str, duty: str, constraints: list) -> str:
    lines = [
        f"# {role} doctrine (generated -- do not edit; see doctrine_generator.py)",
        "",
        f"Duty: {duty}",
        "",
        "Constraints:",
    ]
    lines += [f"- {constraint}" for constraint in constraints]
    lines.append("")
    return "\n".join(lines)


def generate_doctrine() -> Dict[str, str]:
    """The projection: {filename: content}, deterministic, budgeted,
    vendor-free."""
    shared = [
        "the substrate is an acquisition-first loop; external information "
        "enters through acquisition only",
        "every enforcement validator records its authoring binding "
        "(builder_check_lineage_recorded)",
        "resource telemetry is operational metadata and never enters "
        "evidence identity",
    ]
    documents = {
        "epistemic.md": _epistemic_doctrine(),
        "builder.md": _role_doctrine("Builder", "implementation and building", shared + [
            "core schemas are closed to verticals; extension happens in "
            "vertical modules against open content mappings",
            "a core invariant change is a version increment plus a re-run of "
            "every declared vertical and probe -- never a silent widening",
        ]),
        "scout.md": _role_doctrine("Scout", "discovery and proposal", shared + [
            "extraction declares its method at ingest; an undeclared method "
            "is refused, never guessed",
            "model-extracted claims are the document's claims (asserted), "
            "never measurements",
        ]),
        "resolver.md": _role_doctrine("Resolver", "semantic resolution and proposal", shared + [
            "substance-level merge requires compatible declared identity "
            "policies on both records; mismatch blocks the merge",
            "contradiction requires evaluated discriminating variables; "
            "values without their conditions are not comparable",
        ]),
        "validator.md": _role_doctrine("Validator", "acceptance and rejection", shared + [
            "the validator is vendor-independent from the proposing lineage "
            "(binding details live in the canonical binding configuration, "
            "not here)",
            "acceptance is fail-closed; rejected input enters quarantine "
            "with failing invariant ids -- there is no force path",
            "validation is a status on a claim, never an evidence class",
        ]),
    }
    for name, content in documents.items():
        lint_doctrine_vendor_free(content, where=name)
        if len(content) > DOCTRINE_BUDGET_CHARS:
            raise DoctrineBudgetError(
                f"{name} is {len(content)} chars against a budget of "
                f"{DOCTRINE_BUDGET_CHARS}; move structural material into "
                f"schemas or enforcement"
            )
    return documents


def write_doctrine() -> None:
    out = ROOT / "generated" / "doctrine"
    out.mkdir(parents=True, exist_ok=True)
    for name, content in generate_doctrine().items():
        (out / name).write_text(content)


if __name__ == "__main__":
    write_doctrine()
