"""Fixture source data (§7: "do NOT attempt to build a giant crawler").

Two source types are represented -- enough to prove `SourceAdapter` is a
real abstraction over more than one kind of source, not a special case
for one -- both using the line format `scout.extraction` parses. No live
network access anywhere in this module; every timestamp is a fixed
constant, so a SCOUT run over these fixtures is fully reproducible.
"""

from __future__ import annotations

from scout.interface import RawDocument

FIXED_RETRIEVED_AT = "2026-08-01T00:00:00Z"

PAPER_DOCUMENT = RawDocument(
    source_name="Journal of Polymer Science, Vol. 40",
    source_kind="paper",
    content="""
ENTITY: FEP :: material
ENTITY: extrusion :: process
RELATION: FEP | used_in | extrusion
FACT: property=melt_viscosity value=1250 unit=Pa.s temperature=260
""".strip(),
    locator="page_17_table_4",
    retrieval_method="fixture:paper_v1",
    retrieved_at=FIXED_RETRIEVED_AT,
)

GITHUB_REPO_DOCUMENT = RawDocument(
    source_name="github.com/example/rheo-sim",
    source_kind="github_repo",
    content="""
ENTITY: rheo-sim :: software
ENTITY: FEP :: material
RELATION: rheo-sim | models | FEP
FACT: property=repository_stars value=42 unit=count
""".strip(),
    locator="README.md",
    retrieval_method="fixture:github_v1",
    retrieved_at=FIXED_RETRIEVED_AT,
)

ALL_FIXTURE_DOCUMENTS = (PAPER_DOCUMENT, GITHUB_REPO_DOCUMENT)
