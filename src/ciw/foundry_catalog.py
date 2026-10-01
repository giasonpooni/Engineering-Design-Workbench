"""Authored production breakdown, not Ubisoft's proprietary schedule or agent claims.

Stage order is a presentation aid. Edges determine readiness; technical art, QA,
research and infrastructure deliberately overlap. Execution stays in production.py.
"""
from __future__ import annotations
from copy import deepcopy

STAGES = (
    ("definition", "01 · Product definition and evidence"),
    ("foundation", "02 · Technical preproduction"),
    ("prototype", "03 · Mechanics prototypes"),
    ("slice", "04 · Representative vertical slice"),
    ("tooling", "05 · Repeatable production tooling"),
    ("content", "06 · World and content production"),
    ("systems", "07 · Connected simulation and progression"),
    ("alpha", "08 · Content-complete integration"),
    ("beta", "09 · Performance and compatibility qualification"),
    ("release", "10 · Release preparation and maintenance"),
)

# id, stage, title, responsibility, automation class, prerequisites, evidence required.
# Automation class describes potential division of labour, NOT an installed provider.
_ROWS = (
    ("vision", "definition", "Set the player promise and non-goals", "creative-direction", "human_led", (), "Reviewed player promise, non-goals and identity boundaries."),
    ("core-loop", "definition", "Specify moment-to-moment and long-term play", "game-design", "human_led", ("vision",), "Playable-loop specification with observable success and failure cases."),
    ("historical-scope", "definition", "Separate chronology, lore and authored variants", "research", "agent_assisted", ("vision",), "Source register, dated claims and explicit disputed or authored variants; expert review."),
    ("rights-register", "definition", "Record source, asset and performance permissions", "production", "agent_assisted", ("vision",), "Attributed rights inventory; unresolved permissions remain blocked."),
    ("scope-budget", "definition", "Choose production scope and financial limits", "production", "human_led", ("core-loop",), "Human-approved scope, exclusions, resource limits and change policy; no guessed savings."),
    ("platform-matrix", "definition", "Define supported inputs and hardware targets", "technical-direction", "human_led", ("vision",), "Named platform/input matrix, minimum targets and measurable frame/memory budgets."),
    ("runtime-bindings", "foundation", "Pin engine, providers and their ownership", "tools-engineering", "deterministic", ("platform-matrix",), "Executable/source pins, provider boundaries and reproducible environment instructions."),
    ("repro-build", "foundation", "Establish reproducible build and CI smoke path", "build-engineering", "deterministic", ("runtime-bindings",), "Fresh-checkout build logs and retained artifact identities, not a build-script existence check."),
    ("save-contract", "foundation", "Define state, persistence and compatibility", "gameplay-engineering", "agent_assisted", ("core-loop",), "Versioned save contract, invalid-state refusal and migration/rollback tests."),
    ("movement-profile", "foundation", "Measure movement and camera contracts", "gameplay-engineering", "agent_assisted", ("core-loop", "platform-matrix"), "Measured acceleration, turning, jump, clearance and camera cases plus human feel review."),
    ("combat-contract", "foundation", "Define reusable combat action timing", "gameplay-engineering", "agent_assisted", ("core-loop",), "Attack/guard/recovery and interruption contracts, readable telegraphs and test cases."),
    ("telemetry", "foundation", "Retain performance and failure observations", "qa-engineering", "deterministic", ("runtime-bindings",), "Replayable input, state, runtime and resource observations with separate execution identities."),
    ("traversal", "prototype", "Qualify the linked traversal course", "gameplay-engineering", "agent_assisted", ("movement-profile", "save-contract"), "Input-driven linked course, collision and airborne/contact restore tests, actual captures."),
    ("paired-combat", "prototype", "Build one readable paired combat encounter", "combat-design", "agent_assisted", ("combat-contract", "movement-profile"), "Actual paired inputs, spacing, defensive timing, recovery, failure and human feel review."),
    ("riding", "prototype", "Qualify riding, gates and mount transitions", "gameplay-engineering", "agent_assisted", ("movement-profile", "save-contract"), "Stopping, steering, slopes, mounting and collision-safe dismount scenarios."),
    ("companion-route", "prototype", "Qualify followers, separation and regrouping", "ai-engineering", "agent_assisted", ("movement-profile", "save-contract"), "No teleport, lost-sight behavior, alternate routes and persistence on a real route."),
    ("interaction-access", "prototype", "Gate interaction by reach, sight and authority", "gameplay-engineering", "deterministic", ("save-contract",), "Wrong-floor, obstruction-after-menu, wrong-actor and knowledge-boundary regressions."),
    ("water-domain", "prototype", "Recheck the existing 1792 water reducer and save", "qa-engineering", "deterministic", (), "Installed 1792.water-round.v1 primary AND dependent regression accepted at the locked source; domain fixture only."),
    ("slice-journey", "slice", "Assemble a representative connected playable journey", "level-design", "agent_assisted", ("traversal", "paired-combat", "riding", "companion-route", "interaction-access"), "Start-to-finish play with state transitions, recovery and no progress/position injection."),
    ("art-target", "slice", "Establish an original visual quality target", "art-direction", "human_led", ("vision", "historical-scope"), "Reviewed original character, architecture, lighting and material sample in engine."),
    ("audio-target", "slice", "Establish sound and performance direction", "audio-direction", "human_led", ("vision", "rights-register"), "Representative licensed/original audio and performance sample with human approval."),
    ("slice-history-review", "slice", "Review the slice's history and portrayal", "historical-review", "human_led", ("historical-scope", "slice-journey"), "Human-reviewed chronology, attribution, sites and character portrayal, not model confidence."),
    ("slice-playtest", "slice", "Run independent human playtests", "user-research", "human_led", ("slice-journey", "art-target", "audio-target"), "Observed play sessions, usability findings and retained fixes; automated tests are insufficient."),
    ("slice-signoff", "slice", "Approve expansion beyond the slice", "creative-direction", "human_led", ("slice-history-review", "slice-playtest", "scope-budget"), "Explicit human production decision, unresolved risks and updated budget."),
    ("asset-contracts", "tooling", "Define asset naming, units and admission contracts", "technical-art", "agent_assisted", ("runtime-bindings", "movement-profile"), "Versioned scale, axes, collisions, LOD, metadata and asset-rights requirements."),
    ("blender-export", "tooling", "Qualify Blender export and engine import", "technical-art", "deterministic", ("asset-contracts",), "Actual export/import of representative original assets, including rejected malformed cases."),
    ("collision-lod", "tooling", "Automate mesh, collision and LOD checks", "technical-art", "deterministic", ("asset-contracts",), "Geometry/LOD budget checks and in-engine collision observations; aesthetics stay human reviewed."),
    ("mission-validation", "tooling", "Validate mission graphs and state effects", "tools-engineering", "deterministic", ("save-contract", "historical-scope"), "Reachability, once-only effects, references, incompatible variants and interrupted quest tests."),
    ("localization-contracts", "tooling", "Separate strings, voice and locale metadata", "localization", "agent_assisted", ("rights-register", "core-loop"), "Stable keys, locale/voice contracts, font and script handling plus language review."),
    ("pipeline-repeatability", "tooling", "Produce a second unit without one-off tools", "production", "human_led", ("blender-export", "collision-lod", "mission-validation", "slice-signoff"), "Second accepted integrated unit, measured setup/rework and human time; no generated-file metric."),
    ("world-cells", "content", "Build dated terrain and world-cell content", "world-design", "agent_assisted", ("pipeline-repeatability", "historical-scope"), "Source-bound terrain/placement and streaming/collision constraints; not a claimed 1:1 survey without data."),
    ("settlements", "content", "Assemble streets, yards and settlement variants", "level-art", "agent_assisted", ("world-cells", "art-target"), "Movement-compatible layout with dated architecture, entrances, routes and human composition review."),
    ("props-materials", "content", "Produce prop and material families", "technical-art", "agent_assisted", ("asset-contracts", "art-target", "rights-register"), "Original licensed asset batches passing technical gates and art review."),
    ("people-costume", "content", "Produce rigs, outfits and character variants", "character-art", "agent_assisted", ("asset-contracts", "historical-scope", "art-target"), "Rig/skin/retarget tests, correct date contexts and human anatomical/costume review."),
    ("missions-dialogue", "content", "Build missions and situated conversations", "narrative-design", "agent_assisted", ("mission-validation", "settlements", "localization-contracts"), "Playable actions/consequences, attributed lore, actor-specific knowledge and editorial review."),
    ("content-review", "content", "Accept complete world/content batches", "creative-direction", "human_led", ("missions-dialogue", "people-costume", "props-materials"), "Integrated gameplay/art/history checks and a human-reviewed content acceptance record."),
    ("economy-custody", "systems", "Connect budgets, goods and delivery custody", "systems-design", "agent_assisted", ("save-contract", "interaction-access", "water-domain"), "Conservation, no double spending, paid/received distinction and whole-world rollback tests."),
    ("funded-recruitment", "systems", "Connect agents, appointments and recurring pay", "systems-design", "agent_assisted", ("economy-custody", "companion-route"), "Actual funding, consent, travel, arrival, arrears and limited role authority."),
    ("workshop-chain", "systems", "Connect production, inspection and unit issue", "systems-design", "agent_assisted", ("economy-custody",), "Tracked work in progress, accepted/rejected output, transport and once-only issue."),
    ("doctrine-training", "systems", "Connect named pupils, equipment and training", "combat-design", "agent_assisted", ("funded-recruitment", "workshop-chain", "paired-combat"), "Paid equipped instruction and individual observed proficiency, not global upgrade on hiring."),
    ("political-memory", "systems", "Connect households, orders and actor knowledge", "narrative-engineering", "agent_assisted", ("historical-scope", "save-contract", "mission-validation"), "Distinct intent, transmission, receipt, action and memory; no omniscient role switch."),
    ("systems-review", "systems", "Review integrated progression and delegation", "game-design", "human_led", ("doctrine-training", "political-memory"), "Playtested obligations/delegation that remain engaging, with measured failure and recovery cases."),
    ("campaign-assembly", "alpha", "Connect the complete campaign progression", "production", "agent_assisted", ("content-review", "systems-review"), "End-to-end progression, chronology, fixed outcomes and optional branches exercised."),
    ("save-migration", "alpha", "Qualify upgrades and durable saves", "gameplay-engineering", "deterministic", ("campaign-assembly", "save-contract"), "Old/new fixtures, failed-upgrade preservation and complete retained-state accounting."),
    ("automation-soak", "alpha", "Run traversal, economy and mission soak tests", "qa-engineering", "deterministic", ("campaign-assembly", "telemetry"), "Retained repeated runs, classified failures and bounded reproduction, not just process exit."),
    ("accessibility", "alpha", "Test accessibility and input alternatives", "user-research", "human_led", ("slice-playtest", "platform-matrix"), "Human accessibility sessions, readable UI/captions and alternative-input verification."),
    ("localization", "alpha", "Integrate and review languages and voices", "localization", "agent_assisted", ("missions-dialogue", "audio-target"), "Reviewed translations/performances, script layout, timings, attribution and permission records."),
    ("alpha-signoff", "alpha", "Declare feature/content completeness", "production", "human_led", ("save-migration", "automation-soak", "accessibility", "localization"), "Explicit scope-completeness decision and tracked remaining defects."),
    ("cpu-profiling", "beta", "Profile simulation and crowd CPU costs", "performance-engineering", "deterministic", ("telemetry", "slice-journey"), "Physical-target profiling under representative crowd/AI loads, distributions not invented averages."),
    ("gpu-profiling", "beta", "Profile rendering on target GPUs", "performance-engineering", "deterministic", ("art-target", "telemetry"), "Actual target-GPU frame-time observations; software rendering does not qualify hardware."),
    ("memory-streaming", "beta", "Exercise memory, loading and streaming", "performance-engineering", "deterministic", ("world-cells", "telemetry"), "Measured memory/IO and traversal stress with gaps, slow storage and interruption cases."),
    ("device-matrix", "beta", "Exercise supported devices and operating systems", "qa-engineering", "deterministic", ("platform-matrix", "campaign-assembly"), "Named real configurations, controller tests and unsupported/skipped cases clearly separated."),
    ("regression-matrix", "beta", "Recheck release candidates across required suites", "qa-engineering", "deterministic", ("alpha-signoff", "cpu-profiling", "gpu-profiling", "memory-streaming", "device-matrix"), "Source-bound regression results with no stale or missing required evidence."),
    ("beta-signoff", "beta", "Review release-blocking defects and quality", "production", "human_led", ("regression-matrix",), "Human quality decision with remaining limitations, severity and reproduction evidence."),
    ("final-rights", "release", "Review final rights, credits and licenses", "rights-review", "human_led", ("rights-register", "content-review", "localization"), "Final human-reviewed asset/music/performance permissions and attribution inventory."),
    ("store-packaging", "release", "Assemble store/build metadata and packages", "release-engineering", "agent_assisted", ("beta-signoff", "final-rights"), "Versioned packages, manifest, install/uninstall checks and human-approved store representation."),
    ("platform-certification", "release", "Complete external platform qualification", "release-engineering", "human_led", ("device-matrix", "beta-signoff"), "Actual platform-required approval; NET cannot manufacture certification."),
    ("release-candidate", "release", "Freeze and inspect the candidate artifact", "release-engineering", "deterministic", ("store-packaging", "regression-matrix"), "Exact artifact/source identities, reproducible install and rollback plan."),
    ("release-signoff", "release", "Make the human release decision", "release-authority", "human_led", ("release-candidate", "platform-certification", "final-rights"), "Explicit release decision outside this tool; a recorded review never deploys or merges."),
    ("postrelease-triage", "release", "Classify feedback and produce bounded repair work", "qa-engineering", "agent_assisted", ("release-signoff",), "Reproduction packets and reviewed corrective candidates with no silent save incompatibility."),
)


