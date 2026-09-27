# bevy-render-view

Thin **Bevy** projector over the same host `*_render.json` records that Godot tabs read.

| Item | Value |
| --- | --- |
| Bevy pin | `0f38358f573a7dc6ea961076f6151be662142010` (`giasonpooni/bevy`, `0.20.0-dev`) |
| Local engine checkout | `/workspace/bevy` (patched via `.cargo/config.toml`; **not** vendored into this repo) |
| Role | Second stacked presentation provider |
| Schema | **Same** render JSON as Godot — no second schema |
| Science | **None** — cards / trajectories / status only |
| CIW kind | **None** for the viewport |
| Cross-calls | Godot ↛ Bevy and Bevy ↛ Godot |

```sh
# Window: night clear, path gizmos, card HUD
cargo run --manifest-path tools/bevy-render-view/Cargo.toml -- \
  examples/pyramid-method-gap/results/analog_render.json

# Stdout only
cargo run --manifest-path tools/bevy-render-view/Cargo.toml -- --summary \
  examples/pyramid-method-gap/results/analog_render.json
```

Missing file → `STALE`. Paint **VERIFIED** only when JSON has `fresh_verifier_occurrence: true`.
`HISTORICAL` displays as `retained_runtime_report_requires_fresh_verification`.

See [`docs/VISUALIZATION_PROVIDERS.md`](../../docs/VISUALIZATION_PROVIDERS.md).

## Toolchain

Pinned Bevy `0.20.0-dev` requires **rustc ≥ 1.96.0**. Boxes with older rustc cannot `cargo check` until the toolchain is upgraded. Sources and the git pin remain the integration contract. Do not patch the engine tree for instrument tabs.
