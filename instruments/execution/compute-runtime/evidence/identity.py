"""Content-addressed identity for pool objects.

Same discipline as `core/canonical/version.py::compute_version_id`,
applied one layer upstream: an id is always a SHA-256 digest of a
canonical (sorted-key, fixed-separator) JSON payload of exactly the
fields that define *identity* -- never of epistemic annotations like
confidence, timestamps, or free-text descriptions, which can be revised
without the object being "a different object." This mirrors `Version.id`
excluding provenance/timestamp from its own hash for the same reason.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(payload: Any) -> bytes:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return text.encode("utf-8")


def content_hash(payload: Any) -> str:
    """SHA-256 hex digest of `payload`'s canonical JSON form. `payload`
    must be built from plain dict/list/str/int/float/bool/None values --
    callers are responsible for reducing dataclasses to that shape first
    (see each `make_*` factory in `evidence/types.py`)."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
