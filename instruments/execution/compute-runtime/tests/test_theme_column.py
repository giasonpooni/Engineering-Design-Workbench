"""Phase 94: the label/value column primitive.

WHY THIS EXISTS (the abstraction's one real responsibility)

Phases 90, 91 and 93 each fixed the same defect in a different
primitive -- `lineage`, then `tree`, then `kv` -- and each wrote the
rule slightly differently. Phase 94 found it STILL LIVE in
`transition`, where it merged a scientific value into the glyph in an
ordinary CLI session (the unit is caller-supplied text, so a long one
is reachable by normal use):

    80.0 kilonewtons_per_square_metre->  90.0 ...

The shared cause is the `pad(...) + value` idiom. `pad` is a geometry
helper: it correctly leaves an oversized string unchanged, because a
clipped panel body line must not gain a character. That is the wrong
behaviour for any cell a value is concatenated onto, and re-deriving
the distinction at each call site is what produced four bugs.

`column(text, width, gap=1)` owns exactly that distinction and nothing
else. The abstraction is justified by a demonstrated defect at four
independent sites, not by tidiness.

THE INVARIANT
    visible_len(column(t, w)) >= w
    column(t, w) always ends in at least `gap` spaces
    column(t, w) == pad(t, w) for every t shorter than w

The third clause is what makes this a safe consolidation: nothing that
already rendered correctly changes. Verified end-to-end -- all sixteen
views render byte-identically before and after this phase.

CLIPPING POLICY (unchanged, not re-invented): descriptive text may be
clipped by the frame; a scientific value, an identity, or a separator
never is.
"""

import pytest

from workbench import theme


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


# -- the invariant -----------------------------------------------------------------------------------


@pytest.mark.parametrize("width", [1, 4, 12, 14, 18, 22, 40])
@pytest.mark.parametrize("length", [0, 1, 2, 13, 17, 18, 19, 22, 36, 80])
def test_column_always_ends_in_separation(width: int, length: int):
    rendered = theme.column("A" * length, width)
    assert theme.visible_len(rendered) >= width
    assert rendered.endswith(" "), (width, length, repr(rendered))
    # and never eats into the text itself
    assert rendered.strip() == "A" * length


@pytest.mark.parametrize("width", [4, 12, 14, 18, 22])
def test_column_is_identical_to_pad_below_the_width(width: int):
    """The consolidation is safe precisely because of this: every cell
    that already rendered correctly is untouched."""
    for length in range(width):
        text = "A" * length
        assert theme.column(text, width) == theme.pad(text, width)


@pytest.mark.parametrize("length", [18, 19, 25, 50])
def test_column_separates_where_pad_did_not(length: int):
    """The defect, at exactly the boundary and beyond."""
    text = "A" * length
    assert not theme.pad(text, 18).endswith(" ")   # the old behaviour
    assert theme.column(text, 18).endswith(" ")    # the guarantee


def test_column_is_ansi_aware():
    theme.set_color(True)
    painted = theme.paint("LABEL", theme.LABEL)
    rendered = theme.column(painted, 18)
    assert theme.visible_len(rendered) == 18
    assert theme.visible_len(theme.column(theme.paint("A" * 20, theme.LABEL), 18)) == 21


def test_gap_is_configurable_but_never_zero_by_default():
    assert theme.column("A" * 20, 18, gap=3).endswith("   ")
    assert theme.visible_len(theme.column("A" * 20, 18, gap=3)) == 23


def test_pad_still_leaves_oversized_geometry_alone():
    """`pad` must keep its own contract -- a clipped frame line must not
    gain a character. The two helpers are deliberately different."""
    assert theme.pad("A" * 30, 10) == "A" * 30
    assert theme.visible_len(theme.pad("A" * 30, 10)) == 30


# -- every label primitive now makes the same guarantee ------------------------------------------------


@pytest.mark.parametrize("length", [1, 13, 14, 15, 17, 18, 19, 28, 36])
def test_every_label_primitive_separates_label_from_value(length: int):
    """The four sites that independently exhibited the defect."""
    label = "L" * length
    value = "VALUE"

    rendered = theme.kv(label, value)
    assert "L" + value not in rendered, f"kv merged at length {length}"

    rendered = theme.tree([(label, value)])[0]
    assert "L" + value not in rendered, f"tree merged at length {length}"

    rendered = theme.lineage([(label, value)])[0]
    assert "L" + value not in rendered, f"lineage merged at length {length}"

    rendered = theme.transition(label, value)
    assert "L" + theme.TRANSITION not in rendered, f"transition merged at length {length}"


@pytest.mark.parametrize("value", [
    "80.0 MPa", "-3000.25 MPa", "1234567.89 MPa", "-0.0001 MPa",
    "80.0 kilonewtons_per_square_metre", theme.UNDETERMINED, "NOT_DETERMINABLE",
    "0", "2",
])
def test_a_scientific_value_is_never_fused_to_a_separator(value: str):
    """The Phase 94 defect, at the site it was actually found: a value
    long enough to fill the column must still be readable as a value."""
    rendered = theme.transition(value, "90.0 MPa", width_before=22)
    before = rendered.split(theme.TRANSITION)[0]
    assert before.rstrip() == value
    assert before.endswith(" "), repr(rendered)


@pytest.mark.parametrize("label,width", [("A", 18), ("A" * 18, 18), ("A" * 19, 18), ("A" * 36, 18)])
def test_the_pathological_label_matrix(label: str, width: int):
    """1 char, exactly the column, column+1, and 2x the column."""
    for rendered in (
        theme.kv(label, "VALUE", label_width=width),
        theme.tree([(label, "VALUE")], label_width=width)[0],
        theme.lineage([(label, "VALUE")])[0],
    ):
        plain = theme._ANSI.sub("", rendered)
        assert "VALUE" in plain
        # the value is reachable as its own token, never glued to the label
        assert plain.split()[-1] == "VALUE"
