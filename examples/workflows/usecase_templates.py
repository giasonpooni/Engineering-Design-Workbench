#!/usr/bin/env python3
"""Owned-family render templates for generated use-case scenarios.

Every function below replays one existing owned teaching emitter and only
reframes its retained numbers.  It does not add a CIW kind or a solver.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping

EXAMPLES = Path(__file__).resolve().parents[1]
REPO = EXAMPLES.parent
if str(EXAMPLES) not in sys.path:
    sys.path.insert(0, str(EXAMPLES))
from _render_json import write_render as _write_render  # noqa: E402

ESM_URL = "https://github.com/giasonpooni/Evidence-and-State-Management"

_EMITTERS = {
    "FSRT": EXAMPLES / "fsrt-two-reservoir" / "emit_render.py",
    "CSG": EXAMPLES / "csg-path-sensitivity" / "emit_render.py",
    "CSE": EXAMPLES / "cse-bim-quantity" / "emit_render.py",
    "PROVED_HEAT": EXAMPLES / "proved-heat" / "emit_proof_render.py",
    "RESIDUAL_CUSUM": EXAMPLES / "residual-cusum-teach" / "emit_render.py",
    "GTE_CIRCLE": EXAMPLES / "gte-circle-eligibility" / "run_or_emit.py",
    "PLSR": EXAMPLES / "plsr-stability-verdict" / "emit_render.py",
    "ENERGY_ACCURACY": EXAMPLES / "energy-accuracy-teach" / "emit_render.py",
    "VFE": EXAMPLES / "vfe-sensor-bias-teach" / "emit_render.py",
    "MEASUREMENT_CHAIN": EXAMPLES / "measurement-chain-teach" / "emit_render.py",
}

_BUILDER_CACHE: dict[str, Any] = {}


def _owned_payload(family: str) -> dict[str, Any]:
    """Load and call the existing family emitter's build_payload once/process."""
    if family not in _BUILDER_CACHE:
        source = _EMITTERS[family]
        module_name = "owned_template_" + family.lower().replace("_", "_")
        spec = importlib.util.spec_from_file_location(module_name, source)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load owned emitter: {source}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _BUILDER_CACHE[family] = module.build_payload
    return copy.deepcopy(_BUILDER_CACHE[family]())


def _render_json(family: str, output: Path | str, scenario: Mapping[str, Any]) -> Path:
    """Reframe owned retained numbers as a presentation-only use case."""
    data = _owned_payload(family)
    slug = str(scenario["slug"])
    title = str(scenario["title"])
    industry = str(scenario["industry"])
    sentence = str(scenario["sentence"])
    non_claim = str(scenario["non_claim"])
    source_label = f"HOST_FROM_OWNED_CONFIG::{family}::{slug}"
    data.update(
        {
            # Keep the owned schema/kind and operation fields; they are not new
            # CIW kinds.  These keys identify this presentation framing only.
            "source": source_label,
            "upstream_status": "HOST_FROM_OWNED_CONFIG",
            "claim_scope": "computational-integrity-only",
            "may_authorize": False,
            "presentation_only": True,
            "use_case_slug": slug,
            "scenario": {
                "title": title,
                "industry": industry,
                "lesson": sentence,
                "owned_family": family,
                "non_claim": non_claim,
            },
            "data_source": (
                f"HOST_FROM_OWNED_CONFIG: examples/{_EMITTERS[family].parent.name}/ "
                f"owned {family} teaching emitter; same retained numbers, no second solver."
            ),
            "caption": f"{title}. {sentence} Presentation only; {non_claim}.",
            "evidence_seam": {
                "provider": "Evidence-and-State-Management",
                "role": "evidence seam / retention path only",
                "url": ESM_URL,
                "local_receipt": f"examples/{slug}/results/{slug}_render.json",
                "verification": "not claimed; may_authorize remains false",
                "variant": "UNADMITTED_CANDIDATE_RETENTION",
                "canonicalAdmission": False,
            },
            "canonicalAdmission": False,
            "forbidden_claims": sorted(
                set(
                    list(data.get("forbidden_claims", []))
                    + [non_claim, "new CIW kind", "second solver", "physical verification"]
                )
            ),
            "may_authorize": False,
        }
    )
    return _write_render(output, data)


def emit_fsrt(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("FSRT", output, scenario)


def emit_csg(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("CSG", output, scenario)


def emit_cse(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("CSE", output, scenario)


def emit_proved_heat(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("PROVED_HEAT", output, scenario)


def emit_residual_cusum(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("RESIDUAL_CUSUM", output, scenario)


def emit_gte_circle(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("GTE_CIRCLE", output, scenario)


def emit_plsr(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("PLSR", output, scenario)


def emit_energy_accuracy(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("ENERGY_ACCURACY", output, scenario)


def emit_vfe(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("VFE", output, scenario)


def emit_measurement_chain(output: Path | str, scenario: Mapping[str, Any]) -> Path:
    return _render_json("MEASUREMENT_CHAIN", output, scenario)


EMIT_FUNCTIONS = {
    "FSRT": emit_fsrt,
    "CSG": emit_csg,
    "CSE": emit_cse,
    "PROVED_HEAT": emit_proved_heat,
    "RESIDUAL_CUSUM": emit_residual_cusum,
    "GTE_CIRCLE": emit_gte_circle,
    "PLSR": emit_plsr,
    "ENERGY_ACCURACY": emit_energy_accuracy,
    "VFE": emit_vfe,
    "MEASUREMENT_CHAIN": emit_measurement_chain,
}
