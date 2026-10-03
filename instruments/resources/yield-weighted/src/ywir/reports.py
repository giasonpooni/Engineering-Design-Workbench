"""Plain-text reports. Not a dashboard."""

from __future__ import annotations

from pathlib import Path

from ywir.runtime import HostState, Verdict, snapshot


def render(host: HostState, verdicts: list[Verdict]) -> str:
    snap = snapshot(host)
    lines = [
        f"# YWIR {snap['loop']}",
        "",
        f"base: {snap['base']}",
        f"closed: {snap['closed']}",
        f"eta_hat: {snap['eta_hat']:.6f}",
        f"budget: {snap['budget']}",
        f"store: {snap['store']}",
        "",
        "## letters",
        "",
    ]
    for v in verdicts:
        extra = f" code={v.refuse_code}" if v.refuse_code else ""
        lines.append(f"- {v.letter} {v.status}{extra} \u2014 {v.details}")
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, host: HostState, verdicts: list[Verdict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(host, verdicts), encoding="utf-8")
