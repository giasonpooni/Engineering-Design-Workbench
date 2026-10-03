"""workbench.theme: the workbench's visual system -- palette, glyphs,
and layout primitives. Presentation only: nothing here reads, computes,
or interprets a domain value. Every function takes strings and returns
strings.

DESIGN REFERENCE -- clinical / corporate / futuristic / industrial:
restrained monochrome chrome (steel greys for structure, near-white for
data) with exactly three semantic accents and no decorative colour:

    ACCENT (cyan)   system voice -- panel titles, recommendations, the
                    machine telling you what it computed.
    WARN  (amber)   epistemic attention -- UNDETERMINED quantities and
                    HYPOTHETICAL projections. Amber never means "bad";
                    it means "this is not established fact."
    ERR   (red)     rejected input only. Never applied to a residual, a
                    utility, or any scientific quantity -- the interface
                    does not grade results.

Colour degrades cleanly: disabled when stdout is not a TTY (so piped
output and captured test output are plain text), when NO_COLOR is set
(no-color.org), and forced on by WORKBENCH_FORCE_COLOR for demos and
screenshots. Layout is identical either way -- colour is never the only
carrier of meaning; every state also has a word or a glyph.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from typing import List, Optional, Sequence, Tuple

# -- palette ----------------------------------------------------------------------------------------

RESET = "\x1b[0m"
BOLD = "\x1b[1m"

STRUCTURE = "\x1b[38;5;238m"  # borders, rules, frame chrome
MUTED = "\x1b[38;5;241m"      # content hashes, units, secondary annotation
LABEL = "\x1b[38;5;245m"      # field labels
VALUE = "\x1b[38;5;253m"      # primary data
TITLE = "\x1b[38;5;231m"      # masthead
ACCENT = "\x1b[38;5;45m"      # system voice
WARN = "\x1b[38;5;214m"       # undetermined / hypothetical
OK = "\x1b[38;5;79m"          # admitted / confirmed
ERR = "\x1b[38;5;203m"        # rejected input

# -- glyphs -----------------------------------------------------------------------------------------

ARROW = "▸"       # ▸  recommendation / prompt
TRANSITION = "→"  # →  state transition
DOT = "·"         # ·  field separator
HEAVY = "━"       # ━  masthead rule
BULLET = "─"      # ─  panel rule
TREE_MID = "├"    # ├
TREE_END = "└"    # └

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# -- colour control ---------------------------------------------------------------------------------

_FORCED: Optional[bool] = None


def set_color(enabled: Optional[bool]) -> None:
    """Force colour on (True) / off (False), or restore auto-detection
    (None). Used by tests and by demo capture; never called in normal
    interactive use."""
    global _FORCED
    _FORCED = enabled


def color_enabled() -> bool:
    if _FORCED is not None:
        return _FORCED
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("WORKBENCH_FORCE_COLOR"):
        return True
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def paint(text: str, *styles: str) -> str:
    if not styles or not color_enabled():
        return text
    return "".join(styles) + text + RESET


# -- measurement / layout ---------------------------------------------------------------------------


def visible_len(text: str) -> int:
    """Length excluding ANSI styling -- every padding calculation uses
    this, so styled and unstyled output align identically."""
    return len(_ANSI.sub("", text))


def width() -> int:
    """Frame width: the terminal's, clamped to a legible band. Falls
    back to a fixed 78 when not attached to a terminal, so piped and
    captured output is deterministic."""
    try:
        columns = shutil.get_terminal_size(fallback=(80, 24)).columns
    except (OSError, ValueError):
        columns = 80
    return max(64, min(columns - 2, 96))


def pad(text: str, to: int) -> str:
    """Pad to a visible width. An already-oversized string is returned
    UNCHANGED -- which is correct for frame geometry (a clipped body line
    must not gain a character) and wrong for a label column. Use
    `column` for anything a value is concatenated onto."""
    return text + " " * max(0, to - visible_len(text))


def column(text: str, width: int, *, gap: int = 1) -> str:
    """A fixed-width cell that ALWAYS ends in separation.

    Phases 90, 91 and 93 each fixed the same defect in a different
    primitive -- `lineage`, then `tree`, then `kv` -- and Phase 94 found
    it still live in `transition`, where it merged a scientific value
    into the transition glyph:

        80.0 kilonewtons_per_square_metre->  90.0 ...

    The shared cause is `pad(...) + value`: `pad` is a geometry helper
    and correctly leaves an oversized string alone, so a cell whose
    contents reach its own width concatenates straight onto whatever
    follows. That is a real responsibility no view should re-implement,
    and it is this function's only one.

    The guarantee: the result is at least `width` visible columns AND
    ends in at least `gap` spaces. For any text shorter than `width` the
    output is byte-identical to `pad(text, width)` -- so this changes
    nothing that was already rendering correctly, and only ever adds
    separation where there was none.

    Descriptive text may still be clipped by the frame; a value never
    loses its separator. The project's clipping policy is unchanged --
    clip descriptive text, preserve the value, preserve the separator.
    """
    return text + " " * max(gap, width - visible_len(text))


def truncate(text: str, to: int) -> str:
    """ANSI-aware clip to a visible width, with an ellipsis. Styling
    sequences are preserved and never cut mid-escape, and the result is
    reset so a clipped span cannot bleed colour into the frame."""
    if visible_len(text) <= to:
        return text
    if to <= 0:
        return ""
    out: List[str] = []
    visible = 0
    i = 0
    while i < len(text):
        match = _ANSI.match(text, i)
        if match:
            out.append(match.group())
            i = match.end()
            continue
        if visible >= to - 1:
            break
        out.append(text[i])
        visible += 1
        i += 1
    out.append("…")
    if color_enabled():
        out.append(RESET)
    return "".join(out)


# -- value rendering --------------------------------------------------------------------------------

UNDETERMINED = "UNDETERMINED"


def num(value: Optional[float], *, signed: bool = False) -> str:
    """Renders a quantity for display. `None` becomes the explicit word
    UNDETERMINED -- never a dash that could be misread as zero, and
    never zero. `signed=True` prefixes a positive value with `+` so a
    residual's direction is unmissable."""
    if value is None:
        return UNDETERMINED
    text = f"{value:.4f}".rstrip("0")
    if text.endswith("."):
        text += "0"
    if signed and value > 0:
        text = "+" + text
    return text


