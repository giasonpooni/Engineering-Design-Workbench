"""Composition store G.

Accepted morphisms only. YWIR does not generate maps. It records
typed ids the caller declares after an admitted burst settles.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Morphism:
    morphism_id: str
    type_name: str
    department: str
    loop: str


class CompositionStore:
    def __init__(self) -> None:
        self._items: dict[str, Morphism] = {}

    def __contains__(self, morphism_id: str) -> bool:
        return morphism_id in self._items

    def __len__(self) -> int:
        return len(self._items)

    def get(self, morphism_id: str) -> Morphism | None:
        return self._items.get(morphism_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(self._items)

    def accept(self, item: Morphism) -> None:
        self._items[item.morphism_id] = item

    def present(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(i for i in ids if i in self._items)
