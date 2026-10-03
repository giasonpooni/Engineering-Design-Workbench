"""Refuse exceptions. No clip, no silent repair."""

from __future__ import annotations


class YwirRefuse(Exception):
    """Admission law refused the request. Not a quality score."""

    def __init__(self, code: str, details: str = "") -> None:
        self.code = code
        self.details = details
        super().__init__(f"{code}: {details}" if details else code)