def quantity(value: Optional[float], unit: str = "", *, signed: bool = False) -> str:
    """A rendered quantity plus its dim unit. An UNDETERMINED value
    carries no unit -- there is no measurement to attach one to."""
    text = num(value, signed=signed)
    if value is None:
        return paint(text, WARN)
    return paint(text, VALUE) + (paint(" " + unit, MUTED) if unit else "")


def ident(identifier: str, size: int = 12) -> str:
    """A content-addressed id, abbreviated for display and marked with a
    leading `·` so it reads as a reference rather than a value. The full
    id always remains on the underlying object."""
    return paint(DOT + identifier[:size], MUTED)


def context(mapping: object) -> str:
    """One-line experimental context. A key ending `_c` renders as
    `<value> C` -- the unit comes from the key the scenario author
    wrote, never inferred from the value."""
    try:
        items = sorted(dict(mapping).items())  # type: ignore[call-overload]
    except (TypeError, ValueError):
        items = []
    if not items:
        return "no context"
    return ", ".join(f"{v} C" if k.endswith("_c") else f"{k}={v}" for k, v in items)


def index(n: int) -> str:
    """Zero-padded candidate index -- `01`, `02` -- so registries stay
    column-aligned past nine entries."""
    return f"{n:02d}"


# -- structural primitives --------------------------------------------------------------------------


def masthead(lines: Sequence[str], *, w: Optional[int] = None) -> str:
    """The session header: heavy rules above and below, no box. Visually
    distinct from every panel so the top of a session is unmistakable."""
    frame = w or width()
    rule_line = paint(HEAVY * frame, STRUCTURE)
    body = [paint("  " + line, TITLE if i == 0 else LABEL) for i, line in enumerate(lines)]
    return "\n".join([rule_line, *body, rule_line])


def panel(
    title: str,
    body: Sequence[str],
    *,
    right: Optional[str] = None,
    tone: str = ACCENT,
    double: bool = False,
    w: Optional[int] = None,
) -> str:
    """A titled frame. `double=True` draws the frame in double rule --
    reserved exclusively for hypothetical/counterfactual content, so a
    projection can never be mistaken at a glance for admitted evidence.
    `right` is a dim right-aligned annotation in the top rule (counts,
    policy, status)."""
    frame = w or width()
    if double:
        tl, tr, bl, br, h, v = "╔", "╗", "╚", "╝", "═", "║"
    else:
        tl, tr, bl, br, h, v = "┌", "┐", "└", "┘", BULLET, "│"

    label = title.upper()
    annotation = right.upper() if right else ""
    # A narrow frame must never break the top rule. Shed the annotation
    # first (it is always secondary), then clip the title if even that
    # does not fit -- the same precedence a reader would apply.
    if annotation and len(label) + len(annotation) + 8 > frame:
        annotation = ""
    if len(label) + 6 > frame:
        label = truncate(label, frame - 6)
    head_plain = f"{tl}{h} {label} " if label else f"{tl}{h}{h}"
    tail_plain = f" {annotation} {h}{tr}" if annotation else f"{h}{tr}"
    fill = max(0, frame - len(head_plain) - len(tail_plain))

    if label:
        head = paint(f"{tl}{h} ", STRUCTURE) + paint(label, BOLD, tone) + paint(" ", STRUCTURE)
    else:
        head = paint(f"{tl}{h}{h}", STRUCTURE)
    if annotation:
        tail = paint(" ", STRUCTURE) + paint(annotation, MUTED) + paint(f" {h}{tr}", STRUCTURE)
    else:
        tail = paint(f"{h}{tr}", STRUCTURE)

    edge = paint(v, STRUCTURE)
    out = [head + paint(h * fill, STRUCTURE) + tail]
    for line in body:
        # clip before padding: no view can overflow the frame, whatever it renders
        out.append(edge + pad(truncate("  " + line, frame - 2), frame - 2) + edge)
    out.append(paint(bl + h * (frame - 2) + br, STRUCTURE))
    return "\n".join(out)


