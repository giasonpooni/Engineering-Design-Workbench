# Installed wheel and dependency closure

The Bevy Cargo.lock retained by the qualified `76075f9` campaign is now committed.
Build with `cargo +1.96.0 build --release --locked --manifest-path
 tools/interactive-simulation/bevy/Cargo.toml` (one command, without the line break).
The lock's original SHA-256 is
`13ce9938bca2bb845afc6e423f3510daa3653b94d76e11506d5cf331fe5b1482`.
No Bevy revision or physics implementation changed.

An installed NET wheel can use an explicitly supplied
`--adapter-root /path/to/checkout/tools/interactive-simulation` on `run`,
`candidate` or `replay`. This is trusted operator configuration, never a path
loaded from retained records. The adapter bytes, Cargo manifest and lock remain
bound to reproduction; relocating identical source files is permitted, silently
changing them is not. Inspection requires neither adapter sources nor engines.
The native check script supplies its source root explicitly and uses an installed
wheel rather than relying on an editable install.

See [combined qualification](INTEGRATION_QUALIFICATION.md) for the integration
branch and separate scientific/native, contract and access outcomes.
