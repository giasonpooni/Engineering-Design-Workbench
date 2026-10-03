"""Conway departments that may hold a token budget.

Gauge is legal to declare and legal to cap at zero. Exploration may
hold entropy. Ledger and evidence are ship channels.
"""

from __future__ import annotations

from ywir.constitution import DEPARTMENTS, MAX_DEPARTMENTS
from ywir.errors import YwirRefuse


def check_department(name: str) -> str:
    if name not in DEPARTMENTS:
        raise YwirRefuse("unknown_department", name)
    return name


def check_department_count(names: tuple[str, ...]) -> None:
    if len(names) > MAX_DEPARTMENTS:
        raise YwirRefuse("too_many_departments", str(len(names)))
    unseen = [n for n in names if n not in DEPARTMENTS]
    if unseen:
        raise YwirRefuse("unknown_department", ",".join(unseen))
