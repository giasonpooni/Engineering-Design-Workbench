"""The API planes' shared contract.

WHAT EXISTS HERE AND WHAT DOES NOT. The plane architecture names four
planes and roughly sixty module families; measured against the three
apparatuses, twenty of those concepts exist and forty-one do not --
including `tenant`, `http`, `mcp`, `router`, `token`, `signature`,
`federation` and `replay`. This package is NOT that architecture. It is
the one part of it that can be built before any of them: the envelope
every response must carry, so that when the planes arrive no response
can escape the invariant by having been written first.
"""
