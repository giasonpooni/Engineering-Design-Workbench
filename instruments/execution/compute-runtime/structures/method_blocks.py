"""Computed-chemistry method blocks: execution provenance is necessary,
not sufficient.

The substrate records computation identity (program bytes,
configuration, input -- `ExecutionSpecification`) and occurrence
(`OperationTrace`); nothing here duplicates that. What the CHEMISTRY
vertical adds is the domain-method declaration a computed result needs
before it can support a canonical assertion: a quantum result without
functional and basis set, or an MD result without force field and
ensemble, is not yet a scientific result. This is a QUALIFIED
interpretation of `execution_recorded` -- narrower for canonical
assertion inside this vertical, core semantics unchanged.

For the workloads that already run here, the block is derivable from
the real inputs (the GROMACS descriptor embeds the engine version,
topology, and .mdp bytes -- the parameters ARE in the computation
identity; the block names them for the canonical-assertion gate).
"""

from __future__ import annotations

from typing import Mapping

METHOD_BLOCKS = {
    "quantum": frozenset({"method", "functional", "basis_set",
                          "solvation_model", "convergence"}),
    "md": frozenset({"force_field", "force_field_version", "ensemble",
                     "timestep", "equilibration", "sampling_time",
                     "thermostat", "barostat"}),
    "ml": frozenset({"model_id", "snapshot", "training_evidence_classes",
                     "applicability_domain"}),
}


class MethodBlockError(ValueError):
    """Computed evidence missing its method block is inadmissible for
    canonical assertion."""


def assert_method_block(kind: str, block: Mapping[str, object]) -> None:
    """The gate (`chem.assert_method_block`): fully specified or refused."""
    required = METHOD_BLOCKS.get(kind)
    if required is None:
        raise MethodBlockError(
            f"unknown computed-method kind {kind!r}; known: {sorted(METHOD_BLOCKS)}"
        )
    missing = required - set(block)
    if missing:
        raise MethodBlockError(
            f"{kind} method block is missing {sorted(missing)}; the result "
            f"is inadmissible for canonical assertion until fully specified"
        )


def assert_applicability(block: Mapping[str, object], inputs: Mapping[str, object]) -> None:
    """The gate (`chem.assert_applicability`): an ML prediction outside
    its DECLARED applicability domain is refused for canonical
    assertion. The domain is a mapping of input keys to (lo, hi)
    bounds; an input outside any declared bound, or an input the domain
    never declared, refuses."""
    domain = block.get("applicability_domain")
    if not isinstance(domain, Mapping) or not domain:
        raise MethodBlockError(
            "prediction carries no declared applicability domain; refused"
        )
    for key, value in inputs.items():
        if key not in domain:
            raise MethodBlockError(
                f"input {key!r} is outside the declared applicability domain "
                f"(never declared); refused"
            )
        lo, hi = domain[key]  # type: ignore[misc]
        if not (lo <= value <= hi):  # type: ignore[operator]
            raise MethodBlockError(
                f"input {key}={value!r} is outside the declared domain "
                f"[{lo}, {hi}]; flagged and inadmissible for canonical assertion"
            )
