# Bevy render projector

Thin Bevy projector over the host-render JSON contract. It presents retained
cards, series and status; it does not compute science, verify proofs, or
authorize operations.

```sh
cargo run --manifest-path tools/bevy-render-view/Cargo.toml -- \
  examples/<name>/results/<name>_render.json
cargo run --manifest-path tools/bevy-render-view/Cargo.toml -- --summary \
  examples/<name>/results/<name>_render.json
```

The projector uses the same JSON as Godot. Missing render data is `STALE` and
historical verifier reports remain explicitly historical. Do not patch or vendor
the Bevy engine tree.
