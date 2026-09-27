# 03 — Bevy projector (same JSON)

Second stacked provider over the **same** `*_render.json`. No second schema.
No Godot↔Bevy calls. Do **not** patch the Bevy engine tree.

## Pin

| Item | Value |
| --- | --- |
| Crate | `tools/bevy-render-view` |
| Bevy | `giasonpooni/bevy` @ `0f38358f573a7dc6ea961076f6151be662142010` (`0.20.0-dev`) |
| Role | Cards / trajectories / status only |

## Run

```sh
cargo run --manifest-path tools/bevy-render-view/Cargo.toml -- \
  examples/<name>/results/<name>_render.json

cargo run --manifest-path tools/bevy-render-view/Cargo.toml -- --summary \
  examples/<name>/results/<name>_render.json
```

Missing file → `STALE`. `HISTORICAL` displays as
`retained_runtime_report_requires_fresh_verification`.

Requires rustc ≥ 1.96.0 for this pin. Sources + git pin remain the contract
even when the local toolchain cannot `cargo check` yet.

See [`tools/bevy-render-view/README.md`](../../tools/bevy-render-view/README.md)
and [`docs/VISUALIZATION_PROVIDERS.md`](../../docs/VISUALIZATION_PROVIDERS.md).