def tasks() -> list[dict]:
    result = []
    for name, stage, title, owner, automation, deps, acceptance in _ROWS:
        watches = ["**"]  # conservative default: an unknown change invalidates qualification
        if name == "water-domain":
            from .foundry_project import FILES
            watches = list(FILES)
        result.append({"task_id": name, "stage": stage, "title": title,
            "owner_role": owner, "automation": automation, "depends_on": list(deps),
            "acceptance": acceptance, "watches": watches,
            "completion": "native_foundry" if name == "water-domain" else "operator_review",
            "installed_recipe": "1792.water-round.v1" if name == "water-domain" else None,
            "agent_may": "produce candidate artifacts and tests within operator-granted paths; never approve itself",
            "human_judgment": automation != "deterministic"})
    return deepcopy(result)

SOURCES = (
    {"id": "ubisoft-ghostwriter", "url": "https://news.ubisoft.com/en-gb/article/7Cm07zbBGy4Xml6WgYi25d/the-convergence-of-ai-and-creativity-introducing-ghostwriter",
     "supports": "AI-assisted drafts of NPC barks with writers retained in the process; not autonomous narrative approval."},
    {"id": "ubisoft-farcry5-gdc", "url": "https://www.gdcvault.com/play/1025557/Procedural-World-Gen",
     "supports": "Ubisoft developer presentation: procedural biome/terrain/water tooling plus local artistic control and iteration."},
)
