"""Substance and distribution identity: declared policy, never inference.

A molecule has multiple valid representations that do not round-trip
(tautomers, stereocentres, salts/solvates, isotopologues are the same
substance or different substances DEPENDING ON THE QUESTION). So
substance identity is a POLICY -- declared, versioned, carried on the
record -- and a merge between records whose policies disagree is
refused, never silently resolved. Computational identity
(`Molecule.identity()`, exact bytes) is untouched and remains a
different relation; this module adds the substance layer beside it.

Distribution-kind entities (polymer, formulation, batch) have NO point
identity at all: a structure string alone is inadmissible for them.

Every refusal here is fail-closed (`IdentityPolicyError`), and nothing
here merges anything -- these are the guards a merge must pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple

from execution.commitments import commit_hex

SUBSTANCE_TAG = "ste.chem.substance-identity.v1"
DISTRIBUTION_TAG = "ste.chem.distribution-identity.v1"


class IdentityPolicyError(ValueError):
    """An undeclared, malformed, or mismatched identity policy refuses."""


_POLICY_DIMENSIONS = {
    "tautomer": ("distinct", "normalized"),   # normalized requires rule_id
    "stereo": ("distinct", "ignored"),
    "salt_solvate": ("distinct", "parent_only"),
    "isotope": ("distinct", "ignored"),
}


@dataclass(frozen=True)
class ResolutionPolicy:
    """One declared choice per dimension. `tautomer` may be
    "normalized(<rule_id>)" -- the rule id is part of the policy."""

    tautomer: str = "distinct"
    stereo: str = "distinct"
    salt_solvate: str = "distinct"
    isotope: str = "distinct"

    def __post_init__(self):
        for dimension, allowed in _POLICY_DIMENSIONS.items():
            value = getattr(self, dimension)
            base = value.split("(", 1)[0]
            if base not in allowed:
                raise IdentityPolicyError(
                    f"resolution_policy.{dimension}={value!r} is not one of {allowed}"
                )
            if base == "normalized" and not (
                value.startswith("normalized(") and value.endswith(")")
                and len(value) > len("normalized()")
            ):
                raise IdentityPolicyError(
                    "tautomer normalization requires an explicit rule id: "
                    "normalized(<rule_id>)"
                )

    def canonical(self) -> str:
        return (f"tautomer={self.tautomer};stereo={self.stereo};"
                f"salt_solvate={self.salt_solvate};isotope={self.isotope}")


@dataclass(frozen=True)
class SubstanceIdentity:
    """A substance-level identity: which representation, at which
    version, under which declared resolution policy. The identity
    commits to all three -- the policy is retained on the record, so a
    later merge can CHECK it instead of guessing it."""

    representation: str          # e.g. the molecule's canonical bytes hex,
                                 # an InChI, a SMILES -- caller-declared
    representation_version: str  # e.g. "ste-molecule v1", "standard-inchi 1.06"
    policy: ResolutionPolicy

    def __post_init__(self):
        if not self.representation or not self.representation_version:
            raise IdentityPolicyError(
                "substance identity requires representation and "
                "representation_version"
            )

    def identity(self) -> str:
        return commit_hex(SUBSTANCE_TAG, [
            self.representation.encode(),
            self.representation_version.encode(),
            self.policy.canonical().encode(),
        ])


def assert_identity_policy(a: SubstanceIdentity, b: SubstanceIdentity) -> None:
    """The merge guard (`chem.assert_identity_policy`): substance-level
    merge requires BOTH records to declare policies, and the policies,
    representation systems and versions to agree exactly. Mismatch
    blocks the merge -- it never silently resolves."""
    if a.policy != b.policy:
        raise IdentityPolicyError(
            f"identity policy mismatch blocks the merge: "
            f"{a.policy.canonical()} vs {b.policy.canonical()}"
        )
    if (a.representation_version != b.representation_version):
        raise IdentityPolicyError(
            f"representation version mismatch blocks the merge: "
            f"{a.representation_version!r} vs {b.representation_version!r}"
        )


_DISTRIBUTION_FIELDS = {
    "polymer": frozenset({"repeat_units", "composition", "molar_mass",
                          "dispersity", "end_groups", "architecture"}),
    "formulation": frozenset({"components", "fractions", "process_history_ref"}),
    "batch": frozenset({"material_ref", "process_ref", "timestamp", "facility"}),
}


@dataclass(frozen=True)
class DistributionIdentity:
    """An entity of distribution kind -- identified by its field set,
    never by a structure string. `molar_mass` carries Mn and/or Mw for
    polymers; `timestamp`/`facility` make a batch a PRODUCTION EVENT."""

    kind: str
    fields: Mapping[str, object]

    def __post_init__(self):
        required = _DISTRIBUTION_FIELDS.get(self.kind)
        if required is None:
            raise IdentityPolicyError(
                f"unknown distribution kind {self.kind!r}; "
                f"known: {sorted(_DISTRIBUTION_FIELDS)}"
            )
        missing = required - set(self.fields)
        if missing:
            raise IdentityPolicyError(
                f"{self.kind} identity is missing {sorted(missing)}; a "
                f"distribution-kind entity has no point identity"
            )

    def identity(self) -> str:
        canonical = ";".join(
            f"{key}={self.fields[key]!r}" for key in sorted(self.fields))
        return commit_hex(DISTRIBUTION_TAG, [self.kind.encode(), canonical.encode()])


def assert_distribution_identity(kind: str, fields: Mapping[str, object]) -> "DistributionIdentity":
    """The ingest guard (`chem.assert_distribution_identity`): construct
    or refuse. A structure string alone -- or any incomplete field set --
    is inadmissible for a distribution-kind entity."""
    if set(fields) == {"structure"} or not fields:
        raise IdentityPolicyError(
            f"a {kind} identified only by a structure string is inadmissible"
        )
    return DistributionIdentity(kind, fields)
