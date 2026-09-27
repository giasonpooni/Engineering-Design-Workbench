# 02 — Godot presentation tab

## Pattern

1. Create `godot/scripts/<name>_view.gd` extending `VBoxContainer`.
2. Preload PresentationKit (and Strip / Schematic as needed):

```gdscript
const Kit = preload("res://scripts/presentation_kit.gd")
const Strip = preload("res://scripts/presentation_strip.gd")

const DEFAULT_RELATIVE := "../examples/<name>/results/<name>_render.json"
const MATCH_NAME := "<name>_render.json"
```

3. On `_ready`: build UI → `_try_load()`.
4. `_try_load` uses `Kit.resolve_render_path` + `Kit.load_json`.
   - Empty / missing → `_apply_stale("STALE", "… missing — generate with …")`.
5. Cards use `Kit.make_card` / `Kit.status_color` / `Kit.format_status_label`.
6. Verification footer: `Kit.verification_label(_data)` — never paint VERIFIED
   unless `fresh_verifier_occurrence` is true.
7. House colors come from PresentationKit (`BG` `0c1521`, live `60dfcd`,
   stale `537778`, axes `4e647e`, labels `a4b4c8`, marker `ffcc80`).

## Wire `main.gd`

```gdscript
const MyView = preload("res://scripts/<name>_view.gd")
var _my_view = MyView.new()
# in _build_ui:
_my_view.name = "My Tab Title"
_tabs.add_child(_my_view)
```

## Rules

- No websocket / no second solver in the tab.
- No fluid-volume / building / proof-byte drawing.
- Godot may be off PATH; keep scripts runnable when present:

```sh
godot --path godot
# optional: godot --headless --path godot --script res://tests/presentation_smoke.gd
```
