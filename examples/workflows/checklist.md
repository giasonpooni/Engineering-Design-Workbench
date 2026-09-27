# Teaching-sample acceptance checklist

- [ ] Folder `examples/<name>/` with `README.md` (non-claims explicit)
- [ ] `emit_render.py` or `run_or_emit.py` uses `examples/_render_json.write_render`
- [ ] Payload: `may_authorize: false`, `claim_scope`, `fresh_verifier_occurrence: false`
- [ ] Reuses existing operation language / kind — **no new CIW kind**
- [ ] `results/.gitignore` contains `*` and `!.gitignore`
- [ ] `python3 examples/<name>/emit_render.py` succeeds
- [ ] Godot `*_view.gd` preloads PresentationKit; missing JSON → **STALE**
- [ ] Tab wired in `godot/scripts/main.gd` with the agreed tab title
- [ ] Row added under Teaching samples in `docs/VISUALIZATION_PROVIDERS.md`
- [ ] No fluid-volume / building / proof-byte viewport content
- [ ] No push required for local laboratory acceptance
- [ ] (Optional) Bevy summary reads the same JSON without engine patches
