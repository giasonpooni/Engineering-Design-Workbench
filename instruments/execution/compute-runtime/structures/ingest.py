"""The chemistry vertical's ingest path: its gates, wired to acquisition.

WHY THIS FILE EXISTS. The vertical's guards -- typed quantities,
property context, distribution identity, method blocks -- were correct,
tested, and had NO CALLER on any acquisition or execution path. A
per-code probe measured it: twenty refusal codes, twenty LIVE, ZERO
reachable, with the path terminating at the import graph. A gate nothing
reaches cannot refuse anything, and a rejection rate over it would read
0% and be evidence about nothing.

This wires them, and the ORDER matters. Wiring must come BEFORE any real
dataset arrives: a first real measurement over unreached gates produces
silence that reads as cleanliness, and a first number carries an
authority a probe result does not.

WHAT ROUTES WHAT. A candidate declares what kind of claim it is and the
gate that governs that kind runs. The declaration is the payload's, made
at ingest, and the routing is total and fail-closed -- the same shape as
`class_assigned_at_ingest`, where the extraction method declares and the
map refuses anything undeclared.

    property         -> assert_property_context (and the quantity gates
                        beneath it)
    distribution_kind -> assert_distribution_identity
    method_block     -> assert_method_block, and assert_applicability
                        when the payload also carries inputs

A candidate declaring NONE of these is not a chemistry claim and passes
untouched. That is deliberate: the gate governs claims of a kind, not
every document that happens through the door, and a gate that refused
everything it did not recognise would make the vertical a filter on the
whole corpus.
"""

from __future__ import annotations

from typing import Mapping, Optional, Tuple

from evidence.quarantine import Quarantine

from structures.method_blocks import (
    MethodBlockError,
    assert_applicability,
    assert_method_block,
)
from structures.quantity import QuantityError, assert_property_context
from structures.substance import (
    IdentityPolicyError,
    assert_distribution_identity,
)

#: The invariant ids this gate can refuse under: what a quarantined
#: record names, and what a per-invariant rejection rate is computed
#: over.
#:
#: THESE ARE NOT THIS FILE'S NAMES TO CHOOSE. All five were already
#: declared in the acquisition layer's `architecture/invariants.yaml`,
#: and the first three ids written here -- `distribution_has_no_point_
#: identity`, `computed_method_fully_specified`, `prediction_within_
#: declared_domain` -- were renames of `no_point_identity_for_
#: distributions`, `computed_fully_specified` and `applicability_domain_
#: declared`. Same rule, second name: the alias problem, in its fourth
#: position, shipped one commit after building the register whose whole
#: purpose is to detect it. The derived register would have grown from
#: 26 rows to 29 and read as three more unimplemented rules over there
#: plus three unrelated ones here.
#:
#: So the earlier declaration keeps the id. A rule gets ONE id across
#: the project, and the party that implements it second does not get to
#: rename it by implementing it.
PROPERTY_CONTEXT = "no_context_free_property"
QUANTITY_TYPED = "quantity_is_typed"
DISTRIBUTION_IDENTITY = "no_point_identity_for_distributions"
METHOD_BLOCK = "computed_fully_specified"
APPLICABILITY = "applicability_domain_declared"

GATE_INVARIANTS = (
    PROPERTY_CONTEXT, QUANTITY_TYPED, DISTRIBUTION_IDENTITY,
    METHOD_BLOCK, APPLICABILITY,
)

#: Which refusals belong to which invariant. `assert_property_context`
#: delegates to `assert_quantity_type`, so one call can refuse for either
#: reason and the two are told apart by the message -- recorded here
#: rather than inferred at the call site, because attributing a quantity
#: refusal to the property invariant would corrupt the per-invariant rate
#: while leaving the total unchanged.
_QUANTITY_REFUSALS = (
    "without a unit", "not one of", "contradicts", "requires the",
    "bare scalars",
)


def _quantity_or_property(message: str) -> str:
    return QUANTITY_TYPED if any(f in message for f in _QUANTITY_REFUSALS) else PROPERTY_CONTEXT


def chemistry_content_gate(content: Mapping[str, object]) -> Tuple[str, ...]:
    """The gate itself: the invariant ids this content fails, or ().

    Total and fail-closed over the kinds it recognises. Every refusal is
    attributed to ONE invariant id, because the metric this feeds is per
    invariant and a refusal filed under the wrong one is a wrong rate
    with a right total.
    """
    failing = []

    if "property" in content:
        try:
            assert_property_context(content)
        except QuantityError as error:
            failing.append(_quantity_or_property(str(error)))

    kind = content.get("distribution_kind")
    if isinstance(kind, str) and kind:
        fields = content.get("distribution_fields")
        try:
            assert_distribution_identity(kind, fields if isinstance(fields, Mapping) else {})
        except IdentityPolicyError:
            failing.append(DISTRIBUTION_IDENTITY)

    block = content.get("method_block")
    if isinstance(block, Mapping):
        block_kind = str(content.get("method_block_kind", ""))
        try:
            assert_method_block(block_kind, block)
        except MethodBlockError:
            failing.append(METHOD_BLOCK)
        else:
            inputs = content.get("method_inputs")
            if isinstance(inputs, Mapping):
                try:
                    assert_applicability(block, inputs)
                except MethodBlockError:
                    failing.append(APPLICABILITY)

    return tuple(failing)


def ingest_documents(adapter, extractor, pool,
                     quarantine: Optional[Quarantine] = None):
    """Acquisition with the chemistry vertical's gates wired in.

    The single production call site that makes these guards reachable.
    `run_scout` stays vertical-agnostic; the coupling lives here, where
    the vertical owns it.
    """
    from scout.pipeline import run_scout

    return run_scout(adapter, extractor, pool,
                     content_gates=(chemistry_content_gate,),
                     quarantine=quarantine)
