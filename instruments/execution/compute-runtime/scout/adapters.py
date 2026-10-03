"""The smallest useful source abstraction: one adapter, parameterized by
a fixed tuple of documents, structurally satisfying `SourceAdapter`.

Deliberately not four separate classes for "papers"/"patents"/"github"/
"docs" -- per §7's "do NOT attempt to build a giant crawler," one
adapter that is agnostic to `source_kind` (the field that actually
distinguishes a paper from a repo) is the smaller, equally general
choice. Additional adapters (live network access, a real API client)
implement the same `SourceAdapter` Protocol later without changing
anything in `scout.pipeline` or `evidence/`.
"""

from __future__ import annotations

from typing import Tuple

from scout.interface import RawDocument


class FixtureSourceAdapter:
    def __init__(self, documents: Tuple[RawDocument, ...]) -> None:
        self._documents = documents

    def fetch(self) -> Tuple[RawDocument, ...]:
        return self._documents
