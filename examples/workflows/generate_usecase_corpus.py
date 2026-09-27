#!/usr/bin/env python3
"""Generate a deterministic, combinatorial corpus of owned-family use cases.

This writes folders and thin wrappers only. Numbers come from
``usecase_templates.py`` and its ten existing owned teaching emitters.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
WORKFLOWS = EXAMPLES / "workflows"
INDEX_PATH = EXAMPLES / "usecase-index.json"
CATALOG_PATH = EXAMPLES / "usecase-catalog.md"
ESM_URL = "https://github.com/giasonpooni/Evidence-and-State-Management"

# Deliberately broad domain roots.  Combined with operating contexts below this
# is a 480-name industry/domain catalog, rather than a hand-written README list.
INDUSTRY_ROOTS = [
    ("airport", "airport", "fuel quality or flight release"),
    ("aquaculture", "aquaculture", "stock health or harvest release"),
    ("archaeology", "archaeology", "cultural-site certification"),
    ("asphalt", "asphalt paving", "pavement acceptance"),
    ("battery", "battery manufacturing", "cell safety or warranty"),
    ("brewery", "brewery", "food safety or batch release"),
    ("bridge", "bridge maintenance", "structural safety or load rating"),
    ("bus", "bus operations", "passenger safety or dispatch authority"),
    ("cement", "cement production", "material certification or emissions compliance"),
    ("ceramics", "ceramics manufacturing", "product conformity"),
    ("chemical", "chemical processing", "process safety or product release"),
    ("cold-storage", "cold storage", "food quality or temperature compliance"),
    ("concrete", "concrete placement", "construction acceptance"),
    ("construction", "construction logistics", "site safety or contract approval"),
    ("crane", "crane operations", "lift authorization or collision clearance"),
    ("cryogenics", "cryogenic services", "cryogenic safety or release"),
    ("data-center", "data-center operations", "uptime authorization or thermal compliance"),
    ("dairy", "dairy processing", "food safety or custody transfer"),
    ("dam", "dam maintenance", "dam safety or seepage acceptance"),
    ("desalination", "desalination", "water-quality compliance"),
    ("district-energy", "district energy", "billing or network thermohydraulics"),
    ("drone", "drone logistics", "flight authorization or airworthiness"),
    ("earthwork", "earthwork", "survey grade or site acceptance"),
    ("electric-vehicle", "electric-vehicle charging", "vehicle release or grid authorization"),
    ("fertilizer", "fertilizer production", "agronomic guarantee or product release"),
    ("ferry", "ferry operations", "seaworthiness or passenger release"),
    ("film", "film production", "content release or rights clearance"),
    ("fireproofing", "fireproofing", "fire rating or life-safety acceptance"),
    ("food", "food processing", "food safety or lot release"),
    ("foundry", "foundry operations", "metallurgical certification"),
    ("freight", "freight logistics", "custody transfer or delivery authority"),
    ("geothermal", "geothermal operations", "well integrity or production forecast"),
    ("glass", "glass fabrication", "facade performance or product acceptance"),
    ("grain", "grain handling", "commodity grade or custody transfer"),
    ("greenhouse", "greenhouse horticulture", "crop outcome or food safety"),
    ("hospital", "hospital facilities", "patient readiness or medical-gas safety"),
    ("hotel", "hotel facilities", "guest safety or service release"),
    ("hvac", "HVAC service", "comfort guarantee or code compliance"),
    ("hydrogen", "hydrogen operations", "fuel safety or production certification"),
    ("hydropower", "hydropower operations", "grid dispatch or dam safety"),
    ("ice-rink", "ice-rink operations", "occupant safety or ice quality"),
    ("irrigation", "irrigation", "water rights or field calibration"),
    ("laboratory", "laboratory operations", "assay validity or sample release"),
    ("landfill", "landfill operations", "environmental compliance or waste acceptance"),
    ("lighthouse", "lighthouse maintenance", "navigation assurance"),
    ("livestock", "livestock operations", "animal health or food safety"),
    ("lng", "LNG operations", "cryogenic safety or custody transfer"),
    ("machine-tool", "machine-tool production", "dimensional certification"),
    ("marine", "marine services", "seaworthiness or class approval"),
    ("meat", "meat processing", "food safety or batch release"),
    ("medical-device", "medical-device production", "clinical safety or product release"),
    ("mine", "mining", "mine safety or resource estimate"),
    ("municipal", "municipal services", "public-service authorization"),
    ("museum", "museum conservation", "artifact authenticity or display release"),
    ("nuclear", "nuclear facilities", "nuclear safety or licensing"),
    ("offshore", "offshore operations", "asset integrity or marine safety"),
    ("oil", "oil processing", "product quality or custody transfer"),
    ("pharma", "pharmaceutical production", "sterility or batch release"),
    ("pipeline", "pipeline operations", "leak detection or pressure integrity"),
    ("port", "port operations", "ballast control or cargo release"),
    ("power-grid", "power-grid operations", "grid reliability or dispatch"),
    ("printing", "printing", "color conformity or publication release"),
    ("rail", "rail operations", "track authorization or passenger safety"),
    ("recycling", "recycling", "material grade or environmental compliance"),
    ("refinery", "refinery operations", "process safety or product release"),
    ("research", "research instrumentation", "scientific truth or publication claim"),
    ("restaurant", "restaurant operations", "food safety or service release"),
    ("robotics", "robotics", "autonomy authorization or collision safety"),
    ("roofing", "roofing", "weatherproofing or construction acceptance"),
    ("runway", "runway maintenance", "airport certification or pavement acceptance"),
    ("salt", "salt production", "product grade or environmental compliance"),
    ("school", "school facilities", "occupant safety or education authorization"),
    ("semiconductor", "semiconductor fabrication", "device yield or product release"),
    ("shipyard", "shipyard operations", "class approval or hull integrity"),
    ("solar", "solar generation", "collector efficiency or grid authorization"),
    ("sports", "sports venue operations", "crowd safety or event authorization"),
    ("steel", "steel production", "structural adequacy or tonnage certification"),
    ("storage", "energy storage", "thermal runaway safety or dispatch"),
    ("subway", "subway operations", "transit authorization or passenger safety"),
    ("telecom", "telecom infrastructure", "network availability or service guarantee"),
    ("textile", "textile production", "fiber conformity or product release"),
    ("theater", "theater operations", "crowd safety or event release"),
    ("timber", "timber operations", "harvest inventory or structural capacity"),
    ("tunnel", "tunnel operations", "clearance certification or geotechnical truth"),
    ("university", "university facilities", "campus safety or research authorization"),
    ("utility", "utility operations", "public-service continuity"),
    ("warehouse", "warehouse operations", "inventory custody or dispatch"),
    ("wastewater", "wastewater treatment", "discharge compliance or treatment performance"),
    ("water", "water utility", "water rights or regulatory metering"),
    ("waterfront", "waterfront infrastructure", "flood protection or public safety"),
    ("wind", "wind generation", "tower fatigue or grid authorization"),
    ("wine", "winery operations", "food safety or batch release"),
    ("wood-product", "wood-products manufacturing", "product conformity or structural capacity"),
    ("zoo", "zoo facilities", "animal welfare or visitor safety"),
]
INDUSTRY_CONTEXTS = [
    ("operations", "operations"),
    ("planning", "planning"),
    ("maintenance", "maintenance"),
    ("quality", "quality"),
]

# Scenario verbs are intentionally mapped to existing owned emitters only.
VERBS = [
    ("shift-check", "shift-check", "FSRT", "compare a retained pair before the shift window closes", "custody transfer or calibrated inventory"),
    ("gate", "gate", "CSE", "screen a quantity teaching case before review", "construction approval or field quantity"),
    ("path-sensitivity", "path-sensitivity", "CSG", "inspect a retained path and sensitivity strip", "surveyed geometry or structural capacity"),
    ("drift-watch", "drift-watch", "RESIDUAL_CUSUM", "review ordered residual windows without advancing held windows", "physical drift or alarm probability"),
    ("proof-gate", "proof-gate", "PROVED_HEAT", "present a retained proof-gated result without re-verifying it", "fresh verification or proof bytes"),
    ("circle-fit", "circle-fit", "GTE_CIRCLE", "review circle eligibility and held cases", "legal boundary or physical fit"),
    ("stability-verdict", "stability-verdict", "PLSR", "review a retained stability verdict and level-set case", "model stability or operational authorization"),
    ("energy-accuracy", "energy-accuracy", "ENERGY_ACCURACY", "compare retained energy-accuracy phases", "energy certification or physical efficiency"),
    ("free-energy", "free-energy", "VFE", "review a retained free-energy sensor-bias teaching case", "sensor truth or physical state"),
    ("measurement-chain", "measurement-chain", "MEASUREMENT_CHAIN", "trace a retained measurement-chain receipt", "calibration certification or metrology truth"),
    ("inventory-balance", "inventory-balance", "FSRT", "reconcile an inventory teaching pair", "inventory custody or leak attribution"),
    ("route-check", "route-check", "CSG", "compare a route sensitivity strip", "right-of-way approval or as-built route"),
    ("quantity-review", "quantity-review", "CSE", "review retained quantity cases", "procurement release or building mesh"),
    ("residual-hold", "residual-hold", "RESIDUAL_CUSUM", "record a residual hold point", "fault localization or confidence bars"),
    ("thermal-release", "thermal-release", "PROVED_HEAT", "present a thermal teaching release state", "physical temperature or release authority"),
    ("radial-screen", "radial-screen", "GTE_CIRCLE", "screen retained radial residuals", "survey acceptance or geometric truth"),
    ("contour-check", "contour-check", "PLSR", "compare a contour-level stability case", "clinical, safety, or production certification"),
    ("phase-review", "phase-review", "ENERGY_ACCURACY", "review a retained phase accuracy strip", "efficiency guarantee or energy forecast"),
    ("bias-review", "bias-review", "VFE", "review a sensor-bias teaching record", "diagnostic truth or device safety"),
    ("chain-audit", "chain-audit", "MEASUREMENT_CHAIN", "walk the retained instrument-chain stages", "audit compliance or calibrated truth"),
    ("reservoir-reconcile", "reservoir-reconcile", "FSRT", "compare two retained reservoir indications", "fluid-volume field or regulatory meter"),
    ("jacobi-strip", "jacobi-strip", "CSG", "inspect the retained Jacobi sensitivity strip", "geodesic truth or design approval"),
    ("evidence-screen", "evidence-screen", "CSE", "screen retained evidence-needed quantity cases", "field evidence or contract entitlement"),
    ("verdict-review", "verdict-review", "PLSR", "review a retained numerical verdict", "fresh solver proof or authority transition"),
]

# 480 distinct industry/domain names.
INDUSTRIES = [
    (f"{root_slug}-{context_slug}", f"{root_name} {context_name}", risk)
    for root_slug, root_name, risk in INDUSTRY_ROOTS
    for context_slug, context_name in INDUSTRY_CONTEXTS
]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _scenario(slug: str, industry: str, verb: tuple[str, str, str, str, str], root_risk: str) -> dict[str, Any]:
    verb_slug, verb_name, family, lesson, verb_risk = verb
    title = f"{industry.title()} {verb_name.replace('-', ' ').title()}"
    sentence = f"The {industry} team uses this {verb_name} teaching window to {lesson}, with an explicit human hold point."
    # Include the full domain label so every generated experiment carries a
    # distinct non-claim, not merely a distinct slug.
    non_claim = f"Not {industry}-specific {root_risk}; not {verb_risk}."
    return {
        "slug": slug,
        "title": title,
        "industry": industry,
        "sentence": sentence,
        "non_claim": non_claim,
        "family": family,
        "verb": verb_name,
        "owned_template": f"emit_{family.lower()}" if family != "GTE_CIRCLE" else "emit_gte_circle",
        "evidence_variant": "UNADMITTED_CANDIDATE_RETENTION",
    }


def _candidate_scenarios(existing: set[str]):
    # Interleave roots, contexts, and verbs so the first 1,000 samples span the
    # entire domain catalog instead of exhausting one industry first.
    candidates = []
    for industry_slug, industry_name, root_risk in INDUSTRIES:
        for verb in VERBS:
            slug = f"{industry_slug}-{verb[0]}"
            if slug in existing:
                continue
            candidates.append(_scenario(slug, industry_name, verb, root_risk))
    return candidates


def _write_wrapper(folder: Path, scenario: dict[str, Any]) -> None:
    family = scenario["family"]
    function = scenario["owned_template"]
    text = f'''#!/usr/bin/env python3
"""Thin generated wrapper for {scenario['title']}."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / "examples" / "workflows"
if str(WORKFLOWS) not in sys.path:
    sys.path.insert(0, str(WORKFLOWS))
