"""A deterministic extractor for scientific property claims.

The shipped `DeterministicExtractor` reads `FACT: key=value` into a FLAT
mapping, which cannot express what a property claim needs: `conditions`
is a mapping, and a value without its method and conditions is a
different fact than it appears to be. So a property line has its own
syntax, and it is still rule-based -- `extraction_method` never begins
with `model:` and confidence is the fixed transcription constant.

    PROPERTY: glass_transition | method=DSC | conditions=heating_rate:10K/min
              | value=373 | unit=K | uncertainty_kind=absent
    DISTRIBUTION: polymer | Mn=3251 | Mw=8271 | dispersity=2.54
    METHOD: quantum | functional=B3LYP | basis=6-31G* | domain=T:200-400
              | inputs=T:300

DELIBERATELY PERMISSIVE. It parses what the line says and emits it; it
does not check that a property carries a method, that a quantity carries
a unit, or that a distribution carries its field set. Those are the
VERTICAL'S GATES and they run in the pipeline, where a refusal is
visible and quarantinable. An extractor that declined to emit a bad
candidate would refuse it invisibly -- and an invisible refusal cannot
be told from a source that never made the claim, which is exactly the
difference between a measured rejection rate and no measurement.
"""

from __future__ import annotations

from typing import Dict, Tuple

from evidence.types import Record
from scout.interface import ExtractionCandidate


def _scalar(text: str):
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _pairs(body: str) -> Dict[str, object]:
    """`a:1,b:2` -> {"a": 1, "b": 2}. Empty body -> {}."""
    out: Dict[str, object] = {}
    for chunk in body.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        out[key.strip()] = _scalar(value.strip())
    return out


def _range(body: str) -> Dict[str, object]:
    """`T:200-400` -> {"T": [200, 400]}."""
    out: Dict[str, object] = {}
    for chunk in body.split(","):
        chunk = chunk.strip()
        if ":" not in chunk:
            continue
        key, span = chunk.split(":", 1)
        if "-" in span:
            low, _, high = span.partition("-")
            out[key.strip()] = [_scalar(low.strip()), _scalar(high.strip())]
    return out


class PropertyExtractor:
    """Rule-based, no model, confidence fixed -- a verbatim
    transcription of what the line states."""

    extraction_method = "regex:property_v1"
    confidence = 1.0

    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]:
        candidates = []
        for raw_line in record.raw_content.splitlines():
            line = raw_line.strip()
            content: Dict[str, object] = {}

            if line.startswith("PROPERTY:"):
                parts = [p.strip() for p in line[len("PROPERTY:"):].split("|")]
                content["property"] = parts[0]
                for part in parts[1:]:
                    if "=" not in part:
                        continue
                    key, value = (p.strip() for p in part.split("=", 1))
                    content[key] = _pairs(value) if key == "conditions" else _scalar(value)

            elif line.startswith("DISTRIBUTION:"):
                parts = [p.strip() for p in line[len("DISTRIBUTION:"):].split("|")]
                fields: Dict[str, object] = {}
                for part in parts[1:]:
                    if "=" in part:
                        key, value = (p.strip() for p in part.split("=", 1))
                        fields[key] = _scalar(value)
                content["distribution_kind"] = parts[0]
                content["distribution_fields"] = fields

            elif line.startswith("METHOD:"):
                parts = [p.strip() for p in line[len("METHOD:"):].split("|")]
                block: Dict[str, object] = {}
                inputs: Dict[str, object] = {}
                for part in parts[1:]:
                    if "=" not in part:
                        continue
                    key, value = (p.strip() for p in part.split("=", 1))
                    if key == "domain":
                        block["applicability_domain"] = _range(value)
                    elif key == "inputs":
                        inputs = _pairs(value)
                    else:
                        block[key] = _scalar(value)
                content["method_block_kind"] = parts[0]
                content["method_block"] = block
                if inputs:
                    content["method_inputs"] = inputs

            if content:
                candidates.append(ExtractionCandidate(
                    content=content, entities=(), relations=(),
                    extraction_method=self.extraction_method,
                    confidence=self.confidence))
        return tuple(candidates)
