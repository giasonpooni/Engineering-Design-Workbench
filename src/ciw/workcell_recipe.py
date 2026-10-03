"""Installed workcell recipes share the existing supervisor and production runner.

A recipe selects contracts, not a shell command. JSON cannot import providers.
The default prop recipe remains byte-for-byte owned by workcell_contracts.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from . import workcell_contracts as legacy


@dataclass(frozen=True)
class Recipe:
    recipe_id: str
    source_paths: tuple[str, ...]
    writable_paths: tuple[str, ...]
    outputs: dict[str, tuple[str, ...]]
    exports: dict[str, tuple[str, ...]]
    operations: dict[str, str]
    policy: dict
    checks: Callable
    gates: Callable
    register: Callable
    validate: Callable
    carry_source: bool = False

    def input_paths(self, stage: str) -> set[str]:
        if stage not in legacy.STAGES:
            raise ValueError("Unknown installed stage")
        if stage == 'build':
            return set(self.source_paths)
        return set(self.outputs['build']) | (set(self.source_paths) if self.carry_source else set())


PROP = Recipe(
    recipe_id=legacy.RECIPE,
    source_paths=('compiler.py','motion.gd','spec.json'),
    writable_paths=('compiler.py','motion.gd'),
    outputs={'build':('mesh.json','motion.gd','prop.res','main.scn'), 'test':(), 'package':('slice.pck',)},
    exports={'package':('slice.pck',)}, operations=legacy.OPS, policy=legacy.POLICY,
    checks=legacy.checks_for, gates=legacy.gates, register=legacy.register_schemas,
    validate=legacy.validate_capture,
)


def installed(name: str = legacy.RECIPE) -> Recipe:
    if name == PROP.recipe_id:
        return PROP
    if name == '1792.smith.v1':
        from .workcell_smith import SMITH
        return SMITH
    raise ValueError('Workcell recipe is not explicitly installed')