from usecase_templates import {function}

ROOT = Path(__file__).resolve().parent
SCENARIO = {scenario!r}


def main() -> int:
    parser = argparse.ArgumentParser(description=SCENARIO["title"])
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "{scenario['slug']}_render.json")
    args = parser.parse_args()
    output = {function}(args.output, SCENARIO)
    print(f"wrote {{output}} :: {scenario['slug']} :: HOST_FROM_OWNED_CONFIG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
    (folder / "emit_render.py").write_text(text, encoding="utf-8")
    (folder / "emit_render.py").chmod(0o755)


def _write_readme(folder: Path, scenario: dict[str, Any]) -> None:
    text = f'''# {scenario['title']}

Original generated teaching use case for **{scenario['industry']}**.  This
scenario is generated from a combinatorial catalog; its retained numbers come
from the owned **{scenario['family']}** emitter and are not a new solver.

## Scenario

{scenario['sentence']}

## Non-claims

- **{scenario['non_claim']}**
- `may_authorize` remains `false`; this is presentation-only.
- No fluid-volume mesh, building mesh, proof bytes, or second solver.

## Evidence seam / retention path

This sample keeps a local render receipt at
`examples/{scenario['slug']}/results/{scenario['slug']}_render.json` and names
[Evidence-and-State-Management]({ESM_URL}) only as an evidence seam / retention
path.  The framing flag is **UNADMITTED_CANDIDATE_RETENTION**: it does not claim
ESM verification, does not invent an ESM pin, and does not authorize a state
transition (`canonicalAdmission=false`).

## Owned template and emit

- Family: `{scenario['family']}`
- Shared template: `examples/workflows/usecase_templates.py::{scenario['owned_template']}`
- `python3 examples/usecase-{scenario['slug']}/emit_render.py`

The wrapper copies the owned teaching numbers and reframes their title,
scenario sentence, source label, and non-claim; it does not mint a CIW kind.
'''
    (folder / "README.md").write_text(text, encoding="utf-8")
    results = folder / "results"
    results.mkdir(exist_ok=True)
    (results / ".gitignore").write_text("*\n", encoding="utf-8")


def _generated_scenario(folder: Path) -> dict[str, Any] | None:
    wrapper = folder / "emit_render.py"
    try:
        text = wrapper.read_text(encoding="utf-8")
        match = re.search(r"^SCENARIO = (\{.*?\})$", text, re.MULTILINE | re.DOTALL)
        if match:
            value = ast.literal_eval(match.group(1))
            if isinstance(value, dict) and "slug" in value:
                return value
    except (OSError, SyntaxError, ValueError):
        pass
    return None


def _metadata_from_render(folder: Path) -> dict[str, Any]:
    generated = _generated_scenario(folder)
    renders = sorted((folder / "results").glob("*_render.json"))
    if renders:
        try:
            data = json.loads(renders[0].read_text(encoding="utf-8"))
            scenario = data.get("scenario", {})
            # Generated wrappers are the source of truth for scenario metadata;
            # their prior receipt may predate a metadata refresh. Hand-authored
            # folders continue to use their retained JSON.
            source_scenario = generated if generated is not None else scenario
            title = source_scenario.get("title", folder.name.removeprefix("usecase-").replace("-", " ").title())
            return {
                "slug": folder.name.removeprefix("usecase-"),
                "title": title,
                "industry": source_scenario.get("industry", "existing hand-authored domain"),
                "sentence": source_scenario.get("sentence", source_scenario.get("lesson", data.get("caption", "retained presentation scenario"))),
                "non_claim": source_scenario.get("non_claim", "; ".join(data.get("forbidden_claims", [])[:2]) or "no operational authorization"),
                "family": source_scenario.get("family", data.get("source", "HOST_FROM_OWNED_CONFIG")),
                "verb": (generated or {}).get("verb", "hand-authored"),
                "owned_template": (generated or {}).get("owned_template", "hand-authored emitter"),
                "render_path": str(renders[0].relative_to(EXAMPLES.parent)).replace("\\", "/"),
                "generated": generated is not None,
                "source": data.get("source", "HOST_FROM_OWNED_CONFIG"),
            }
        except (OSError, json.JSONDecodeError):
            pass
    if generated is not None:
        generated = dict(generated)
        generated.update({
            "render_path": f"examples/{folder.name}/results/{folder.name.removeprefix('usecase-')}_render.json",
            "generated": True,
            "source": f"HOST_FROM_OWNED_CONFIG::{generated['family']}::{generated['slug']}",
        })
        return generated
    return {
        "slug": folder.name.removeprefix("usecase-"),
        "title": folder.name.removeprefix("usecase-").replace("-", " ").title(),
        "industry": "existing hand-authored domain",
        "sentence": "retained presentation scenario",
        "non_claim": "no operational authorization",
        "family": "existing owned emitter",
        "verb": "hand-authored",
        "owned_template": "hand-authored emitter",
        "render_path": "",
        "generated": False,
        "source": "HOST_FROM_OWNED_CONFIG",
    }


def _write_index_and_catalog() -> list[dict[str, Any]]:
    entries = []
    for folder in sorted(EXAMPLES.glob("usecase-*")):
        if folder.is_dir():
            entries.append(_metadata_from_render(folder))
    entries.sort(key=lambda item: item["slug"])
    INDEX_PATH.write_text(json.dumps({"schema": "usecase-index.v1", "count": len(entries), "entries": entries}, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Use-case catalog",
        "",
        f"Generated from disk by `examples/workflows/generate_usecase_corpus.py`; **{len(entries)} folders** and retained render paths are indexed below.",
        "Every row is presentation-only, keeps `may_authorize: false`, and reuses an owned emitter. ESM is named only as an evidence seam / retention path; no ESM pin or verification claim is made.",
        "",
        "| # | Slug | Human title | Industry/domain | Owned family | Scenario / non-claim | Render |",
        "|---:|---|---|---|---|---|---|",
    ]
    for number, item in enumerate(entries, 1):
        scenario = str(item["sentence"]).replace("|", "\\|").replace("\n", " ")
        non_claim = str(item["non_claim"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {number} | `{item['slug']}` | {item['title']} | {item['industry']} | `{item['family']}` | {scenario} **Non-claim:** {non_claim} | `{item.get('render_path', '')}` |")
    lines += [
        "",
        "## Rendering contract",
        "",
        "- Generate or merge without replacing existing hand-authored folders: `python3 examples/workflows/generate_usecase_corpus.py --count 1000`.",
        "- Emit all retained records: `python3 examples/workflows/emit_all_usecases.py`.",
        "- Missing JSON is `STALE`; no catalog row authorizes an operation.",
    ]
    CATALOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=None, help="optional floor; the full product is always materialized")
    args = parser.parse_args()
    if args.count is not None and args.count < 1:
        parser.error("--count must be positive")
    existing = {p.name.removeprefix("usecase-") for p in EXAMPLES.glob("usecase-*") if p.is_dir()}
    full_product = len(INDUSTRIES) * len(VERBS)
    target = max(full_product, args.count or 0)
    candidates = _candidate_scenarios(existing)
    if len(existing) < target:
        needed = target - len(existing)
        if len(candidates) < needed:
            raise SystemExit(f"catalog has only {len(candidates)} unused combinations; need {needed}")
        for scenario in candidates[:needed]:
            folder = EXAMPLES / f"usecase-{scenario['slug']}"
            folder.mkdir(parents=True, exist_ok=False)
            _write_wrapper(folder, scenario)
            _write_readme(folder, scenario)
            print(f"generated {folder.name}")
    else:
        print(f"preserving {len(existing)} existing folders (target {target})")
    entries = _write_index_and_catalog()
    remaining = len(_candidate_scenarios({e['slug'] for e in entries}))
    print(
        f"folders={len(entries)} full_product={full_product} generated_target={target} "
        f"remaining_unused={remaining} exhausted={remaining == 0} "
        f"index={INDEX_PATH} catalog={CATALOG_PATH}"
    )
    return 0 if len(entries) >= target and remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