def divider(label: str = "", *, w: Optional[int] = None, inset: int = 6) -> str:
    """A rule inside a panel body, optionally labelled -- used to
    separate a section without nesting another frame."""
    frame = (w or width()) - inset
    if not label:
        return paint(BULLET * frame, STRUCTURE)
    text = label.upper()
    fill = max(0, frame - len(text) - 3)
    return paint(BULLET + " ", STRUCTURE) + paint(text, LABEL) + paint(" " + BULLET * fill, STRUCTURE)


def kv(
    label: str, value: str, *, label_width: int = 18, tone: Optional[str] = None, upper: bool = True,
) -> str:
    """A labelled field. Labels are uppercase, dim, and fixed-width so
    every panel's values land on the same column. `upper=False` keeps a
    label verbatim -- for mathematical notation like `S(t)`, where case
    carries meaning."""
    rendered = paint(value, tone) if tone else value
    text = label.upper() if upper else label
    return paint(column(text, label_width), LABEL) + rendered


def tree(rows: Sequence[Tuple[str, str]], *, label_width: int = 14) -> List[str]:
    """An attribute block, drawn as a small tree so a registry of
    many entries stays visually grouped. Labels are rendered verbatim --
    the caller chooses their case, so notation like `Δ` survives."""
    out: List[str] = []
    for i, (label, value) in enumerate(rows):
        stem = TREE_END if i == len(rows) - 1 else TREE_MID
        out.append(
            paint("    " + stem + " ", STRUCTURE)
            + paint(column(label, label_width), LABEL) + value
        )
    return out


def lineage(steps: Sequence[Tuple[str, str]]) -> List[str]:
    """A provenance tree: each step indented under the one above, so the
    derivation of what is being shown is visible as geometry rather than
    prose. `predict` and `explore` render the SAME tree rooted at the
    same real state -- one stops at the first branch, the other
    continues into the hypothetical one."""
    out: List[str] = []
    for depth, (label, value) in enumerate(steps):
        stem = "" if depth == 0 else "  " * (depth - 1) + "  " + TREE_END + " "
        # pad the whole stem+label prefix to one common column, so values
        # stay aligned however deep the branch goes and however long the
        # label is -- a longer label pushes its own value, never the frame.
        prefix = paint(stem, STRUCTURE) + paint(label.upper(), LABEL)
        # 18 == kv's label column, so both blocks align however deep the
        # branch goes: a longer label pushes its own value, never the frame.
        out.append(column(prefix, 18) + value)
    return out


def transition(before: str, after: str, *, width_before: int = 20) -> str:
    """`before  →  after` -- the shape every before/after pair in the
    interface uses, so a state transition reads the same way whether it
    is a sample count, a prediction, or a state identity."""
    return column(before, width_before) + paint(f"{TRANSITION}  ", STRUCTURE) + after


def badge(text: str, tone: str = ACCENT, *, filled: bool = False) -> str:
    """A status chip. `filled` inverts it -- reserved for the single
    active/selected state in any given view, so exactly one thing draws
    the eye."""
    label = text.upper()
    if not color_enabled():
        return f"[{label}]" if filled else label
    if filled:
        return paint(f" {label} ", "\x1b[7m", tone)
    return paint(label, tone)


def notice(kind: str, message: str, *, hint: str = "", tone: str = ERR, w: Optional[int] = None) -> str:
    """A compact framed message for rejected input and unavailable
    actions -- same frame vocabulary as every other view, so an error is
    a state of the interface rather than a break in it."""
    body = [paint(message, VALUE)]
    if hint:
        body.append("")
        body.append(kv("expected", paint(hint, MUTED)))
    return panel(kind, body, tone=tone, w=w)
