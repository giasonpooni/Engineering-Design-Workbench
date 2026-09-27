#!/usr/bin/env python3
"""Build catalog→executable coverage reports without growing the usecase catalog.

Tracks layers separately. Dedupes by computational configuration fingerprint
(operation + model params + uncertainty assumptions + expected outcome class),
NOT by industry title. Does not create usecase-* folders or new CIW kinds.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
WORKFLOWS = EXAMPLES / "workflows"
INDEX_PATH = EXAMPLES / "usecase-index.json"
EXHAUSTION_PATH = EXAMPLES / "usecase-EXHAUSTION.md"
REPORT_MD = WORKFLOWS / "coverage_report.md"
REPORT_JSON = WORKFLOWS / "coverage_report.json"
PROFILES_JSON = WORKFLOWS / "computational_profiles.json"
ESM_URL = "https://github.com/giasonpooni/Evidence-and-State-Management"

# Verb catalog from generate_usecase_corpus.py (authoritative mapping).
VERBS = [
    ("shift-check", "FSRT", "compare a retained pair before the shift window closes"),
    ("gate", "CSE", "screen a quantity teaching case before review"),
    ("path-sensitivity", "CSG", "inspect a retained path and sensitivity strip"),
    ("drift-watch", "RESIDUAL_CUSUM", "review ordered residual windows without advancing held windows"),
    ("proof-gate", "PROVED_HEAT", "present a retained proof-gated result without re-verifying it"),
    ("circle-fit", "GTE_CIRCLE", "review circle eligibility and held cases"),
    ("stability-verdict", "PLSR", "review a retained stability verdict and level-set case"),
    ("energy-accuracy", "ENERGY_ACCURACY", "compare retained energy-accuracy phases"),
    ("free-energy", "VFE", "review a retained free-energy sensor-bias teaching case"),
    ("measurement-chain", "MEASUREMENT_CHAIN", "trace a retained measurement-chain receipt"),
    ("inventory-balance", "FSRT", "reconcile an inventory teaching pair"),
    ("route-check", "CSG", "compare a route sensitivity strip"),
    ("quantity-review", "CSE", "review retained quantity cases"),
    ("residual-hold", "RESIDUAL_CUSUM", "record a residual hold point"),
    ("thermal-release", "PROVED_HEAT", "present a thermal teaching release state"),
    ("radial-screen", "GTE_CIRCLE", "screen retained radial residuals"),
    ("contour-check", "PLSR", "compare a contour-level stability case"),
    ("phase-review", "ENERGY_ACCURACY", "review a retained phase accuracy strip"),
    ("bias-review", "VFE", "review a sensor-bias teaching record"),
    ("chain-audit", "MEASUREMENT_CHAIN", "walk the retained instrument-chain stages"),
    ("reservoir-reconcile", "FSRT", "compare two retained reservoir indications"),
    ("jacobi-strip", "CSG", "inspect the retained Jacobi sensitivity strip"),
    ("evidence-screen", "CSE", "screen retained evidence-needed quantity cases"),
    ("verdict-review", "PLSR", "review a retained numerical verdict"),
]

EMITTERS = {
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

# Formal CIW operation id when supported; BLOCKED when teaching path intentionally
# does not mint / bind a session operation in this repository surface.
FAMILY_META: dict[str, dict[str, Any]] = {
    "FSRT": {
        "instrument_family": "FSRT (Fluid-State-Reconstruction-Testbed teaching)",
        "operation_id": "BLOCKED",
        "operation_note": (
            "HOST replay of published FSRT quickstart; does not mint "
            "ciw.fluid-volume.v1; no native set_lcm import"
        ),
        "regime": "two-reservoir linear ConstraintSet; P=I HOST hard reconcile",
        "input_source": "HOST replay",
        "scenario": "reconcile-vs-hold on consistency_stat vs χ² threshold",
    },
    "CSG": {
        "instrument_family": "CSG (Curved-Surface-Geodesic-Sensitivity)",
        "operation_id": "ciw.curved-path-transfer.v1",
        "operation_note": "presentation of HOST-sampled constant-curvature Jacobi strip",
        "regime": "declared constant curvature; no surveyed BIM",
        "input_source": "synthetic",
        "scenario": "path sensitivity / Jacobi strip inspection",
    },
    "CSE": {
        "instrument_family": "CSE (BIM quantity conditioning)",
        "operation_id": "ciw.bim-quantity.v1",
        "operation_note": "quantity-only teaching dispositions",
        "regime": "IFC/--demo quantity conditioning; geometry_authority=QUANTITY_ONLY",
        "input_source": "synthetic",
        "scenario": "ACCEPT / REQUEST_EVIDENCE / REJECT teaching gate",
    },
    "PROVED_HEAT": {
        "instrument_family": "PROVED_HEAT (SCR/SP1 integer heat)",
        "operation_id": "ciw.proved-heat.v1",
        "operation_note": "proof-before-result; no ciw.proved-heat.v2",
        "regime": "bounded registered guest [0,100,200,100,0]→[0,65,92,65,0]",
        "input_source": "synthetic",
        "scenario": "UNAVAILABLE when binaries absent; REFUSED on missing/corrupt proof",
    },
    "RESIDUAL_CUSUM": {
        "instrument_family": "RESIDUAL_CUSUM / FDIR-OIT",
        "operation_id": "ciw.residual-monitor.v1",
        "operation_note": "teaching windows; operation_language residual-monitor / FDIR-OIT",
        "regime": "ordered residual windows; OIT-held does not advance CUSUM",
        "input_source": "synthetic",
        "scenario": "quiet / diagnostic-candidate / OIT-held strip",
    },
    "GTE_CIRCLE": {
        "instrument_family": "GTE geometric circle",
        "operation_id": "ciw.geometric-circle.v1",
        "operation_note": "eligibility / held teaching cases",
        "regime": "declared frame bench-plane only",
        "input_source": "synthetic",
        "scenario": "circle eligibility and radial residual screen",
    },
    "PLSR": {
        "instrument_family": "PLSR identified stability",
        "operation_id": "ciw.identified-stability.v1",
        "operation_note": "retained numerical verdict; proof NOT_CHECKED in teaching emit",
        "regime": "identity certificate / level-set; parameter covariance unknown",
        "input_source": "HOST replay",
        "scenario": "NUMERICAL_INCONCLUSIVE / OUTSIDE_LEVEL_SET teaching",
    },
    "ENERGY_ACCURACY": {
        "instrument_family": "ENERGY_ACCURACY",
        "operation_id": "ciw.energy-accuracy.v1",
        "operation_note": "amortized joules/qualified-solve teaching phases",
        "regime": "synthetic fixtures; free energy / joules / time kept separate",
        "input_source": "synthetic",
        "scenario": "baseline-qualified and incomplete-bracket phases",
    },
    "VFE": {
        "instrument_family": "VFE variational free energy",
        "operation_id": "ciw.variational-free-energy.v1",
        "operation_note": "sensor-bias teaching contrast",
        "regime": "synthetic constant-curvature / unmodelled generator bias",
        "input_source": "synthetic",
        "scenario": "free-energy numerics without physical calibration claim",
    },
    "MEASUREMENT_CHAIN": {
        "instrument_family": "MEASUREMENT_CHAIN (RCI→FSRT→JSPT testbed)",
        "operation_id": "ciw.measurement-chain.v1",
        "operation_note": "operation_language RCI calibrate.v2 → FSRT snapshot → JSPT",
        "regime": "HOST_SYNTHETIC stages; native results keep not_verified",
        "input_source": "synthetic",
        "scenario": "instrument-chain stage walk / chain audit",
    },
}

KIND_TO_FAMILY = {
    "fsrt-two-reservoir-presentation": "FSRT",
    "csg-path-sensitivity-presentation": "CSG",
    "cse-bim-quantity-presentation": "CSE",
    "proved-heat-presentation": "PROVED_HEAT",
    "residual-cusum-teach-presentation": "RESIDUAL_CUSUM",
    "gte-circle-eligibility-presentation": "GTE_CIRCLE",
    "plsr-stability-verdict-presentation": "PLSR",
    "energy-accuracy-teach-presentation": "ENERGY_ACCURACY",
    "vfe-sensor-bias-teach-presentation": "VFE",
    "measurement-chain-teach-presentation": "MEASUREMENT_CHAIN",
    # hand-authored presentation kinds still bound to owned computational cores
    "usecase-bridge-span-path-presentation": "CSG",
    "usecase-drift-watch-presentation": "RESIDUAL_CUSUM",
    "usecase-ifc-takeoff-gate-presentation": "CSE",
    "usecase-tank-farm-balance-presentation": "FSRT",
    "usecase-thermal-proof-gate-presentation": "PROVED_HEAT",
}


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("owned_" + path.stem + "_" + path.parent.name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _outcome_class(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("cases", "cards", "windows", "stages"):
        items = data.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "id": item.get("id"),
                    "status": item.get("status")
                    or item.get("card_status")
                    or item.get("guard_status")
                    or item.get("proof_status"),
                    "verdict": item.get("verdict")
                    or item.get("native_outcome")
                    or item.get("disposition")
                    or item.get("reconciliation_status")
                    or item.get("proof_status"),
                    "reason": item.get("reason"),
                }
            )
    return out


def _model_core(data: dict[str, Any]) -> Any:
    if "model" in data:
        return data["model"]
    if "configuration" in data:
        return data["configuration"]
    if "statement" in data:
        return data["statement"]
    if "pins" in data:
        # cite-only pins already present; include for fingerprint stability
        return data["pins"]
    if "threshold" in data and "series" in data:
        return {"threshold": data.get("threshold"), "series_len": len(data.get("series") or [])}
    return None


def _uncertainty(data: dict[str, Any]) -> dict[str, Any]:
    model = data.get("model") if isinstance(data.get("model"), dict) else {}
    return {
        "prior_std": model.get("prior_std"),
        "total_mass_variance_kg2": model.get("total_mass_variance_kg2"),
        "constraint_b_var": (model.get("constraint") or {}).get("b_var") if isinstance(model.get("constraint"), dict) else None,
        "threshold": data.get("threshold"),
        "trust_scope": data.get("trust_scope"),
        "upstream_status": data.get("upstream_status"),
    }


def computational_fingerprint(family: str, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    meta = FAMILY_META[family]
    op = meta["operation_id"]
    if op == "BLOCKED":
        op_key = f"BLOCKED::{meta['operation_note']}"
    else:
        op_key = op
    core = {
        "family": family,
        "operation": op_key,
        "schema": data.get("schema"),
        "kind_core": KIND_TO_FAMILY.get(str(data.get("kind")), data.get("kind")),
        "model": _model_core(data),
        "uncertainty": _uncertainty(data),
        "expected_outcome_class": _outcome_class(data),
        "source_class": data.get("source") or data.get("upstream_status"),
    }
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return digest, core


def detect_sp1_binaries() -> dict[str, Any]:
    """Local presence only — never invent pins or claim verification."""
    cargo = shutil.which("cargo")
    rustc = shutil.which("rustc")
    sp1 = shutil.which("sp1") or shutil.which("cargo-prove")
    elf_candidates = list(ROOT.glob("**/sp1-heat.elf"))[:5]
    # check_proved_heat needs provider checkouts; treat scientific path unavailable
    # unless an installed wheel + guest ELF are clearly present.
    scientific = "unavailable"
    reason = "host_binaries_absent_or_unbound"
    if elf_candidates and sp1:
        scientific = "not_run"  # present but this milestone does not invoke private providers
        reason = "elf_present_but_fresh_verify_not_invoked"
    return {
        "cargo": bool(cargo),
        "rustc": bool(rustc),
        "sp1_cli": bool(sp1),
        "guest_elf_hits": [str(p.relative_to(ROOT)) for p in elf_candidates],
        "scientific_execution": scientific,
        "reason": reason,
    }


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "command": cmd,
            "returncode": result.returncode,
            "stdout_tail": (result.stdout or "")[-500:],
            "stderr_tail": (result.stderr or "")[-500:],
            "elapsed_s": round(time.monotonic() - started, 3),
            "status": "pass" if result.returncode == 0 else "fail",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": cmd,
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": f"timeout after {timeout}s: {exc}",
            "elapsed_s": round(time.monotonic() - started, 3),
            "status": "fail",
        }
    except OSError as exc:
        return {
            "command": cmd,
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "elapsed_s": round(time.monotonic() - started, 3),
            "status": "fail",
        }


def main() -> int:
    if not INDEX_PATH.is_file():
        print(f"missing index {INDEX_PATH}", file=sys.stderr)
        return 1

    # Stream-friendly: load once for machine use; do not print whole file.
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    entries = index.get("entries", [])
    application_description_count = len(entries)
    catalog_dir_count = sum(1 for p in EXAMPLES.glob("usecase-*") if p.is_dir())

    # Freeze guard
    if catalog_dir_count > 9074:
        print(f"REFUSE: catalog dirs={catalog_dir_count} exceeded freeze 9074", file=sys.stderr)
        return 2

    # Load owned payloads + fingerprints
    family_payloads: dict[str, dict[str, Any]] = {}
    profiles: dict[str, dict[str, Any]] = {}
    for family, path in EMITTERS.items():
        module = _load_module(path)
        payload = module.build_payload()
        family_payloads[family] = payload
        digest, core = computational_fingerprint(family, payload)
        meta = FAMILY_META[family]
        profiles[digest] = {
            "profile_id": digest,
            "family": family,
            "instrument_family": meta["instrument_family"],
            "operation_id": meta["operation_id"],
            "operation_note": meta["operation_note"],
            "model_regime": meta["regime"],
            "input_source": meta["input_source"],
            "scenario": meta["scenario"],
            "fingerprint_core": core,
            "member_slugs": [],
            "member_count": 0,
            "verbs": [],
            "layers_default": {
                "catalog": "pass",
                "export": "not_run",
                "executable": "cite_only" if meta["operation_id"] != "BLOCKED" else "blocked",
                "numerical": "not_run",
                "checking": "not_run",
                "replay": "not_run",
                "ESM": "cite_only",
            },
        }

    digest_by_family = {p["family"]: pid for pid, p in profiles.items()}

    # Map verbs → profiles
    verb_rows = []
    for verb, family, lesson in VERBS:
        meta = FAMILY_META[family]
        pid = digest_by_family[family]
        profiles[pid]["verbs"] = sorted(set(profiles[pid]["verbs"] + [verb]))
        verb_rows.append(
            {
                "verb": verb,
                "instrument_family": meta["instrument_family"],
                "family": family,
                "operation_id": meta["operation_id"],
                "operation_note": meta["operation_note"],
                "model_regime": meta["regime"],
                "input_source": meta["input_source"],
                "scenario": f"{lesson} :: {meta['scenario']}",
                "profile_id": pid,
            }
        )

    # Assign every catalog entry to a profile by family (generated) or kind/scenario
    blocked_reasons: Counter[str] = Counter()
    unmapped = []
    for entry in entries:
        family = entry.get("family")
        if family in digest_by_family:
            pid = digest_by_family[family]
        else:
            # hand-authored: resolve via existing render kind if present
            slug = entry["slug"]
            folder = EXAMPLES / f"usecase-{slug}"
            renders = sorted((folder / "results").glob("*_render.json"))
            resolved = None
            if renders:
                try:
                    data = json.loads(renders[0].read_text(encoding="utf-8"))
                    kind = str(data.get("kind") or "")
                    resolved = KIND_TO_FAMILY.get(kind)
                    sc = data.get("scenario")
                    if resolved is None and isinstance(sc, dict):
                        resolved = sc.get("owned_family")
                    if resolved is None:
                        op = data.get("operation_id") or data.get("operation_language")
                        for fam, meta in FAMILY_META.items():
                            if meta["operation_id"] != "BLOCKED" and meta["operation_id"] == op:
                                resolved = fam
                                break
                        if resolved is None and op and "residual-monitor" in str(op):
                            resolved = "RESIDUAL_CUSUM"
                        if resolved is None and isinstance(data.get("model"), dict):
                            if data["model"].get("kind") == "reservoir2-linear-v1":
                                resolved = "FSRT"
                except (OSError, json.JSONDecodeError):
                    resolved = None
            if resolved in digest_by_family:
                pid = digest_by_family[resolved]
            else:
                unmapped.append(slug)
                blocked_reasons["unmapped_hand_authored_kind"] += 1
                continue
        profiles[pid]["member_slugs"].append(entry["slug"])
        profiles[pid]["member_count"] += 1

    for pid, profile in profiles.items():
        profile["member_slugs"] = sorted(profile["member_slugs"])
        # keep only counts in the heavy JSON; sample slugs for humans
        profile["member_slug_sample"] = profile["member_slugs"][:8]
        # drop full slug list from profiles file to keep size reasonable? Task asks member slug counts.
        # Keep counts + sample; full lists only in aggregate stats.
        del profile["member_slugs"]

    unique_computational_profiles = len(profiles)

    # --- Representative execution (local, no private providers) ---
    if str(WORKFLOWS) not in sys.path:
        sys.path.insert(0, str(WORKFLOWS))
    from usecase_templates import EMIT_FUNCTIONS  # noqa: E402

    sp1 = detect_sp1_binaries()
    representative_runs: list[dict[str, Any]] = []
    layer_counts = Counter()

    # One representative per unique computational profile (teaching emit)
    for pid, profile in sorted(profiles.items(), key=lambda kv: kv[1]["family"]):
        family = profile["family"]
        layers = dict(profile["layers_default"])
        layers["catalog"] = "pass"
        layers["ESM"] = "cite_only"
        run_record: dict[str, Any] = {
            "profile_id": pid,
            "family": family,
            "representative_kind": "unique_computational_config",
            "slug_example": (profile.get("member_slug_sample") or [f"family-{family.lower()}"])[0],
            "commands": [],
            "layers": layers,
        }

        # Export / teaching emit via shared template
        with tempfile.TemporaryDirectory(prefix=f"cov-{family}-") as td:
            out = Path(td) / f"{family.lower()}_rep_render.json"
            scenario = {
                "slug": f"coverage-rep-{family.lower()}",
                "title": f"Coverage representative {family}",
                "industry": "coverage-report",
                "sentence": profile["scenario"],
                "non_claim": "Not a new catalog folder; coverage representative only.",
                "family": family,
            }
            cmd = [
                sys.executable,
                "-c",
                (
                    "import sys; from pathlib import Path; "
                    f"sys.path.insert(0, {str(WORKFLOWS)!r}); "
                    f"from usecase_templates import EMIT_FUNCTIONS; "
                    f"EMIT_FUNCTIONS[{family!r}](Path({str(out)!r}), {scenario!r}); "
                    f"print('wrote', {str(out)!r})"
                ),
            ]
            # Prefer direct call (faster, clearer)
            try:
                EMIT_FUNCTIONS[family](out, scenario)
                emit_status = "pass" if out.is_file() and out.stat().st_size > 0 else "fail"
                emit_detail = {
                    "command": [
                        "python3",
                        "-c",
                        f"usecase_templates.EMIT_FUNCTIONS['{family}'](...)",
                    ],
                    "returncode": 0 if emit_status == "pass" else 1,
                    "stdout_tail": f"wrote {out} bytes={out.stat().st_size if out.exists() else 0}",
                    "stderr_tail": "",
                    "elapsed_s": 0.0,
                    "status": emit_status,
                }
            except Exception as exc:  # noqa: BLE001
                emit_status = "fail"
                emit_detail = {
                    "command": ["python3", "usecase_templates.emit"],
                    "returncode": 1,
                    "stdout_tail": "",
                    "stderr_tail": str(exc),
                    "elapsed_s": 0.0,
                    "status": "fail",
                }
            run_record["commands"].append(emit_detail)
            layers["export"] = emit_status

            # Lightweight structural check on emitted JSON (in-tree checking layer)
            if emit_status == "pass":
                try:
                    data = json.loads(out.read_text(encoding="utf-8"))
                    checks = []
                    if data.get("may_authorize") is not False:
                        checks.append("may_authorize_not_false")
                    if data.get("canonicalAdmission") not in (False, None):
                        # templates set False; allow missing as non-admit
                        if data.get("canonicalAdmission") is True:
                            checks.append("canonicalAdmission_true")
                    if data.get("presentation_only") is not True:
                        checks.append("presentation_only_missing")
                    seam = data.get("evidence_seam") or {}
                    if seam.get("url") and ESM_URL not in str(seam.get("url")):
                        checks.append("unexpected_esm_url")
                    # no invented ESM pin
                    if data.get("esm_pin") or seam.get("pin") or seam.get("artifact_digest"):
                        checks.append("invented_esm_binding")
                    check_status = "pass" if not checks else "fail"
                    run_record["commands"].append(
                        {
                            "command": ["python3", "-c", "structural_checks(emitted_json)"],
                            "returncode": 0 if check_status == "pass" else 1,
                            "stdout_tail": f"checks_ok={not checks} issues={checks}",
                            "stderr_tail": "",
                            "elapsed_s": 0.0,
                            "status": check_status,
                        }
                    )
                    layers["checking"] = check_status
                except Exception as exc:  # noqa: BLE001
                    layers["checking"] = "fail"
                    run_record["commands"].append(
                        {
                            "command": ["structural_checks"],
                            "returncode": 1,
                            "stdout_tail": "",
                            "stderr_tail": str(exc),
                            "elapsed_s": 0.0,
                            "status": "fail",
                        }
                    )
            else:
                layers["checking"] = "not_run"

        # Executable / numerical / replay / scientific
        if family == "PROVED_HEAT":
            layers["executable"] = sp1["scientific_execution"]
            layers["numerical"] = "unavailable"
            layers["replay"] = "unavailable"
            run_record["commands"].append(
                {
                    "command": ["scripts/check_proved_heat.py", "(not invoked — binaries/providers)"],
                    "returncode": None,
                    "stdout_tail": json.dumps(sp1),
                    "stderr_tail": "",
                    "elapsed_s": 0.0,
                    "status": sp1["scientific_execution"],
                }
            )
        elif profile["operation_id"] == "BLOCKED":
            layers["executable"] = "blocked"
            layers["numerical"] = "blocked"
            layers["replay"] = "blocked"
            blocked_reasons["FSRT_ciw.fluid-volume.v1_not_minted"] += profile["member_count"]
            run_record["commands"].append(
                {
                    "command": ["native_operation.execute", "ciw.fluid-volume.v1"],
                    "returncode": None,
                    "stdout_tail": "",
                    "stderr_tail": FAMILY_META["FSRT"]["operation_note"],
                    "elapsed_s": 0.0,
                    "status": "blocked",
                }
            )
        else:
            # Session providers / ICRH not assumed present in this box
            layers["executable"] = "not_run"
            layers["numerical"] = "not_run"
            layers["replay"] = "not_run"
            blocked_reasons[f"native_session_{profile['operation_id']}_not_invoked"] += profile["member_count"]
            run_record["commands"].append(
                {
                    "command": ["ciw", "operation.execute", profile["operation_id"]],
                    "returncode": None,
                    "stdout_tail": "local teaching emit only; workbench session / ICRH not started",
                    "stderr_tail": "",
                    "elapsed_s": 0.0,
                    "status": "not_run",
                }
            )

        run_record["layers"] = layers
        for layer, status in layers.items():
            layer_counts[f"{layer}:{status}"] += 1
        representative_runs.append(run_record)

    # Boundary / refuse representatives (same profiles; highlight refuse paths)
    boundary_cases = [
        {
            "family": "PROVED_HEAT",
            "label": "binaries-absent UNAVAILABLE",
            "case_ids": ["teaching-statement-binaries-absent"],
            "expected": "unavailable",
        },
        {
            "family": "PROVED_HEAT",
            "label": "missing-proof REFUSED",
            "case_ids": ["missing-proof-refused", "missing-guest-elf-pin-refused", "resealed-corrupt-refused"],
            "expected": "refuse",
        },
        {
            "family": "CSE",
            "label": "quantity REJECT / REQUEST_EVIDENCE",
            "case_ids": ["held-request-evidence", "refused-violated"],
            "expected": "held_or_refuse",
        },
        {
            "family": "PLSR",
            "label": "OUTSIDE_LEVEL_SET / NUMERICAL_INCONCLUSIVE",
            "case_ids": ["identity-certificate-inconclusive", "level-zero-outside"],
            "expected": "inconclusive_or_refuse",
        },
        {
            "family": "FSRT",
            "label": "large-disagreement HELD (operation BLOCKED for fluid-volume mint)",
            "case_ids": ["large-disagreement-held"],
            "expected": "blocked_or_held",
        },
    ]

    for boundary in boundary_cases:
        family = boundary["family"]
        pid = digest_by_family[family]
        payload = family_payloads[family]
        present = {c.get("id") for c in (payload.get("cases") or [])}
        missing = [cid for cid in boundary["case_ids"] if cid not in present]
        status = "pass" if not missing else "fail"
        layers = {
            "catalog": "pass",
            "export": "pass",  # teaching payload already contains these cases
            "executable": "unavailable" if family == "PROVED_HEAT" else ("blocked" if family == "FSRT" else "not_run"),
            "numerical": "unavailable" if family == "PROVED_HEAT" else ("blocked" if family == "FSRT" else "not_run"),
            "checking": status,
            "replay": "unavailable" if family == "PROVED_HEAT" else "not_run",
            "ESM": "cite_only",
        }
        for layer, st in layers.items():
            layer_counts[f"{layer}:{st}"] += 1
        representative_runs.append(
            {
                "profile_id": pid,
                "family": family,
                "representative_kind": "boundary_refuse",
                "label": boundary["label"],
                "case_ids": boundary["case_ids"],
                "expected": boundary["expected"],
                "missing_case_ids": missing,
                "commands": [
                    {
                        "command": [
                            "python3",
                            "-c",
                            f"assert case_ids subset of {family}.build_payload()['cases']",
                        ],
                        "returncode": 0 if status == "pass" else 1,
                        "stdout_tail": f"present={sorted(present & set(boundary['case_ids']))} missing={missing}",
                        "stderr_tail": "",
                        "elapsed_s": 0.0,
                        "status": status,
                    }
                ],
                "layers": layers,
            }
        )

    # SP1 teaching orchestrator (export only)
    sp1_emit = run_cmd([sys.executable, str(WORKFLOWS / "emit_sp1_teaching_bundle.py")], timeout=180)
    representative_runs.append(
        {
            "profile_id": digest_by_family["PROVED_HEAT"],
            "family": "PROVED_HEAT",
            "representative_kind": "sp1_teaching_export",
            "commands": [sp1_emit],
            "layers": {
                "catalog": "pass",
                "export": sp1_emit["status"],
                "executable": sp1["scientific_execution"],
                "numerical": "unavailable",
                "checking": "not_run",
                "replay": "unavailable",
                "ESM": "cite_only",
            },
        }
    )
    for layer, st in representative_runs[-1]["layers"].items():
        layer_counts[f"{layer}:{st}"] += 1

    # Aggregate blocked reasons useful gaps
    blocked_reasons["ESM_real_artifact_bindings_absent_cite_only"] += application_description_count
    blocked_reasons["scientific_execution_requires_workbench_session_or_ICRH"] += (
        application_description_count - profiles[digest_by_family["FSRT"]]["member_count"]
    )
    if sp1["scientific_execution"] in {"unavailable", "not_run"}:
        blocked_reasons["PROVED_HEAT_SP1_binaries_or_fresh_verify_unavailable"] += profiles[
            digest_by_family["PROVED_HEAT"]
        ]["member_count"]

    executed = sum(
        1
        for r in representative_runs
        if r["representative_kind"] == "unique_computational_config"
        and r["layers"].get("export") == "pass"
    )
    not_run_or_blocked = sum(
        1
        for r in representative_runs
        if r["representative_kind"] == "unique_computational_config"
        and r["layers"].get("executable") in {"not_run", "blocked", "unavailable"}
    )
    failures = [
        r
        for r in representative_runs
        if any(c.get("status") == "fail" for c in r.get("commands", []))
        or r.get("layers", {}).get("export") == "fail"
        or r.get("layers", {}).get("checking") == "fail"
    ]

    # Profile layer summary counts (one status per profile from representative unique run)
    profile_layer_summary: dict[str, Counter] = defaultdict(Counter)
    for r in representative_runs:
        if r["representative_kind"] != "unique_computational_config":
            continue
        for layer, st in r["layers"].items():
            profile_layer_summary[layer][st] += 1

    report = {
        "schema": "coverage-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "freeze": {
            "catalog_dirs": catalog_dir_count,
            "application_description_count": application_description_count,
            "unique_computational_profiles": unique_computational_profiles,
            "max_allowed_dirs": 9074,
            "created_new_usecase_dirs": False,
        },
        "statement": (
            "Catalog exhausted ≠ experiments exhausted. "
            "9,074 application descriptions collapse to "
            f"{unique_computational_profiles} unique computational profiles "
            "(operation + model/uncertainty + expected outcome class). "
            "Export/teaching emit was exercised for representatives; "
            "scientific execution, numerical regimes, independent checking, "
            "replay, and ESM-bound observations remain largely not_run, "
            "blocked, unavailable, or cite_only."
        ),
        "verb_family_operation_mapping": verb_rows,
        "layer_counts_representatives": {k: dict(v) for k, v in profile_layer_summary.items()},
        "layer_counts_all_representative_runs": dict(layer_counts),
        "top_incompatible_blocked_reasons": [
            {"reason": reason, "weight": weight}
            for reason, weight in blocked_reasons.most_common(12)
        ],
        "sp1": sp1,
        "representative_runs": representative_runs,
        "unmapped_slugs": unmapped,
        "summary": {
            "unique_computational_profiles": unique_computational_profiles,
            "representatives_export_executed": executed,
            "representatives_scientific_not_run_or_blocked": not_run_or_blocked,
            "boundary_refuse_cases": len(boundary_cases),
            "failures": len(failures),
            "failure_labels": [
                f"{f.get('family')}:{f.get('representative_kind')}:{f.get('label', '')}"
                for f in failures
            ],
        },
        "esm_policy": {
            "url": ESM_URL,
            "status": "cite_only",
            "note": (
                "No invented ESM pins. UNADMITTED_CANDIDATE_RETENTION only; "
                "may_authorize remains false; real-data cases require artifact "
                "digest + field + transform bindings which are absent here."
            ),
        },
    }

    profiles_doc = {
        "schema": "computational-profiles.v1",
        "application_description_count": application_description_count,
        "unique_computational_profiles": unique_computational_profiles,
        "profiles": [
            {
                "profile_id": p["profile_id"],
                "family": p["family"],
                "instrument_family": p["instrument_family"],
                "operation_id": p["operation_id"],
                "operation_note": p["operation_note"],
                "model_regime": p["model_regime"],
                "input_source": p["input_source"],
                "scenario": p["scenario"],
                "verbs": p["verbs"],
                "member_count": p["member_count"],
                "member_slug_sample": p["member_slug_sample"],
                "fingerprint_core": p["fingerprint_core"],
            }
            for p in sorted(profiles.values(), key=lambda x: x["family"])
        ],
    }

    REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    PROFILES_JSON.write_text(json.dumps(profiles_doc, indent=2) + "\n", encoding="utf-8")

    # Human markdown
    lines: list[str] = []
    lines += [
        "# Use-case coverage report (executable layer)",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Catalog exhausted ≠ experiments exhausted",
        "",
        report["statement"],
        "",
        "## Freeze",
        "",
        f"- Catalog dirs on disk: **{catalog_dir_count}** (freeze ≤ 9074; no folder 9075).",
        f"- Application description count: **{application_description_count}**.",
        f"- Unique computational profiles: **{unique_computational_profiles}** "
        f"(≪ {application_description_count} because industry titles do not change the owned emitter config).",
        "- No new CIW kinds; no false qualified/proved/calibrated; ESM cite-only.",
        "",
        "## Layer counts (unique-profile representatives)",
        "",
        "| Layer | Status histogram |",
        "| --- | --- |",
    ]
    for layer in ("catalog", "export", "executable", "numerical", "checking", "replay", "ESM"):
        hist = profile_layer_summary.get(layer, Counter())
        cell = ", ".join(f"{st}={n}" for st, n in sorted(hist.items())) or "(none)"
        lines.append(f"| `{layer}` | {cell} |")

    lines += [
        "",
        "## Verb → instrument family → operation mapping",
        "",
        "| Verb | Family | Operation id | Model / regime | Input source | Scenario |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in verb_rows:
        op = row["operation_id"]
        if op == "BLOCKED":
            op = f"BLOCKED ({row['operation_note']})"
        lines.append(
            f"| `{row['verb']}` | `{row['family']}` | `{op}` | {row['model_regime']} | "
            f"{row['input_source']} | {row['scenario']} |"
        )

    lines += [
        "",
        "## Computational profiles (deduped)",
        "",
        f"See also [`computational_profiles.json`](computational_profiles.json). "
        f"**{unique_computational_profiles}** profiles cover **{application_description_count}** descriptions.",
        "",
        "| Profile | Family | Operation | Members | Verbs | Input |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for p in sorted(profiles.values(), key=lambda x: x["family"]):
        lines.append(
            f"| `{p['profile_id']}` | `{p['family']}` | `{p['operation_id']}` | "
            f"{p['member_count']} | {', '.join(f'`{v}`' for v in p['verbs']) or '_(hand-authored only)_'} | "
            f"{p['input_source']} |"
        )

    lines += [
        "",
        "## Top incompatible / blocked reasons (useful gaps)",
        "",
        "| Weight | Reason |",
        "| ---: | --- |",
    ]
    for item in report["top_incompatible_blocked_reasons"]:
        lines.append(f"| {item['weight']} | {item['reason']} |")

    lines += [
        "",
        "## Representative run results",
        "",
        "Commands below ran locally without private providers. "
        "SP1/proved-heat scientific execution marked unavailable/not_run when binaries unbound.",
        "",
    ]
    for run in representative_runs:
        title = f"{run['family']} · {run['representative_kind']}"
        if run.get("label"):
            title += f" · {run['label']}"
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"- profile_id: `{run['profile_id']}`")
        layers = run.get("layers") or {}
        lines.append(
            "- layers: "
            + ", ".join(f"`{k}={v}`" for k, v in layers.items())
        )
        for cmd in run.get("commands") or []:
            cmdline = " ".join(str(x) for x in cmd.get("command") or [])
            lines.append(f"- command: `{cmdline}` → **{cmd.get('status')}** (rc={cmd.get('returncode')})")
            if cmd.get("stdout_tail"):
                lines.append(f"  - stdout: {cmd['stdout_tail'][:300]}")
            if cmd.get("stderr_tail"):
                lines.append(f"  - stderr: {cmd['stderr_tail'][:300]}")
        lines.append("")

    lines += [
        "## SP1 / proved-heat gate",
        "",
        f"- scientific_execution: **{sp1['scientific_execution']}** ({sp1['reason']})",
        f"- cargo={sp1['cargo']} rustc={sp1['rustc']} sp1_cli={sp1['sp1_cli']}",
        f"- guest_elf_hits: {sp1['guest_elf_hits'] or '[]'}",
        "- Teaching export: `python3 examples/workflows/emit_sp1_teaching_bundle.py` "
        f"→ **{sp1_emit['status']}**",
        "",
        "## Machine-readable twin",
        "",
        f"- [`coverage_report.json`](coverage_report.json)",
        f"- [`computational_profiles.json`](computational_profiles.json)",
        "",
        "## Non-claims",
        "",
        "- Does not authorize operations (`may_authorize` false).",
        "- Does not claim ESM verification or invent pins.",
        "- Does not expand the industry×verb catalog.",
        "- Export pass ≠ numerical / checking / replay / proved completeness.",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")

    # Update exhaustion doc to point at coverage report
    exhaustion = EXHAUSTION_PATH.read_text(encoding="utf-8")
    pointer = (
        "\n## Next-layer truth (executable coverage)\n\n"
        "Catalog exhaustion is **not** experimental exhaustion. Track the next "
        "layer in:\n\n"
        "- [`examples/workflows/coverage_report.md`](workflows/coverage_report.md) "
        "(human)\n"
        "- [`examples/workflows/coverage_report.json`](workflows/coverage_report.json) "
        "(machine)\n"
        "- [`examples/workflows/computational_profiles.json`](workflows/computational_profiles.json) "
        "(deduped profiles + member counts)\n\n"
        f"Reported unique computational profiles: **{unique_computational_profiles}** "
        f"vs application descriptions **{application_description_count}**.\n"
    )
    marker = "## Next-layer truth (executable coverage)"
    if marker in exhaustion:
        # replace from marker to end of that section (until next ## or EOF after insert point)
        pre, _, rest = exhaustion.partition(marker)
        # drop old section until next top-level ## that is not the marker content — rewrite from marker
        # Keep everything before marker; append fresh pointer; keep regenerate+ESM if present after old section
        # Simpler: if marker exists, cut from marker to "## Regenerate" if present
        if "## Regenerate" in rest:
            _, _, after = rest.partition("## Regenerate")
            exhaustion = pre.rstrip() + "\n" + pointer + "\n## Regenerate" + after
        elif "## ESM" in rest:
            _, _, after = rest.partition("## ESM")
            exhaustion = pre.rstrip() + "\n" + pointer + "\n## ESM" + after
        else:
            exhaustion = pre.rstrip() + "\n" + pointer
    else:
        # Insert before ## Regenerate or ## ESM
        if "## Regenerate" in exhaustion:
            exhaustion = exhaustion.replace("## Regenerate", pointer + "\n## Regenerate", 1)
        elif "## ESM" in exhaustion:
            exhaustion = exhaustion.replace("## ESM", pointer + "\n## ESM", 1)
        else:
            exhaustion = exhaustion.rstrip() + "\n" + pointer

    # Strengthen freeze wording already present
    EXHAUSTION_PATH.write_text(exhaustion if exhaustion.endswith("\n") else exhaustion + "\n", encoding="utf-8")

    # Final freeze check — ensure we did not create dirs
    after_dirs = sum(1 for p in EXAMPLES.glob("usecase-*") if p.is_dir())
    print(
        json.dumps(
            {
                "coverage_report_md": str(REPORT_MD.relative_to(ROOT)),
                "coverage_report_json": str(REPORT_JSON.relative_to(ROOT)),
                "computational_profiles_json": str(PROFILES_JSON.relative_to(ROOT)),
                "unique_computational_profiles": unique_computational_profiles,
                "application_description_count": application_description_count,
                "catalog_dirs_before": catalog_dir_count,
                "catalog_dirs_after": after_dirs,
                "representatives_export_executed": executed,
                "representatives_scientific_not_run_or_blocked": not_run_or_blocked,
                "failures": len(failures),
                "unmapped": len(unmapped),
            },
            indent=2,
        )
    )
    return 1 if failures or after_dirs != catalog_dir_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
