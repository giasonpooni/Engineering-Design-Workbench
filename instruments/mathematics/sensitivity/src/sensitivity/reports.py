"""Plain-text experiment reports with explicit numerical limits."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .checks import CheckResult
from .perturbation import LocalValidity, PerturbationSweep


def format_checks(title: str, checks: Iterable[CheckResult]) -> str:
    lines = [f"# {title}", "", "These checks are first-order and local.", ""]
    for check in checks:
        mark = "PASS" if check.passed else "FAIL"
        lines.append(f"- [{mark}] {check.name}: {check.details}")
    lines.append("")
    return "\n".join(lines)


def format_sweep(sweep: PerturbationSweep, validity: LocalValidity | None = None) -> str:
    lines = [
        f"## Perturbation sweep: {sweep.model}",
        "",
        f"Jacobian source: {sweep.source}",
        "",
        "| scale | absolute remainder | relative remainder |",
        "| --- | --- | --- |",
    ]
    for sample in sweep.samples:
        lines.append(
            f"| {sample.scale:.3e} | {sample.absolute_error:.3e} | {sample.relative_error:.3e} |"
        )
    lines.append("")
    if validity is not None:
        lines.append(
            f"Declared local radius along this direction: "
            f"{validity.valid_scale!s} "
            f"(first invalid scale: {validity.first_invalid_scale!s})."
        )
        lines.append(validity.notes)
        lines.append("")
    return "\n".join(lines)


def write_report(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
