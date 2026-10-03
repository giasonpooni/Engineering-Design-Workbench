"""Frozen numeric law for charts and covariances.

These are not user parameters. The caller sets T, S, offsets, the plant,
and a declared metric. They do not set the condition cap or the round-trip
tolerance.
"""

MAX_CONDITION_NUMBER = 1e12
ROUND_TRIP_TOLERANCE = 1e-8
