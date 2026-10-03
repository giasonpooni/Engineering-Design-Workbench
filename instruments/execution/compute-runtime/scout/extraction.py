"""The only Extractor implementation in this codebase: deterministic,
rule-based, no model.

Fixture Records use a small, explicit line format (chosen for the same
reason `adapters/json_adapter.py`'s `__`-joined flattening was chosen
over an ambiguous alternative -- unambiguous, trivially deterministic to
parse, and easy to read in a test fixture):

    ENTITY: <label> :: <kind>
    RELATION: <from_label> | <type> | <to_label>
    FACT: <key>=<value> <key>=<value> ...

The `RELATION:` line uses `|` rather than an arrow embedded in the label
text (an earlier draft used `-<type>->`, which mis-parses the moment a
label itself contains a hyphen, e.g. `rheo-sim` -- caught by running the
fixtures through this extractor, see `docs/SCOUT_ARCHITECTURE.md`).

This exists to prove the `scout.interface.Extractor` Protocol end-to-end
without a model dependency (§R step 2: "deterministic sources only").
A future model-based extractor (Mistral or otherwise) implements the
same Protocol and would set `extraction_method="model:<name>"` with an
explicit, non-None `confidence` -- `scout.pipeline.run_scout` enforces
that rule regardless of which Extractor produced the candidate.
"""

from __future__ import annotations

from evidence.types import Record
from scout.interface import ExtractedEntity, ExtractedRelation, ExtractionCandidate


def _coerce(raw: str):
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


class DeterministicExtractor:
    """Rule-based extraction over the `ENTITY:`/`RELATION:`/`FACT:` line
    format. `extraction_method` never starts with `"model:"`, and
    `confidence` is a fixed constant -- a verbatim transcription, not an
    inference, per `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §B."""

    extraction_method = "regex:kv_v1"
    confidence = 1.0

    def extract(self, record: Record):
        entities = []
        relations = []
        content: dict = {}

        for raw_line in record.raw_content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("ENTITY:"):
                body = line[len("ENTITY:") :].strip()
                if "::" in body:
                    label, kind = body.split("::", 1)
                    entities.append(ExtractedEntity(label=label.strip(), kind=kind.strip()))
            elif line.startswith("RELATION:"):
                body = line[len("RELATION:") :].strip()
                parts = [p.strip() for p in body.split("|")]
                if len(parts) == 3 and all(parts):
                    from_label, rel_type, to_label = parts
                    relations.append(
                        ExtractedRelation(from_label=from_label, type=rel_type, to_label=to_label)
                    )
            elif line.startswith("FACT:"):
                body = line[len("FACT:") :].strip()
                for token in body.split():
                    if "=" in token:
                        key, value = token.split("=", 1)
                        content[key.strip()] = _coerce(value.strip())

        if not entities and not relations and not content:
            return ()

        return (
            ExtractionCandidate(
                content=content,
                entities=tuple(entities),
                relations=tuple(relations),
                extraction_method=self.extraction_method,
                confidence=self.confidence,
            ),
        )
