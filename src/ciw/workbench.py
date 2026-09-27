"""Shared retained sources and native instrument results for one CIW session.

Loads the transport-packed module body from adjacent _wb_pack_*.txt fragments.
"""
from __future__ import annotations

from pathlib import Path

_pack = Path(__file__).resolve().parent
_code = "".join((_pack / f"_wb_pack_{i}.txt").read_text() for i in range(4))
exec(compile(_code, __file__, "exec"), globals())
